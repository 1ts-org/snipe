# -*- encoding: utf-8 -*-
# Copyright © 2014 Karl Ramm
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

import sys
import unittest

sys.path.append('..')
import snipe.ttyfe


class TestTTYFE(unittest.TestCase):
    def testTTYRendererDoline(self):
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abc', 80, 80)),
            [('abc', 77)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline("\tabc", 80, 0)),
            [('        abc', 69)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abc\n', 80, 80)),
            [('abc', -1)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('a\01bc', 80, 80)),
            [('abc', 77)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abcdef', 3, 3)),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('ab\tdef', 3, 3)),
            [('ab', 0), ('def', 0)])


if __name__ == '__main__':
    unittest.main()
