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
Unit tests for tty color infrastructure
'''

import unittest
import unittest.mock
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.ttycolor as ttycolor  # noqa: E402,F401


class TestTTYColor(unittest.TestCase):
    def test_get_assigner(self):
        with unittest.mock.patch('snipe.ttycolor.curses', mocks.Curses()):
            self.assertIsInstance(
                ttycolor.get_assigner(), ttycolor.NoColorAssigner)

        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=256, dynamic=True)):
            self.assertIsInstance(
                ttycolor.get_assigner(),
                ttycolor.DynamicColorAssigner)

        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=256, dynamic=False)):
            self.assertIsInstance(
                ttycolor.get_assigner(), ttycolor.StaticColorAssigner)

    def test_NoColorAssigner(self):
        assign = ttycolor.NoColorAssigner()
        self.assertEqual(assign(None, None), 0)
        assign.close()

    def test_SimpleColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=8, color_pairs=2)):
            assign = ttycolor.SimpleColorAssigner()
            pair = assign.next
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('black', 'white'), 0)

    def test_CleverColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=8, color_pairs=2)):
            assign = ttycolor.CleverColorAssigner()
            self.assertEqual(assign.strtorgb('#fff'), (255, 255, 255))
            self.assertEqual(assign.strtorgb('#ffffff'), (255, 255, 255))
            self.assertEqual(assign.strtorgb('231'), (255, 255, 255))
            self.assertIsNone(assign.strtorgb('nonexistent color'))

    def test_StaticColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=8, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(len(assign.map), len(ttycolor.colors_simple))
            pair = assign.next
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('black', 'white'), 0)
            self.assertEqual(assign.getcolor('nonexistent color'), -1)
            self.assertIs(assign.getcolor('#fff'), assign.getcolor('#fff'))
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=256, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm_256color))
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=88, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm_88color))
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=16, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm))

    def test_DynamicColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                mocks.Curses(colors=8, color_pairs=2)):
            assign = ttycolor.DynamicColorAssigner()
            pair = assign.next
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('black', 'white'), 0)
            self.assertEqual(assign.getcolor('nonexistent color'), -1)
            self.assertIs(assign.getcolor('#fff'), assign.getcolor('#fff'))
            self.assertEqual(assign.getcolor('#003'), 3)
            self.assertEqual(assign.getcolor('#004'), 4)
            self.assertEqual(assign.getcolor('#005'), 5)
            self.assertEqual(assign.getcolor('#006'), 6)
            self.assertEqual(assign.getcolor('#007'), 7)
            self.assertEqual(assign.getcolor('#008'), -1)
            assign.close()


if __name__ == '__main__':
    unittest.main()
