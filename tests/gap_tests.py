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
Unit tests for the Gapbuffer object
'''

import sys
import unittest
import array
import random

sys.path.append('..')
import snipe.gap


class TestGapBuffer(unittest.TestCase):
    def testGapBufferSimple(self):
        g = snipe.gap.GapBuffer()
        g.replace(0, 0, 'flam')
        g.replace(0, 0, 'flim')
        self.assertEqual(g.text, 'flimflam')
        g.replace(8, 0, 'blam')
        self.assertEqual(g.text, 'flimflamblam')

    def testGapBufferExpansion(self):
        g = snipe.gap.GapBuffer(chunksize=1)
        g.replace(0, 0, 'flam')
        g.replace(0, 0, 'flim')
        self.assertEqual(g.text, 'flimflam')
        g.replace(8, 0, 'blam')
        self.assertEqual(g.text, 'flimflamblam')

    def testGapBufferMore(self):
        g = snipe.gap.GapBuffer()
        g.replace(0, 0, 'bar')
        self.assertEqual(g.text, 'bar')
        self.assertEqual(g.size, 3)
        m = g.mark(1)
        self.assertEqual(m.point, 1)
        g.replace(0, 0, 'foo')
        self.assertEqual(g.text, 'foobar')
        self.assertEqual(m.point, 4)
        g.replace(6, 0, 'baz')
        self.assertEqual(g.text, 'foobarbaz')
        self.assertEqual(m.point, 4)
        g.replace(6, 0, 'quux')
        self.assertEqual(g.text, 'foobarquuxbaz')
        self.assertEqual(m.point, 4)
        g.replace(3, 0, 'Q'*8192)
        self.assertEqual(g.text, 'foo' + 'Q'*8192 + 'barquuxbaz')
        self.assertEqual(m.point, 8196)
        g.replace(3, 8192, '')
        self.assertEqual(g.text, 'foobarquuxbaz')
        self.assertEqual(g.size, 13)
        self.assertEqual(m.point, 4)
        g.replace(3, 3, 'honk')
        self.assertEqual(g.text, 'foohonkquuxbaz')
        self.assertEqual(m.point, 7)
        g.replace(4, 1, 'u')
        self.assertEqual(g.text[4], 'u')
        g.replace(4, 1, '')
        self.assertEqual(g.text, 'foohnkquuxbaz')
        g.replace(3, 3, '')
        self.assertEqual(g.text, 'fooquuxbaz')

    def testfuzz(
        self,
        iterations=10000,
        max_len=74,
        max_op_len=10,
        show_delay=0.01,
        ):
        """
        For many <iterations> randomly either insert or delete up to
        <max_op_len> chars or just move the gap around.

        Make sure the entire thing is never more than max_len chars long.

        Make a parallel array and confirm after each operation that
        the gap buffer's contents are the same as the array's.

        If show_delay is > 0, then the gap buffer will be shown each
        iteration.  If it's 0 then nothign will display during
        iteration, but the operations will be dumped after all
        iterations.
        """

        contents = (
            u'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

        g = snipe.gap.GapBuffer()
        a = array.array('u')
        for n in range(iterations):
            pos = g.size and random.randint(0, g.size-1)
            # A 1 in 3 chance to delete, unless we're at max length,
            # then delete regardless
            if not random.randint(0, 2) or g.size >= max_len:
                howmany = min(g.size - pos, random.randint(1, max_op_len))
                g.replace(pos, howmany, '')
                for d in range(howmany):
                    a.pop(pos)
            else:
                # A 1 in 2 chance to insert instead of just moving th gap
                if not random.randint(0, 1):
                    howmany = random.randint(
                        1, max(max_op_len, max_len - g.size))
                    char = random.choice(contents)
                    g.replace(pos, 0, char * howmany)
                    for i in range(howmany):
                        a.insert(pos, char)
            self.assertEqual(a.tounicode(), g.text)
            print (g.text)

    def test_mark(self):
        g = snipe.gap.GapBuffer()
        g.replace(0, 0, 'ac')
        m = g.mark(1)
        m2 = g.mark(1, right=True)
        n = g.mark(2)
        g.replace(1, 0, 'b')
        self.assertEqual(m.point, 1)
        self.assertEqual(m2.point, 2)
        self.assertEqual(n.point, 3)
        self.assertEqual(g.text, 'abc')


if __name__ == '__main__':
    unittest.main()
