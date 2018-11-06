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
Some useful things built on top of the imbroglio primitives
"""

__all__ = [
    'Timeout',
    'TimeoutError',
    'gather',
    'run_in_thread',
    ]


import os
import threading


from . import core


class TimeoutError(core.ImbroglioException):
    pass


class Timeout:
    """
    Async context manager for timeouts.
    Only works for operations that block in imbroglio.
    """

    def __init__(self, duration):
        self.duration = duration

    async def _timer(self):
        await core.sleep(self.duration)
        self.watched_task.throw(
            TimeoutError(f'timed out after {self.duration}'))

    async def __aenter__(self):
        self.watched_task = await core.this_task()
        self.timer_task = await core.spawn(self._timer())
        return self.timer_task

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.timer_task.cancel()
        except TimeoutError:  # pragma: nocover
            pass  # this is here to reduce raciness
        await core.sleep()  # so the cancel above gets processed
        return exc_type == TimeoutError


async def gather(*coros, return_exceptions=False):
    async def signaller(coro):
        # so we always schedule _after_ the parent sleeps
        await core.sleep()
        # this following is a little off but should produce cleaner
        # backtraces?
        if not return_exceptions:
            result = await coro
        else:
            try:
                result = await coro
            except Exception as exception:
                result = exception

        monitor_task.rouse()
        return result

    monitor_task = await core.this_task()
    tasks = [(await core.spawn(signaller(coro))) for coro in coros]

    while not any(not t.is_done() for t in tasks):
        await core.sleep(None)


async def run_in_thread(func, *args, **kwargs):
    read_fd, write_fd = os.pipe()
    try:
        result = None
        exception = None
        def runner():
            nonlocal result
            nonlocal exception
            try:
                result = func(*args, **kwargs)
            except Exception as exception:
                pass
            os.write(write_fd, b'X')

        thread = threading.Thread(target=runner)
        thread.start()
        await core.readwait(read_fd, None)
        thread.join()
        if exception is not None:
            raise exception
        return result
    finally:
        os.close(write_fd)
        os.close(read_fd)
