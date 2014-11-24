# -*- encoding: utf-8 -*-
# Copyright © 2014 Karl Ramm
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


import asyncio
import aiohttp
import json
import time
import netrc
import urllib.parse

from . import messages
from . import util
from . import _websocket

IRCCLOUD = 'https://www.irccloud.com'


class IRCCloud(messages.SnipeBackend):
    name = 'irccloud'
    loglevel = util.Level('log.irccloud', 'IRCCloud')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.messages = []
        self.task = asyncio.Task(self.connect())
        self.connections = {}
        self.buffers = {}
        self.channels = {}
        self.servers = {}

    @asyncio.coroutine
    def do_connect(self):
        try:
            yield from self.connect()
        except:
            self.log.exception('In IRCCloud.connect')

    @util.coro_cleanup
    def connect(self):
        try:
            authdata = netrc.netrc().authenticators(
                urllib.parse.urlparse(IRCCLOUD).netloc)
        except netrc.NetrcParseError as e:
            self.log.warn(str(e)) # need better notification
            return
        except FileNotFoundError as e:
            self.log.warn(str(e))
            return

        username, _, password = authdata

        self.log.debug('retrieving formtoken')
        result = yield from self.http_json(
            'POST', urllib.parse.urljoin(IRCCLOUD, '/chat/auth-formtoken'), '')
        if not result.get('success'):
            self.log.warn('Could not get formtoken: %s', repr(result))
            return
        token = result['token']

        self.log.debug('retrieving logging in')
        result = yield from self.http_json(
            'POST',
            urllib.parse.urljoin(IRCCLOUD, '/chat/login'),
            urllib.parse.urlencode({
                'email': username,
                'password': password,
                'token': token,
                }),
            {'x-auth-formtoken': token},
            )
        if not result.get('success'):
            self.log.warn('login failed: %s', repr(result))
            return
        self.session = result['session']

        self.log.debug('connecting to websocket')
        reader, self.writer, response = yield from _websocket.websocket(
            IRCCLOUD,
            {
                'Origin': IRCCLOUD,
                'Cookie': 'session=%s' % (self.session,),
            },
            )

        while True:
            message = yield from reader.read()
            self.log.debug('message: %s', repr(message))

            if message.tp == aiohttp.websocket.MSG_PING:
                self.writer.pong()
            elif message.tp == aiohttp.websocket.MSG_CLOSE:
                break
            elif message.tp == aiohttp.websocket.MSG_BINARY:
                self.log.error(
                    'Unknown binary message: %s', repr(message))
            elif message.tp == aiohttp.websocket.MSG_TEXT:
                try:
                    m = json.loads(message.data)
                except:
                    self.log.exception('Decoding json')
                    continue
                try:
                    yield from self.incoming(m)
                except:
                    self.log.exception('Processing incoming message')
            else:
                self.log.error('Unknown websocket message type from irccloud')

    @asyncio.coroutine
    def process_message(self, msglist, m):
        mtype = m.get('type')
        if mtype == 'idle':
            pass
        elif mtype in  ('bannned', 'socket_closed'):
            # the system seems to generate multiple
            # socket_closed/banned messages with the same eid/time
            # with distinct cids, which confuses the message list.
            pass
        elif mtype in ('num_invites', 'stat_user',):
            # we can presumably do something useful with this later
            pass
        elif mtype in ('header', 'backlog_starts', 'end_of_backlog', 'backlog_complete'):
            # presumptively useless-to-us metadata
            pass
        elif mtype == 'oob_include':
            yield from self.include(m['url'])
        elif mtype == 'makeserver':
            self.connections[m['cid']] = m
        elif mtype == 'server_details_changed':
            self.connections[m['cid']].update(m)
        elif mtype == 'status_changed':
            self.connections[m['cid']]['status'] = m['new_status']
            self.connections[m['cid']]['fail_info'] = m['fail_info']
        elif mtype == 'isupport_params':
            self.servers[m['cid']] = m
        elif mtype == 'makebuffer':
            self.buffers[m['bid']] = m
        elif mtype == 'channel_init':
            self.channels[m['bid']] = m
        else:
            msg = IRCCloudMessage(self, m)
            msglist.append(msg)
            return msg

    @asyncio.coroutine
    def incoming(self, m):
        msg = yield from self.process_message(self.messages, m)
        if msg is not None:
            self.redisplay(msg, msg)

    @asyncio.coroutine
    def include(self, url):
        oob_data = yield from self.http_json(
            'GET',
            urllib.parse.urljoin(IRCCLOUD, url),
            headers={'Cookie': 'session=%s' % self.session},
            compress='gzip',
            )
        included = []
        for m in oob_data:
            yield from self.process_message(included, m)
        included.sort()

        if included:
            self.messages = list(messages.merge([self.messages, included]))
            self.redisplay(included[0], included[-1])

    def shutdown(self):
        self.task.cancel()
        # this is kludgy, but make sure the task runs a tick to
        # process its cancellation
        try:
            asyncio.get_event_loop().run_until_complete(self.task)
        except asyncio.CancelledError:
            pass
        super().shutdown()
        # this is also nigh-identical to a function in snipe.roost.Roost,
        # so, factoring opportunity!

    @asyncio.coroutine
    def http_json(self, method, url, data=None, headers={}, compress=None):
        send_headers = {
            'User-Agent': util.USER_AGENT,
        }
        if data is not None:
            data = data.encode('UTF-8')
            headers['Content-Length'] = str(len(data))
        send_headers.update(headers)

        response = yield from aiohttp.request(
            method, url, data=data, compress=compress, headers=headers)

        result = []
        while True:
            data = yield from response.content.read()
            if data == b'':
                break
            result.append(data)

        response.close()

        result = b''.join(result)
        result = result.decode('utf-8')
        result = json.loads(result)
        return result


class IRCCloudMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        when = m.get('eid', -1)
        if when == -1:
            when = time.time()
        else:
            when = when / 1000000

        super().__init__(backend, m.get('msg', repr(m)), when)
        self.data = m
        if 'from' in m and 'from_name' in m and 'from_host' in m:
            self._sender = IRCCloudUser(
                backend, m['from'], m['from_name'], m['from_host'])
        elif 'nick' in m and 'from_name' in m and 'from_host' in m:
            self._sender = IRCCloudUser(
                backend, m['nick'], m['from_name'], m['from_host'])
        else:
            self._sender = IRCCloudNonAddress(backend, 'system')

    def __str__(self):
        return str(self.time) + ' ' + repr(self.data)

    def display(self, decoration):
        timestring = time.strftime('%H:%M', time.localtime(self.time))
        mtype = self.data.get('type')
        chan = self.backend.buffers.get(self.data.get('bid', -1), {}).get('name', None)

        s = timestring + ' '
        if chan is not None:
            s += chan + ' '

        msgy = {
            'buffer_msg': ':',
            'buffer_me_msg': '',
            'quit': ' [quit irc]',
#            'user_away': ' [away]',
            'kicked_channel': ' [kicked]',
            'notice': ' [notice]',
            }
        if mtype in msgy:
            s += '%s%s %s' % (self.sender, msgy[mtype], self.body)
        elif mtype == 'joined_channel':
            s += '+ %s' % (self.sender,)
        elif mtype == 'parted_channel':
            s += '- %s: %s' % (self.sender, self.data['msg'])
        elif mtype == 'nickchange':
            s += '%s %s -> %s' % (
                self.sender, self.data['oldnick'], self.data['nick'])
        else:
            import pprint

            d = dict(
                (k, v) for (k,v) in self.data.items()
                if k not in ('type', 'eid', 'cid', 'bid'))
            s += '%s [%s] eid %s bid %s cid %s\n%s' % (
                self.sender,
                self.data.get('type', '[no type]'),
                self.data.get('eid', '-'),
                self.data.get('cid', '-'),
                self.data.get('bid', '-'),
                pprint.pformat(d),
                )
        return [(self.decotags(decoration), s + '\n')]


class IRCCloudUser(messages.SnipeAddress):
    def __init__(self, backend, nick, user, host):
        self.nick = nick
        self.user = user
        self.host = host
        super().__init__(backend, [host, user, nick])

    def __str__(self):
        return '%s!%s@%s' % (self.nick, self.user, self.host)


class IRCCloudNonAddress(messages.SnipeAddress):
    def __init__(self, backend, word):
        self.word = word
        super().__init__(backend, ['', word])

    def __str__(self):
        return 'IRCCloud %s' % (self.word)
