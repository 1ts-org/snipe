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
    'Event',
    'Promise',
    'Timeout',
    'TimeoutError',
    'gather',
    'process_filter',
    'run_in_thread',
    'test',
    ]


import fcntl
import functools
import inspect
import os
import socket
import subprocess
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
            result = await coro
        else:
            try:
                result = await coro
            except Exception as exception:
                result = exception

        monitor_task.rouse()
        return result

    unawaitable = [repr(c) for c in coros if not inspect.isawaitable(c)]
    if unawaitable:
        unawaitable = ' '.join(unawaitable)
        raise imbroglio.ImbroglioException(f'got unawaitable {unawaitable}')
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

    def set_result_exception(self, exception):
        self.done = True
        self.exception_set = True
        self.exception = exception
        if self.task is not None:
            self.task.rouse()

    def __await__(self):
        self.task = yield from imbroglio.this_task()
        while not self.done:
            yield from imbroglio.sleep(None)
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

            try:
                sender.send(b'X')
            except Exception:  # pragma: nocover
                pass

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


async def process_filter(cmd, inbuf):
    inr, inw = os.pipe()
    outr, outw = os.pipe()

    async def sender(inbuf):
        inbuf = inbuf.encode()
        while inbuf:
            await imbroglio.writewait(inw)
            count = os.write(inw, inbuf)
            inbuf = inbuf[count:]
        os.close(inw)

    try:
        for fd in (inw, outr):
            fcntl.fcntl(
                fd,
                fcntl.F_SETFL,
                fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

        with subprocess.Popen(
                cmd,
                stdin=inr,
                stdout=outw,
                stderr=subprocess.STDOUT) as p:
            os.close(inr)
            os.close(outw)

            await imbroglio.spawn(sender(inbuf))
            output = []
            s = None
            while s != b'':
                await imbroglio.readwait(outr)
                s = os.read(outr, 4096)
                output.append(s)
            retval = await run_in_thread(p.wait)
            return retval, b''.join(output).decode(errors='replace')
    finally:
        try:
            os.close(inw)
        except OSError:
            pass
        try:
            os.close(outr)
        except OSError:  # pragma: nocover
            pass


class Event:
    def __init__(self):
        self.flag = False
        self.promises = set()

    def clear(self):
        self.flag = False

    def is_set(self):
        return self.flag

    async def set(self):
        if not self.flag:
            self.flag = True
            promises, self.promises = self.promises, set()
            for p in promises:
                p.set_result(True)
        await imbroglio.sleep()

    async def wait(self):
        if self.flag:
            return

        p = Promise()
        self.promises.add(p)
        await p


def test(f):
    """
    Wrap an async function in a call to the imbroglio supervisor,
    intended for tests.
    """
    @functools.wraps(f)
    def run(self):
        imbroglio.run(f(self))
    return run
