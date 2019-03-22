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

import logging
import os
import unittest

from unittest.mock import (patch, Mock)

import mocks

import snipe.context as context
import snipe.filters as filters
import snipe.imbroglio as imbroglio
import snipe.messages as messages
import snipe.slack as slack
import snipe.util as util

from snipe.chunks import (Chunk)


class TestSlack(unittest.TestCase):
    def test_instantiate(self):
        s = slack.Slack(None, name='test')

    @imbroglio.test
    async def test_backoff(self):
        with patch('snipe.imbroglio.sleep') as sleep:
            sleep.return_value = mocks.promise(None)
            self.assertEqual(.5, (await slack.Slack.backoff(0)))
            sleep.assert_not_called()

            self.assertEqual(1.0, (await slack.Slack.backoff(.5)))
            sleep.assert_called_with(.5)

    def test_destinations_senders(self):
        s = slack.Slack(None, name='test')
        s.dests = {'foo': slack.SlackDest(s, 'user', {'name': 'bar'})}
        self.assertEqual({'test; bar'}, s.destinations())
        self.assertEqual({'test; bar'}, s.senders())


    @imbroglio.test
    async def test_incoming_find(self):
        s = slack.Slack(None, name='test')
        self.assertEqual(0, len(s.messages))
        with self.assertLogs(level=logging.DEBUG) as l:
            self.assertIsNone(s.find_message(0, {'type': 'foo'}))
        self.assertIn('unknown', l.output[0])
        await s.incoming({
            'channel': 'D03RVNN0U',
            'text': 'To start, what is your first name?',
            'ts': '1425140075.000003',
            'type': 'message',
            'user': 'USLACKBOT',
            })
        self.assertEqual(1, len(s.messages))
        with self.assertLogs(level=logging.DEBUG) as l:
            self.assertIsNone(s.find_message(0, {'type': 'foo'}))
        self.assertIn('found message', l.output[0])
        self.assertIs(
            s.messages[0],
            s.find_message(float(s.messages[0].time), {}))

    @imbroglio.test
    async def test_process_message_misc(self):
        s = slack.Slack(None, name='test')
        l = []
        self.assertIsNone(
            await s.process_message(l, {
                'type': list(s.IGNORED_TYPE_PREFIXES)[0] + 'foo'}))
        self.assertIsNone(
            await s.process_message(l, {
                'type': list(s.IGNORED_TYPES)[0]}))
        self.assertIsNone(
            await s.process_message(l, {
                'type': 'team_migration_started'}))
        with self.assertRaises(slack.SlackReconnectException):
            await s.process_message(s.messages, {
                'type': 'team_migration_started'})
        s.emoji_update = Mock(return_value = mocks.promise())
        self.assertIsNone(
            await s.process_message(l, {
                'type': 'emoji_changed'}))
        s.emoji_update.assert_called()

    @imbroglio.test
    async def test_process_message_duplicate(self):
        s = slack.Slack(None, name='test')
        l = []
        await s.process_message(l, {
            'channel': 'D03RVNN0U',
            'text': 'To start, what is your first name?',
            'ts': '1425140075.000003',
            'type': 'message',
            'user': 'USLACKBOT',
            })
        await s.process_message(l, {
            'channel': 'D03RVNN0U',
            'text': 'To start, what is your first name?',
            'ts': '1425140075.000003',
            'type': 'message',
            'user': 'USLACKBOT',
            })
        a, b = l
        self.assertNotEqual(a.time, b.time)

    @imbroglio.test
    async def test_process_message_reply_to(self):
        s = slack.Slack(None, name='test')
        l = []

        s.data['self'] = {'id': 'user'}

        await s.process_message(l, {
            'channel': 'D03RVNN0U',
            'text': 'To start, what is your first name?',
            'ts': '1425140075.000003',
            'type': 'message',
            'reply_to': 'bar',
            })

        self.assertEqual('user', l[0].data['user'])

    @imbroglio.test
    async def test_process_message_3(self):
        s = slack.Slack(None, name='test')

        await s.process_message(s.messages, {
            'channel': 'D03RVNN0U',
            'text': 'To start, what is your first name?',
            'ts': '1425140075.000003',
            'type': 'message',
            'user': 'USLACKBOT',
            })


        self.assertEqual(
            s.messages[0].body,
            'To start, what is your first name?')

        self.assertIsNone(
            await s.process_message(s.messages, {
                'type': 'message',
                'subtype': 'message_changed',
                'message': {'ts': '0'},
                }))

        self.assertIsNotNone(
            await s.process_message(s.messages, {
                'type': 'message',
                'subtype': 'message_changed',
                'message': {
                    'text': 'To start, what is your FIRST name?',
                    'ts': '1425140075.000003',
                    'type': 'message',
                    'user': 'USLACKBOT',
                    }}))

        self.assertEqual(
            s.messages[0].data['text'],
            'To start, what is your FIRST name?')

        self.assertIsNone(
            await s.process_message(s.messages, {
                'type': 'reaction_added',
                'reaction': 'foo',
                'user': 'USLACKBOT',
                'item': {
                    'ts': '0',
                }}))

        self.assertIsNotNone(
            await s.process_message(s.messages, {
                'type': 'reaction_added',
                'reaction': 'foo',
                'user': 'USLACKBOT',
                'item': {
                    'ts': '1425140075.000003',
                }}))

        self.assertEqual('foo', s.messages[0].data['reactions'][0]['name'])
        self.assertEqual(1, s.messages[0].data['reactions'][0]['count'])

        self.assertIsNotNone(
            await s.process_message(s.messages, {
                'type': 'reaction_added',
                'reaction': 'foo',
                'user': 'UNOTSLACKBOT',
                'item': {
                    'ts': '1425140075.000003',
                }}))

        self.assertEqual('foo', s.messages[0].data['reactions'][0]['name'])
        self.assertEqual(2, s.messages[0].data['reactions'][0]['count'])

        self.assertIsNotNone(
            await s.process_message(s.messages, {
                'type': 'reaction_removed',
                'reaction': 'foo',
                'user': 'USLACKBOT',
                'item': {
                    'ts': '1425140075.000003',
                }}))

        self.assertEqual('foo', s.messages[0].data['reactions'][0]['name'])
        self.assertEqual(1, s.messages[0].data['reactions'][0]['count'])

        self.assertIsNotNone(
            await s.process_message(s.messages, {
                'type': 'reaction_removed',
                'reaction': 'foo',
                'user': 'UNOTSLACKBOT',
                'item': {
                    'ts': '1425140075.000003',
                }}))

        self.assertEqual(0, len(s.messages[0].data['reactions']))

        self.assertIsNone(
            await s.process_message(s.messages, {
                'type': 'reaction_removed',
                'reaction': 'foo',
                'user': 'UNOTSLACKBOT',
                'item': {
                    'ts': '1425140075.000003',
                }}))

    @imbroglio.test
    async def test_process_message_meta(self):
        s = slack.Slack(None, name='test')
        l = []

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'team_join',
                'user': {'id': 'F00', 'name': 'foo'},
                }))

        self.assertEqual('F00', s.users['F00']['id'])
        self.assertEqual('foo', s.users['F00']['name'])
        self.assertEqual('foo', str(s.dests['F00']))

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'user_change',
                'user': {'id': 'F00', 'name': 'bar'},
                }))

        self.assertEqual('bar', s.users['F00']['name'])
        self.assertEqual('bar', str(s.dests['F00']))

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'channel_created',
                'channel': {'id': 'BAR', 'name': 'bar', 'is_member': True},
                }))

        self.assertEqual('#bar', str(s.dests['BAR']))

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'channel_rename',
                'channel': {'id': 'BAR', 'name': 'baz'},
                }))

        self.assertEqual('#baz', str(s.dests['BAR']))

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'group_joined',
                'channel': {'id': 'QUUX', 'name': 'quux'},
                }))

        self.assertEqual('+quux', str(s.dests['QUUX']))

        self.assertIsNone(
            await s.process_message(l, {
                'ts': '1425140075.000003',
                'type': 'im_created',
                'channel': {'id': 'QUUX', 'user': 'F00'},
                }))

        self.assertEqual('@bar', str(s.dests['QUUX']))

    @imbroglio.test
    async def test_emoji_update(self):
        s = slack.Slack(None, name='test')
        s.method = Mock(return_value=mocks.promise({'foo': 'bar'}))
        await s.emoji_update()
        s.method.assert_called_with('emoji.list')
        self.assertEqual(s.emoji, {'foo': 'bar'})

    @imbroglio.test
    async def test_metadump(self):
        s = slack.Slack(None, name='test')

        window = Mock()
        s.dump_users(window)
        window.show.assert_called_with('{}')

        window = Mock()
        s.dump_dests(window)
        window.show.assert_called_with('{}')

        window = Mock()
        s.dump_meta(window)
        window.show.assert_called_with('{}')

    @imbroglio.test
    async def test_method(self):
        s = slack.Slack(None, name='test')
        s.token = 'TOKEN'
        s._post = Mock(return_value=mocks.promise('foo'))

        self.assertEqual(
            'foo',
            (await s.method('method')))

        s._post.assert_called_with('method', token='TOKEN')

    def test_check(self):
        s = slack.Slack(None, name='test')

        with self.assertRaises(util.SnipeException):
            s.check({'ok': False, 'error': 'bad'}, 'context')

        self.assertTrue(s.check_ok({'ok': True}, 'context'))
        self.assertFalse(s.check_ok({'ok': False, 'error': 'bad'}, 'context'))

        self.assertEqual(
            "context: bad\n{'ok': False, 'error': 'bad'}",
            s.messages[0].body)


