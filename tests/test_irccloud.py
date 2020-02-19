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

from unittest.mock import (patch, Mock)

import mocks

import snipe.context as context
import snipe.imbroglio as imbroglio
import snipe.irccloud as irccloud
import snipe.messages as messages
import snipe.util as util

from snipe.chunks import (Chunk)


class TestIRCCloud(unittest.TestCase):
    def test___init__(self):
        i = irccloud.IRCCloud(None)
        self.assertEqual(i.reqid + 1, i.reqid)

    @imbroglio.test
    async def test_say(self):
        i = irccloud.IRCCloud(None)
        i.websocket = Mock()
        i.websocket.write.return_value = mocks.promise()
        x = i.reqid
        await i.say('x', 'y', 'z')
        i.websocket.write.assert_called_with({
            '_method': 'say',
            '_reqid': x + 1,
            'cid': 'x',
            'to': 'y',
            'msg': 'z',
            })

    @imbroglio.test
    async def test_process_message(self):
        i = irccloud.IRCCloud(None)
        l = []
        self.assertIsNone(await i.process_message(l, None))

        i.last_eid = -1
        i.buffers[1] = {}

        for mtype in (
                'idle', 'banned', 'socket_closed', 'num_invites',
                'stat_user', 'backlog_starts', 'end_of_backlog',
                'you_joined_channel', 'self_details',
                'your_unique_id', 'cap_ls', 'cap_req', 'cap_ack',
                'user_account', 'heartbeat_echo',
                ):
            ml = []
            self.assertIsNone(await i.process_message(ml, {
                'type': mtype,
                'eid': 0,
                }))
            self.assertFalse(ml)

        d = {}
        self.assertIsNone(await i.process_message([], {
            'type': 'header',
            'eid': 0,
            'header': d,
            }))
        self.assertIs(d, i.header.get('header'))

        i.include = Mock(return_value=mocks.promise())
        self.assertIsNone(await i.process_message([], {
            'type': 'oob_include',
            'eid': 0,
            'url': 'http://foo/',
            }))
        i.include.assert_called_with('http://foo/')
        self.assertIsNone(i.message_set)

        self.assertIsNone(await i.process_message([], {
            'type': 'oob_skipped',
            'eid': 0,
            }))
        self.assertEqual(set(), i.message_set)

        self.assertIsNone(await i.process_message([], {
            'type': 'backlog_complete',
            'eid': 0,
            }))
        self.assertIsNone(i.message_set)

        self.assertIsNone(await i.process_message([], {
            'type': 'makeserver',
            'eid': 0,
            'cid': 0,
            'foo': 'bar',
            }))
        self.assertEqual('bar', i.connections[0]['foo'])

        self.assertIsNone(await i.process_message([], {
            'type': 'status_changed',
            'eid': 0,
            'cid': 0,
            'new_status': 'foo',
            'fail_info': 'bar',
            }))
        self.assertEqual('foo', i.connections[0]['status'])
        self.assertEqual('bar', i.connections[0]['fail_info'])

        self.assertIsNone(await i.process_message([], {
            'type': 'isupport_params',
            'eid': 0,
            'cid': 0,
            'foo': 'bar',
            }))
        self.assertEqual('bar', i.servers[0]['foo'])

        self.assertIsNone(await i.process_message([], {
            'type': 'makebuffer',
            'eid': 0,
            'bid': 0,
            'foo': 'bar',
            }))
        self.assertEqual('bar', i.buffers[0]['foo'])

        self.assertIsNone(await i.process_message([], {
            'type': 'channel_init',
            'eid': 0,
            'bid': 0,
            'foo': 'bar',
            }))
        self.assertEqual('bar', i.channels[0]['foo'])

        self.assertIsNotNone(await i.process_message(l, {
            'type': 'buffer_msg',
            'bid': 1,
            'cid': 2,
            'eid': 2,
            'from': 'user',
            'msg': 'message body',
            }))

        i.since_id = 2
        self.assertIsNone(await i.process_message(l, {
            'type': 'buffer_msg',
            'bid': 1,
            'cid': 2,
            'eid': 1,
            'from': 'user',
            'msg': 'message body',
            }))

        i.message_set = set(float(m) for m in l)
        self.assertIsNone(await i.process_message(l, {
            'type': 'buffer_msg',
            'bid': 1,
            'cid': 2,
            'eid': 2,
            'from': 'user',
            'msg': 'message body',
            }))

        i.since_id = 0
        self.assertIsNotNone(await i.process_message(l, {
            'type': 'buffer_msg',
            'bid': 1,
            'cid': 2,
            'eid': 1,
            'from': 'user',
            'msg': 'message body',
            }))
        self.assertEqual(2, len(l))
        self.assertEqual(1, l[0].data['eid'])
        self.assertEqual(2, l[1].data['eid'])

    @imbroglio.test
    async def test_incoming(self):
        i = irccloud.IRCCloud(None)

        # this seems to cause a RunTimeError to the effect that the
        # mock is never awaited, except coverage says that the
        # exception is definitely propagated appropriately
        i.process_message = Mock(
            return_value=mocks.promise(exception=KeyError))
        with self.assertLogs():
            await i.incoming({})

        o = object()
        i.process_message = Mock(return_value=mocks.promise(o))
        i.drop_cache = Mock()
        i.redisplay = Mock()
        await i.incoming(o)
        i.process_message.assert_called_with([], o)
        i.drop_cache.assert_called()
        i.redisplay.assert_called_with(o, o)

    @imbroglio.test
    async def test_include(self):
        i = irccloud.IRCCloud(None)
        i.context = Mock()
        i.context.ui = Mock()
        i.context.ui.redisplay = Mock()
        i._get = Mock(return_value=mocks.promise({
            'success': False,
            'message': 'ouch',
            }))
        with self.assertLogs():
            await i.include('http://foo/')
        i._get.assert_called_with('http://foo/')

        i._get = Mock(return_value=mocks.promise([{
            'type': 'buffer_msg',
            'cid': 2,
            'eid': 2,
            'from': 'user',
            'msg': 'message body',
            }]))
        i.drop_cache = Mock()
        i.redisplay = Mock()

        await i.include('http://foo/')

        self.assertEqual(1, len(i.messages))
        i.drop_cache.assert_called()
        i.redisplay.assert_called_with(i.messages[0], i.messages[0])

    @imbroglio.test
    async def test_send(self):
        i = irccloud.IRCCloud(None)
        with self.assertRaises(util.SnipeException) as ar:
            await i.send('', '')
        self.assertEqual('nowhere to send the message', str(ar.exception))

        with self.assertRaises(util.SnipeException) as ar:
            await i.send('host nick', '')
        self.assertEqual('unknown server name host', str(ar.exception))

        i.connections = {
            0: {
                'hostname': 'host.domain0',
                'cid': 0,
                },
            1: {
                'hostname': 'host.domain1',
                'cid': 1,
                },
            }

        with self.assertRaises(util.SnipeException) as ar:
            await i.send('host nick', '')
        self.assertEqual(
            "ambiguous server name host matches "
            "('host.domain0', 'host.domain1')",
            str(ar.exception))

        i.connections = {
            0: {
                'hostname': 'host.domain',
                'cid': 0,
                },
            }

        i.say = Mock(return_value=mocks.promise())
        await i.send('host nick', 'body')
        i.say.assert_called_with(0, '*', '/msg nick body')

        i.say = Mock(return_value=mocks.promise())
        await i.send('host', 'body')
        i.say.assert_called_with(0, '*', '/msg * body')

        i.say = Mock(return_value=mocks.promise())
        with self.assertRaises(RuntimeError):
            await i.send('host nick', 'body\nbody')

    def test_dumps(self):
        i = irccloud.IRCCloud(None)

        w = Mock()
        i.dump_connections(w)
        w.show.assert_called_with('{}')

        w = Mock()
        i.dump_channels(w)
        w.show.assert_called_with('{}')

        w = Mock()
        i.dump_buffers(w)
        w.show.assert_called_with('{}')

        w = Mock()
        i.dump_servers(w)
        w.show.assert_called_with('{}')

        w = Mock()
        i.dump_header(w)
        w.show.assert_called_with('{}')

    @imbroglio.test
    async def test_disconnect(self):
        i = irccloud.IRCCloud(None)

        i.reap_tasks = Mock()
        i.shutdown = Mock()
        await i.disconnect()
        i.reap_tasks.assert_called()
        i.shutdown.assert_not_called()

        i.reap_tasks = Mock()
        i.shutdown = Mock(return_value=mocks.promise())
        i.new_task = True
        await i.disconnect()
        i.reap_tasks.assert_called()
        i.shutdown.assert_called()
        self.assertIsNone(i.new_task)

    @imbroglio.test
    async def test_reconnect(self):
        i = irccloud.IRCCloud(None)
        i.disconnect = Mock(return_value=mocks.promise())
        i.new_task = True
        i.start = Mock(return_value=mocks.promise())

        await i.reconnect()
        i.disconnect.assert_called()
        i.start.assert_called()


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
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                (('bold',), 'mock'),
                ((), ': bar'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'error'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'bar'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'banned'
        msg.data['server'] = 'quux'
        msg.data['reason'] = 'because'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'quux: because'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'hidden_host_set'
        msg.data['hidden_host'] = 'thing'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'quux: thing bar'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'myinfo'
        msg.data['version'] = '0'
        msg.data['user_modes'] = 'user'
        msg.data['channel_modes'] = 'b'
        msg.data['rest'] = 'a'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'quux: 0, user modes: user, channel modes: ab'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'connecting_failed'
        msg.data['hostname'] = 'jupiter'
        msg.data['port'] = 1999
        msg.data['ssl'] = True
        msg.data['reason'] = 'doubtful'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'jupiter:1999 (ssl) connection failed: doubtful'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'quit_server'
        msg.data['nick'] = 'She'
        msg.data['msg'] = 'umami'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'jupiter:1999 (ssl) She quit: umami'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'you_nickchange'
        msg.data['newnick'] = 'red'
        msg.data['oldnick'] = 'blue'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'you are now red (née blue)'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'channel_topic'
        msg.data['from_name'] = 'someone'
        msg.data['topic'] = 'something boring'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'someone set topic to '),
                (('bold',), 'something boring'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'channel_timestamp'
        msg.data['timestamp'] = 0

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'created Thu Jan  1 00:00:00 1970'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'user_channel_mode'
        msg.data['ops'] = {
            'add': [{'mode': 'mode', 'param': 'param'}],
            'remove': [{'mode': 'mode', 'param': 'param'}],
            }

        print(repr(Decor.headline(msg)))
        print(repr(Chunk([
                (('bold',), '#foo '),
                ((), 'She set '),
                (('bold',), '+mode param -mode param'),
                (('right',), ' 00:00:00'),
                ])))
        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'She set '),
                (('bold',), '+mode param -mode param'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'user_mode'
        msg.data['from'] = 'droid'
        msg.data['diff'] = '9000'
        msg.data['newmode'] = 'ants'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'droid set '),
                (('bold',), '9000'),
                ((), ' ('),
                (('bold',), 'ants'),
                ((), ') on you'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'channel_mode_is'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'mode '),
                (('bold',), '9000'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'channel_url'
        msg.data['url'] = 'file:///'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'url: '),
                (('bold',), 'file:///'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'channel_mode_list_change'
        msg.data['url'] = 'file:///'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'channel mode '),
                (('bold',), '9000'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'joined_channel'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), '+ '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'parted_channel'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), '- '),
                (('bold',), 'mock'),
                ((), ': bar'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data['type'] = 'nickchange'

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'blue'),
                ((), ' -> '),
                (('bold',), 'mock'),
                (('right',), ' 00:00:00'),
                ]))

        msg.data = {}

        self.assertEqual(
            Decor.headline(msg), Chunk([
                (('bold',), '#foo '),
                ((), 'mock [no type] eid - bid - cid -\n{}'),
                (('right',), ' 00:00:00'),
                ]))


