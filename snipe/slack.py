# -*- encoding: utf-8 -*-
# Copyright © 2015 the Snipe contributors
# All rights reserved.
'''
snipe.slack
--------------
Backend for talking to `Slack <https://slack.com>`.
'''

import os
import time
import re
import netrc
import urllib.parse
import aiohttp
import json
import pprint

import asyncio

from . import messages
from . import _websocket
from . import util
from . import keymap
from . import interactive

SLACKDOMAIN = 'slack.com'
SLACKAPI = '/api/'


class Slack(messages.SnipeBackend, util.HTTP_JSONmixin):
    name = 'slack'
    loglevel = util.Level('log.slack', 'Slack')

    def __init__(self, *args, **kw):
        slackname = kw['slackname']
        del kw['slackname']
        super().__init__(*args, **kw)
        self.name = Slack.name + '.' + slackname
        self.tasks.append(asyncio.Task(self.connect(slackname)))

    @asyncio.coroutine
    def connect(self, slackname):
        try:
            hostname = slackname + '.' + SLACKDOMAIN

            try:
                rc = netrc.netrc(os.path.join(self.context.directory, 'netrc'))
                authdata = rc.authenticators(hostname)
            except netrc.NetrcParseError as e:
                self.log.warn(str(e)) # need better notification
                return
            except FileNotFoundError as e:
                self.log.warn(str(e))
                return

            token = authdata[2]

            url = 'https://' + SLACKDOMAIN + SLACKAPI

            self.log.debug('about to rtm.start')

            self.data = yield from self.http_json(
                'GET',
                url + 'rtm.start?' + urllib.parse.urlencode(dict(token=token)))

            if not self.data['ok']:
                self.messages.append(
                    SnipeErrorMessage(
                        self,
                        'connecting to %s: %s' % (
                            slackname,
                            self.data['error']
                        )))
                return

            url = self.data['url']

            self.users = {u['id']: u for u in self.data['users']}

            self.dests = dict(
                [(u['id'], SlackDest('user', u)) for u in self.data['users']] +
                [(i['id'], SlackDest('im', i)) for i in self.data['ims']] +
                [(g['id'], SlackDest('group', g)) for g in self.data['groups']] +
                [(c['id'], SlackDest('channel', c)) for c in self.data['channels']])

            self.log.debug('websocket url is %s', url)

            self.websocket = util.JSONWebSocket(self.log)
            yield from self.websocket.connect(url)

            while True:
                m = yield from self.websocket.read()
                self.log.debug('message: %s', repr(m))
                try:
                    self.incoming(m)
                except:
                    self.log.exception(
                        'Processing incoming message: %s', repr(m))
        except asyncio.CancelledError:
            raise
        except:
            self.log.exception('connecting to slack')

    def incoming(self, m):
        t = m['type'].lower()
        if t in ('hello', 'user_typing', 'channel_marked'):
            return
        elif t in ('team_join', 'user_change'):
            u = m['user']
            self.users[u['id']] = u
        elif t == 'channel_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest('channel', c)
        elif t in ('channel_rename', 'group_rename'):
            c = m['channel']
            self.dests[c['id']].update(c)
        elif t == 'group_joined':
            c = m['channel']
            self.dests[c['id']] = SlackDest('group', c)
        elif t == 'im_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest('im', c)
        msg = SlackMessage(self, m)
        if self.messages and msg.time <= self.messages[-1].time:
            msg.time = self.messages[-1].time + .000001
        self.messages.append(msg)
        self.redisplay(msg, msg)

    @keymap.bind('S U')
    def dump_users(self, window: interactive.window):
        window.show(pprint.pformat(self.users))

    @keymap.bind('S D')
    def dump_dests(self, window: interactive.window):
        window.show(pprint.pformat(self.dests))

    def backfill(self, mfilter, target=None):
        pass


class SlackDest:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data

    def update(self, data):
        self.data.update(data)

    def __repr__(self):
        return self.__class__.__name__ + '(\n    ' \
          + repr(self.type) + ',\n    ' \
          + '\n    '.join(pprint.pformat(self.data).split('\n')) \
          + '\n    )'


class SlackUser(messages.SnipeAddress):
    def __init__(self, backend, identifier):
        self.id = identifier
        super().__init__(backend, ['USER', identifier])

    def __str__(self):
        return self.backend.users[self.id]['name']


class SlackMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        import pprint
        backend.log.debug('message: %s', pprint.pformat(m))
        t = m['type']

        super().__init__(
            backend,
            t + ' ' + pprint.pformat(m),
            float(m.get('ts', time.time())))

        self.data = m

        if 'user' in m:
            if isinstance(m['user'], dict):
                self._sender = SlackUser(backend, m['user']['id'])
            else:
                self._sender = SlackUser(backend, m['user'])

        self.channel = None

        if t == 'message' and 'text' in m:
            bodylist = re.split(r'<(.*)>', m['text'])
            self.body = ''
            for (n, s) in enumerate(bodylist):
                if n%2 == 0:
                    self.body += s
                else:
                    if '|' in s:
                        self.body += s.split('!', 1)[-1]
                    else:
                        if s[:2] in ('#C', '@U'):
                            self.body += self.displayname(s[1:])
                        else:
                            self.body += s
            self.channel = self.displayname(m['channel'])
            if self.backend.dests.get(m['channel'], SlackDest('_', {})).type == 'im':
                self.personal = True
        elif t == 'presence_change':
            self.body = backend.users[m['user']]['name'] + ' is ' + m['presence']
            self.noise = True

    def displayname(self, s):
        d = self.backend.dests.get(s)
        if d is None:
            return s
        prefix = {'im': '@', 'user': '@', 'group': '+', 'channel': '#'}[d.type]
        if d.type == 'im':
            return prefix + self.backend.users[d.data['user']]['name']
        else:
            return prefix + d.data['name']

    def display(self, decoration):
        tags = self.decotags(decoration)
        timestring = time.strftime(' %H:%M:%S', time.localtime(self.time))
        chunk = []
        if self.channel is not None:
            chunk += [((tags + ('bold',)), self.channel + ' ')]

        t = self.data['type']
        t_ = self.data.get('subtype')
        if t == 'message' and t_ in (None, 'me_message'):
            chunk += [(tags + ('bold',), self.sender.short())]
            if t_ != 'me_message':
                chunk += [(tags, ': ')]
            else:
                chunk += [(tags, ' ')]

            bodylist = re.split(r'<(.*)>', self.data['text'])
            for (n, s) in enumerate(bodylist):
                if n%2 == 0:
                    chunk += [(tags, s)]
                else:
                    if '|' in s:
                        chunk += [(tags + ('bold',), s.split('!', 1)[-1])]
                    else:
                        if s[:2] in ('#C', '@U'):
                            chunk += [(
                                tags + ('bold',),
                                self.displayname(s[1:]),
                                )]
                        else:
                            chunk += [(tags + ('bold',), s)]
            chunk += [(tags + ('right',), timestring)]
        elif t == 'presence_change':
            if self.data['presence'] == 'active':
                chunk += [(tags, '+ ')]
            else:
                chunk += [(tags, '- ')]
            chunk += [
                (tags + ('bold',), self.sender.short()),
                (tags + ('right',), timestring),
                ]
        else:
            return super().display(decoration)
        return chunk
