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

'''
Unit tests for the imbroglio core
'''

import socket
import signal
import sys
import time
import unittest

sys.path.append('..')

from snipe import imbroglio   # noqa: E402


class TestImbroglioCore(unittest.TestCase):
    def test_simple(self):
        # single coroutine with a single call
        val = None

        async def coro():
            nonlocal val
            val = await imbroglio.this_task()

        imbroglio.run(coro())

        self.assertIsInstance(val, imbroglio.Task)

    def test_noncoro(self):
        # coroutine that isn't

        val = None

        async def coro():
            nonlocal val
            val = 17

        imbroglio.run(coro())

        self.assertEqual(17, val)

    def test_sleep(self):
        # single coroutine that sleeps for a second
        async def coro():
            await imbroglio.sleep(1.0)

        t0 = time.time()

        imbroglio.run(coro())

        self.assertGreaterEqual(time.time(), t0 + 1.0)

    def test_spawn(self):
        # spawn three coroutines that increment a thing and then sleep
        counter = 0

        async def spawned():
            nonlocal counter
            counter += 1
            await imbroglio.sleep(1)

        async def spawner():
            for i in range(3):
                await imbroglio.spawn(spawned())

            return 85

        self.assertEqual(85, imbroglio.run(spawner()))
        self.assertEqual(3, counter)

    def test_wait(self):
        # spawn a counter, a reader, and a writer.

        counter = 0

        a, b = socket.socketpair()

        try:
            async def driver():
                await imbroglio.spawn(reader())
                await imbroglio.spawn(ticker())
                await imbroglio.spawn(writer())

            async def reader():
                timedout, duration = await imbroglio.readwait(a.fileno())
                self.assertFalse(timedout)
                self.assertEqual(b'X', a.recv(1))

            async def ticker():
                nonlocal counter

                for i in range(5):
                    await imbroglio.sleep(.1)
                    counter += 1

            async def writer():
                await imbroglio.sleep(.5)

                # make sure the ticker's been running while the reader's
                # been waiting
                self.assertGreater(counter, 3)

                # should come back immediately
                timedout, duration = \
                    await imbroglio.writewait(b.fileno(), 10)
                self.assertFalse(timedout)
                b.send(b'X')

            imbroglio.run(driver())
        finally:
            a.close()
            b.close()

    def test_wait_timeout(self):
        # spawn a reader and let it timeout

        a, b = socket.socketpair()

        try:
            async def reader():
                timedout, duration = \
                    await imbroglio.readwait(a.fileno(), .1)
                self.assertTrue(timedout)

            imbroglio.run(reader())
        finally:
            a.close()
            b.close()

    def test_wait_zero(self):
        a, b = socket.socketpair()

        try:
            async def waiter():
                timedout, duration = \
                    await imbroglio.readwait(a.fileno(), 0)
                self.assertTrue(timedout)

                b.send(b'foo')

                timedout, duration = \
                    await imbroglio.readwait(a.fileno(), 0)
                self.assertFalse(timedout)

            imbroglio.run(waiter())
        finally:
            a.close()
            b.close()

    def test_exception(self):
        async def keyerror():
            {}[None]

        with self.assertRaises(KeyError):
            imbroglio.run(keyerror(), exception=True)

    def test_cancellation(self):
        counter = 0

        async def ticker():
            nonlocal counter

            while True:
                await imbroglio.sleep(.1)
                counter += 1

        async def driver():
            task = await imbroglio.spawn(ticker())
            await imbroglio.sleep(1)
            try:
                task.cancel()
            except BaseException:
                raise

        imbroglio.run(driver())

        self.assertGreater(counter, 3)

    def test_task_misc(self):
        with self.assertRaises(TypeError):
            imbroglio.Task(lambda: None, None)

        async def nothing():
            await imbroglio.sleep(.1)

        coro = nothing()

        t = imbroglio.Task(coro, None)
        with self.assertRaises(imbroglio.UnfinishedError):
            t.result()

        imbroglio.run(coro)

    def test_result_exception(self):
        async def boring():
            pass

        coro = boring()
        task = imbroglio.Task(coro, imbroglio.Supervisor())
        exception = Exception()
        task.set_cancelled(exception)
        self.assertIs(task.result(False), exception)

        # prevent "coroutine not awaited" warnings
        coro.close()

    def test_get_supervisor(self):
        supervisor = None

        async def do_get_supervisor():
            nonlocal supervisor
            supervisor = await imbroglio.get_supervisor()

        imbroglio.run(do_get_supervisor())
        self.assertIsInstance(supervisor, imbroglio.Supervisor)

    def test_task_list(self):
        tasks = None

        async def do_get_task_list():
            nonlocal tasks
            tasks = await imbroglio.tasks()

        imbroglio.run(do_get_task_list())
        self.assertEqual(([], []), tasks)
        # current task is not on the list

        async def sleep_forever():
            await imbroglio.sleep(None)

        task = None

        async def do_get_waiting_task():
            nonlocal task
            task = await imbroglio.spawn(sleep_forever())
            print(await imbroglio.tasks())
            await do_get_task_list()
            print(await imbroglio.tasks())
            task.cancel()
            await imbroglio.sleep()  # so task gets reaped

        imbroglio.run(do_get_waiting_task())

        self.assertEqual(2, len(tasks))
        runnable, waiting = tasks
        print(runnable)
        print(waiting)
        self.assertEqual(0, len(runnable))
        self.assertEqual(1, len(waiting))
        self.assertEqual([task], waiting)

    def test_sleepy_cancel(self):
        alarmed = False

        def alarm(*args, **kw):
            nonlocal alarmed
            alarmed = True

        handler = signal.signal(signal.SIGALRM, alarm)
        try:
            signal.alarm(2)

            async def sleepy():
                await imbroglio.sleep(1)

            async def driver():
                task = await imbroglio.spawn(sleepy())
                await imbroglio.sleep()
                task.cancel()

            imbroglio.run(driver())
            signal.alarm(0)

            self.assertFalse(alarmed)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, handler)

    def test_throw_exception_type(self):
        # throw a bare type as an inspection.  To spice it up, make sure that
        # it sucessfully cancells a task in a long sleep.

        async def sleepy():
            await imbroglio.sleep(float('Inf'))

        async def driver():
            task = await imbroglio.spawn(sleepy())
            await imbroglio.sleep(0)
            task.throw(NotADirectoryError)
            await imbroglio.sleep(0)
            self.assertTrue(task.is_done())

        imbroglio.run(driver())

    def test_taskwait(self):
        async def longsleep():
            await imbroglio.sleep(1)

        async def shortsleep():
            await imbroglio.sleep(.5)

        async def driver():
            sleepers = [
                (await imbroglio.spawn(longsleep())) for i in range(10)]
            task = await imbroglio.spawn(shortsleep())
            await task
            self.assertTrue(all(not t.is_done() for t in sleepers))

        imbroglio.run(driver())


