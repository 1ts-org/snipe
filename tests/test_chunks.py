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
Unit tests for stuff in chunks.py
'''

import re
import unittest

from snipe.chunks import Chunk


class TestChunk(unittest.TestCase):
    def test(self):
        self.assertEqual(repr(Chunk()), 'Chunk([])')
        self.assertEqual(list(Chunk([((), 'foo')])), [(set(), 'foo')])
        self.assertEqual(Chunk([((), 'foo')]), [(set(), 'foo')])
        self.assertEqual(Chunk([((), 'foo')])[:], Chunk([(set(), 'foo')]))
        self.assertRaises(ValueError, lambda: Chunk().extend([()]))
        c = Chunk()
        self.assertRaises(IndexError, lambda: c[5])
        c.extend([((), 'a'), ({'bold'}, 'b')])
        self.assertEqual(c[:], [(set(), 'a'), ({'bold'}, 'b')])
        self.assertEqual(c[0], (set(), 'a'))
        self.assertRaises(ValueError, lambda: c.__setitem__(0, ()))
        self.assertRaises(
            ValueError, lambda: c.__setitem__(slice(0, 10, 5), []))
        c[0] = (), 'c'
        self.assertEqual(c[:], [(set(), 'c'), ({'bold'}, 'b')])
        self.assertEqual(str(c), 'cb')
        self.assertEqual(len(c), 2)
        c[:] = [((), 'd')]
        self.assertEqual(c[:], [(set(), 'd')])
        self.assertEqual(len(c), 1)
        self.assertEqual(
            str(Chunk([(set(), 'x')]) + Chunk([(set(), 'y')])), 'xy')
        c = Chunk([((), 'foo')])
        c += Chunk([((), 'bar')])
        self.assertEqual(str(c), 'foobar')
        c += [((), 'baz')]
        self.assertEqual(str(c), 'foobarbaz')
        d = [((), 'zog')] + c
        self.assertEqual(str(d), 'zogfoobarbaz')
        del d[0]
        self.assertEqual(str(d), '')
        e = Chunk([((), 'foo'), ({'bold'}, 'baz'), ((), 'bar')])
        self.assertEqual(str(e), 'foobazbar')
        self.assertEqual(len(e), 3)
        del e[1]
        self.assertEqual(str(e), 'foobar')
        self.assertEqual(len(e), 1)

    def test_slice(self):
        X, Y, Z = {'x'}, {'y'}, {'z'}
        l = Chunk([(X, 'abc'), (Y, 'def'), (Z, 'ghi')])
        self.assertEqual(l.slice(0), (Chunk(), l))
        self.assertEqual(
            l.slice(1), (
                Chunk([(X, 'a')]),
                Chunk([(X, 'bc'), (Y, 'def'), (Z, 'ghi')])))
        self.assertEqual(
            l.slice(3), (
                Chunk([(X, 'abc')]),
                Chunk([(Y, 'def'), (Z, 'ghi')])))
        self.assertEqual(
            l.slice(4), (
                Chunk([(X, 'abc'), (Y, 'd')]),
                Chunk([(Y, 'ef'), (Z, 'ghi')])))
        self.assertEqual(
            l.slice(6), (
                Chunk([(X, 'abc'), (Y, 'def')]),
                Chunk([(Z, 'ghi')])))
        self.assertEqual(
            l.slice(7), (
                Chunk([(X, 'abc'), (Y, 'def'), (Z, 'g')]),
                Chunk([(Z, 'hi')])))
        self.assertEqual(l.slice(9), (l, Chunk()))
        self.assertEqual(
            Chunk([(X, 'abc'), (Y, ''), (Z, 'def')]).slice(3), (
                Chunk([(X, 'abc')]),
                Chunk([(Y, ''), (Z, 'def')])))
        self.assertEqual(
            Chunk([(X, ''), (Y, 'abc'), (Z, 'def')]).slice(3), (
                Chunk([(X, ''), (Y, 'abc')]),
                Chunk([(Z, 'def')])))
        self.assertEqual(
            Chunk([(X, ''), (Y, 'abc'), (Z, 'def')]).slice(0), (
                Chunk(),
                Chunk([(X, ''), (Y, 'abc'), (Z, 'def')])))
        self.assertEqual(Chunk().slice(0), (Chunk(), Chunk()))

    def test_slice_point_tags(self):
        self.assertEqual(
            Chunk([({'cursor'}, 'foobar')]).slice(3),
            (Chunk([({'cursor'}, 'foo')]), Chunk([((), 'bar')])))
        self.assertEqual(
            Chunk([({'cursor'}, 'foobar')]).slice(0),
            (Chunk(), Chunk([({'cursor'}, 'foobar')])))
        self.assertEqual(
            Chunk([((), 'foo'), ({'cursor'}, 'bar')]).slice(3), (
                Chunk([((), 'foo')]),
                Chunk([({'cursor'}, 'bar')])))
        self.assertEqual(
            Chunk([((), 'foo'), ({'cursor'}, ''), ((), 'bar')]).slice(3), (
                Chunk([((), 'foo')]),
                Chunk([({'cursor'}, ''), ((), 'bar')])))

    def test_mark_re(self):
        self.assertEqual(
            list(Chunk([
                ((), 'xxx'),
                ((), 'abc'),
                ((), 'xxxab'),
                ((), ''),
                ((), 'cxxx'),
                ((), 'abcxxx'),
                ((), 'xxxabc'),
                ]).mark_re(re.compile('abc'), Chunk.tag_reverse)),
            list(Chunk([
                ((), 'xxx'),
                (('reverse',), 'abc'),
                ((), 'xxx'),
                (('reverse',), ('ab'),),
                (('reverse',), ''),
                (('reverse',), 'c'),
                ((), 'xxx'),
                (('reverse',), 'abc'),
                ((), 'xxx'),
                ((), 'xxx'),
                (('reverse',), 'abc'),
            ])))

    def test_at_add(self):
        x = Chunk([((), 'abcdef')])

        y = x + Chunk([(('bar',), '')])
        self.assertEqual(y.at_add(6, {'foo'}).tagsets(), [
            ((), 'abcdef'),
            ({'bar', 'foo'}, ''),
            ])

        y = Chunk(x)
        self.assertEqual(
            y.at_add(3, {'foo'}).tagsets(), [((), 'abc'), ({'foo'}, 'def')])

        y = Chunk(x)
        self.assertEqual(y.at_add(0, {'foo'}).tagsets(), [({'foo'}, 'abcdef')])

        y = Chunk(x)
        self.assertEqual(
            y.at_add(6, {'foo'}).tagsets(), [((), 'abcdef'), ({'foo'}, '')])

        y = Chunk([(('bar',), '')]) + x
        self.assertEqual(
            y.at_add(0, {'foo'}).tagsets(),
            [({'bar', 'foo'}, ''), ((), 'abcdef')])

        x = Chunk([((), 'abcdef'), (('bar',), 'ghijkl')])
        self.assertEqual(x.at_add(9, {'foo'}).tagsets(), [
            ((), 'abcdef'),
            ({'bar'}, 'ghi'),
            ({'bar', 'foo'}, 'jkl'),
            ])

    def test_tagsets(self):
        self.assertEqual(Chunk().tagsets(), [])
        self.assertEqual(Chunk([((), 'foo')]).tagsets(), [((), 'foo')])
        self.assertEqual(
            Chunk([((), 'foo'), ({'bar'}, 'baz')]).tagsets(),
            [((), 'foo'), ({'bar'}, 'baz')])

    def test_endswith(self):
        self.assertTrue(
            Chunk([({'bold'}, 'foo'), ({'italic'}, 'bar')]).endswith('foobar'))

    def test_show_control(self):
        self.assertEqual(
            Chunk([((), 'foo bar')]).show_control().tagsets(),
            [((), 'foo bar')])
        self.assertEqual(
            Chunk([((), 'foo\007bar')]).show_control().tagsets(),
            [((), 'foo'), (Chunk.SHOW_CONTROL, '^G'), ((), 'bar')])
        self.assertEqual(
            Chunk([((), '\007bar')]).show_control().tagsets(),
            [(Chunk.SHOW_CONTROL, '^G'), ((), 'bar')])
        self.assertEqual(
            Chunk([((), 'foo\007')]).show_control().tagsets(),
            [((), 'foo'), (Chunk.SHOW_CONTROL, '^G')])
        self.assertEqual(
            Chunk([((), 'foo\177bar')]).show_control().tagsets(),
            [((), 'foo'), (Chunk.SHOW_CONTROL, '^?'), ((), 'bar')])
