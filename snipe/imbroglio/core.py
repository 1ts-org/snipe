#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2018 the Snipe contributors
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following
# disclaimer in the documentation and/or other materials provided
# with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
# TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
# THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
"""
This is the core of the imbroglio coroutine supervisor.
"""

__all__ = [
    'CancelledError',
    'ImbroglioException',
    'Supervisor',
    'Task',
    'UnfinishedError',
    'run',
    ]


import bisect
import collections
import functools
import itertools
import inspect
import logging
import math
import os
import selectors
import sys
import types
import time


TIME_THRESHOLD = .1  # 100 ms, completely arbitrary


class ImbroglioException(Exception):
    """Catch-all exceptions for imbroglio"""


class CancelledError(ImbroglioException):
    """Your task has been cancelled"""


class UnfinishedError(ImbroglioException):
    """Your task isn't done so it doesn't have a result"""


class Task:
    _next_id = itertools.count().__next__

    def __init__(self, coro, supervisor):
        if not inspect.iscoroutine(coro):
            raise TypeError(
                'Cannot make a task from non-coroutine %s' % (repr(coro,)))
        self.task_id = self._next_id()
        self.coro = coro
        self.supervisor = supervisor
        self.pending_exception = None
        self.state = 'GO'
        self.exception = None
        self._result = None

        self.creation = _framemeta(coro.cr_frame)

    def throw(self, exception):
        if self.is_done():
            return False

        if isinstance(exception, type):
            exception = exception()

        self.pending_exception = exception
        self.rouse()
        return True

    def rouse(self):
        self.supervisor._rouse(self)

    def cancel(self):
        self.throw(CancelledError('Task cancelled'))

    def set_result(self, result):
        self.state = 'DONE'
        self._result = result

    def set_result_exception(self, exception):
        self.state = 'EXCEPTION'
        self.exception = exception

    def set_cancelled(self, exception=CancelledError):
        self.exception = exception
        self.state = 'CANCELLED'

    def result(self, exception=True):
        if not self.is_done():
            raise UnfinishedError('task is unfinished')
        if self.exception is not None:
            if exception:
                raise self.exception
            return self.exception
        return self._result

    def is_done(self):
        return self.state in {'DONE', 'EXCEPTION', 'CANCELLED'}

    done = is_done

    def __await__(self):
        yield from taskwait(self)  # noqa: F821

    def __repr__(self):
        cstate = ''
        if inspect.iscoroutine(self.coro):
            crst = inspect.getcoroutinestate(self.coro)
            cstate = f' {crst} {_framemeta(self.coro.cr_frame)}'
            if crst == 'CORO_SUSPENDED':
                cstate += f' {self.coro.cr_await!r}'
        tstate = self.state
        if self.is_done():
            result = self.result(False)
            if result is not None:
                tstate += f' {result!r}'
        return (
            f'<{self.__class__.__name__}'
            f' {tstate}'
            f' #{self.task_id}:{self.creation}{cstate}'
            '>'
            )


Runnable = collections.namedtuple('Runnable', 'task retval')
Waiting = collections.namedtuple(
    'Waiting', 'target start events fd task other')


def _framemeta(frame):
    if frame is None:
        return ''
    f = inspect.getframeinfo(frame)
    try:
        return f'{os.path.basename(f.filename)}:{f.lineno}'
    finally:
        del f
        del frame


