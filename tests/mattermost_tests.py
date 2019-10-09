# -*- encoding: utf-8 -*-
# Copyright © 2019 the Snipe contributors
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
Unit tests for the mattermost backend
'''


import unittest

from typing import List
from unittest import mock

import snipe.imbroglio as imbroglio
import snipe.mattermost as mattermost
import snipe.util as util


class AsyncMock(mock.MagicMock):
    async_seq: List[dict] = []
    async_except = None

    async def __call__(self, *args, **kw):
        if self.async_seq:
            r = self.async_seq.pop(0)
            return r
        if self.async_except is not None:
            raise self.async_except
        return super().__call__(*args, **kw)


class TestMattermost(unittest.TestCase):
    @imbroglio.test
    async def test_start(self):
        async def mock_connect_once(self):
            raise util.SnipeException('Testing 123')
        with mock.patch.object(
                mattermost.Mattermost, 'connect_once', mock_connect_once):
            context = mock.Mock()
            context.ui = mock.Mock()
            m = mattermost.Mattermost(context)
            m.reconnect = False
            await m.start()
            (connect,) = m.tasks
            await connect

    @imbroglio.test
    async def test_connect_once(self):
        context = mock.Mock()
        context.credentials.return_value = (
            'email@example.com', 'example.com')
        context.ui = mock.Mock()
        m = mattermost.Mattermost(context)
        m._response = mock.Mock()
        m._response.headers = [(b'token', b'foo')]

        m._post_json = AsyncMock(return_value=[])

        team_object = {'id': 'a', 'name': 'team'}
        user_object = {'id': 'b', 'username': 'user'}

        m._get = AsyncMock(return_value=[])
        m._get.async_seq = [[team_object], [user_object], []]

        m.process_event = mock.Mock()
        event = {'event': 'fake'}

        ws = mock.Mock()
        ws.return_value = ws
        ws.connect = AsyncMock()
        ws.connect.return_value = ws
        ws.read = AsyncMock()
        ws.read.async_seq = [event]
        ws.read.async_except = util.SnipeException('done')

        with mock.patch('snipe.util.JSONWebSocket', ws):
            with self.assertRaises(util.SnipeException):
                await m.connect_once()

        self.assertIn('a', m.team_id)
        self.assertEqual(m.team_id['a'], team_object)
        self.assertIn('team', m.team_name)
        self.assertEqual(m.team_name['team'], team_object)

        self.assertIn('b', m.user_id)
        self.assertEqual(m.user_id['b'], user_object)
        self.assertIn('user', m.user_name)
        self.assertEqual(m.user_name['user'], user_object)

        m.process_event.assert_called_with(event)

    def test_process_event(self):
        m = mattermost.Mattermost(None)
        self.assertEqual(len(m.messages), 0)

        event = {'event': 'fake'}

        m.process_event(event)

        self.assertEqual(len(m.messages), 1)


if __name__ == '__main__':
    unittest.main()
