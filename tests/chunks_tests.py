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

import unittest
import sys

sys.path.append('..')
sys.path.append('../lib')

from snipe.chunks import Chunk  # noqa: E402


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
        self.assertEqual(str(d), 'foobarbaz')

    def test_slice(self):
        l = Chunk([((), 'abc'), ((), 'def'), ((), 'ghi')])
        self.assertEqual(l.slice(0), (Chunk(), l))
        self.assertEqual(
            l.slice(1), (
                Chunk([((), 'a')]),
                Chunk([((), 'bc'), ((), 'def'), ((), 'ghi')])))
        self.assertEqual(
            l.slice(3), (
                Chunk([((), 'abc')]),
                Chunk([((), 'def'), ((), 'ghi')])))
        self.assertEqual(
            l.slice(4), (
                Chunk([((), 'abc'), ((), 'd')]),
                Chunk([((), 'ef'), ((), 'ghi')])))
        self.assertEqual(
            l.slice(6), (
                Chunk([((), 'abc'), ((), 'def')]),
                Chunk([((), 'ghi')])))
        self.assertEqual(
            l.slice(7), (
                Chunk([((), 'abc'), ((), 'def'), ((), 'g')]),
                Chunk([((), 'hi')])))
        self.assertEqual(l.slice(9), (l, Chunk()))
        self.assertEqual(
            Chunk([((), 'abc'), ((), ''), ((), 'def')]).slice(3), (
                Chunk([((), 'abc')]),
                Chunk([((), ''), ((), 'def')])))
        self.assertEqual(
            Chunk([((), ''), ((), 'abc'), ((), 'def')]).slice(3), (
                Chunk([((), ''), ((), 'abc')]),
                Chunk([((), 'def')])))
        self.assertEqual(
            Chunk([((), ''), ((), 'abc'), ((), 'def')]).slice(0), (
                Chunk(),
                Chunk([((), ''), ((), 'abc'), ((), 'def')])))
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
                ]).mark_re('abc', Chunk.tag_reverse)),
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
