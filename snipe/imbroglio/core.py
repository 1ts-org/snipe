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
import sys
import time


class Supervisor:
    def __init__(self):
        self.runq = []
        self.sleepq = []

    def _call_spawn(self, coro, *coros):
        """Spawns new coroutines in the event loop"""

        self.runq.extend(zip(coros, [None] * len(coros)))
        self.runq.append((coro, True))  # should be the task objects eventually

    def _call_sleep(self, coro, duration=None):
        """sleep for duration seconds"""
        now = time.monotonic()
        if duration is None:
            bisect.insort_left(self.sleepq, (now, now, coro))
        else:
            bisect.insort_left(self.sleepq, (now + duration, now, coro))

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

            division = bisect.bisect_right(self.sleepq, (tick, tick, None))
            sleepq, self.sleepq = \
                self.sleepq[:division], self.sleepq[division:]

            for coro, retval in runq:
                _step(coro, retval)

            for target, start, coro in sleepq:
                _step(coro, time.monotonic() - start)

            if self.sleepq:
                duration = self.sleepq[0][0] - time.monotonic()
                if duration >= 0.0:
                    time.sleep(duration)

            if not self.runq and not self.sleepq:
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