class TestSlackDest(unittest.TestCase):
    def test_update(self):
        s = slack.Slack(None, name='test')
        d = slack.SlackDest(s, 'user', {'name': 'fred'})
        d.update({'flig': 'quoz'})
        self.assertEqual(dict(name='fred', flig='quoz'), d.data)

    def test___repr__(self):
        s = slack.Slack(None, name='test')
        d = slack.SlackDest(s, 'user', {'name': 'fred'})
        self.assertEqual(
            "SlackDest(\n    'user',\n    {'name': 'fred'}\n    )", repr(d))

    def test___str__(self):
        s = slack.Slack(None, name='test')
        d = slack.SlackDest(s, 'user', {'name': 'fred'})
        self.assertEqual('fred', str(d))
        e = slack.SlackDest(s, 'im', {'name': 'fred', 'user': 'FRED0'})
        s.users['FRED0'] = {'name': 'Fred'}
        self.assertEqual('@Fred', str(e))


class TestSlackAddress(unittest.TestCase):
    def test(self):
        s = slack.Slack(None, name='test')
        s.dests['FOO'] = slack.SlackDest(s, 'channel', {
            'id': 'FOO',
            'name': 'foo',
            'is_member': True,
            })

        a = slack.SlackAddress(s, 'FOO')

        self.assertEqual('test; #foo', str(a))
        self.assertEqual('#foo', a.short())


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


