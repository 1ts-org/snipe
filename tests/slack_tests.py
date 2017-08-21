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
Unit tests for slack backend
'''

import os
import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

from snipe.chunks import Chunk     # noqa: E402,F401
import snipe.messages as messages  # noqa: E402,F401
import snipe.slack as slack        # noqa: E402,F401


class TestSlackDecor(unittest.TestCase):
    def test(self):
        Decor = slack.SlackMessage.Decor
        msg = mocks.Message(data={
            'type': 'message',
            'subtype': 'me_message',
            'edited': '?',
            'is_starred': True,
            'pinned_to': True,
            'text': 'baz',
            })
        msg.time = 0.0
        msg.channel = '#foo'
        msg.body = 'bar'
        msg.sender = messages.SnipeAddress(mocks.Backend())
        os.environ['TZ'] = 'GMT'
        msg.slackmarkup = lambda text, tags: [(tags, text)]

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), '~'),
                ((), '*'),
                ((), '+'),
                (('bold',), 'mock'),
                ((), ' '),
                ((), 'baz'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['is_starred'] = False
        msg.data['pinned_to'] = False
        del msg.data['edited']
        msg.data['subtype'] = ''

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                ((), ': '),
                ((), 'baz'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['file'] = {'url': 'file:///'}

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                ((), ': '),
                ((), 'baz'),
                ((), '\nfile:///'),
                (('right',), ' 00:00:00'),
                ]))

        del msg.data['file']

        msg.data['reactions'] = [{'name': 'over', 'count': 9000}]

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                ((), ': '),
                ((), 'baz'),
                ((), '\n:over: 9000'),
                (('right',), ' 00:00:00'),
                ]))

        del msg.data['reactions']
        msg.data['attachments'] = [
            {
                'color': 'danger',
                'title_link': 'file:///',
                'text': 'things',
                'fields': [{'title': 'key', 'value': 'value'}],
            }, {
                'color': 'f0f0f0',
                'text': 'stuff',
            }]

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                ((), ': '),
                ((), 'baz'),
                ((), '\n'),
                (('bg:red',), ' '),
                ((), ' '),
                ((), 'file:///'),
                ((), '\n'),
                (('bg:red',), ' '),
                ((), ' '),
                ((), 'things'),
                ((), '\n'),
                (('bg:red',), ' '),
                ((), ' '),
                (('bold',), 'key'),
                ((), '\n'),
                (('bg:red',), ' '),
                ((), ' '),
                ((), 'value'),
                ((), '\n'),
                (('bg:#f0f0f0',), ' '),
                ((), ' '),
                ((), 'stuff'),
                (('right',), ' 00:00:00'),
                ]))

        del msg.data['attachments']

        msg.data['type'] = 'presence_change'
        msg.data['presence'] = 'active'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), '+ '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['presence'] = 'passive'  # ?

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), '- '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = None

        self.assertEqual(
            Decor.headline(msg, {'fg:white', 'bg:blue'}), [
                    ({'fg:white', 'bg:blue', 'bold'}, 'followup'),
                    ({'fg:white', 'bg:blue'}, ' : '),
                    ({'fg:white', 'bg:blue', 'bold'}, 'mock'),
                    ({'fg:white', 'bg:blue', 'right'}, ' 00:00:00'),
                    ({'fg:white', 'bg:blue'}, 'bar\n')
                ])


if __name__ == '__main__':
    unittest.main()
