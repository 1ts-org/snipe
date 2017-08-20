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
Unit tests for irccloud backend
'''

import os
import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.irccloud as irccloud  # noqa: E402,F401
import snipe.messages as messages  # noqa: E402,F401


class TestIRCCloudDecor(unittest.TestCase):
    def test(self):
        Decor = irccloud.IRCCloudMessage.Decor
        msg = mocks.Message(data={
            'type': 'buffer_msg',
            })
        msg.time = 0.0
        msg.channel = '#foo'
        msg.body = 'bar'
        msg.sender = messages.SnipeAddress(mocks.Backend())
        os.environ['TZ'] = 'GMT'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                (('fill',), ': bar'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'error'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'bar'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'banned'
        msg.data['server'] = 'quux'
        msg.data['reason'] = 'because'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'quux: because'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'hidden_host_set'
        msg.data['hidden_host'] = 'thing'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'quux: thing bar'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'myinfo'
        msg.data['version'] = '0'
        msg.data['user_modes'] = 'user'
        msg.data['channel_modes'] = 'b'
        msg.data['rest'] = 'a'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'quux: 0, user modes: user, channel modes: ab'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'connecting_failed'
        msg.data['hostname'] = 'jupiter'
        msg.data['port'] = 1999
        msg.data['ssl'] = True
        msg.data['reason'] = 'doubtful'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'jupiter:1999 (ssl) connection failed: doubtful'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'quit_server'
        msg.data['nick'] = 'She'
        msg.data['msg'] = 'umami'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'jupiter:1999 (ssl) She quit: umami'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'you_nickchange'
        msg.data['newnick'] = 'red'
        msg.data['oldnick'] = 'blue'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'you are now red (née blue)'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'channel_topic'
        msg.data['from_name'] = 'some luser'
        msg.data['topic'] = 'something boring'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'some luser set topic to '),
                (('bold',), 'something boring'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'channel_timestamp'
        msg.data['timestamp'] = 0

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'created Thu Jan  1 00:00:00 1970'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'user_channel_mode'
        msg.data['ops'] = {
            'add': [{'mode': 'mode', 'param': 'param'}],
            'remove': [{'mode': 'mode', 'param': 'param'}],
            }

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'some luser set '),
                (('bold',), '+mode param -mode param'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'user_mode'
        msg.data['from'] = 'droid'
        msg.data['diff'] = '9000'
        msg.data['newmode'] = 'ants'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'droid set '),
                (('bold',), '9000'),
                ((), ' ('),
                (('bold',), 'ants'),
                ((), ') on you'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'channel_mode_is'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'mode '),
                (('bold',), '9000'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'channel_url'
        msg.data['url'] = 'file:///'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'url: '),
                (('bold',), 'file:///'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'channel_mode_list_change'
        msg.data['url'] = 'file:///'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'channel mode '),
                (('bold',), '9000'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'joined_channel'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), '+ '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'parted_channel'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), '- '),
                (('bold',), 'mock'),
                ((), ': bar'),
                (('right',), ' 00:00:00'),
                ])

        msg.data['type'] = 'nickchange'

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'blue'),
                ((), ' -> '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ])

        msg.data = {}

        self.assertEqual(
            Decor.headline(msg), [
                (('bold',), '#foo '),
                ((), 'mock [no type] eid - bid - cid -\n{}'),
                (('right',), ' 00:00:00'),
                ])


if __name__ == '__main__':
    unittest.main()
