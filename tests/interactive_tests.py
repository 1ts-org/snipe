#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2017 the Snipe contributors
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
Unit tests for interactive function infrastructure
'''

import inspect
import unittest

from unittest.mock import (Mock)
from typing import (TYPE_CHECKING)

import snipe.interactive as interactive  # noqa: F401


class TestInteractive(unittest.TestCase):
    def test__keyword(self):
        f = interactive._keyword('foo')

        self.assertTrue(inspect.isfunction(f))

        self.assertIsNone(f())
        self.assertEqual('bar', f(foo='bar'))

    def test_integer_argument(self):
        if TYPE_CHECKING:
            return
        self.assertEqual(
            5, interactive.integer_argument(argument=5))
        self.assertEqual(
            -1, interactive.integer_argument(argument='-'))
        self.assertEqual(
            4,  interactive.integer_argument(argument=[True]))
        self.assertEqual(
            3, interactive.positive_integer_argument(
                argument=-3))
        self.assertIsNone(interactive.positive_integer_argument())

    def test_isinteractive(self):
        self.assertTrue(interactive.isinteractive())

    def test_call(self):
        def callable(i: interactive.integer_argument):
            return 5

        self.assertEqual(5, interactive.call(callable))

        def callable(i: interactive.integer_argument=4):
            return i

        self.assertEqual(4, interactive.call(callable))

        def callable(i):
            pass

        with self.assertRaises(Exception):
            interactive.call(callable)


class TestUnCompleter(unittest.TestCase):
    def test(self):
        u = interactive.UnCompleter()
        self.assertEqual([], u.candidates)
        self.assertFalse(u.live)

        self.assertEqual([], u.matches())
        self.assertIsNone(u.roll(5))
        self.assertIsNone(u.roll_to('foo'))
        self.assertFalse(u.check(None, None))
        self.assertEqual((None, None), u.expand('value'))


class TestCompleter(unittest.TestCase):
    def test(self):
        c = interactive.Completer(['aaa', 'bab', 'aab'])
        self.assertEqual(
            [(0, 'aaa', 'aaa'), (1, 'aab', 'aab')], c.matches('aa'))
        c.roll(1)
        self.assertEqual(
            [(0, 'aab', 'aab'), (2, 'aaa', 'aaa')], c.matches('aa'))
        c.roll_to('aaa')
        self.assertEqual(
            [(0, 'aaa', 'aaa'), (1, 'aab', 'aab')], c.matches('aa'))
        self.assertEqual('aaa', c.expand('a'))
        self.assertEqual('ccc', c.expand('ccc'))


class TestFileCompleter(unittest.TestCase):
    def test(self):
        f = interactive.FileCompleter()
        self.assertEqual(1, len(f.matches('interactive')))
        self.assertEqual(
            ('interactive_tests.py', 'interactive_tests.py'),
            f.matches('interactive')[0][1:])
        self.assertEqual('interactive_tests.py', f.expand('interactive'))
        f.directory = '../tests'
        self.assertEqual(
            ('interactive_tests.py', 'interactive_tests.py'),
            f.matches('interactive')[0][1:])
        self.assertEqual(
            '../tests/interactive_tests.py',
            f.expand('../tests/interactive'))


class TestDestCompleter(unittest.TestCase):
    def test(self):
        roost = Mock()
        roost.name = 'roost'
        irccloud = Mock()
        irccloud.name = 'irccloud'
        context = Mock()
        context.backends = [roost, irccloud]
        d = interactive.DestCompleter(
            ['roost; foo', 'roost; bar', 'irccloud; baz'], context)
        self.assertEqual(['roost; bar'], [x[1] for x in d.matches('bar')])
        self.assertEqual(['roost; bar'], [x[1] for x in d.matches('r;bar')])
        self.assertEqual(
            ['irccloud; baz'], [x[1] for x in d.matches('i;baz')])
        self.assertEqual(
            ['irccloud; baz'], [x[1] for x in d.matches('i;')])
        self.assertEqual(
            ['irccloud; baz'], [x[1] for x in d.matches(';baz')])
