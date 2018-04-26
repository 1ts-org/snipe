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

import unittest
import sys
import time

sys.path.append('..')

from snipe import imbroglio   # noqa: E402


class TestImbroglio(unittest.TestCase):
    def test_simple(self):
        # single coroutine with a single call
        val = None

        @imbroglio.coroutine
        def coro():
            nonlocal val
            val = yield from imbroglio.magic()

        imbroglio.run(coro())

        self.assertEqual(42, val)

    def test_noncoro(self):
        # coroutine that isn't

        val = None

        @imbroglio.coroutine
        def coro():
            nonlocal val
            val = 17

        imbroglio.run(coro())

        self.assertEqual(17, val)

    def test_noncoro2(self):
        # coroutine that isn't exactly

        val = None

        @imbroglio.coroutine
        def coro():
            nonlocal val
            val = 17

            @imbroglio.coroutine
            def actual():
                yield from imbroglio.sleep()

            return actual()

        imbroglio.run(coro())

        self.assertEqual(17, val)

    def test_sleep(self):
        # single coroutine that sleeps for a second
        @imbroglio.coroutine
        def coro():
            yield from imbroglio.sleep(1.0)

        t0 = time.time()

        imbroglio.run(coro())

        self.assertGreaterEqual(time.time(), t0 + 1.0)

    def test_spawn(self):
        # spawn three coroutines that increment a thing and then sleep
        counter = 0

        @imbroglio.coroutine
        def spawned():
            nonlocal counter
            counter += 1
            yield from imbroglio.sleep(1)

        @imbroglio.coroutine
        def spawner():
            yield from imbroglio.spawn(spawned(), spawned(), spawned())

            return 85

        self.assertEqual(85, imbroglio.run(spawner()))
        self.assertEqual(3, counter)


if __name__ == '__main__':
    unittest.main()
