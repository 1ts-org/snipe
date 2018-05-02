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
import inspect
import logging
import math
import selectors
import sys
import types
import time


class ImbroglioException(Exception):
    """Catch-all exceptions for imbroglio"""


class CancelledError(ImbroglioException):
    """Your task has been cancelled"""


class UnfinishedError(ImbroglioException):
    """Your task isn't done so it doesn't have a result"""


class Task:
    def __init__(self, coro, supervisor):
        if not inspect.isawaitable(coro):
            raise TypeError(
                'Cannot make a task from non-coroutine %s' % (repr(coro,)))

        self.coro = coro
        self.supervisor = supervisor
        self.pending_exception = None
        self.state = 'FOO'
        self.exception = None
        self._result = None

    def throw(self, exception):
        if self.is_done():
            return False

        if isinstance(exception, type):
            exception = exception()

        # import traceback
        # logging.error(
        #     'Throwing exception %s in task %s:\n%s',
        #     exception, self, ''.join(traceback.format_stack()))

        self.pending_exception = exception
        self.supervisor._rouse(self)
        return True

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

    def result(self):
        if self.state == 'CANCELLED':
            return self.exception
        if self.state not in {'DONE', 'EXCEPTION'}:
            raise UnfinishedError('task is unfinished')
        if self.exception is not None:
            raise self.exception
        return self._result

    def is_done(self):
        return self.state in {'DONE', 'EXCEPTION', 'CANCELLED'}


Runnable = collections.namedtuple('Runnable', 'task retval')
Waiting = collections.namedtuple('Waiting', 'target start events fd task')


class Supervisor:
    def __init__(self):
        self.runq = []
        self.waitq = []

    def _call_spawn(self, task, coro):
        """Spawns new coroutines in the event loop"""

        newtask = Task(coro, self)
        self.runq.append(Runnable(newtask, None))
        self.runq.append(Runnable(task, newtask))

    def _call_sleep(self, task, duration=0):
        """sleep for duration seconds

        If duration is 0 (the default), just yield until the next tick.

        Returns a tuple (bool, float) of whether the timeout expired and
        how long we waited.  If duration is None, potentially wait forever.
        """
        self._wait_internal(task, -1, 0, duration)

    def _call_readwait(self, task, fd, duration=None):
        """wait for an fd to be readable

        Returns a tuple (bool, float) of whether the timeout expired and
        how long we waited.  If duration is None (the default), potentially
        wait forever.
        """

        self._wait_internal(task, fd, selectors.EVENT_READ, duration)

    def _call_writewait(self, task, fd, duration=None):
        """wait for an fd to be writable

        Returns a tuple (bool, float) of whether the timeout expired and
        how long we waited.  If duration is None (the default), potentially
        wait forever.
        """
        self._wait_internal(task, fd, selectors.EVENT_WRITE, duration)

    def _wait_internal(self, task, fd, events, duration):
        """internals of _call_readwiat and _call_writewait"""
        now = time.monotonic()
        if duration is None:
            bisect.insort_left(
                self.waitq, Waiting(float('Inf'), now, events, fd, task))
        else:
            bisect.insort_left(
                self.waitq, Waiting(now + duration, now, events, fd, task))

    def _call_this_task(self, task):
        self.runq.append(Runnable(task, task))

    def _rouse(self, task):
        for i, qe in enumerate(self.waitq):
            if qe.task == task:
                del self.waitq[i]
                self.runq.append(
                    Runnable(task, (False, time.monotonic() - qe[1])))
                break

    def _run(self, runtask):
        def _step(task, retval):
            try:
                if task.pending_exception is None:
                    val = task.coro.send(retval)
                else:
                    exc, task.pending_exception = task.pending_exception, None
                    val = task.coro.throw(type(exc), exc)
            except StopIteration as e:
                task.set_result(e.value)
                return
            except CancelledError:
                task.set_cancelled()
                return
            except Exception as e:
                logging.exception('%s dropped through exception', task)
                task.set_result_exception(e)  # XXX leakage
                return

            call = getattr(self, '_call_' + val[0])
            call(task, *val[1:])

        self.runq.append(Runnable(runtask, None))

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
                    for i in sorted(cleanup, reverse=True):
                        del self.waitq[i]

            if not self.runq and not self.waitq:
                break

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


def run(coro):
    supervisor = Supervisor()
    task = Task(coro, supervisor)
    supervisor._run(task)
    return task.result()
