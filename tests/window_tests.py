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
Unit tests for stuff in windows.py
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
        w = window.Window(mocks.FE())
        w.balance_windows()
        self.assertIn('balance_windows', w.fe.called)

    def test_mode(self):
        class AMode:
            cheatsheet = ['foo']
        w = window.Window(None, modes=[AMode()])
        self.assertEqual(w.cheatsheet[-1], 'foo')

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
        self.assertEquals(cheatsheetify(''), [])
        self.assertEquals(cheatsheetify('foo'), [((), 'foo')])
        self.assertEquals(cheatsheetify('*foo*'), [(TAGS, 'foo')])
        self.assertEquals(
            cheatsheetify('f*o*o'), [((), 'f'), (TAGS, 'o'), ((), 'o')])
        self.assertEquals(cheatsheetify('f\*o'), [((), 'f*o')])
        self.assertEquals(cheatsheetify('f**oo'), [((), 'foo')])
        self.assertEquals(cheatsheetify('f*\*oo'), [((), 'f'), (TAGS, '*oo')])


if __name__ == '__main__':
    unittest.main()