class TestSlackMessage(unittest.TestCase):
    def test___init___0(self):
        m = slack.SlackMessage(
            slack.Slack(context.Context(), slackname='test'), {
                'type': 'message',
                'channel': 'foo',
                'ts': 0.0,
                })
        os.environ['TZ'] = 'GMT'

        self.assertEqual(str(m), '00:00 slack.test; foo\n')
        self.assertEqual(
            repr(m),
            '<SlackMessage 0.0 <SlackAddress slack.test ?, foo> 0 chars>')

    @imbroglio.test
    async def test___init___1(self):
        s = slack.Slack(None, name='test')

        await s.incoming({
            'type': 'team_join',
            'user': {'id': 'USER', 'name': 'user'},
            })

        await s.incoming({
            'type': 'channel_created',
            'channel': {
                'id': 'CHANNEL', 'name': 'channel', 'is_member': True},
            })

        await s.incoming({
            'type': 'im_created',
            'channel': {
                'id': 'IM', 'user': 'USER'},
            })

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': 'USER',
            'type': 'message',
            'text': None,
            'channel': 'CHANNEL',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\n', str(m))

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'bot_id': 'USER',
            'type': 'message',
            'text': None,
            'channel': 'CHANNEL',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\n', str(m))

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': {'id': 'USER'},
            'type': 'message',
            'text': 'text',
            'channel': 'CHANNEL',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\ntext', str(m))

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': 'USER',
            'type': 'message',
            'text': 'text<bar|foo>text',
            'channel': 'CHANNEL',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\ntextfootext', str(m))

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': 'USER',
            'type': 'message',
            'text': '<@USER>\n<#CHANNEL>\n<foo>',
            'channel': 'CHANNEL',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\nuser\n#channel\nfoo', str(m))
        self.assertEqual('test; #channel', m.followup())
        self.assertEqual(
            filters.And(
                filters.Compare('==', 'backend', 'test'),
                filters.Compare('==', 'channel', '#channel'),
                filters.Compare('==', 'sender', 'test; user'),
            ),
            m.filter(1))

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': 'USER',
            'type': 'message',
            'text': 'foo',
            'channel': 'IM',
            })

        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\nfoo', str(m))
        self.assertTrue(m.personal)
        self.assertEqual('test; user', m.followup())

        m = slack.SlackMessage(s, {
            'ts': 0.0,
            'user': 'USER',
            'type': 'presence_change',
            'presence': 'out',
            })
        self.assertEqual('test; user', str(m.sender))
        self.assertEqual('00:00 test; user\nuser is out', str(m))
        self.assertTrue(m.noise)
        self.assertEqual('test; user', m.followup())

    @imbroglio.test
    async def test_slackmarkup(self):
        s = slack.Slack(None, name='test')
        m = slack.SlackMessage(s, {'type': 'message', 'channel': 'foo'})

        Ø = frozenset()

        self.assertEqual([(Ø, '')], m.slackmarkup(None, Ø))
        self.assertEqual([(Ø, '<&>')], m.slackmarkup('&lt;&amp;&gt;', Ø))
        self.assertEqual(
            [
                (Ø, ''),
                ({'bold'}, 'foo'),
                (Ø, '')
            ], m.slackmarkup('<|foo>', Ø))

        await s.incoming({
            'type': 'team_join',
            'user': {'id': 'USER', 'name': 'user'},
            })

        self.assertEqual(
            [
                (Ø, ''),
                ({'bold'}, '@user'),
                (Ø, '')
            ], m.slackmarkup('<@USER>', Ø))

        self.assertEqual(
            [
                (Ø, ''),
                ({'bold'}, 'FOO'),
                (Ø, '')
            ], m.slackmarkup('<FOO>', Ø))

    @imbroglio.test
    async def test_react_add_remove(self):
        s = slack.Slack(None, name='test')
        m = slack.SlackMessage(s, {'type': 'message', 'channel': 'foo'})
        o = object()

        m.react = Mock(return_value = mocks.promise())

        await m.add_reaction(o)
        m.react.assert_called_with(o, 'reactions.add')

        m.react = Mock(return_value = mocks.promise())

        await m.remove_reaction(o)
        m.react.assert_called_with(o, 'reactions.remove')

    @imbroglio.test
    async def test_react(self):
        s = slack.Slack(None, name='test')
        s.emoji = {}
        m = slack.SlackMessage(
            s, {'type': 'message', 'channel': 'foo', 'ts': 0.0})
        window = Mock()
        window.read_oneof.return_value = mocks.promise('foo')

        await m.react(window, 'reactions.add')

        window.read_oneof.assert_called()

        m.data['reactions'] = [{'name': 'star'}]
        window.read_oneof.return_value = mocks.promise('star')
        s.method = Mock(return_value=mocks.promise({'ok': True}))

        await m.react(window, 'reactions.add')

        self.assertEqual(['star'], s.used_emoji)
        s.method.assert_called_with(
            'reactions.add', name='star', channel='foo', timestamp=0.0)

    @imbroglio.test
    async def test_edit_message(self):
        s = slack.Slack(None, name='test')
        m = slack.SlackMessage(
            s, {'type': 'message', 'channel': 'foo', 'ts': 0.0})

        window = Mock()
        window.cursor=None
        window.read_string.return_value = mocks.promise('foo')

        with self.assertRaises(Exception):
            await m.edit_message(window)

        s.method = Mock(return_value = mocks.promise({'ok': True}))

        window.read_string.return_value = mocks.promise('\nfoo')
        await m.edit_message(window)

        window.read_string.assert_called()
        s.method.assert_called_with(
            'chat.update', channel='foo', ts=0.0, text='foo')


if __name__ == '__main__':
    unittest.main()
