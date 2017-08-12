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
import unittest.mock

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.ttyfe as ttyfe        # noqa: E402
import snipe.window as window      # noqa: E402
import snipe.ttycolor as ttycolor  # noqa: E402


class TestTTYFrontend(unittest.TestCase):
    def test_window_management(self):
        curses = mocks.Curses()
        with unittest.mock.patch('snipe.ttyfe.curses', curses):
            fe = ttyfe.TTYFrontend()
            # emulating fe.__enter_
            fe.stdscr = curses.stdscr
            fe.maxy = curses.LINES
            fe.maxx = curses.COLUMNS
            fe.context = mocks.Context()
            fe.color_assigner = ttycolor.NoColorAssigner()

            fe.windows = [ttyfe.TTYRenderer(fe, 0, fe.maxy, window.Window(fe))]
            fe.set_active(0)

            self.assertEqual(fe.maxy, 24)

            fe.split_window(window.Window(fe), False)

            self.assertEqual(fe.input, 0)

            fe.delete_current_window()

            self.assertEqual(fe.input, 0)

            fe.split_window(window.Window(fe), True)

            self.assertEqual(fe.input, 1)

            self.assertEqual(len(fe.windows), 2)

            fe.split_window(window.Window(fe))

            self.assertEqual(len(fe.windows), 3)

            fe.split_window(window.Window(fe))

            self.assertEqual(len(fe.windows), 4)

            self.assertRaises(
                Exception, lambda: fe.split_window(window.Window(fe)))

            fe.delete_current_window()

            self.assertEqual(len(fe.windows), 3)

            fe.delete_other_windows()

            self.assertEqual(len(fe.windows), 1)

            self.assertRaises(
                Exception,
                lambda: fe.delete_window_window(fe.windows[0].window))

            # would raise if it actually tried to delete anything
            fe.delete_window_window(window.Window(fe))

            fe.split_window(window.Window(fe))
            fe.split_window(window.Window(fe))

            fe.context.status = fe.windows[fe.output].window

            self.assertRaises(
                Exception,
                lambda: fe.delete_current_window())

            fe.context.status = None

            fe.delete_other_windows()

            self.assertEqual(len(fe.windows), 1)
            self.assertEqual(fe.output, 0)
            # popup a window
            fe.popup_window(window.Window(fe), 1, fe.windows[0].window)
            self.assertEqual(len(fe.windows), 2)
            self.assertEqual(fe.output, 1)
            # popup one over that
            fe.popup_window(window.Window(fe), 1, fe.windows[1].window)
            self.assertEqual(len(fe.windows), 2)
            self.assertEqual(fe.output, 1)

            # should bring the old popup back
            fe.delete_current_window()
            # XXX switches back to the original indow
            self.assertEqual(fe.output, 0)

            self.assertEqual(len(fe.windows), 2)

            fe.set_active(1)
            fe.delete_current_window()
            # should take care of that
            self.assertEqual(fe.output, 0)

            self.assertEqual(len(fe.windows), 1)

            print(fe.output, fe.windows)
            fe.split_window(window.Window(fe))
            print(fe.output, fe.windows)
            self.assertEqual(len(fe.windows), 2)

            fe.split_window(window.Window(fe))
            self.assertEqual(len(fe.windows), 3)
            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 6)
            self.assertEqual(fe.windows[2].height, 12)

            fe.delete_window(1)

            self.assertEqual(len(fe.windows), 2)
            self.assertEqual(fe.windows[0].height, 12)
            self.assertEqual(fe.windows[1].height, 12)

            fe.delete_window(0)
            self.assertEqual(fe.windows[0].height, 24)

            fe.split_window(window.Window(fe))
            fe.split_window(window.Window(fe))
            fe.set_active(2)
            fe.split_window(window.Window(fe))

            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 6)
            self.assertEqual(fe.windows[2].height, 6)
            self.assertEqual(fe.windows[3].height, 6)

            fe.windows[1].window.noresize = True

            fe.delete_window(0)
            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 12)
            self.assertEqual(fe.windows[2].height, 6)

            fe.delete_window(1)
            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 18)

            self.assertRaises(Exception, lambda: fe.delete_window(1))
            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 18)

            fe.set_active(1)
            fe.windows[0].window.noactive = True
            fe.switch_window(1)
            self.assertEqual(fe.output, 1)

            fe.delete_window(0)
            self.assertEqual(fe.windows[0].height, 24)

            fe.split_window(window.Window(fe))
            self.assertEqual(fe.windows[0].height, 12)
            self.assertEqual(fe.windows[1].height, 12)

            fe.popup_window(window.Window(fe), 1, fe.windows[0].window, True)
            self.assertEqual(fe.windows[0].height, 11)
            self.assertEqual(fe.windows[1].height, 1)
            self.assertEqual(fe.windows[2].height, 12)

            fe.set_active(0)
            fe.delete_other_windows()
            self.assertEqual(fe.windows[0].height, 24)

            fe.split_window(window.Window(fe))
            fe.split_window(window.Window(fe))
            self.assertEqual(len(fe.windows), 3)
            self.assertEqual(fe.windows[0].height, 6)
            self.assertEqual(fe.windows[1].height, 6)
            self.assertEqual(fe.windows[2].height, 12)

            fe.windows[1].window.noactive = True
            self.assertEqual(fe.output, 0)
            fe.delete_current_window()
            self.assertEqual(fe.output, 1)


