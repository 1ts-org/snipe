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
Unit tests for help system
'''

import unittest
import sys

sys.path.append('..')
sys.path.append('../lib')

import snipe.help as help  # noqa: E402,F401


class TestHelp(unittest.TestCase):
    def test_follow_link(self):
        w = help.HelpBrowser(None)

        called = []

        w.load = lambda link: called.append(link)
        w.links = [(10, 10, 'one'), (30, 10, 'two')]

        w.cursor = 5
        w.follow_link()
        self.assertFalse(called)
        w.cursor = 25
        w.follow_link()
        self.assertFalse(called)
        w.cusor = 45
        w.follow_link()
        self.assertFalse(called)
        w.cursor = 10
        w.follow_link()
        self.assertEqual(called[-1], 'one')
        w.cursor = 35
        w.follow_link()
        self.assertEqual(called[-1], 'two')
        w.cursor = 20
        w.follow_link()
        self.assertEqual(called[-1], 'one')


if __name__ == '__main__':
    unittest.main()
