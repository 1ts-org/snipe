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
This is a cheap knockoff of curio that runs under python 3.4 becasue reasons.
"""

__all__ = ['Supervisor', 'run', 'coroutine']

import bisect
import functools
import inspect
import math
import selectors
import sys
import time


class Supervisor:
    def __init__(self):
        self.runq = []
        self.waitq = []

    def _call_spawn(self, coro, *coros):
        """Spawns new coroutines in the event loop"""

        self.runq.extend(zip(coros, [None] * len(coros)))
        self.runq.append((coro, True))  # should be the task objects eventually

    def _call_sleep(self, coro, duration=None):
        """sleep for duration seconds and return how long we actually slept.

        If duration is None (the default), just yield until the next tick.
        """
        now = time.monotonic()
        if duration is None:
            bisect.insort_left(self.waitq, (now, now, 0, -1, coro))
        else:
            bisect.insort_left(self.waitq, (now + duration, now, 0, -1, coro))

    def _call_readwait(self, coro, fd, duration=None):
        """wait for an fd to be readable

        Returns a tuple (bool, float) of whether the timeout expired and
        how long we waited.  If duration is None (the default), potentially
        wait forever.
        """

        self._wait_internal(coro, fd, selectors.EVENT_READ, duration)

    def _call_writewait(self, coro, fd, duration=None):
        """wait for an fd to be writable

        Returns a tuple (bool, float) of whether the timeout expired and
        how long we waited.  If duration is None (the default), potentially
        wait forever.
        """
        self._wait_internal(coro, fd, selectors.EVENT_WRITE, duration)

    def _wait_internal(self, coro, fd, events, duration):
        """internals of _call_readwiat and _call_writewait"""
        now = time.monotonic()
        if duration is None:
            bisect.insort_left(
                self.waitq, (float('Inf'), now, events, fd, coro))
        else:
            bisect.insort_left(
                self.waitq, (now + duration, now, events, fd, coro))

    def _call_magic(self, coro):
        """return a magic number"""
        self.runq.append((coro, 42))

    def _run(self, coroutine):
        result = None

        def _step(coro, retval):
            nonlocal result

            try:
                val = coro.send(retval)
            except StopIteration as e:
                if coro is coroutine:
                    result = e.value
                return

            call = getattr(self, '_call_' + val[0])
            call(coro, *val[1:])

        self.runq.append((coroutine, None))

        while True:
            tick = time.monotonic()
            runq, self.runq = self.runq, []

            # get the expired waits
            division = bisect.bisect_right(
                self.waitq, (tick, tick, None))
            wake, self.waitq = self.waitq[:division], self.waitq[division:]

            for target, start, events, fd, coro in wake:
                duration = time.monotonic() - start
                if not events:
                    self.runq.append((coro, duration))
                else:
                    self.runq.append((coro, (True, duration)))

            for coro, retval in runq:
                _step(coro, retval)

            if self.waitq:
                target = self.waitq[0][0]
                if not math.isinf(target):
                    duration = max(0.0, target - time.monotonic())
                else:
                    duration = None
                if self.runq:  # we have runnable tasks, don't wait
                    duration = 0
                with selectors.DefaultSelector() as selector:
                    for i, entry in enumerate(self.waitq):
                        target, start, events, fd, coro = entry
                        if events:
                            selector.register(fd, events, (i, entry))
                    cleanup = []
                    now = time.monotonic()
                    for key, events in selector.select(duration):
                        i, entry = key.data
                        target, start, events, fd, coro = entry
                        cleanup.append(i)
                        self.runq.append((coro, (False,  now - start)))
                    for i in sorted(cleanup, reverse=True):
                        del self.waitq[i]

            if not self.runq and not self.waitq:
                break

        return result


def _reify_calls():
    CALL_PREFIX = '_call_'
    mod = sys.modules[__name__]

    def _reify_call(method):
        name = method.__name__[len(CALL_PREFIX):]

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
    result = Supervisor()._run(coro)
    return result


def coroutine(coro):
    if inspect.isgeneratorfunction(coro):
        return coro

    @functools.wraps(coro)
    def wrapper(*args, **kw):
        result = coro(*args, **kw)
        if inspect.isgenerator(result):
            result = yield from result
        return result

    return wrapper
