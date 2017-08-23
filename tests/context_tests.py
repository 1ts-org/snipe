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
Unit tests for context code
'''

import os
import logging
import sys
import unittest
import tempfile

sys.path.append('..')
sys.path.append('../lib')

import snipe.context as context  # noqa: E402,F401


class TestContext(unittest.TestCase):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            c = context.Context(home=tmp_path)
            self.assertIsNone(c.backends)
            self.assertEqual(c.home_directory, tmp_path)
            c.load()
            self.assertIsNotNone(c.backends)

            c.backend_spec = c.backend_spec + '; .smeerp'
            c.conf_write()

            self.assertTrue(
                os.path.exists(os.path.join(tmp_path, '.snipe', 'config')))

            d = context.Context(home=tmp_path)
            with self.assertLogs('Snipe', logging.ERROR):
                d.load()

            self.assertEqual(c.backend_spec, d.backend_spec)


if __name__ == '__main__':
    unittest.main()
