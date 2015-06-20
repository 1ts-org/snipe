# -*- encoding: utf-8 -*-
# Copyright © 2015 the Snipe contributors
# All rights reserved.
'''
snipe.slack
--------------
Backend for talking to `Slack <https://slack.com>`.
'''

_backend = 'Slack'


import os
import time
import re
import netrc
import urllib.parse
import aiohttp
import json
import pprint
import contextlib

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
        self.backfilling = False
        self.dests = {}
        self.connected = False
        self.messages = []

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

            self.token = authdata[2]

            self.url = 'https://' + SLACKDOMAIN + SLACKAPI

            self.log.debug('about to rtm.start')

            self.data = yield from self.http_json(
                'GET',
                self.url + 'rtm.start?' + urllib.parse.urlencode({
                    'token': self.token,
                    }))

            if not self.data['ok']:
                self.messages.append(
                    messages.SnipeErrorMessage(
                        self,
                        'connecting to %s: %s' % (
                            slackname,
                            self.data['error']
                        )))
                return

            url = self.data['url']

            self.users = {u['id']: u for u in self.data['users']}

            self.dests = dict(
                [(u['id'], SlackDest(self, 'user', u)) for u in self.data['users']] +
                [(i['id'], SlackDest(self, 'im', i)) for i in self.data['ims']] +
                [(g['id'], SlackDest(self, 'group', g)) for g in self.data['groups']] +
                [(c['id'], SlackDest(self, 'channel', c)) for c in self.data['channels']])

            self.log.debug('websocket url is %s', url)

            self.websocket = util.JSONWebSocket(self.log)
            yield from self.websocket.connect(url)

            self.connected = True

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
        msg = self.process_message(self.messages, m)
        if msg is not None:
            self.redisplay(msg, msg)

    def process_message(self, messagelist, m):
        if 'reply_to' in m:
            #XXX we'll want to do something more intelligent once we have
            #sending but for now we don't want the "reconnect" reply
            return
        t = m['type'].lower()
        if t in ('hello', 'user_typing', 'channel_marked'):
            return
        elif t in ('team_join', 'user_change'):
            u = m['user']
            self.users[u['id']] = u
        elif t == 'channel_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'channel', c)
        elif t in ('channel_rename', 'group_rename'):
            c = m['channel']
            self.dests[c['id']].update(c)
        elif t == 'group_joined':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'group', c)
        elif t == 'im_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'im', c)
        msg = SlackMessage(self, m)
        if messagelist and msg.time <= messagelist[-1].time:
            msg.time = messagelist[-1].time + .000001
        messagelist.append(msg)
        return msg

    @keymap.bind('S U')
    def dump_users(self, window: interactive.window):
        window.show(pprint.pformat(self.users))

    @keymap.bind('S D')
    def dump_dests(self, window: interactive.window):
        window.show(pprint.pformat(self.dests))

    @contextlib.contextmanager
    def backfill_guard(self):
        if self.backfilling:
            yield True
        else:
            self.log.debug('entering guard')
            self.backfilling = True
            yield False
            self.backfilling = False
            self.log.debug('leaving guard')

    def backfill(self, mfilter, target=None):
        if not self.connected:
            return
        self.tasks.append(asyncio.Task(self.do_backfill(mfilter, target)))

    @asyncio.coroutine
    def do_backfill(self, mfilter, target):
        self.log.debug('backfill([filter], %s)', repr(target))
        with self.backfill_guard() as already:
            if already:
                self.log.debug('already backfilling')
                return

            backfillers = [
                asyncio.Task(self.do_backfill_dest(dest, mfilter, target))
                for dest in self.dests if self.dests[dest].type != 'user']
            self.tasks += backfillers
            yield from asyncio.gather(*backfillers, return_exceptions=True)

    @asyncio.coroutine
    def do_backfill_dest(self, dest, mfilter, target):
        d = self.dests[dest]

        if d.loaded:
            return

        d.loaded=True

        q = {
            'token': self.token,
            'channel': dest,
            }

        if d.oldest is not None:
            q['latest'] = d.oldest

        verb = {
            'channel': 'channels.history',
            'im': 'im.history',
            'group': 'groups.history',
            }[d.type]

        data = yield from self.http_json(
            'GET',
            self.url + verb + '?' + urllib.parse.urlencode(q))
        self.log.debug('%s: backfill got: %s', dest, pprint.pformat(data))
        if not data['ok']:
            self.messages.append(
                messages.SnipeErrorMessage(
                    self,
                    'backfilling %s %s: %s' % (
                        dest,
                        d.data,
                        data['error'],
                    )))
            return
        messagelist = []
        for m in reversed(data['messages']):
            m['channel'] = dest
            try:
                msg = self.process_message(messagelist, m)
                if d.oldest is None or d.oldest > msg.time:
                    d.oldest = msg.time
            except:
                self.log.exception('processing message: %s', pprint.pformat(m))
                raise
        self.log.debug('%s: got %d messages', dest, len(messagelist))
        self.messages = list(messages.merge([self.messages, messagelist]))
        self.startcache = {}
        if messagelist:
            self.redisplay(messagelist[0], messagelist[-1])


