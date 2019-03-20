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

import mocks

import snipe.context as context
import snipe.messages as messages
import snipe.roost as roost


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

        self.assertEqual(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.data['recipient'] = '@QUUX'

        self.assertEqual(
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

        self.assertEqual(
            Decor.headline(msg).tagsets(), [
                ({'bold'}, '<personal)'),
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar [baz] <'),
                ({'bold'}, 'mock'),
                ((), '>'),
                ({'right'}, ' 00:00:00')])

        msg.outgoing = True

        self.assertEqual(
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

        self.assertEqual(
            Decor.headline(msg).tagsets(), [
                ((), '-c '),
                ({'bold'}, 'foo'),
                ((), ' -i bar <'),
                ({'bold'}, 'mock'),
                ((), '> The Great Quux'),
                ({'right'}, ' 00:00:00')])

        msg.backend.format_zsig = 'strip'

        self.assertEqual(
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

        self.assertEqual(Decor.format(msg), [])

        msg.body = '@[foo]'

        msg.backend.format_body = 'format'
        self.assertEqual(
            Decor.format(msg), [
                (set(), 'foo\n'),
                ])

        msg.backend.format_body = 'strip'
        self.assertEqual(
            Decor.format(msg), [
                (set(), 'foo\n'),
                ])


class TestRoostMessage(unittest.TestCase):
    def test(self):
        m = roost.RoostMessage(
            roost.Roost(context.Context()), {
                'message': 'foo',
                'receiveTime': 0.0,
                'sender': 'tim@ATHENA.MIT.EDU',
                'class': 'MESSAGE',
                'instance': 'white-magic',
                'recipient': '',
                'opcode': 'stark',
                'signature': 'Tim The Beaver',
                'time': 0.0,
                })
        os.environ['TZ'] = 'GMT'

        self.assertEqual(
            str(m),
            'Class: MESSAGE Instance: white-magic Recipient:  [stark]\n'
            'From: Tim The Beaver <roost; tim> at Thu Jan  1 00:00:00 1970\n'
            'foo\n\n')
        self.assertEqual(
            repr(m),
            '<RoostMessage 0.0 <RoostPrincipal roost tim@ATHENA.MIT.EDU>'
            ' 3 chars>')

        self.assertEqual(
            m.canon('sender', 'foo@X' + m.backend.realm),
            'foo@X' + m.backend.realm)
        self.assertEqual(
            m.canon('sender', 'foo@' + m.backend.realm),
            'foo')

        self.assertEqual(m.canon('class', 'foo'), 'foo')
        self.assertEqual(m.canon('class', 'ununfoo.d.d'), 'foo')
        self.assertEqual(m.canon('class', 'ｆｏｏ'), 'foo')
        self.assertEqual(m.canon('class', 'ｕｎｆｏｏ'), 'foo')

        self.assertEqual(m.canon('instance', 'foo'), 'foo')
        self.assertEqual(m.canon('instance', 'ｆｏｏ'), 'foo')

        self.assertEqual(m.canon('opcode', 'foo'), 'foo')
        self.assertEqual(m.canon('opcode', ' foo'), 'foo')
        self.assertEqual(m.canon('opcode', 'ｆｏｏ'), 'ｆｏｏ')

        self.assertEqual(m.reply(), 'roost; tim')

        m.data['recipient'] = 'foo'

        self.assertEqual(m.reply(), 'roost; -i white-magic tim')

        m.data['class'] = 'white-magic'

        self.assertEqual(m.reply(), 'roost; -c white-magic -i white-magic tim')

        m.outgoing = True

        self.assertEqual(m.reply(), 'roost; -c white-magic -i white-magic foo')

        m.transformed = 'rot13'

        self.assertEqual(
            m.reply(), 'roost; -R -c white-magic -i white-magic foo')

        self.assertEqual(
            m.followup(), 'roost; -R -c white-magic -i white-magic foo')

        m.body = 'CC: foo bar baz\nquux'

        self.assertEqual(
            m.followup(),
            'roost; -R -c white-magic -i white-magic -C bar baz foo tim')

        m.transformed = 'zcrypt'
        m.data['recipient'] = ''

        self.assertEqual(
            m.followup(), 'roost; -x -c white-magic -i white-magic')

        m.data['recipient'] = '@FOO'

        self.assertEqual(
            m.followup(), 'roost; -x -c white-magic -i white-magic @FOO')

        self.assertEqual(
            str(m.filter(0)), 'backend == "roost" and class = "white-magic"')
        self.assertEqual(
            str(m.filter(1)),
            'backend == "roost" and class = "white-magic"'
            ' and instance = "white-magic"')
        self.assertEqual(
            str(m.filter(2)),
            'backend == "roost" and class = "white-magic"'
            ' and instance = "white-magic" and sender = "roost; tim"')

        m.data['recipient'] = 'foo'
        m.personal = True

        self.assertEqual(
            str(m.filter(0)),
            'backend == "roost" and personal'
            ' and (sender = "roost; tim" or recipient = "tim")')

        m.backend.r.principal = str(m._sender)
        self.assertEqual(
            str(m.filter(0)),
            'backend == "roost" and personal'
            ' and (sender = "roost; foo" or recipient = "foo")')


class TestRoostAddresses(unittest.TestCase):
    def test(self):
        r = roost.Roost(context.Context())
        p = roost.RoostPrincipal(r, 'foo@X' + r.realm)
        self.assertEqual(str(p), 'roost; foo@X' + r.realm)
        p = roost.RoostPrincipal(r, 'foo@' + r.realm)
        self.assertEqual(str(p), 'roost; foo')


class TestRoostRegistrationMessage(unittest.TestCase):
    def test(self):
        f = MockPromise()
        m = roost.RoostRegistrationMessage(
            roost.Roost(context.Context()), 'foo', f)
        self.assertFalse(f.set)
        m.forward_the_future()
        self.assertTrue(f.set)


class MockPromise:
    def __init__(self):
        self.set = False

    def is_done(self):
        return False

    def set_result(self, result):
        self.set = True


if __name__ == '__main__':
    unittest.main()
