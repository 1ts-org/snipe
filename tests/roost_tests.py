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
Unit tests for roost backend
'''

import os
import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.messages as messages  # noqa: E402,F401
import snipe.roost as roost        # noqa: E402,F401


class TestRoostDecor(unittest.TestCase):
    def test_headline(self):
        Decor = roost.RoostMessage.Decor
        msg = mocks.Message(data={
            'class': 'foo',
            'instance': 'bar',
            'recipient': '',
            'opcode': 'baz',
            'time': 0.0,
            })
        msg.sender = messages.SnipeAddress(mocks.Backend())
        os.environ['TZ'] = 'GMT'

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.data['recipient'] = '@QUUX'

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar'),
                ({'bold'}, ' @QUUX'),
                ((), ' [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.data['recipient'] = 'someone'
        msg.personal = True

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ({'bold'}, '<personal)'),
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.outgoing = True

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ({'bold'}, '(personal> <>'),
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.data['opcode'] = ''
        msg.data['recipient'] = ''
        msg.personal = False
        msg.outgoing = False

        msg.data['signature'] = '@{The Great Quux}'

        msg.backend.format_zsig = 'format'

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar <'),
                ({'bold'}, 'mock'),
                ((), '> The Great Quux'),
                ({'right'}, ' 00:00:00')])

        msg.backend.format_zsig = 'strip'

        self.assertEquals(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar <'),
                ({'bold'}, 'mock'),
                ((), '> The Great Quux'),
                ({'right'}, ' 00:00:00')])

    def test_format(self):
        Decor = roost.RoostMessage.Decor
        msg = mocks.Message()

        self.assertEquals(Decor.format(msg), [])

        msg.body = '@[foo]'

        msg.backend.format_body = 'format'
        self.assertEquals(
            Decor.format(msg), [
                (set(), 'foo\n'),
                ])

        msg.backend.format_body = 'strip'
        self.assertEquals(
            Decor.format(msg), [
                (set(), 'foo\n'),
                ])


if __name__ == '__main__':
    unittest.main()
