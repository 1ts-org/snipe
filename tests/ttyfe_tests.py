# -*- encoding: utf-8 -*-
# Copyright © 2014 the Snipe contributors
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
Unit tests for the TTY frontend objects

(hard because we haven't mocked curses yet.)
"""

import curses
import sys
import unittest

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.ttyfe     # noqa: E402


class TestTTYFE(unittest.TestCase):
    def testTTYRendererDoline(self):
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline('abc', 80, 80),
            [('abc', 77)])
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline("\tabc", 80, 0),
            [('        abc', 69)])
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline('abc\n', 80, 80),
            [('abc', -1)])
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline('a\01bc', 80, 80),
            [('abc', 77)])
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline('abcdef', 3, 3),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            snipe.ttyfe.TTYRenderer.doline('ab\tdef', 3, 3),
            [('ab', 0), ('def', 0)])

    def testMockWindow(self):
        w = mocks.Window(cx(['']))
        self.assertEqual(list(w.view(0, 'forward')), [(0, [((), '')])])
        w = mocks.Window(cx(['abc\n', 'def\n']))
        self.assertEqual(
            list(w.view(0, 'forward')),
            [
                (0, [((), 'abc\n')]),
                (1, [((), 'def\n')]),
            ])

    def testLocation0(self):
        w = mocks.Window(cx(['']))
        self.assertEqual(list(w.view(0, 'forward')), [(0, [((), '')])])
        ui = mocks.UI()
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 24, w)
        l = snipe.ttyfe.Location(renderer, 0, 0)
        m = l.shift(100)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)
        m = l.shift(-100)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)

    def testLocation1(self):
        w = mocks.Window(cx(['abc\n', 'def']))
        ui = mocks.UI()
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 24, w)

        l = snipe.ttyfe.Location(renderer, 0, 0)
        self.assertEqual(l.cursor, 0)
        self.assertEqual(l.offset, 0)
        m = l.shift(100)
        self.assertEqual(m.cursor, 1)
        self.assertEqual(l.offset, 0)

        m = l.shift(1)
        self.assertEqual(m.cursor, 1)
        self.assertEqual(l.offset, 0)

        m = m.shift(-1)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)

    def testLocation2(self):
        w = mocks.Window(cx(['abc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 24, w)

        l = snipe.ttyfe.Location(renderer, 0, 0)
        self.assertEqual(l.cursor, 0)
        self.assertEqual(l.offset, 0)
        m = l.shift(100)
        self.assertEqual(m.cursor, 3)
        self.assertEqual(l.offset, 0)

        m = l.shift(3)
        self.assertEqual(m.cursor, 3)
        self.assertEqual(l.offset, 0)

        m = m.shift(-3)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)

    def testLocation3(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 24, w)

        l = snipe.ttyfe.Location(renderer, 0, 0)
        self.assertEqual(l.cursor, 0)
        self.assertEqual(l.offset, 0)
        m = l.shift(100)
        self.assertEqual(m.cursor, 3)
        self.assertEqual(l.offset, 0)

        m = l.shift(3)
        self.assertEqual(m.cursor, 2)
        self.assertEqual(l.offset, 0)

        m = m.shift(-3)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)

    def testChunksize(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI(5)
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 24, w)

        doline = snipe.ttyfe.TTYRenderer.doline

        def _chunksize(chunk):  # essentially chunksize classic
            return len(doline(''.join(c[1] for c in chunk), 24, 24))

        self.assertEqual(
            renderer.chunksize([((), '')]),
            _chunksize([((), '')]))
        self.assertEqual(
            renderer.chunksize([((), 'one')]),
            _chunksize([((), 'one')]))
        self.assertEqual(
            renderer.chunksize([((), 'one\n')]),
            _chunksize([((), 'one\n')]))
        self.assertEqual(
            renderer.chunksize([((), 'one')]),
            1)

        # is this doing what I think it's doing?
        self.assertEqual(
            renderer.chunksize([((), 'a'), ((), 'b')]),
            1)
        self.assertEqual(
            renderer.chunksize([((), 'a'), ((), 'b\n')]),
            _chunksize([((), 'a'), ((), 'b\n')]))
        self.assertEqual(
            renderer.chunksize([((), 'a'), ((), 'b\n')]),
            1)
        self.assertEqual(
            renderer.chunksize([((), 'a'), ((), 'b\n'), ((), 'c')]),
            _chunksize([((), 'a'), ((), 'b\n'), ((), 'c')]))
        self.assertEqual(
            renderer.chunksize([((), 'a'), ((), 'b\n'), ((), 'c')]),
            2)

        # Okay, right text
        self.assertEqual(
            renderer.chunksize([((), 'a'), (('right'), 'b')]),
            1)
        self.assertEqual(
            renderer.chunksize([((), 'a'), (('right'), 'b\n')]),
            1)
        self.assertEqual(
            renderer.chunksize([((), 'a'), (('right'), 'b\n'), ((), 'c')]),
            2)
        self.assertEqual(
            renderer.chunksize([((), 'a'), (('right'), 'b\n'), ((), 'c')]),
            2)

        self.assertEqual(
            renderer.chunksize([((), 'aaaa'), ((''), 'bbbb')]),
            2)
        self.assertEqual(
            renderer.chunksize([((), 'aaaa'), (('right'), 'bbbb')]),
            2)
        self.assertEqual(
            renderer.chunksize([((), 'aaaa'), (('right'), 'bbbb\n')]),
            2)

    def testRedisplayCalculate(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 6, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEquals(len(output), 6)
        self.assertFalse(visible)
        self.assertIsNone(cursor)

        chunks = [[
            (('visible',), ''), (('bg:grey24',), '00:58'),
            ((), ' filter default'), (('right',), '2'),
            (('bg:grey24', 'bold'), 'n'), ((), 'ext'), ((), '             '),
            (('bg:grey24', 'bold'), 'p'), ((), 'revious'), ((), '         '),
            (('bg:grey24', 'bold'), '}'), ((), ' n. like'), ((), '        '),
            (('bg:grey24', 'bold'), '{'), ((), ' p. like'), ((), '        '),
            (('bg:grey24', 'bold'), ']'), ((), ' n. stark'), ((), '       '),
            (('bg:grey24', 'bold'), '['), ((), ' p. stark'), ((), '       '),
            (('bg:grey24', 'bold'), 'r'), ((), 'eply'), ((), '            '),
            (('bg:grey24', 'bold'), 'f'), ((), 'ollowup'), ((), '         '),
            (('bg:grey24', 'bold'), 's'), ((), 'end'), ((), '             '),
            (('bg:grey24', 'bold'), '/'), ((), ' filter…'), ((), '        '),
            (('bg:grey24', 'bold'), '^X^C'), ((), ' quit'), ((), '        '),
            (('bg:grey24', 'bold'), '?'), ((), ' help'), ((), '\n'),
            ]]

        w = mocks.Window(chunks)

        ui = mocks.UI(maxx=205)
        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 2, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEquals(len(output), 2)
        self.assertTrue(visible)
        self.assertIsNone(cursor)
        self.assertTrue(all(a & curses.A_UNDERLINE for (a, t) in output[-1]))

        renderer = snipe.ttyfe.TTYRenderer(ui, 0, 3, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEquals(len(output), 3)
        self.assertTrue(visible)
        self.assertIsNone(cursor)
        self.assertTrue(all(a & curses.A_UNDERLINE for (a, t) in output[-1]))


def cx(chunks):
    return [[((), chunk)] for chunk in chunks]


if __name__ == '__main__':
    unittest.main()