class TestIRCCloudMessage(unittest.TestCase):
    def test(self):
        i = irccloud.IRCCloud(context.Context())
        m = irccloud.IRCCloudMessage(
            i, {
                'eid': 0.0,
                })
        self.assertEqual(str(m), "0.0 {'eid': 0.0}")
        self.assertEqual(
            repr(m),
            '<IRCCloudMessage 0.0 <IRCCloudNonAddress irccloud , system>'
            ' 12 chars None noise>')
        self.assertEqual('irccloud; IRCCloud system', str(m.sender))

        with patch('time.time', return_value=3.2):
            m = irccloud.IRCCloudMessage(i, {})
            self.assertEqual(3.2, float(m))

        m = irccloud.IRCCloudMessage(i, {
            'type': 'motd_response',
            'start': 'start',
            'lines': ['A', 'B'],
            'msg': 'X'
            })
        self.assertEqual('start\nA\nB\nX', m.body)

        i.connections[0] = {'hostname': 'quux'}
        m = irccloud.IRCCloudMessage(i, {
            'from': 'foo',
            'from_name': 'bar',
            'from_host': 'baz',
            'cid': 0,
            })
        self.assertEqual('irccloud; quux foo', str(m.sender))

        i.connections[0] = {'hostname': 'quux'}
        m = irccloud.IRCCloudMessage(i, {
            'nick': 'foo',
            'from_name': 'bar',
            'from_host': 'baz',
            'cid': 0,
            })
        self.assertEqual('irccloud; quux foo', str(m.sender))
        self.assertEqual('foo', m.sender.short())

    def test_followup_filter(self):
        i = irccloud.IRCCloud(context.Context())
        i.connections[0] = {'hostname': 'host'}
        i.buffers[0] = {'name': '#channel'}
        m = irccloud.IRCCloudMessage(i, {
            'bid': 0,
            'cid': 0,
            'from': 'nick',
            'from_name': 'bar',
            'from_host': 'baz',
            })

        self.assertEqual('irccloud; host #channel', m.followup())
        self.assertEqual('irccloud; host nick', m.reply())

        self.assertEqual(
            'backend == "irccloud" and channel = "#channel"', str(m.filter()))
        self.assertEqual(
            'backend == "irccloud" and channel = "#channel"'
            ' and sender = "irccloud; host nick"',
            str(m.filter(1)))

        m = irccloud.IRCCloudMessage(i, {})
        self.assertEqual('backend == "irccloud"', str(m.filter()))