class SlackDest:
    def __init__(self, backend, type_, data):
        self.backend = backend
        self.type = type_
        self.data = data

        self.oldest = None
        self.loaded = False

    def update(self, data):
        self.data.update(data)

    def __repr__(self):
        return self.__class__.__name__ + '(\n    ' \
          + repr(self.type) + ',\n    ' \
          + '\n    '.join(pprint.pformat(self.data).split('\n')) \
          + '\n    )'

    def __str__(self):
        prefix = {
            'im': '@', 'user': '', 'group': '+', 'channel': '#',
            }[self.type]
        if self.type == 'im':
            return prefix + self.backend.users[self.data['user']]['name']
        else:
            return prefix + self.data['name']


class SlackAddress(messages.SnipeAddress):
    def __init__(self, backend, identifier):
        self.backend = backend
        self.id = identifier
        super().__init__(backend, [self.backend.dests[identifier].type, identifier])

    def __str__(self):
        return str(self.backend.dests[self.id])


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
                self._sender = SlackAddress(backend, m['user']['id'])
            else:
                self._sender = SlackAddress(backend, m['user'])
        elif 'channel' in m:
            self._sender = SlackAddress(backend, m['channel'])

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

            ch = m['channel']
            self.channel = self.displayname(ch)
            if ch in self.backend.dests and self.backend.dests[ch].type == 'im':
                self.personal = True
        elif t == 'presence_change':
            self.body = backend.users[m['user']]['name'] + ' is ' + m['presence']
            self.noise = True

    def displayname(self, s):
        return str(self.backend.dests.get(s, s))

    def display(self, decoration):
        tags = self.decotags(decoration)
        timestring = time.strftime(' %H:%M:%S', time.localtime(self.time))
        chunk = []
        if self.channel is not None:
            chunk += [((tags + ('bold',)), self.channel + ' ')]

        t = self.data['type']
        t_ = self.data.get('subtype')
        if t == 'message' and 'text' in self.data:
            chunk += [(tags + ('bold',), self.sender.short())]
            if t_ != 'me_message':
                chunk += [(tags, ': ')]
            else:
                chunk += [(tags, ' ')]

            bodylist = re.split(r'<(.*)>', self.data['text'])
            for (n, s) in enumerate(bodylist):
                if n%2 == 0:
                    chunk += [
                        (tags, s.replace('&lt;', '<').replace('&gt;', '>')),
                        ]
                else:
                    if '|' in s:
                        chunk += [(tags + ('bold',), s.split('|', 1)[-1])]
                    else:
                        if s[:2] in ('#C', '@U'):
                            nametext = self.displayname(s[1:])
                            if s[1] == 'U':
                                nametext = '@' + nametext
                            chunk += [(tags + ('bold',), nametext)]
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
