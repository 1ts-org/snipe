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


'''
Unit tests for various context-related things
'''


import curses
import sys
import unittest

sys.path.append('..')
sys.path.append('../lib')

import snipe.keymap  # noqa: E402


class TestKeymap(unittest.TestCase):
    def testkeyseq_re(self):
        self.assertFalse(snipe.keymap.Keymap.keyseq_re.match('frob'))
        s = 'control-Shift-META-hyper-SUPER-aLT-ctl-[LATIN CAPITAL LETTER A]'
        m = snipe.keymap.Keymap.keyseq_re.match(s)
        self.assertTrue(m, msg='Keymap.keyseq_re.match(' + s + ')')

        self.assertEqual(
            m.groupdict(),
            {
                'char': None,
                'modifiers': 'control-Shift-META-hyper-SUPER-aLT-ctl-',
                'name': 'LATIN CAPITAL LETTER A',
                'rest': None,
                })

    def testsplit(self):
        split = snipe.keymap.Keymap.split

        with self.assertRaises(TypeError):
            split('frob')

        with self.assertRaises(TypeError):
            split('[IPHONE 5C WITH DECORATIVE CASE]')

        self.assertEqual(split('Hyper-[latin capital letter a]'), (None, None))
        self.assertEqual(split('Meta-[escape]'), ('\x1b', '[ESCAPE]'))
        self.assertEqual(split('Control-C Control-D'), ('\x03', 'Control-D'))
        self.assertEqual(split('[latin capital letter a]'), ('A', None))
        self.assertEqual(split('Shift-a'), ('A', None))
        self.assertEqual(split('[F1]'), (curses.KEY_F1, None))
        self.assertEqual(split('Meta-A'), ('\x1b', 'A'))
        self.assertEqual(split('Meta-[F1]'), ('\x1b', '[F1]'))
        self.assertEqual(split('Control-[F1]'), (None, None))  # XXX
        self.assertEqual(split('Shift-[F1]'), (None, None))    # XXX
        self.assertEqual(split('Control-?'), ('\x7f', None))
        self.assertEqual(split('Control-$'), (None, None))
        self.assertEqual(split('Meta--'), ('\x1b', '-'))
        self.assertEqual(
            split('Meta-:'),
            ('\x1b', ':'))
        self.assertEqual(
            split('Meta-Control-x'),
            ('\x1b', 'Control-X'))
        self.assertEqual(
            split('Meta-[escape] oogledyboo'),
            ('\x1b', '[ESCAPE] oogledyboo'))
        self.assertEqual(
            split('Control-C Control-D oogledyboo'),
            ('\x03', 'Control-D oogledyboo'))
        self.assertEqual(split(-5), (-5, None))
        self.assertEqual(
            split('Meta-\N{LATIN SMALL LETTER A WITH DIAERESIS}'),
            ('\x1b', '[LATIN SMALL LETTER A WITH DIAERESIS]'))

    def testdict(self):
        k = snipe.keymap.Keymap()
        k['a b'] = 1
        self.assertEqual(k['a b'], 1)
        l = snipe.keymap.Keymap(k)
        self.assertEqual(k['a b'], 1)
        self.assertIsNot(k, l)
        self.assertIsNot(k['a'], l['a'])
        del k['a b']
        with self.assertRaises(KeyError):
            k['c']
        k['c'] = 2
        with self.assertRaises(KeyError):
            k['c d'] = 3
        k['\n'] = 4
        self.assertEqual(k['\n'], 4)
        del k['\n']
        with self.assertRaises(KeyError):
            k['\n']

    def testsetmarkkey(self):
        split = snipe.keymap.Keymap.split
        self.assertEqual(split('Control-@'), ('\0', None))
        self.assertEqual(split('Control-[space]'), ('\0', None))

    def testcheatseat(self):
        k = snipe.keymap.Keymap()
        k.set_cheatsheet('foo')
        self.assertEquals(k.get_cheatsheet(), 'foo')

    def test_default(self):
        k = snipe.keymap.Keymap()
        k.default = 5
        self.assertEqual(k['9'], 5)

    def test_repr(self):
        k = snipe.keymap.Keymap()
        self.assertRegex(
            repr(k),
            r"^Keymap\({'\\x07': <function noop at 0x[0-9a-f]+>}\)$")

    def test_get_misc(self):
        k = snipe.keymap.Keymap()
        k[5] = 5
        self.assertEqual(k[5], 5)

    def test_del_misc(self):
        k = snipe.keymap.Keymap()
        k[5] = 5
        del k[5]
        self.assertNotIn(5, k)

        k['a'] = 5
        self.assertRaises(KeyError, lambda: k.__delitem__('a b'))

    def test_unkey(self):
        unkey = snipe.keymap.Keymap.unkey

        self.assertEqual(unkey('a'), 'a')
        self.assertEqual(unkey('\x01'), 'Control-A')
        self.assertEqual(unkey('\x01', True), '^A')
        self.assertEqual(unkey('\x1b'), '[escape]')
        self.assertEqual(
            unkey('\N{latin small letter a with diaeresis}'),
            '[latin small letter a with diaeresis]')
        self.assertEqual(unkey('\x96'), '[?96]')
        self.assertEqual(unkey(curses.KEY_LEFT), '[left]')
        self.assertEqual(unkey(65535), '[ffff?]')

    def test_str(self):
        k = snipe.keymap.Keymap()

        self.assertEqual(str(k), 'Control-G  noop')

        del k['Control-G']
        for c in 'abc':
            k[c] = snipe.keymap.noop
        self.assertEqual(str(k), 'a .. c  noop')

        k = snipe.keymap.Keymap()
        del k['Control-G']
        k['a b'] = snipe.keymap.noop
        del k['a Control-G']
        self.assertEqual(str(k), 'a b  noop')

        k = snipe.keymap.Keymap()
        del k['Control-G']
        k['a'] = 5
        self.assertEqual(str(k), 'a  ???')


if __name__ == '__main__':
    unittest.main()
