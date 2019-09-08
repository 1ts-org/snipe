# -*- encoding: utf-8 -*-
# Copyright © 2014 the Snipe contributors
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
snipe.irccloud
--------------
Backend for talking to `IRCCloud <https://irccloud.com>`.
'''


import functools
import itertools
import math
import pprint
import time
import urllib.parse

from . import chunks
from . import filters
from . import imbroglio
from . import interactive
from . import keymap
from . import messages
from . import util


_backend = 'IRCCloud'

IRCCLOUD = 'https://www.irccloud.com'
IRCCLOUD_API = 'https://api.irccloud.com'


class IRCCloud(messages.SnipeBackend, util.HTTP_JSONmixin):
    name = 'irccloud'
    url = IRCCLOUD_API
    loglevel = util.Level('log.irccloud', 'IRCCloud')

    floodpause = util.Configurable(
        'irccloud.floodpause',
        0.5,
        'time in seconds to wait between lines in a message',
        coerce=float,
        )

    backfill_length = util.Configurable(
        'irccloud.backfill_length', 24 * 3600,
        'only backfill this far at a time (seconds)',
        coerce=int)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.reqid_counter = itertools.count()

        self.messages = []
        self.connections = {}
        self.buffers = {}
        self.channels = {}
        self.servers = {}
        self.backfillers = []
        self.last_eid = 0
        self.new_task = None
        self.header = {}
        self.since_id = 0
        self.setup_client_session(read_timeout=5.0, conn_timeout=5.0)
        self.message_set = None

    async def start(self):
        await super().start()
        self.new_task = await imbroglio.spawn(self.connect())
        self.tasks.append(self.new_task)

    @property
    def reqid(self):
        return next(self.reqid_counter)

    async def say(self, cid, to, msg):
        await self.websocket.write(dict(
            _method='say',
            _reqid=self.reqid,
            cid=cid,
            to=to,
            msg=msg,
        ))

    async def connect(self):
        while True:
            self.log.debug('top of connect loop')
            try:
                await self.connect_once()
                await imbroglio.switch()
            except imbroglio.TimeoutError:
                self.log.debug('timeout')
            except Exception:
                self.log.exception('connect once:')
            finally:
                self.state_set(messages.BackendState.DISCONNECTED)
            await imbroglio.sleep(10)

    async def connect_once(self):
        creds = self.context.credentials(
            urllib.parse.urlparse(IRCCLOUD).netloc)
        if creds is None:
            return
        username, password = creds

        self.state_set(messages.BackendState.CONNECTING)
        self.log.debug('retrieving formtoken')
        result = await self._post(
            urllib.parse.urljoin(IRCCLOUD, '/chat/auth-formtoken'), '')
        if not result.get('success'):
            self.log.warn('Could not get formtoken: %s', repr(result))
            return
        token = result['token']

        self.log.debug('retrieving logging in')
        for backoff in ((1/16) * 2**min(i, 9) for i in itertools.count()):
            try:
                await self.reset_client_session_headers(
                    {'x-auth-formtoken': token})
                result = await self._post(
                    urllib.parse.urljoin(IRCCLOUD, '/chat/login'),
                    email=username,
                    password=password,
                    token=token,
                    )
                break
            except util.JSONDecodeError:
                self.log.exception('logging in, sleeping then trying again')
                await imbroglio.sleep(backoff)

        if not result.get('success'):
            self.log.warn('login failed: %s', repr(result))
            return
        self.session = result['session']
        await self.reset_client_session_headers(dict(
            compress='gzip',
            cookie=f'session={self.session}',
            ))

        self.log.debug('connecting to websocket')
        url = IRCCLOUD_API
        if self.header.get('streamid'):
            url += '?' + urllib.parse.urlencode([
                ('stream_id', self.header.get('streamid')),
                ('since_id', str(self.last_eid)),
                ])
            self.since_id = self.last_eid

        self.websocket = util.JSONWebSocket(self.log)
        try:
            await self.websocket.connect(
                url,
                [('Origin', IRCCLOUD_API.encode()),
                 ('Cookie', f'session={self.session}')]
                )

            self.message_set = None

            self.state_set(messages.BackendState.IDLE)

            while True:
                waittime = self.header.get('idle_interval', 30000) / 1000
                m = None
                async with imbroglio.Timeout(waittime):
                    m = await self.websocket.read()
                if m is None:
                    self.log.error('irccloud socket idle too long')
                    return
                self.log.debug('message: %s', repr(m))
                try:
                    await self.incoming(m)
                except Exception:
                    self.log.exception(
                        'Processing incoming message: %s', repr(m))
                    raise
        except Exception:
            self.log.exception('in websocket loop')
        finally:
            self.log.debug('leaving connect loop')
            if self.websocket is not None:
                await self.websocket.close()
            self.websocket = None

    async def process_message(self, msglist, m):
        if m is None:
            return

        mtype = m.get('type')

        self.log.debug(f'process_message: {mtype}')

        last_eid = self.last_eid

        eid = int(m.get('eid', 0))
        if eid > last_eid:
            self.last_eid = eid

        if mtype == 'idle':
            pass
        elif mtype == 'header':
            self.header = m
        elif mtype in ('banned', 'socket_closed'):
            # the system seems to generate multiple
            # socket_closed/banned messages with the same eid/time
            # with distinct cids, which confuses the message list.
            pass
        elif mtype in ('num_invites', 'stat_user',):
            # we can presumably do something useful with this later
            pass
        elif mtype in (
                'backlog_starts', 'end_of_backlog',
                'you_joined_channel', 'self_details', 'your_unique_id',
                'cap_ls', 'cap_req', 'cap_ack', 'user_account',
                'heartbeat_echo',
                ):
            # presumptively useless-to-us metadata
            pass
        elif mtype == 'oob_include':
            try:
                self.message_set = set(float(m) for m in self.messages)
                await self.include(m['url'])
            finally:
                self.message_set = None
        elif mtype == 'oob_skipped':
            await imbroglio.switch()
            self.message_set = set(float(m) for m in self.messages)
            await imbroglio.switch()
        elif mtype == 'backlog_complete':
            self.message_set = None
        elif mtype in ('makeserver', 'server_details_changed'):
            self.connections.setdefault(m['cid'], m).update(m)
        elif mtype == 'status_changed':
            self.connections[m['cid']]['status'] = m['new_status']
            self.connections[m['cid']]['fail_info'] = m['fail_info']
        elif mtype == 'isupport_params':
            self.servers.setdefault(m['cid'], m).update(m)
        elif mtype == 'makebuffer':
            self.buffers.setdefault(m['bid'], m).update(m)
        elif mtype == 'channel_init':
            self.channels.setdefault(m['bid'], m).update(m)
        else:
            if eid < self.since_id and eid > 0:
                return
            if 'bid' in m:
                buf = self.buffers[m['bid']]
                if 'have_eid' not in buf or m['eid'] < buf['have_eid']:
                    buf['have_eid'] = m['eid']
            msg = IRCCloudMessage(self, m)
            if self.message_set and float(msg) in self.message_set:
                self.log.debug(f'dropping {float(msg)} {msg!r}')
                return
            msglist.append(msg)
            if len(msglist) > 1 and msglist[-1] < msglist[-2]:
                msglist.sort()
            # really this should come from the current channel membership
            self._destinations.add(msg.reply())
            self._destinations.add(msg.followup())
            self._senders.add(msg.reply())
            return msg
        return None

    async def incoming(self, m):
        try:
            msg = await self.process_message(self.messages, m)
        except KeyError:
            # should make an error-message
            self.log.error('failed {m}')
            return
        self.drop_cache()
        if msg is not None:
            self.redisplay(msg, msg)

    async def include(self, url):
        self.log.debug('including %s', url)
        self.state_set(messages.BackendState.LOADING)
        try:
            oob_data = await self._get(url)
            if 'success' in oob_data and not oob_data['success']:
                self.log.error(
                    f'including out of band data {url} failure:' +
                    f' f{oob_data["message"]}')
                return

            included = []

            await imbroglio.switch()
            for m in oob_data:
                await self.process_message(included, m)
                await imbroglio.switch()
            included.sort()

            if included:
                self.messages = list(messages.merge([self.messages, included]))
                self.drop_cache()
                self.redisplay(included[0], included[-1])
        finally:
            self.state_set(messages.BackendState.IDLE)

    async def send(self, paramstr, body):
        params = paramstr.split()

        if not params:
            raise util.SnipeException('nowhere to send the message')

        connections = [
            (c['cid'], c['hostname']) for c in self.connections.values()
            if params[0] in c['hostname']]

        if not connections:
            raise util.SnipeException('unknown server name ' + params[0])

        if len(connections) > 1:
            raise util.SnipeException(
                f'ambiguous server name {params[0]}'
                f' matches {list(zip(*connections))[1]}')

        ((cid, _)), = connections

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
            await self.say(cid, dest, prefix + lines[0])
        else:
            for line in lines:
                if line:
                    await self.say(cid, dest, prefix + line)
                await imbroglio.sleep(self.floodpause)

    @keymap.bind('I C')
    def dump_connections(self, window: interactive.window):
        window.show(pprint.pformat(self.connections))

    @keymap.bind('I c')
    def dump_channels(self, window: interactive.window):
        window.show(pprint.pformat(self.channels))

    @keymap.bind('I B')
    def dump_buffers(self, window: interactive.window):
        window.show(pprint.pformat(self.buffers))

    @keymap.bind('I S')
    def dump_servers(self, window: interactive.window):
        window.show(pprint.pformat(self.servers))

    @keymap.bind('I H')
    def dump_header(self, window: interactive.window):
        window.show(pprint.pformat(self.header))

    def backfill(self, mfilter, target=None):
        self.log.debug('backfill([filter], %s)', util.timestr(target))
        live = [
            b for b in self.buffers.values()
            if (not b.get('deferred', False)
                and (('min_eid' not in b or 'have_eid' not in b)
                or b['have_eid'] > b['min_eid']))]
        if target is None:
            target = min(b.get('have_eid', 0) for b in live) - 1
        elif math.isfinite(target):
            target = int(target * 1000000)
        live = [b for b in live if b.get('have_eid', 0) > target]
        t0 = time.time()
        nb = []
        for task, when in self.backfillers:
            if (t0 - when) > 30.0:
                task.cancel()
            if not task.is_done():
                nb.append((task, when))
        self.backfillers = nb
        self.reap_tasks()
        self.log.debug('%d backfillers active', len(self.backfillers))
        if not self.backfillers:
            for b in live:
                t = self.supervisor.start(self.backfill_buffer(b, target))
                self.backfillers.append((t, t0))
                self.tasks.append(t)
            if self.backfillers:
                self.state_set(messages.BackendState.BACKFILLING)

    async def backfill_buffer(self, buf, target):
        self.log.debug(
            'top of backfill_buffer([%s %s], %s)',
            buf['bid'], buf.get('have_eid'), target)
        try:
            while True:
                await imbroglio.sleep(2)
                self.log.debug(
                    'loop backfill_buffer([%s %s], %s)',
                    buf['bid'], buf.get('have_eid'), target)
                try:
                    target = max(
                        target,
                        buf['have_eid'] - self.backfill_length * 1000000)

                    count = 1
                    while True:
                        try:
                            self.log.debug(
                                'backfilling %s retrieving backlog, try=%d',
                                buf['name'], count)
                            oob_data = await self._get(
                                '/chat/backlog',
                                cid=buf['cid'],
                                bid=buf['bid'],
                                num=256,
                                beforeid=buf['have_eid'] - 1,
                                )
                        except Exception:
                            self.log.exception(
                                'backfilling %s, try=%d, sleeping',
                                buf['name'], count)
                            count += 1
                            await imbroglio.sleep(1)
                            self.log.error(
                                'backfilling %s, try=%d, done sleeping',
                                buf['name'], count)
                            continue
                        break
                    included = []

                    if isinstance(oob_data, dict):
                        raise Exception(str(oob_data))

                    oldest = buf['have_eid']
                    self.log.debug('t = %f', oldest / 1000000)

                    await imbroglio.switch()
                    for m in oob_data:
                        if m['bid'] == -1:
                            self.log.error('? %s', repr(m))
                            continue
                        await self.process_message(included, m)
                        await imbroglio.switch()

                    if len(included) == 0:
                        self.log.debug(
                            'got zero messages, clamping min_eid'
                            ' from %d to %d',
                            buf.get('min_eid', -1), buf['have_eid'])
                        buf['min_eid'] = buf['have_eid']
                        break

                    included.sort()
                    self.log.debug('processed %d messages', len(included))

                    clip = None
                    included.reverse()
                    for i, m in enumerate(included):
                        if m.data['eid'] >= oldest:
                            clip = i
                            self.log.debug(
                                'BETRAYAL %d %f %s',
                                i, m.data['eid'] / 1000000, repr(m.data))
                    if clip is not None:
                        included = included[clip + 1:]
                    included.reverse()

                    if included:
                        self.log.debug('merging %d messages', len(included))
                        l = len(self.messages)
                        self.messages = list(messages.merge(
                            [self.messages, included]))
                        self.log.debug(
                            'len(self.messages): %d -> %d',
                            l, len(self.messages))
                        self.drop_cache()
                        self.redisplay(included[0], included[-1])
                except Exception:
                    self.log.exception('backfilling %s', buf)
                    return

                self.log.debug(
                    'bottom of backfill_buffer([%s %s], %s) loop',
                    buf['bid'], buf.get('have_eid'), target)
                self.log.debug(' have_eid %s', buf.get('have_eid', '-'))
                self.log.debug(' min_eid %s', buf.get('min_eid', '-'))
                if (not math.isfinite(target)
                        or target >= buf['have_eid']
                        or not (
                            'min_eid' not in buf
                            or buf['have_eid'] > buf['min_eid'])):
                    break
        finally:
            if len([t for t in self.backfillers if not t.is_done()]) < 2:
                self.state_set(messages.BackendState.IDLE)

    @keymap.bind('I D')
    async def disconnect(self):
        self.reap_tasks()
        if self.new_task is None:
            return
        await self.shutdown()
        self.new_task = None

    @keymap.bind('I R')
    async def reconnect(self):
        if self.new_task is not None:
            await self.disconnect()
        await self.start()


class IRCCloudMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        when = m.get('eid', -1)
        if when == -1:
            when = time.time()
        else:
            when = when / 1000000

        mtype = m.get('type')

        body = m.get('msg', repr(m))
        if mtype == 'motd_response':
            body = '\n'.join([m['start']] + m['lines'] + [body])

        super().__init__(backend, body, when)
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

        self.channel = self.backend.buffers.get(
            self.data.get('bid', -1), {}).get('name', None)

        self.personal = (
            self.channel and self.channel != '*'
            and self.channel[:1] not in '#!&:')
        self.outgoing = m.get('self', False)
        self.noise = mtype not in ('buffer_msg', 'buffer_me_msg')
        self.unformatted = mtype not in (
            'buffer_msg', 'buffer_me_msg', 'quit', 'kicked_channel',
            'notice', 'channel_topic', 'joined_channel',
            'parted_channel', 'nickchange', 'user_channel_mode',
            'channel_mode_is', 'user_mode', 'motd_response',
            'server_luserconns', 'server_n_global', 'server_n_local',
            'server_luserme', 'server_luserchannels',
            'server_luserunknown', 'server_luserop',
            'server_luserclient', 'server_created', 'server_yourhost',
            'server_welcome', 'services_down', 'myinfo',
            'channel_mode_list_change', 'connecting_failed',
            'logged_in_as', 'sasl_success', 'hidden_host_set',
            'channel_url', 'channel_mode', 'error', 'quit_server',
            'nickname_in_use', 'sasl_aborted', 'you_nickchange',
            'banned',
            )

    def __repr__(self):
        return (
            '<' + self.__class__.__name__ + ' '
            + repr(self.time) + ' '
            + repr(self.sender) + ' '
            + str(len(self.body)) + ' chars'
            + ' ' + str(self.channel)
            + (' personal' if self.personal else '')
            + (' noise' if self.noise else '')
            + '>'
            )

    def __str__(self):
        return str(self.time) + ' ' + repr(self.data)

    def followup(self):
        channel = self.channel
        if not channel:
            return self.reply()
        return '%s; %s %s' % (
            self.backend.name,
            self.backend.connections[self.data['cid']]['hostname'],
            channel,
            )

    def filter(self, specificity=0):
        if self.channel:
            nfilter = filters.And(
                filters.Compare('==', 'backend', self.backend.name),
                filters.Compare('=', 'channel', self.channel))
            if specificity:
                nfilter = filters.And(
                    nfilter,
                    filters.Compare('=', 'sender', self.field('sender')))
            return nfilter
        return super().filter(specificity)

    class Decor(messages.SnipeMessage.OnelineDecor):
        @classmethod
        def headline(self, msg, tags=frozenset()):
            timestring = time.strftime(' %H:%M:%S', time.localtime(msg.time))
            chunk = chunks.Chunk()
            mtype = msg.data.get('type')
            chan = msg.channel

            if chan is not None:
                chunk += [((tags | {'bold'}), chan + ' ')]

            msgy = {
                'buffer_msg': ':',
                'buffer_me_msg': '',
                'quit': ' [quit irc]',
                # 'user_away': ' [away]',
                'kicked_channel': ' [kicked]',
                'notice': ' [notice]',
                }
            if mtype in msgy:
                chunk += [
                    (tags | {'bold'}, msg.sender.short()),
                    (tags | {'fill'}, msgy[mtype] + ' '),
                    ] + irc_format(msg.body, frozenset(tags | {'fill'}))
            elif mtype in (
                    'motd_response', 'server_luserconns',
                    'server_n_global', 'server_n_local', 'server_luserme',
                    'server_luserchannels', 'server_luserunknown',
                    'server_luserop', 'server_luserclient',
                    'server_created', 'server_yourhost', 'server_welcome',
                    'services_down', 'logged_in_as', 'sasl_success',
                    'sasl_aborted', 'error', 'nickname_in_use',
                    ):
                chunk.append((
                    tags,
                    (msg.data['server'] +
                        ': ' if 'server' in msg.data else '')))
                chunk.extend(irc_format(msg.body, frozenset(tags)))

            elif mtype == 'banned':
                chunk.append(
                    (tags, msg.data['server'] + ': ' + msg.data['reason']))
            elif mtype == 'hidden_host_set':
                chunk.append((
                    tags,
                    msg.data['server'] + ': '
                    + msg.data['hidden_host'] + ' ' + msg.body))
            elif mtype == 'myinfo':
                chunk.append((
                    tags,
                    msg.data['server']
                    + ': ' + msg.data['version']
                    + ', user modes: ' + msg.data['user_modes']
                    + ', channel modes: ' + ''.join(sorted(
                        msg.data['channel_modes'] + msg.data['rest']))))
            elif mtype == 'connecting_failed':
                chunk.append((
                    tags,
                    '%s:%s%s connection failed: %s' % (
                        msg.data['hostname'],
                        msg.data['port'],
                        ' (ssl)' if msg.data['ssl'] else '',
                        msg.data['reason'])))
            elif mtype == 'quit_server':
                chunk.append((
                    tags,
                    '%s:%s%s %s quit%s' % (
                        msg.data['hostname'],
                        msg.data['port'],
                        ' (ssl)' if msg.data['ssl'] else '',
                        msg.data['nick'],
                        ': ' + msg.data['msg'] if msg.data['msg'] else '')))
            elif mtype == 'you_nickchange':
                chunk.append((
                    tags,
                    'you are now %s (née %s)' % (
                        msg.data['newnick'], msg.data['oldnick'])))
            elif mtype == 'channel_topic':
                chunk += [
                    (tags, msg.data['from_name'] + ' set topic to '),
                    (tags | {'bold'}, msg.data['topic']),
                    ]
            elif mtype == 'channel_timestamp':
                chunk += [
                    (tags, 'created ' + time.ctime(msg.data['timestamp']))]
            elif mtype == 'user_channel_mode':
                chunk.append((tags, msg.data['nick'] + ' set '))
                out = []
                for prefix, operation in [('+', 'add'), ('-', 'remove')]:
                    for action in msg.data['ops'][operation]:
                        out.append(
                            '%s%s %s' % (
                                prefix, action['mode'], action['param']))
                chunk.append((tags | {'bold'}, ' '.join(out)))
            elif mtype == 'user_mode':
                chunk += [
                    (tags, msg.data['from'] + ' set '),
                    (tags | {'bold'}, msg.data['diff']),
                    (tags, ' ('),
                    (tags | {'bold'}, msg.data['newmode']),
                    (tags, ') on you'),
                    ]
            elif mtype in ('channel_mode_is', 'channel_mode'):
                chunk += [
                    (tags, 'mode ',),
                    (tags | {'bold'}, msg.data['diff'])]
            elif mtype == 'channel_url':
                chunk += [
                    (tags, 'url: '),
                    (tags | {'bold'}, msg.data['url'])]
            elif mtype == 'channel_mode_list_change':
                chunk += [
                    (tags, 'channel mode '),
                    (tags | {'bold'}, msg.data['diff'])]
            elif mtype == 'joined_channel':
                chunk += [
                    (tags, '+ '),
                    ((tags | {'bold'}), msg.sender.short()),
                    ]
            elif mtype == 'parted_channel':
                chunk += [
                    (tags, '- '),
                    ((tags | {'bold'}), msg.sender.short()),
                    (tags, ': ' + msg.body),
                    ]
            elif mtype == 'nickchange':
                chunk += [
                    (tags, msg.data['oldnick']),
                    (tags, ' -> '),
                    ((tags | {'bold'}), msg.sender.short()),
                    ]
            else:
                import pprint

                d = dict(
                    (k, v) for (k, v) in msg.data.items()
                    if k not in ('type', 'eid', 'cid', 'bid'))
                chunk += [(tags, '%s [%s] eid %s bid %s cid %s\n%s' % (
                    msg.sender,
                    msg.data.get('type', 'no type'),
                    msg.data.get('eid', '-'),
                    msg.data.get('cid', '-'),
                    msg.data.get('bid', '-'),
                    pprint.pformat(d),
                    ))]

            chunk += [(tags | {'right'}, timestring)]
            return chunk


class IRCCloudUser(messages.SnipeAddress):
    def __init__(self, backend, server, nick, user, host):
        self.server = server
        self.nick = nick
        self.user = user
        self.host = host
        super().__init__(backend, [server, host, user, nick])

    def __str__(self):
        return '%s; %s %s' % (self.backend.name, self.server, self.nick)

    def short(self):
        return str(self.nick)


class IRCCloudNonAddress(messages.SnipeAddress):
    def __init__(self, backend, word):
        self.word = word
        super().__init__(backend, ['', word])

    def __str__(self):
        return '%s; IRCCloud %s' % (self.backend.name, self.word)


@functools.lru_cache(1024)
def irc_format(text, tags=frozenset()):
    """
    translates text containing irc formatting code into a chunk
    color: 0x03fg[,bg]
        color codes:
           0 white
           1 black
           2 blue
           3 green
           4 red
           5 brown
           6 purple
           7 orange
           8 yellow
           9 light green
           10 teal
           11 cyan
           12 light blue
           13 pink
           14 grey
           15 light grey
           99 default
    bold: 0x02
    italic 0x1d
    underline 0x1f
    reverse fg, bg 0x16
    reset 0x0f
    """

    cur_tags = frozenset(tags)
    x_tags = tags
    chunk = chunks.Chunk()
    sl = []
    number = None
    state = 'start'
    defs = {
        x[0] + ':': x[1] for x in (y.split(':', 1) for y in tags if ':' in y)}

    def emit():
        nonlocal sl, cur_tags
        if sl:
            chunk.extend([(cur_tags, ''.join(sl))])
            sl = []

    def get_color():
        nonlocal number
        return {
            0: 'white',
            1: 'black',
            2: 'blue',
            3: 'green',
            4: 'red',
            5: 'brown',
            6: 'purple',
            7: 'orange',
            8: 'yellow',
            9: 'light green',
            10: 'cyan4',
            11: 'cyan',
            12: 'light blue',
            13: 'pink',
            14: 'grey',
            15: 'light grey',
            99: 'default',
            }.get(number)

    for c in text:
        # kludge so we can go back the start state without consuming a
        # character:
        hold = True
        while hold:
            hold = False
            if state == 'start':
                if c == '\x03':
                    x_tags = cur_tags
                    number = None
                    state = 'fg:'
                elif c == '\x0f':
                    if cur_tags != tags:
                        emit()
                    cur_tags = frozenset(tags)
                elif c == '\x02':
                    emit()
                    cur_tags ^= {'bold'}
                elif c == '\x1d':
                    emit()
                    cur_tags ^= {'dim'}  # italic, but curses
                elif c == '\x1f':
                    emit()
                    cur_tags ^= {'underline'}
                elif c == '\x16':
                    emit()
                    cur_tags ^= {'reverse'}
                elif c != '\n' and c != '\t' and c < ' ' or c == '\x7f':
                    emit()
                    chunk.extend([(
                        {'bold'} | cur_tags,
                        '^' + chr((ord(c) + ord('@')) & 127))])
                else:  # plain text character
                    sl.append(c)
            elif state in {'fg:', 'bg:'}:
                if c in '0123456789':
                    if number is None:
                        number = 0
                    number = 10 * number + int(c)
                else:
                    color = get_color()
                    if number is not None and color is not None:
                        cur_tags = frozenset(
                            x for x in cur_tags if not x.startswith(state))
                        if color == 'default':
                            color = defs.get(state)
                        if color is not None:
                            cur_tags |= {state + color}
                        if cur_tags != x_tags:
                            cur_tags, x_tags = x_tags, cur_tags
                            emit()
                            cur_tags = x_tags
                    if state == 'fg:' and c == ',':
                        state = 'bg:'
                    else:
                        state = 'start'
                        hold = True
    emit()

    return chunk