class Supervisor:
    def __init__(self):
        self.runq = []
        self.waitq = []
        self.log = logging.getLogger('imbroglio')

    def start(self, coro):
        """start a task from non-async code"""
        newtask = Task(coro, self)
        self.runq.append(Runnable(newtask, None))
        return newtask

    def _call_spawn(self, task, coro):
        """spawns a new coroutine in the event loop"""

        newtask = self.start(coro)
        self._return(task, newtask)

    def _call_sleep(self, task, duration=0):
        """sleep for duration seconds

        If duration is 0 (the default), just yield until the next tick.

        Returns a tuple (True, float) of whether the timeout expired
        and how long we waited.  If duration is None, potentially wait
        forever.  (The task can be roused which is how the timeout
        might not have expired.)
        """
        self._wait_internal(task, -1, 0, duration)

    def _call_readwait(self, task, fd, duration=None):
        """wait for an fd to be readable

        Returns a tuple (bool, float) of whether the timeout expired
        and how long we waited.  If duration is None (the default),
        potentially wait forever.

        If duration is zero, the timeout bool indicates whether fd is
        not readable, i.e. True means that it would have timed out and
        thus fd is not readable.
        """

        self._wait_internal(task, fd, selectors.EVENT_READ, duration)

    def _call_writewait(self, task, fd, duration=None):
        """wait for an fd to be writable

        Returns a tuple (bool, float) of whether the timeout expired
        and how long we waited.  If duration is None (the default),
        potentially wait forever.

        If duration is zero, the timeout bool indicates whether fd is
        not writable, i.e. True means that it would have timed out and
        thus fd is not writable.
        """
        self._wait_internal(task, fd, selectors.EVENT_WRITE, duration)

    def _call_taskwait(self, task, other, duration=None):
        """wait for another task to finish

        Returns a tuple (bool, float) of whether the timeout expired
        and how long we waited.  If duration is None (the default),
        potentially wait forever.

        If duration is zero, the timeout bool indicates whether the
        task is running, i.e. True means that it would have timed out
        and thus the task is still running.
        """
        if not other.is_done():
            self._wait_internal(task, -1, 0, duration, other)
        else:
            self._return(task, (False, 0.0))

    def _wait_internal(self, task, fd, events, duration, other=None):
        """internals of _call_readwait and _call_writewait"""
        now = time.monotonic()
        if duration is None:
            bisect.insort_left(
                self.waitq,
                Waiting(float('Inf'), now, events, fd, task, other))
        else:
            bisect.insort_left(
                self.waitq,
                Waiting(now + duration, now, events, fd, task, other))

    def _call_this_task(self, task):
        """return the current task"""
        self._return(task, task)

    def _call_get_supervisor(self, task):
        """return the current supervisor"""
        self._return(task, self)

    def _call_tasks(self, task):
        """return a tuple of lists of the runnable and waiting tasks"""
        self._return(task, (
            [t.task for t in self.runq],
            [t.task for t in self.waitq],
            ))

    def _return(self, task, val=None):
        self.runq.append(Runnable(task, val))

    def _rouse(self, task):
        for i, qe in enumerate(self.waitq):
            if qe.task == task:
                del self.waitq[i]
                self.runq.append(
                    Runnable(task, (False, time.monotonic() - qe[1])))
                break

    def _run(self, runtask):
        self.log.debug('starting scheduler loop')

        def _step(task, retval):
            t0 = time.time()
            try:
                if task.pending_exception is None:
                    val = task.coro.send(retval)
                else:
                    exc, task.pending_exception = task.pending_exception, None
                    val = task.coro.throw(type(exc), exc)
                if not isinstance(val, tuple):
                    msg = f'{task!r} upcalled with {val!r}'
                    self.log.error(msg)
                    exc = ImbroglioException(msg)
                    val = task.coro.throw(type(exc), exc)
            except StopIteration as e:
                task.set_result(e.value)
                return
            except CancelledError:
                task.set_cancelled()
                return
            except Exception as e:
                self.log.debug(
                    '%s dropped through exception',
                    task,
                    exc_info=True,
                    )
                task.set_result_exception(e)
                return
            finally:
                duration = time.time() - t0
                self.log.debug('%s', f'{task!r} ran {duration}s')
                if duration > TIME_THRESHOLD:
                    self.log.warning(
                        '%s',
                        f'spent {duration}s in {task!r}')

            call = getattr(self, '_call_' + val[0])
            call(task, *val[1:])

        self.runq.append(Runnable(runtask, None))

        try:
            while True:
                tick = time.monotonic()
                runq, self.runq = self.runq, []

                # get the expired waits
                division = bisect.bisect_right(
                    self.waitq, (tick, tick, None))
                wake, self.waitq = self.waitq[:division], self.waitq[division:]

                for wakey in wake:
                    duration = time.monotonic() - wakey.start
                    self.runq.append(Runnable(wakey.task, (True, duration)))

                for run in runq:
                    _step(run.task, run.retval)
                    if run.task.is_done():
                        for i, w in reversed(list(enumerate(self.waitq))):
                            if w.other is run.task:
                                duration = time.monotonic() - w.start
                                self.runq.append(
                                    Runnable(w.task, (False, duration)))
                                del self.waitq[i]

                if self.waitq:
                    target = self.waitq[0].target
                    if not math.isinf(target):
                        duration = max(0.0, target - time.monotonic())
                    else:
                        duration = None
                    if self.runq:  # we have runnable tasks, don't wait
                        duration = 0
                    with selectors.DefaultSelector() as selector:
                        for i, e in enumerate(self.waitq):
                            if e.events:
                                selector.register(e.fd, e.events, (i, e))
                        cleanup = []
                        now = time.monotonic()
                        for key, events in selector.select(duration):
                            i, e = key.data
                            cleanup.append(i)
                            self.runq.append(
                                Runnable(e.task, (False, now - e.start)))
                        oldq = list(self.waitq)
                        try:
                            for i in sorted(cleanup, reverse=True):
                                del self.waitq[i]
                        except Exception:  # pragma: nocover
                            self.log.exception(
                                f'old waitq: {oldq!r}  current: {self.waitq!r}'
                                f'  cleanup: {cleanup!r}  i: {i}')
                            raise
                        del oldq

                if not self.runq and not self.waitq:
                    break
        finally:
            if self.runq:  # pragma: nocover
                print('Runnable tasks at supervisor exit:')
                for t in self.runq:
                    print(f' {t!r}')
            if self.waitq:  # pragma: nocover
                print('Waiting tasks at supervisor exit:')
                for t in self.waitq:
                    print(f' {t!r}')

        return


def _reify_calls():
    CALL_PREFIX = '_call_'
    mod = sys.modules[__name__]

    def _reify_call(method):
        name = method.__name__[len(CALL_PREFIX):]

        @types.coroutine
        @functools.wraps(
            method,
            assigned=list(set(
                functools.WRAPPER_ASSIGNMENTS) - {'__name__', '__qualname__'}))
        def call(*args):
            return (yield (name,) + args)
        call.__name__ = name
        call.__qualname__ = name
        method_signature = inspect.signature(method)
        call.__signature__ = method_signature.replace(
            parameters=list(method_signature.parameters.values())[2:])
        setattr(mod, name, call)
        mod.__all__.append(name)

    for method_name in dir(Supervisor):
        if not method_name.startswith(CALL_PREFIX):
            continue
        _reify_call(getattr(Supervisor, method_name))


_reify_calls()
del _reify_calls


def run(coro, exception=True):
    supervisor = Supervisor()
    task = Task(coro, supervisor)
    supervisor._run(task)
    return task.result(exception=exception)
