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
Unit tests for zulip backend
'''

import os
import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.messages as messages  # noqa: E402,F401
import snipe.zulip as zulip        # noqa: E402,F401


class TestZulipDecor(unittest.TestCase):
    def test_headline(self):
        Decor = zulip.ZulipMessage.Decor
        msg = mocks.Message(data={
            'timestamp': 0.0,
            'sender_email': 'baz',
            })
        msg._chat = 'foo'
        msg.sender = messages.SnipeAddress(mocks.Backend())
        os.environ['TZ'] = 'GMT'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '·foo>'),
                ((), ' <'),
                (('bold',), 'baz'),
                ((), '>'),
                (('right',), ' 00:00:00\n')
                ])

        msg.data['subject'] = 'zog'
        msg.data['sender_full_name'] = 'The Great Quux'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '·foo>'),
                ((), ' zog <'),
                (('bold',), 'baz'),
                ((), '> The Great Quux'),
                (('right',), ' 00:00:00\n')
                ])

    def test_format(self):
        Decor = zulip.ZulipMessage.Decor
        msg = mocks.Message(data={
            'content': 'bar'
            })

        self.assertEqual(
            Decor.format(msg), [
                ((), 'bar\n'),
                ])


if __name__ == '__main__':
    unittest.main()
