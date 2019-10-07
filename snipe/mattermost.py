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

import json
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


class Mattermost(messages.SnipeBackend):
    name = 'mattermost'
    loglevel = util.Level(
        'log.mattermost', 'Mattermost',
        default=logging.DEBUG,
        doc='log level for mattermost backend')

    SOFT_NEWLINES = True

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
            # don't loop for now to avoid spamming the server
            # when something (inevitably) goes wrong await
            break
            # imbroglio.sleep(1)

    async def connect_once(self):
        host = urllib.parse.urlparse(self.url).netloc.split(':')[0]
        email, password = self.context.credentials(host)
        r = await util.Retrieve.post(self.url + 'users/login', json={
            'login_id': email,
            'password': password,
            })
        self.log.debug('login headers=%s', repr(r.headers))
        self.session = json.loads(r.decode())
        self.log.debug('session=%s', repr(self.session))

        self.token = dict(r.headers)[b'token'].decode('iso8859-1')
        ws = util.JSONWebSocket(self.log)

        self.authheader = ('Authorization', 'Bearer ' + self.token)

        await ws.connect(
            self.url + 'websocket', headers=[self.authheader])

        r = await util.Retrieve.get(
            self.url + 'teams', headers=[self.authheader])
        teamdata = json.loads(r.decode())
        self.log.debug('teamdata = %s', pprint.pformat(teamdata))
        self.teams_id = {}
        self.teams_name = {}
        for team in teamdata:
            self.teams_id[team['id']] = team
            self.teams_name[team['id']] = team

        for team in self.teams_id:
            userdata = []
            self.log.debug('retrieving users for team=%s', team)
            page = 0
            while True:
                url = self.url + 'users?' + urllib.parse.urlencode(
                    {'page': page})
                self.log.debug('GETing %s', url)
                r = await util.Retrieve.get(
                    url,
                    headers=[self.authheader])
                got = json.loads(r.decode())
                self.log.debug('got=%s', repr(got))
                if not got:
                    break
                userdata += got
                page += 1
            self.log.debug('userdata = %s', pprint.pformat(userdata))
            users_id = {}
            users_name = {}
            for user in userdata:
                users_id[user['id']] = user
                users_name[user['username']] = user
            self.teams_id[team]['users_id'] = users_id
            self.teams_id[team]['users_name'] = users_name

        if False:
            await ws.write({
                'seq': 1,
                'action': 'authentication_challenge',
                'data': {
                    'token': self.token
                    }
                })

        self.state_set(messages.BackendState.IDLE)

        while True:
            data = await ws.read()
            self.log.debug('got %s', repr(data))
            msg = MattermostMessage(self, pprint.pformat(data))
            self.messages.append(msg)
            self.redisplay(msg, msg)


class MattermostMessage(messages.SnipeMessage):
    pass
