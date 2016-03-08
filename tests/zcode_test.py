#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe Contributors
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
Unit tests for zephyr scribelike markup parsing
'''

import unittest
import sys

sys.path.append('..')

import snipe.zcode as zcode


class TestZcode(unittest.TestCase):
    def test_strip(self):
        self.assertEqual(
            zcode.strip('foo'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@bar{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@bar{foo@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip('@bar{foo@@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip('@{foo@}bar}baz'),
            'foo@bar}baz',
            )
        self.assertEqual(
            zcode.strip('foo@bar{baz@(bang})}'),
            'foobazbang}',
            )
        self.assertEqual(
            zcode.strip(''),
            '',
            )
        self.assertEqual(
            zcode.strip('foo@bar{baz}'),
            'foobaz',
            )
