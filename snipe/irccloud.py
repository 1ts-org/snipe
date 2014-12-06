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
import itertools

from . import messages
from . import util
from . import _websocket
from . import keymap
from . import interactive

IRCCLOUD = 'https://www.irccloud.com'


class IRCCloud(messages.SnipeBackend):
    name = 'irccloud'
    loglevel = util.Level('log.irccloud', 'IRCCloud')

    floodpause = util.Configurable(
        'irccloud.floodpause',
        0.5,
        'time in seconds to wait between lines in a message',
        coerce = float,
        )

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.reqid_counter = itertools.count()

        self.messages = []
        self.task = asyncio.Task(self.connect())
        self.connections = {}
        self.buffers = {}
        self.channels = {}
        self.servers = {}

    @property
    def reqid(self):
        return next(self.reqid_counter)

    @asyncio.coroutine
    def say(self, cid, to, msg):
        blob = json.dumps(dict(
            _method='say',
            _reqid=self.reqid,
            cid=cid,
            to=to,
            msg=msg,
            ))
        self.log.debug('sending: %s', blob)
        self.log.debug('self.writer=%s self.writer.send=%s', repr(self.writer), repr(self.writer.send))
        self.writer.send(blob)

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
            {'x-auth-formtoken': token,
             'content-type': 'application/x-www-form-urlencoded',
            },
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

    @keymap.bind('I C')
    def dump_irccloud_connections(self, window: interactive.window):
        import pprint
        window.show(pprint.pformat(self.connections))

    @keymap.bind('I B')
    def dump_irccloud_buffers(self, window: interactive.window):
        import pprint
        window.show(pprint.pformat(self.buffers))

    @keymap.bind('I s')
    def irccloud_say_kludge(self, window: interactive.window):
        connection = yield from window.read_string(
            'connection: ',
            wkw={
                'complete':
                interactive.completer(
                    c['hostname'] for c in self.connections.values()),
                })
        connection = connection.strip()
        for (cid, conndata) in self.connections.items():
            if conndata['hostname'] == connection:
                break
        else:
            window.whine('no such connection: %s', (connection,))
            return

        bufname = yield from window.read_string(
            'buffer: ',
            wkw={
                'complete':
                interactive.completer(
                    c['name'] for c in self.buffers.values()),
                })
        bufname = bufname.strip()
        for (bid, bufdata) in self.buffers.items():
            if bufdata['name'] == bufname:
                break
        else:
            window.whine('no such buffer:%s', (bufname,))
            return

        msg = yield from window.read_string(
            '%s;%s> ' % (connection, bufname),
            wkw={'history': 'irccloud_say'},
            )

        yield from self.say(cid, bufname, msg)

    @asyncio.coroutine
    def send(self, paramstr, body):
        params = [s.strip() for s in paramstr.split(';')]

        if not params:
            raise util.SnipeException('nowhere to send the message')

        connections = [
            c['cid'] for c in self.connections.values()
            if params[0] in c['hostname']]

        if not connections:
            raise util.SnipeException('unknown server name ' + params[0])

        if len(connections) > 1:
            raise util.SnipeException(
                'ambiguous server name %s matches %s', params[0], connections)

        (cid,) = connections

        if len(params) < 2:
            dest = '*'
        else:
            dest = params[1]

        prefix = ''
        if dest not in [
                b['name'] for b in self.buffers.values() if b['cid'] == cid]:
            prefix = '/msg ' + dest + ' '
            dest = '*'

        lines = body.splitlines()
        if len(lines) == 1:
            yield from self.say(cid, dest, prefix + lines[0])
        else:
            for line in lines:
                if line:
                    yield from self.say(cid, dest, prefix + line)
                yield from asyncio.sleep(self.floodpause)


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
                backend,
                backend.connections[m['cid']]['hostname'],
                m['from'],
                m['from_name'],
                m['from_host'])
        elif 'nick' in m and 'from_name' in m and 'from_host' in m:
            self._sender = IRCCloudUser(
                backend,
                backend.connections[m['cid']]['hostname'],
                m['nick'],
                m['from_name'],
                m['from_host'])
        else:
            self._sender = IRCCloudNonAddress(backend, 'system')

    def __str__(self):
        return str(self.time) + ' ' + repr(self.data)

    @property
    def channel(self):
        return self.backend.buffers.get(
            self.data.get('bid', -1), {}).get('name', None)

    def followup(self):
        channel = self.channel
        if not channel:
            return self.reply()
        return '; '.join([
            self.backend.name,
            self.backend.connections[self.data['cid']]['hostname'],
            channel,
            ])

    def display(self, decoration):
        tags = self.decotags(decoration)
        timestring = time.strftime('%H:%M', time.localtime(self.time))
        chunk = [((tags + ('right',), timestring + ' '))]
        mtype = self.data.get('type')
        chan = self.channel

        if chan is not None:
            chunk += [((tags + ('bold',)), chan + ' ')]

        msgy = {
            'buffer_msg': ':',
            'buffer_me_msg': '',
            'quit': ' [quit irc]',
#            'user_away': ' [away]',
            'kicked_channel': ' [kicked]',
            'notice': ' [notice]',
            }
        if mtype in msgy:
            chunk += [
                (tags + ('bold',), self.sender.short()),
                (tags, msgy[mtype] + ' ' + self.body),
                ]
        elif mtype in 'channel_topic':
            chunk += [
                (tags, self.data['from_name'] + ' set topic to '),
                (tags + ('bold',), self.data['topic']),
                ]
        elif mtype == 'joined_channel':
            chunk += [
                (tags, '+ '),
                ((tags + ('bold',)), self.sender.short()),
                ]
        elif mtype == 'parted_channel':
            chunk += [
                (tags, '- '),
                ((tags + ('bold',)), self.sender.short()),
                (tags, ': ' + self.body),
                ]
        elif mtype == 'nickchange':
            chunk += [
                (tags, self.data['oldnick']),
                (tags, ' -> '),
                ((tags + ('bold',)), self.sender.short()),
                ]
        else:
            import pprint

            d = dict(
                (k, v) for (k,v) in self.data.items()
                if k not in ('type', 'eid', 'cid', 'bid'))
            chunk += [(tags, '%s [%s] eid %s bid %s cid %s\n%s' % (
                self.sender,
                self.data.get('type', '[no type]'),
                self.data.get('eid', '-'),
                self.data.get('cid', '-'),
                self.data.get('bid', '-'),
                pprint.pformat(d),
                ))]
        return chunk + [(tags, '\n')]


class IRCCloudUser(messages.SnipeAddress):
    def __init__(self, backend, server, nick, user, host):
        self.server = server
        self.nick = nick
        self.user = user
        self.host = host
        super().__init__(backend, [server, host, user, nick])

    def __str__(self):
        return '%s; %s; %s!%s@%s' % (self.backend.name, self.server, self.nick, self.user, self.host)

    def short(self):
        return str(self.nick)

    def reply(self):
        return '%s; %s; %s' % (self.backend.name, self.server, self.nick)


class IRCCloudNonAddress(messages.SnipeAddress):
    def __init__(self, backend, word):
        self.word = word
        super().__init__(backend, ['', word])

    def __str__(self):
        return 'IRCCloud %s' % (self.word)
