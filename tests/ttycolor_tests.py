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

import curses
import unittest
import unittest.mock
import sys

sys.path.append('..')
sys.path.append('../lib')

import snipe.ttycolor as ttycolor  # noqa: E402,F401


class MockCurses:
    COLOR_BLACK = curses.COLOR_BLACK
    COLOR_RED = curses.COLOR_RED
    COLOR_GREEN = curses.COLOR_GREEN
    COLOR_YELLOW = curses.COLOR_YELLOW
    COLOR_BLUE = curses.COLOR_BLUE
    COLOR_MAGENTA = curses.COLOR_MAGENTA
    COLOR_CYAN = curses.COLOR_CYAN
    COLOR_WHITE = curses.COLOR_WHITE

    COLOR_PAIRS = None
    COLORS = None
    dynamic = None
    pairs = []

    def __init__(self, colors=0, dynamic=False, color_pairs=256):
        self.COLORS = colors
        self.COLOR_PAIRS = color_pairs
        self.dynamic = dynamic
        self.pairs = [None] * self.COLOR_PAIRS

    def init_pair(self, pair, fg, bg):
        self.pairs[pair] = (fg, bg)

    def color_pair(self, pair):
        return pair

    def color_content(self, number):
        pass

    def init_color(self, color, r, g, b):
        pass

    def has_colors(self):
        return bool(self.COLORS)

    def start_color(self):
        pass

    def use_default_colors(self):
        pass

    def can_change_color(self):
        return self.dynamic


class TestTTYColor(unittest.TestCase):
    def test_get_assigner(self):
        with unittest.mock.patch('snipe.ttycolor.curses', MockCurses()):
            self.assertIsInstance(
                ttycolor.get_assigner(), ttycolor.NoColorAssigner)

        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=256, dynamic=True)):
            self.assertIsInstance(
                ttycolor.get_assigner(), ttycolor.DynamicColorAssigner)

        with unittest.mock.patch(
                'snipe.ttycolor.curses',
                MockCurses(colors=256, dynamic=False)):
            self.assertIsInstance(
                ttycolor.get_assigner(), ttycolor.StaticColorAssigner)

    def test_SimpleColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=8, color_pairs=2)):
            assign = ttycolor.SimpleColorAssigner()
            pair = assign.next
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('white', 'blue'), pair)
            self.assertEqual(assign('black', 'white'), 0)

    def test_CleverColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=8, color_pairs=2)):
            assign = ttycolor.CleverColorAssigner()
            self.assertEqual(assign.strtorgb('#fff'), (255, 255, 255))
            self.assertEqual(assign.strtorgb('#ffffff'), (255, 255, 255))
            self.assertEqual(assign.strtorgb('231'), (255, 255, 255))
            self.assertIsNone(assign.strtorgb('nonexistent color'))

    def test_StaticColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=8, color_pairs=2)):
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
                MockCurses(colors=256, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm_256color))
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=88, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm_88color))
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=16, color_pairs=2)):
            assign = ttycolor.StaticColorAssigner()
            self.assertEqual(
                len(assign.map), len(ttycolor.colors_xterm))

    def test_DynamicColorAssigner(self):
        with unittest.mock.patch(
                'snipe.ttycolor.curses', MockCurses(colors=8, color_pairs=2)):
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


if __name__ == '__main__':
    unittest.main()
