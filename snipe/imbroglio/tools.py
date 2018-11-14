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
    'Promise',
    'Timeout',
    'TimeoutError',
    'gather',
    'run_in_thread',
    ]


import inspect
import logging
import socket
import threading

from . import core as imbroglio


class TimeoutError(imbroglio.ImbroglioException):
    pass


class Timeout:
    """
    Async context manager for timeouts.
    Only works for operations that block in imbroglio.
    """

    def __init__(self, duration):
        self.duration = duration

    async def _timer(self):
        await imbroglio.sleep(self.duration)
        self.watched_task.throw(
            TimeoutError(f'timed out after {self.duration}s'))

    async def __aenter__(self):
        self.watched_task = await imbroglio.this_task()
        self.timer_task = await imbroglio.spawn(self._timer())
        return self.timer_task

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.timer_task.cancel()
        except TimeoutError:  # pragma: nocover
            pass  # this is here to reduce raciness
        await imbroglio.sleep()  # so the cancel above gets processed
        return exc_type == TimeoutError


async def gather(*coros, return_exceptions=False):
    async def signaller(coro):
        # so we always schedule _after_ the parent sleeps
        await imbroglio.sleep()
        # this following is a little off but should produce cleaner
        # backtraces?
        if not return_exceptions:
            if not inspect.isawaitable(coro):
                logging.getLogger('imbroglio').error(
                    f'got unawaitable {coro!r}')
            result = await coro
        else:
            try:
                result = await coro
            except Exception as exception:
                result = exception

        monitor_task.rouse()
        return result

    monitor_task = await imbroglio.this_task()
    tasks = [(await imbroglio.spawn(signaller(coro))) for coro in coros]

    while not all(t.is_done() for t in tasks):
        await imbroglio.sleep(None)

    return [t.result() for t in tasks]


class Promise:
    def __init__(self):
        self.exception_set = False
        self.done = False
        self.result = None
        self.exception = None
        self.task = None

    def set_result(self, result):
        self.done = True
        self.result = result
        if self.task is not None:
            self.task.rouse()

    def set_exception(self, exception):
        self.done = True
        self.exception_set = True
        self.exception = exception
        if self.task is not None:
            self.task.rouse()

    async def __call__(self):
        self.task = await imbroglio.this_task()
        while not self.done:
            await imbroglio.sleep(None)
        if self.exception_set:
            raise self.exception
        return self.result


async def run_in_thread(func, *args, **kwargs):
    result = None
    exception = None

    sender, receiver = socket.socketpair()
    try:
        def runner():
            nonlocal result
            nonlocal exception

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                exception = e

            sender.send(b'X')

        thread = threading.Thread(target=runner)

        async def launcher():
            # wait a tick, so the parent runs again and starts to sleep
            await imbroglio.sleep()
            thread.start()

        await imbroglio.spawn(launcher())
        await imbroglio.readwait(receiver)

        thread.join()
        if exception is not None:
            raise exception
        return result
    finally:
        sender.close()
        receiver.close()