class TestIrcFormat(unittest.TestCase):
    def test(self):
        self.assertEqual(
            irccloud.irc_format('text').tagsets(),
            [((), 'text')])
        self.assertEqual(
            irccloud.irc_format('foo\007bar').tagsets(),
            [((), 'foo'), ({'bold'}, '^G'), ((), 'bar')])
        self.assertEqual(
            irccloud.irc_format('\x02foo\x0fbar').tagsets(),
            [({'bold'}, 'foo'), ((), 'bar')])
        self.assertEqual(
            irccloud.irc_format('foo\x02bar\x02baz').tagsets(),
            [((), 'foo'), ({'bold'}, 'bar'), ((), 'baz')])
        self.assertEqual(
            irccloud.irc_format('\02\x1d\x1f\x16foo\x0fbar').tagsets(),
            [({'bold', 'dim', 'underline', 'reverse'}, 'foo'), ((), 'bar')])
        self.assertEqual(
            irccloud.irc_format('\x030,2foo\x0fbar').tagsets(),
            [({'fg:white', 'bg:blue'}, 'foo'), ((), 'bar')])
        self.assertEqual(
            irccloud.irc_format('foo\x032\x02\x02,bar\x0fbaz').tagsets(),
            [((), 'foo'), ({'fg:blue'}, ',bar'), ((), 'baz')])

        self.assertEqual(
            irccloud.irc_format('foo\x0399\x02\x02,bar\x0fbaz').tagsets(),
            [((), 'foo,barbaz')])

        self.assertEqual(
            irccloud.irc_format(
                'foo\x032bar', frozenset({'fg:blue'})).tagsets(),
            [({'fg:blue'}, 'foobar')])


if __name__ == '__main__':
    unittest.main()
