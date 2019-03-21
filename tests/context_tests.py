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
import unittest
import unittest.mock
import tempfile

from unittest.mock import (patch, Mock)

import snipe.context as context
import snipe.imbroglio as imbroglio

import mocks


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

    def test_ensure_directory(self):
        HOME = '/afs/user/foo'
        DIR = os.path.join(HOME, '.snipe')
        c = context.Context(home=HOME)
        with patch('os.path.isdir') as isdir:
            isdir.return_value = True
            c.ensure_directory()  # doesn't raise
        with patch('os.path.isdir') as isdir, \
                patch('os.mkdir') as mkdir, \
                patch('os.chmod') as chmod, \
                patch('os.path.realpath') as realpath, \
                patch('subprocess.Popen') as Popen:
            isdir.return_value = False
            realpath.return_value = DIR
            pipe = Mock()
            pipe.returncode = 1
            pipe.communicate.return_value = ['foo']
            Popen.return_value = pipe
            with self.assertLogs() as log:
                c.ensure_directory()
            self.assertEqual(
                f'ERROR:Snipe:fs sa {DIR} system:anyuser none'
                ' system:authuser none (=1): foo',
                log.output[0])
            isdir.assert_called_with(DIR)
            mkdir.assert_called_with(DIR)
            chmod.assert_called_with(DIR, 0o700)

            pipe.returncode = 0
            with self.assertLogs(level='DEBUG') as log:
                c.ensure_directory()
            self.assertEqual(
                f'DEBUG:Snipe:fs sa {DIR} system:anyuser none'
                ' system:authuser none: foo',
                log.output[0])

    @imbroglio.test
    async def test_start(self):
        c = context.Context()
        ui = Mock()
        ui.get_erasechar.return_value = chr(8)
        c.backends = Mock()
        c.backends.start.return_value = mocks.promise(None)

        with patch('snipe.util.Configurable') as Configurable:
            await c.start(ui)
            self.assertIs(c.ui, ui)
            self.assertIs(ui.context, c)
            self.assertIs(c.erasechar, chr(8))
            Configurable.immanentize.assert_called()
            ui.initial.assert_called()
            c.backends.start.assert_called()


if __name__ == '__main__':
    unittest.main()
