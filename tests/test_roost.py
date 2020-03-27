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

import io
import os
import unittest

from unittest.mock import (patch, Mock)

import mocks

import snipe.context as context
import snipe.imbroglio as imbroglio
import snipe.messages as messages
import snipe.roost as roost


class TestRoost(unittest.TestCase):
    @imbroglio.test
    async def test_error_message(self):
        r = roost.Roost(mocks.Context())

        async def raises():
            raise Exception('foo')

        r.add_message = Mock()
        await r.error_message('activity', raises)
        m = r.add_message.call_args[0][0]
        self.assertEqual('activity: foo', m.body.splitlines()[0])

    @imbroglio.test
    async def test_send(self):
        r = roost.Roost(mocks.Context())

        r.r.send = Mock(return_value=mocks.promise())
        await r.send('-c class -i instance -s sig -O opcode', 'body')

        self.assertEqual(
            r.r.send.call_args[0][0],
            {
                'class': 'class',
                'instance': 'instance',
                'recipient': '',
                'opcode': 'opcode',
                'signature': 'sig',
                'message': 'body',
            })

        r.r.send = Mock(return_value=mocks.promise())
        await r.send('-c class -R -s sig recipient', 'body')

        self.assertEqual(
            r.r.send.call_args[0][0],
            {
                'class': 'class',
                'instance': 'PERSONAL',
                'recipient': 'recipient',
                'opcode': '',
                'signature': 'sig',
                'message': 'obql',
            })

        r.r.send = Mock(return_value=mocks.promise())
        with self.assertRaises(RuntimeError):
            await r.send('-c class -s sig -C r1 r2', 'body')

        self.assertEqual(
            r.r.send.call_args[0][0],
            {
                'class': 'class',
                'instance': 'PERSONAL',
                'recipient': 'r2',
                'opcode': '',
                'signature': 'sig',
                'message': 'CC: r1 r2\nbody',
            })

        with patch(
                'snipe.imbroglio.process_filter',
                return_value=mocks.promise((0, 'foo'))):
            r.r.send = Mock(return_value=mocks.promise())
            await r.send('-c class -x -s sig recipient', 'body')

            self.assertEqual(
                {
                    'class': 'class',
                    'instance': 'PERSONAL',
                    'recipient': 'recipient',
                    'opcode': 'crypt',
                    'signature': 'sig',
                    'message': 'foo',
                }, r.r.send.call_args[0][0])

        with patch(
                'snipe.imbroglio.process_filter',
                return_value=mocks.promise((1, 'foo'))), \
                self.assertRaises(Exception):
            r.r.send = Mock(return_value=mocks.promise())
            await r.send('-c class -x -s sig recipient', 'body')

    @imbroglio.test
    async def test_new_message(self):
        r = roost.Roost(mocks.Context())

        o = object()
        r.construct_and_maybe_decrypt = Mock(return_value=mocks.promise(o))
        r.add_message = Mock()

        await r.new_message({})
        r.construct_and_maybe_decrypt.assert_called_with({})
        r.add_message.assert_called_with(o)

    def test_add_message(self):
        r = roost.Roost(mocks.Context())

        r.drop_cache = Mock()
        r.redisplay = Mock()

        m = messages.SnipeMessage(r, 'foo', 1.0)
        r.add_message(m)

        r.drop_cache.assert_called()
        r.redisplay.assert_called_with(m, m)

        m = messages.SnipeMessage(r, 'bar', 1.0)
        r.add_message(m)

        self.assertEqual(2, len(r.messages))
        self.assertEqual(1.00001, r.messages[-1].time)

    @imbroglio.test
    async def test_construct_and_maybe_decrypt(self):
        r = roost.Roost(mocks.Context())

        self.assertEqual(0, len(r._destinations))
        self.assertEqual(0, len(r._senders))

        m = await r.construct_and_maybe_decrypt({
                'message': 'body',
                'receiveTime': 0.0,
                'sender': 'sender',
                'class': 'class',
                'instance': 'instance',
                'recipient': '',
                'opcode': '',
                'signature': 'sig',
                'time': 0.0,
                })

        self.assertEqual('body', m.body)
        self.assertEqual(2, len(r._destinations))
        self.assertEqual(1, len(r._senders))

        with patch(
                'snipe.imbroglio.process_filter',
                return_value=mocks.promise((0, 'foo\n**END**\n'))):
            m = await r.construct_and_maybe_decrypt({
                    'message': 'body',
                    'receiveTime': 0.0,
                    'sender': 'sender',
                    'class': 'class',
                    'instance': 'instance',
                    'recipient': '',
                    'opcode': 'crypt',
                    'signature': 'sig',
                    'time': 0.0,
                    })
            self.assertEqual('zcrypt', m.transformed)
            self.assertEqual('foo\n', m.body)

        with patch(
                'snipe.imbroglio.process_filter',
                return_value=mocks.promise((1, 'foo\n**END**\n'))), \
                self.assertLogs() as l:
            m = await r.construct_and_maybe_decrypt({
                    'message': 'body',
                    'receiveTime': 0.0,
                    'sender': 'sender',
                    'class': 'class',
                    'instance': 'instance',
                    'recipient': '',
                    'opcode': 'crypt',
                    'signature': 'sig',
                    'time': 0.0,
                    })
        (m,) = l.output
        self.assertRegex(
            m,
            r'ERROR:Roost.[0-9a-f]+:roost: zcrypt -D -c class returned 1')

        with patch(
                'snipe.imbroglio.process_filter',
                return_value=mocks.promise(exception=Exception)), \
                self.assertLogs() as l:
            m = await r.construct_and_maybe_decrypt({
                    'message': 'body',
                    'receiveTime': 0.0,
                    'sender': 'sender',
                    'class': 'class',
                    'instance': 'instance',
                    'recipient': '',
                    'opcode': 'crypt',
                    'signature': 'sig',
                    'time': 0.0,
                    })
        (m,) = l.output
        m = m.splitlines()[0]
        self.assertRegex(
            m,
            'ERROR:Roost.[0-9a-f]+:zcrypt, decrypting')

    @imbroglio.test
    async def test_dump_subscriptions(self):
        r = roost.Roost(mocks.Context())

        r.r.subscriptions = Mock(return_value=mocks.promise([{
            'class': 'class',
            'instance': 'instance',
            'recipient': '',
            }]))
        w = Mock()

        await r.dump_subscriptions(w)
        w.show.assert_called_with('class instance *')

    def test_spec_to_triplets(self):
        self.assertEqual(
            [('class', 'instance', 'recipient@REALM')],
            roost.Roost.spec_to_triplets(
                '-c class -i instance -r REALM recipient'))

        # at this remoe, not sure what this is for
        self.assertEqual(
            [('c1', '*', ''), ('c2', '*', '')],
            roost.Roost.spec_to_triplets(
                'c1 c2'))

    @imbroglio.test
    async def test_load_subs(self):
        r = roost.Roost(mocks.Context())

        r.r.subscribe = Mock(return_value=mocks.promise())

        with patch('os.path.exists', return_value=False), \
                patch('snipe.roost.open', return_value=io.StringIO(
                    'class,instance,*\n')) as o:
            await r.load_subs('foo')
            o.assert_not_called()

        with patch('os.path.exists', return_value=True), \
                patch('snipe.roost.open', return_value=io.StringIO(
                    'class,instance,@ATHENA.MIT.EDU\n')):
            await r.load_subs('foo')
        r.r.subscribe.assert_called_with([['class', 'instance', '*']])

    def test_do_subunify(self):
        self.assertEqual([
            ('a', 'b', ''),
            ('a.d', 'b', ''),
            ('a.d.d', 'b', ''),
            ('a.d.d.d', 'b', ''),
            ('una', 'b', ''),
            ('una.d', 'b', ''),
            ('una.d.d', 'b', ''),
            ('una.d.d.d', 'b', ''),
            ('ununa', 'b', ''),
            ('ununa.d', 'b', ''),
            ('ununa.d.d', 'b', ''),
            ('ununa.d.d.d', 'b', ''),
            ('unununa', 'b', ''),
            ('unununa.d', 'b', ''),
            ('unununa.d.d', 'b', ''),
            ('unununa.d.d.d', 'b', ''),
            ], roost.Roost.do_subunify([('a', 'b', '')]))

    @imbroglio.test
    async def test_subscribe(self):
        r = roost.Roost(mocks.Context())
        r.subunify = True

        w = Mock()
        w.read_string.return_value = mocks.promise('a')

        r.r.subscribe = Mock(return_value=mocks.promise())

        await r.subscribe(w)

        r.r.subscribe.assert_called_with([
            ('a', '*', ''),
            ('a.d', '*', ''),
            ('a.d.d', '*', ''),
            ('a.d.d.d', '*', ''),
            ('una', '*', ''),
            ('una.d', '*', ''),
            ('una.d.d', '*', ''),
            ('una.d.d.d', '*', ''),
            ('ununa', '*', ''),
            ('ununa.d', '*', ''),
            ('ununa.d.d', '*', ''),
            ('ununa.d.d.d', '*', ''),
            ('unununa', '*', ''),
            ('unununa.d', '*', ''),
            ('unununa.d.d', '*', ''),
            ('unununa.d.d.d', '*', ''),
            ])

    @imbroglio.test
    async def test_subscribe_fie(self):
        r = roost.Roost(mocks.Context())

        w = Mock()
        w.read_filename.return_value = mocks.promise('filename')

        r.load_subs = Mock(return_value=mocks.promise())

        with patch('os.path.exists', return_value=False):
            await r.subscribe_file(w)

        r.load_subs.assert_called_with('filename')

    @imbroglio.test
    async def test_unsubscribe(self):
        r = roost.Roost(mocks.Context())
        r.subunify = True

        w = Mock()
        w.read_string.return_value = mocks.promise('a')

        r.r.unsubscribe = Mock(return_value=mocks.promise())

        await r.unsubscribe(w)

        r.r.unsubscribe.assert_called_with([
            ('a', '*', ''),
            ('a.d', '*', ''),
            ('a.d.d', '*', ''),
            ('a.d.d.d', '*', ''),
            ('una', '*', ''),
            ('una.d', '*', ''),
            ('una.d.d', '*', ''),
            ('una.d.d.d', '*', ''),
            ('ununa', '*', ''),
            ('ununa.d', '*', ''),
            ('ununa.d.d', '*', ''),
            ('ununa.d.d.d', '*', ''),
            ('unununa', '*', ''),
            ('unununa.d', '*', ''),
            ('unununa.d.d', '*', ''),
            ('unununa.d.d.d', '*', ''),
            ])

    @imbroglio.test
    async def test_reconnect(self):
        r = roost.Roost(mocks.Context())

        r.new_task = Mock()
        r.new_task.is_done.return_value = False

        r.disconnect = Mock(return_value=mocks.promise())
        r.start = Mock(return_value=mocks.promise())

        await r.reconnect()

        r.disconnect.assert_called()
        r.start.assert_called()

    @imbroglio.test
    async def test_disconnect(self):
        cancelled = False

        class Tusk:
            def cancel(self):
                nonlocal cancelled
                cancelled = True

            def __await__(self):
                yield ('sleep',)

        r = roost.Roost(mocks.Context())
        r.new_task = Tusk()
        r.tasks.append(r.new_task)
        await r.disconnect()
        self.assertTrue(cancelled)


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
        self.done = False

    def set_result(self, result):
        self.set = True


if __name__ == '__main__':
    unittest.main()
