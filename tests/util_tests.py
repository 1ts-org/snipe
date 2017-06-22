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
Unit tests for stuff in utils.py
'''


import os
import random
import sys
import tempfile
import unittest

sys.path.append('..')
sys.path.append('../lib')

import snipe.util  # noqa: E402


class TestSafeWrite(unittest.TestCase):
    def testSimple(self):

        with tempfile.TemporaryDirectory() as directory:
            pathname = os.path.join(directory, 'file')

            string = hex(random.randrange(2**64)) + '\n'

            with snipe.util.safe_write(pathname) as fp:
                fp.write(string)

            with open(pathname) as fp:
                self.assertEqual(fp.read(), string)


class TestChunkslice(unittest.TestCase):
    def testChunkslice(self):
        l = [((), 'abc'), ((), 'def'), ((), 'ghi')]
        self.assertEqual(
            snipe.util.chunkslice(l, 0),
            ([], l))
        self.assertEqual(
            snipe.util.chunkslice(l, 1),
            ([((), 'a')], [((), 'bc'), ((), 'def'), ((), 'ghi')]))
        self.assertEqual(
            snipe.util.chunkslice(l, 3),
            ([((), 'abc')], [((), 'def'), ((), 'ghi')]))
        self.assertEqual(
            snipe.util.chunkslice(l, 4),
            ([((), 'abc'), ((), 'd')], [((), 'ef'), ((), 'ghi')]))
        self.assertEqual(
            snipe.util.chunkslice(l, 6),
            ([((), 'abc'), ((), 'def')], [((), 'ghi')]))
        self.assertEqual(
            snipe.util.chunkslice(l, 7),
            ([((), 'abc'), ((), 'def'), ((), 'g')], [((), 'hi')]))
        self.assertEqual(
            snipe.util.chunkslice(l, 9),
            (l, []))
        self.assertEqual(
            snipe.util.chunkslice([((), 'abc'), ((), ''), ((), 'def')], 3),
            ([((), 'abc')], [((), ''), ((), 'def')]))
        self.assertEqual(
            snipe.util.chunkslice([((), ''), ((), 'abc'), ((), 'def')], 3),
            ([((), ''), ((), 'abc')], [((), 'def')]))
        self.assertEqual(
            snipe.util.chunkslice([((), ''), ((), 'abc'), ((), 'def')], 0),
            ([], [((), ''), ((), 'abc'), ((), 'def')]))


class TestChunkMarkRe(unittest.TestCase):
    def test_chunk_mark_re(self):
        self.assertEqual(
            snipe.util.chunk_mark_re([
                ((), 'xxx'),
                ((), 'abc'),
                ((), 'xxxab'),
                ((), ''),
                ((), 'cxxx'),
                ((), 'abcxxx'),
                ((), 'xxxabc'),
                ],
                'abc',
                snipe.util.mark_reverse,
            ), [
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
            ])


if __name__ == '__main__':
    unittest.main()