class TestImbroglioTools(unittest.TestCase):
    def test_timeout(self):
        flag = False

        async def driver():
            nonlocal flag
            async with imbroglio.Timeout(.1):
                await imbroglio.sleep(1)
                flag = True
            self.assertFalse(flag)
            async with imbroglio.Timeout(1) as t:
                await imbroglio.sleep(.1)
                flag = True
            self.assertTrue(flag)
            self.assertTrue(t.is_done())

        imbroglio.run(driver())
        self.assertTrue(flag)

    def test_gather(self):
        a = False
        b = False

        async def f():
            nonlocal a
            await imbroglio.sleep(0)
            await imbroglio.sleep(.1)
            a = True

        async def g():
            nonlocal b
            await imbroglio.sleep(0)
            await imbroglio.sleep(.2)
            b = True

        t0 = time.time()
        imbroglio.run(imbroglio.gather(f(), g()))
        self.assertTrue(a and b)
        self.assertGreater(time.time() - t0, .2)

        class DistinctException(Exception):
            pass

        async def h():
            raise DistinctException()

        imbroglio.run(imbroglio.gather(f(), g(), h(), return_exceptions=True))

        with self.assertRaises(DistinctException):
            imbroglio.run(imbroglio.gather(f(), g(), h()))

    def test_promise(self):
        p = imbroglio.Promise()
        p.set_result(5)
        self.assertEqual(5, p.result)

        r = None

        async def get_result():
            nonlocal r
            r = await p()

        imbroglio.run(get_result())

        self.assertEqual(5, r)

        p = imbroglio.Promise()

        async def set_result():
            await imbroglio.spawn(get_result())
            await imbroglio.sleep(.1)
            p.set_result(6)

        imbroglio.run(set_result())

        self.assertEqual(6, r)

        class DistinctException(Exception):
            pass

        p = imbroglio.Promise()
        t = None

        async def set_exception():
            nonlocal t
            t = await imbroglio.spawn(get_result())
            await imbroglio.sleep(.1)
            p.set_exception(DistinctException('foo'))

        imbroglio.run(set_exception())

        with self.assertRaises(DistinctException):
            t.result()

    def test_run_in_thread(self):
        t0 = None
        t1 = None

        async def thread_sleep():
            nonlocal t1
            await imbroglio.run_in_thread(time.sleep, 1)
            t1 = time.time()

        async def do_thing():
            nonlocal t0
            await imbroglio.spawn(thread_sleep())
            t0 = time.time()

        imbroglio.run(do_thing())

        self.assertLess(t0, t1)

    def test_run_in_thread_exception(self):
        class DistinctException(Exception):
            pass

        def sleep_then_raise():
            time.sleep(1)
            raise DistinctException('foo')

        async def check_raise():
            with self.assertRaises(DistinctException):
                await imbroglio.run_in_thread(sleep_then_raise)

        imbroglio.run(check_raise())


if __name__ == '__main__':
    unittest.main()
