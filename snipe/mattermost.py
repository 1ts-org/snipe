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
snipe.mattermost
--------------
Backend for talking to `mattermost <https://mattermost.com>`.
'''

import logging
import pprint
import urllib

from . import imbroglio
from . import messages
from . import util

_backend = 'Mattermost'

HELP = """60
=======================
The mattermost backend
=======================

Place documentation here.
"""


class Mattermost(messages.SnipeBackend, util.HTTP_JSONmixin):
    name = 'mattermost'
    loglevel = util.Level(
        'log.mattermost', 'Mattermost',
        default=logging.DEBUG,
        doc='log level for mattermost backend')

    netloglevel = util.Level(
        'log.mattermost.network', 'Mattermost.network',
        default=logging.INFO,
        doc='log level more mattermost network traffic')

    SOFT_NEWLINES = True

    reconnect = True

    def __init__(self, context, url='https://mattermost.xvm.mit.edu', **kw):
        super().__init__(context, **kw)
        self.url = url.rstrip('/') + '/api/v4/'
        self.messages = []

    async def start(self):
        await super().start()
        self.tasks.append(await imbroglio.spawn(self.connect()))

    async def connect(self):
        self.state_set(messages.BackendState.CONNECTING)

        while True:
            try:
                await self.connect_once()
            except Exception:
                self.log.exception(f'connecting to mattermost {self.name}')
            await imbroglio.sleep(1)
            if not self.reconnect:
                break

        self.log.info('%s shut down', self)
        self.state_set(messages.BackendState.DISCONNECTED)

    async def connect_once(self):
        host = urllib.parse.urlparse(self.url).netloc.split(':')[0]
        email, password = self.context.credentials(host)
        self.setup_client_session()
        self.session = await self._post_json(
            'users/login', login_id=email, password=password)
        self.token = dict(self._response.headers)[b'token'].decode('us-ascii')

        ws = util.JSONWebSocket(self.netlog)

        self.authheaders = [('Authorization', 'Bearer ' + self.token)]
        self.setup_client_session(dict(self.authheaders))

        await ws.connect(
            self.url + 'websocket', headers=self.authheaders)

        self.log.debug('self._get = %s', repr(self._get))
        teamdata = await self._get('teams')
        # XXX should do paging
        self.log.debug('teamdata = %s', pprint.pformat(teamdata))
        self.team_id = {}
        self.team_name = {}
        for team in teamdata:
            self.team_id[team['id']] = team
            self.team_name[team['name']] = team

        # apparently not split by teams?
        userdata = []
        page = 0
        while True:
            got = await self._get('users', page=page)
            self.log.debug('got = %s', repr(got))
            if not got:
                break
            userdata += got
            page += 1
        self.log.debug('userdata = %s', pprint.pformat(userdata))
        self.user_id = {}
        self.user_name = {}
        for user in userdata:
            self.user_id[user['id']] = user
            self.user_name[user['username']] = user

        self.state_set(messages.BackendState.IDLE)

        while True:
            data = await ws.read()
            self.log.debug('got %s', repr(data))
            self.process_event(data)

    def process_event(self, event):
        msg = MattermostMessage(self, pprint.pformat(event) + '\n')
        if self.messages:
            while msg.time <= self.messages[-1].time:
                msg.time += .0000013
        self.messages.append(msg)
        self.log.debug('appended msg %s', repr(msg))
        self.redisplay(msg, msg)


class MattermostMessage(messages.SnipeMessage):
    pass
