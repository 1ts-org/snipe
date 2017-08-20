# -*- encoding: utf-8 -*-
# Copyright © 2015 the Snipe contributors
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
Unit tests for stuff in window.py
'''

import sys
import unittest

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.keymap as keymap  # noqa: E402
import snipe.window as window  # noqa: E402


class TestWindow(unittest.TestCase):
    def test_init(self):
        w = window.Window(mocks.FE())
        w.renderer = mocks.Renderer()
        w.cursor = object()
        x = window.Window(mocks.FE(), prototype=w)
        self.assertIs(w.cursor, x.cursor)

    def test_balance_windows(self):
        with mocks.mocked_up_actual_fe_window(window.Window) as w:
            w.split_window()
            w.split_window()
            w.balance_windows()
            self.assertEqual([w.height for w in w.fe.windows], [8, 8, 8])

    def test_enlarge_windows(self):
        with mocks.mocked_up_actual_fe_window(window.Window) as w:
            w.split_window()
            w.enlarge_window()
            self.assertEqual([w.height for w in w.fe.windows], [13, 11])

    def test_mode(self):
        class AMode:
            cheatsheet = ['foo']
        w = window.Window(None, modes=[AMode()])
        self.assertEqual(w.cheatsheet[-1], 'foo')

    def test_input_char(self):
        with mocks.mocked_up_actual_fe_window(window.Window) as w:
            save = []
            w.intermediate_action = (
                lambda keystroke=None: save.append(keystroke))
            with self.assertLogs(w.log.name, level='ERROR'):
                w.input_char('x')
            self.assertEqual(w.context._message, 'unknown command')
            w.keyerror_action = lambda k: save.append('E' + k)
            w.input_char('x')
            self.assertEqual(save, ['x', 'x', 'Ex'])

            w.keymap['y'] = lambda: save.append('y')
            w.input_char('y')
            self.assertEqual(save, ['x', 'x', 'Ex', 'y', 'y'])

            w.intermediate_action = None
            w.keymap['z'] = keymap.Keymap()
            w.keymap['z']['Z'] = lambda: save.append('z')
            w.input_char('z')
            w.input_char('Z')
            self.assertEqual(save, ['x', 'x', 'Ex', 'y', 'y', 'z'])

    def test_misc(self):
        called = False

        def destroy_cb():
            nonlocal called
            called = True
        with mocks.mocked_up_actual_fe_window(
                lambda fe: window.Window(fe, destroy=destroy_cb)) as w:
            self.assertEqual(w.focus(), True)
            w.destroy()
            self.assertEqual(called, True)

            self.assertEqual(w.title(), 'Window')
            self.assertEqual(w.modeline(), (
                [((), 'Window')],
                [(('right',), '1')]))

    def test_search_interface(self):
        with mocks.mocked_up_actual_fe_window(window.Window) as w:
            self.assertRaises(NotImplementedError, lambda: w.find('foo'))
            self.assertRaises(NotImplementedError, lambda: w.match('foo'))
            self.assertRaises(NotImplementedError, w.beginning)
            self.assertRaises(NotImplementedError, w.end)
            self.assertEqual(w.make_mark(None), None)

    def test_set_cheatsheet(self):
        w = window.Window(None)
        c = []
        w.set_cheatsheet(c)
        self.assertIs(w.cheatsheet, c)
        self.assertIs(w._normal_cheatsheet, c)

        k = keymap.Keymap()
        k.set_cheatsheet(['bar'])
        w.maybe_install_cheatsheet(k)
        self.assertEqual(w.cheatsheet, ['bar'])

    def test_cheatsheetify(self):
        cheatsheetify = window.StatusLine.cheatsheetify
        TAGS = window.StatusLine.KEYTAGS
        self.assertEqual(cheatsheetify(''), [])
        self.assertEqual(cheatsheetify('foo'), [((), 'foo')])
        self.assertEqual(cheatsheetify('*foo*'), [(TAGS, 'foo')])
        self.assertEqual(
            cheatsheetify('f*o*o'), [((), 'f'), (TAGS, 'o'), ((), 'o')])
        self.assertEqual(cheatsheetify('f\*o'), [((), 'f*o')])
        self.assertEqual(cheatsheetify('f**oo'), [((), 'foo')])
        self.assertEqual(cheatsheetify('f*\*oo'), [((), 'f'), (TAGS, '*oo')])


class TestStatusLine(unittest.TestCase):
    def test(self):
        with mocks.mocked_up_actual_fe_window(
                window.Window, window.StatusLine) as w:
            s = w.context.status
            self.assertEqual([[
                (('visible',), ''),
                ((), 'Window'),
                (('right',), '1'),
                ((), 'You'),
                ((), '                 '),
                ((), 'be'),
                ((), '                  '),
                ((), 'this'),
                ((), '                '),
                (('bold',), '^Z'),
                ((), ' suspend'),
                ((), '\n'),
                ((), "shouldn't"),
                ((), '           '),
                ((), 'seeing'),
                ((), '              '),
                (('bold',), '^X^C'),
                ((), ' quit'),
                ((), '           '),
                (('bold',), '?'),
                ((), ' help'),
                ((), '\n')
                ]], [chunk for (mark, chunk) in s.view(0)])

            w.context.conf['set'] = {'cheatsheet': False}
            w.fe.resize_statuswindow()
            self.assertEqual([[
                (('visible',), ''),
                ((), 'Window'),
                (('right',), '1'),
                ]], [chunk for (mark, chunk) in s.view(0)])

            s.message('X' * 80)
            self.assertEqual([[
                ({'visible'}, ''),
                ({'fg:white', 'bg:red'}, '…' + ('X' * 77)),
                ({'right'}, '1'),
                ]], [chunk.tagsets() for (mark, chunk) in s.view(0)])

            # defensiveness time

            class W2(window.Window):
                def modeline(self):
                    return None, []

            s.clear()
            w.fe.split_window(W2(w.fe), True)

            self.assertEqual([[
                (('visible',), ''),
                ]], [chunk for (mark, chunk) in s.view(0)])

            w.fe.output = 99
            self.assertEqual([[
                (('visible',), ''),
                ((), 'StatusLine'),
                (('right',), '1'),
                ]], [chunk for (mark, chunk) in s.view(0)])


if __name__ == '__main__':
    unittest.main()