class TestTTYRenderer(unittest.TestCase):
    def test_doline(self):
        self.assertEqual(
            ttyfe.TTYRenderer.doline('abc', 80, 80),
            [('abc', 77)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline("\tabc", 80, 0),
            [('        abc', 69)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('abc\n', 80, 80),
            [('abc', -1)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('a\01bc', 80, 80),
            [('abc', 77)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('abcdef', 3, 3),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('ab\tdef', 3, 3),
            [('ab', 0), ('def', 0)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('ab\x96cdef', 3, 3),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('ab def', 3, 3, ('fill',)),
            [('ab', -1), ('def', 0)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('abc def', 3, 0, ('fill',)),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            ttyfe.TTYRenderer.doline('abc def\n', 3, 0, ('fill',)),
            [('abc', 0), ('def', 0)])

    def test_chunksize(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI(5)
        renderer = ttyfe.TTYRenderer(ui, 0, 24, w)

        doline = ttyfe.TTYRenderer.doline

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

    def test_redisplay_calculate(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = ttyfe.TTYRenderer(ui, 0, 6, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEqual(len(output), 6)
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
        renderer = ttyfe.TTYRenderer(ui, 0, 2, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEqual(len(output), 2)
        self.assertTrue(visible)
        self.assertIsNone(cursor)
        self.assertTrue(all(a & curses.A_UNDERLINE for (a, t) in output[-1]))

        renderer = ttyfe.TTYRenderer(ui, 0, 3, w)
        ui.windows = [renderer]

        renderer.reframe()

        visible, cursor, sill, output = renderer.redisplay_calculate()

        self.assertEqual(len(output), 3)
        self.assertTrue(visible)
        self.assertIsNone(cursor)
        self.assertTrue(all(a & curses.A_UNDERLINE for (a, t) in output[-1]))


class TestLocation(unittest.TestCase):
    def test_mocks_Window(self):
        w = mocks.Window(cx(['']))
        self.assertEqual(list(w.view(0, 'forward')), [(0, [((), '')])])
        w = mocks.Window(cx(['abc\n', 'def\n']))
        self.assertEqual(
            list(w.view(0, 'forward')),
            [
                (0, [((), 'abc\n')]),
                (1, [((), 'def\n')]),
            ])

    def test_Location_0(self):
        w = mocks.Window(cx(['']))
        self.assertEqual(list(w.view(0, 'forward')), [(0, [((), '')])])
        ui = mocks.UI()
        renderer = ttyfe.TTYRenderer(ui, 0, 24, w)
        l = ttyfe.Location(renderer, 0, 0)
        m = l.shift(100)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)
        m = l.shift(-100)
        self.assertEqual(l.cursor, m.cursor)
        self.assertEqual(l.offset, m.offset)

    def test_Location_1(self):
        w = mocks.Window(cx(['abc\n', 'def']))
        ui = mocks.UI()
        renderer = ttyfe.TTYRenderer(ui, 0, 24, w)

        l = ttyfe.Location(renderer, 0, 0)
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

    def test_Location_2(self):
        w = mocks.Window(cx(['abc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = ttyfe.TTYRenderer(ui, 0, 24, w)

        l = ttyfe.Location(renderer, 0, 0)
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

    def test_Location_3(self):
        w = mocks.Window(cx(['abc\nabc\n', 'def\n', 'ghi\n', 'jkl']))
        ui = mocks.UI()
        renderer = ttyfe.TTYRenderer(ui, 0, 24, w)

        l = ttyfe.Location(renderer, 0, 0)
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


def cx(chunks):
    return [[((), chunk)] for chunk in chunks]


if __name__ == '__main__':
    unittest.main()
