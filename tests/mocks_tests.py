#!/usr/bin/python3
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
When your mocks get complex enough that you want to be sure of
_their_ behavior...
'''

import unittest

import mocks


class TestAggregator(unittest.TestCase):
    def test_walk(self):
        a = mocks.Aggregator()
        self.assertEqual(
            list(a.walk(None, True)),
            [a._messages[0]])  # explicit is better than implicit
        self.assertEqual(
            list(a.walk(float('Inf'), False)),
            [a._messages[0]])
        a._messages.append(mocks.Message())
        self.assertEqual(
            list(a.walk(None, True)),
            [a._messages[0], a._messages[1]])
        self.assertEqual(
            list(a.walk(float('Inf'), False)),
            [a._messages[1], a._messages[0]])
        a._messages.append(mocks.Message())
        self.assertEqual(
            list(a.walk(a._messages[1], True)),
            [a._messages[1], a._messages[2]])
        self.assertEqual(
            list(a.walk(a._messages[1], False)),
            [a._messages[1], a._messages[0]])


if __name__ == '__main__':
    unittest.main()
