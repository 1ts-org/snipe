# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe contributors
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
snipe.zulip
--------------
Backend for talking to `Zulip <https://zulip.org>`.
'''


import base64
import re
import time
import urllib.parse

from . import chunks
from . import filters
from . import imbroglio
from . import interactive
from . import keymap
from . import messages
from . import text
from . import util


_backend = 'Zulip'

HELP = """60
==================
The zulip backend
==================

Zulip setup
-----------

The Zulip backend by default works with ``https://chat.zulip.org/``, the
Zulip developer chat, but can be configured to work against other
realms. To use another Zulip realm, change ``.zulip`` in the
``backends`` configuration variable (which is ``;`` separated) to
``.zulip url=https://chat.example.com/`` (replacing the URL as needed).
To use multiple Zulip realms, you will need to also name your Zulip
backends (you can leave one without an explicit name, which will keep
the default "zulip" name). For example, ``.zulip; .zulip name=example
url=https://chat.example.com/``.

You will also need to configure authentication. First, go to Settings
(gear menu) -> "Your bots" (or
``https://chat.zulip.org/#settings/your-bots``, replacing the hostname
appropriately) and choose "Show/change your API key". Put it in
``~/.snipe/netrc`` like so: ::

 machine chat.zulip.org login myself@example.com password wytD4GoOAWHHxKshmp16sIKwdZCnfLTQ


(You need to have already signed up for the relevant Zulip realm by
other means.)

Zulip-specific message actions
---------------------------------

.. interrogate_keymap:: ZulipMessage


Zulip configuration
-------------------

.. interrogate_config:: Zulip

"""  # noqa: E501


class Zulip(messages.SnipeBackend, util.HTTP_JSONmixin):
    name = 'zulip'
    loglevel = util.Level(
        'log.zulip', 'Zulip',
        doc='loglevel for zulip backend')

    def __init__(self, context, url='https://chat.zulip.org', **kw):
        super().__init__(context, **kw)
        self.url = url.rstrip('/') + '/api/v1/'
        self.messages = []
        self.messages_by_id = {}
        self.backfilling = False
        self.loaded = False
        self.connected = imbroglio.Event()
        hostname = urllib.parse.urlparse(self.url).hostname

        creds = self.context.credentials(hostname)
        if creds is None:
            return
        self.user, self.token = creds

        credstring = f'{self.user}:{self.token}'.encode('UTF-8')
        credb64 = base64.b64encode(credstring).decode('UTF-8')
        self.setup_client_session(
            headers={'Authorization': f'Basic {credb64}'})

    async def start(self):
        await super().start()
        self.tasks.append(await imbroglio.spawn(self.connect()))
        self.tasks.append(await imbroglio.spawn(self.presence_beacon()))

    @util.coro_cleanup
    async def connect(self):
        try:
            self.params = None
            last_event_id = None
            while True:
                if self.params is None:
                    self.log.debug('registering')
                    params = await self._post('register')
                    await imbroglio.switch()

                    # TODO check for an error, backoff, etc.
                    self.params = params

                    queue_id = params['queue_id']
                    if last_event_id is None:
                        last_event_id = params['last_event_id']

                    self._senders |= set(
                        '; '.join((self.name, x['email']))
                        for x in params['realm_users'])

                    self._destinations |= self._senders
                    self._destinations |= set(
                        '; '.join((self.name, x['name'], ''))
                        for x in params['streams'])
                    await self.connected.set()

                self.log.debug(
                    'getting events, queue_id=%s, last_event_id=%s',
                    queue_id, last_event_id)

                try:
                    result = await self._get(
                        'events', queue_id=queue_id, last_event_id=last_event_id)
                except Exception:
                    self.log.exception('getting new messages')
                    self.params = None
                    continue

                await imbroglio.switch()

                msgs = []

                for event in result['events']:
                    try:
                        msg, last_event_id = (
                            await self.process_event(
                                event, last_event_id))
                    except Exception:
                        self.log.exception(
                            'processing event: %s', repr(event))
                    if msg is not None:
                        msgs.append(msg)
                    await imbroglio.switch()

                if msgs:
                    self.messages.extend(msgs)
                    self.drop_cache()
                    await imbroglio.switch()
                    # make sure that the message list remains
                    # monotonically increasing by comparing the new
                    # messages (and the last old message) pairwise.
                    self.readjust(self.messages[-len(msgs) - 1:])
                    await imbroglio.switch()
                    self.redisplay(msgs[0], msgs[-1])
        finally:
            self.connected.clear()

        self.log.debug('connect ends')

    async def process_event(self, event, last_event_id):
        type_ = event.get('type')
        msg = None
        if type_ == 'message':
            msg = ZulipMessage(self, event['message'])
        elif type_ == 'update_message':
            self.log.debug('update_message event: %s', repr(event))
            for mid in event.get('message_ids', [event['message_id']]):
                if mid in self.messages_by_id:
                    m = self.messages_by_id[mid]
                    m.update(event)
        elif type_ in ('heartbeat', 'presence'):
            pass
        else:
            self.log.debug(
                'unknown event type %s: %s',
                type_,
                repr(event),
                )
        last_event_id = max(last_event_id, event['id'])

        return msg, last_event_id

    async def presence_beacon(self):
        while True:
            await self.connected.wait()
            try:
                await self._post(
                    'users/me/presence',
                    status='active',
                    new_user_input='true')
            except Exception:
                pass  # just ignore it
            await imbroglio.sleep(60)

    @staticmethod
    def readjust(msgs):
        for a, b in zip(msgs[:-1], msgs[1:]):
            if b.time <= a.time:
                b.time = a.time + .0001

    def backfill(self, mfilter, target=None):
        self.log.debug(
            'backfill(mfilter=%s, target=%s)',
            repr(mfilter), util.timestr(target))
        self.reap_tasks()
        if not self.backfilling and not self.loaded:
            self.tasks.append(
                self.supervisor.start(self.do_backfill(mfilter, target)))

    async def do_backfill(self, mfilter, target):
        if self.backfilling:
            return
        self.backfilling = True
        try:
            if self.messages:
                anchor = self.messages[0].data['id']
            else:
                anchor = 1000000000  # XXX
            result = await self._get(
                'messages', num_before=1024, num_after=0, anchor=anchor,
                apply_markdown='false')
            await imbroglio.switch()
            if result.get('result') != 'success':
                self.log.error('backfilling: %s', repr(result))
                return
            msgs = [ZulipMessage(self, m) for m in result['messages']]
            self.log.debug('got %d: %s', len(msgs),  repr(msgs[-1]))
            if msgs and self.messages:
                self.log.debug('had %s', repr(self.messages[0]))
                if msgs[-1].data['id'] == self.messages[0].data['id']:
                    del msgs[-1]
                if not msgs:
                    self.log.debug('loaded')
                    self.loaded = True
            self.messages = msgs + self.messages
            self.readjust(self.messages)
            self.drop_cache()
        except Exception:
            self.log.exception('backfilling')
        finally:
            self.backfilling = False

    async def send(self, dest, body):
        comps = dest.split(';', 1)
        to = comps[0].strip()
        subject = comps[1].strip() if len(comps) > 1 else ''
        type_ = 'private' if '@' in to else 'stream'
        body = re.sub('(?<!\n)\n(?!\n)', ' ', body)
        result = await self._post(
            'messages', type=type_, content=body, subject=subject, to=to)
        self.log.debug('send: %s', repr(result))
        if result['result'] != 'success':
            raise util.SnipeException(result['msg'])


class ZulipMessage(messages.SnipeMessage):
    def __init__(self, backend, data):
        super().__init__(
            backend,
            data.get('content', ''),
            float(data.get('timestamp', time.time())),
            )
        self.data = data

        sender = self.data.get('sender_email')
        self._sender = ZulipAddress(backend, sender or '?')
        if sender:
            sender_set = {'; '.join((self.backend.name, sender))}
            self.backend._senders |= sender_set
            self.backend._destinations |= sender_set
        if self.data.get('type') == 'stream':
            self.stream = str(self.data['display_recipient'])
            self._chat = self.stream
            self.subject = str(self.data['subject'])
            self.backend._destinations |= {
                '; '.join((self.backend.name, self.stream, '')),
                '; '.join((self.backend.name, self.stream, self.subject)),
                }
        elif self.data.get('type') == 'private':
            self.personal = True
            self.subject = ''
            self._chat = ', '.join([
                x.get('short_name', x.get('email', str(x)))
                for x in self.data['display_recipient']])
            # XXX the following is a kludge
            self.recipient = ', '.join(
                sorted(x['email'] for x in data['display_recipient']))
        else:
            backend.log.debug('weird message: %s', repr(data))
            self.noise = True

        backend.messages_by_id[data['id']] = self

    def update(self, event):
        self.backend.log.debug('updating %s: %s', self, event)
        data = dict(self.data)
        data['_old'] = self.data
        data['_update_message'] = event
        if 'subject' in event:
            data['subject'] = event['subject']
        if 'content' in event:
            data['content'] = event['content']
            self.body = data['content']
            data.pop('_rendered', None)
            data.pop('_html', None)
        self.data = data
        self.backend.log.debug('updated: %s', repr(self.data))
        self.backend.redisplay(self, self)

    def reply(self):
        if self.personal:
            return self.backend.name + '; ' + ', '.join(
                x['email'] for x in self.data['display_recipient'])
        else:
            return self.backend.name + '; ' + self.data.get('sender_email')

    def followup(self):
        if self.personal:
            return self.reply()
        else:
            return '; '.join([self.backend.name, self.stream, self.subject])

    def filter(self, specificity=0):
        nfilter = filters.Compare('==', 'backend', self.backend.name)
        if self.personal:
            return filters.And(
                nfilter,
                filters.Truth('personal'),
                filters.Compare('==', 'recipient', self.recipient))
        else:
            nfilter = filters.And(
                nfilter,
                filters.Compare('==', 'stream', self.stream))
            if specificity > 0:
                nfilter = filters.And(
                    nfilter,
                    filters.Compare('==', 'subject', self.subject))
            if specificity > 1:
                nfilter = filters.And(
                    nfilter,
                    filters.Compare('==', 'sender', self.field('sender')))
            return nfilter

    @keymap.bind('e')
    async def edit_message(self, window: interactive.window):
        """Edit a message."""

        prompt = (
            'edit (^C^C when finished, ^G aborts) -> ' + self.backend.name +
            '; ' + self._chat + ';')

        if self.personal:
            prompt += '\n'
            text = self.body
        else:
            prompt += ' '
            text = self.subject + '\n' + self.body

        text = await window.read_string(
            prompt,
            height=10,
            content=text,
            history='send',
            fill=True,
            name='edit message %s' % (util.timestr(self)),
            )

        kw = {'message_id': self.data['id']}
        if self.personal:
            kw['content'] = text
        else:
            fields = text.split('\n', 1)
            kw['subject'] = fields[0].strip()
            kw['content'] = fields[1] if len(fields) > 1 else ''

        result = await self.backend._patch(
            'messages/' + str(self.data['id']), **kw)
        if result['result'] != 'success':
            raise util.SnipeException(result['msg'])

    class Decor(messages.SnipeMessage.Decor):
        @classmethod
        def headline(self, msg, tags=set()):
            subject = msg.data.get('subject')
            if subject:
                subject = ' ' + subject
            else:
                subject = ''

            name = msg.data.get('sender_full_name')
            if name:
                name = ' ' + name
            else:
                name = ''

            timestamp = time.strftime(
                ' %H:%M:%S\n', time.localtime(msg.data['timestamp']))

            return chunks.Chunk([
                (tags | {'bold'}, '·' + msg._chat + '>'),
                (tags, subject + ' <'),
                (tags | {'bold'}, msg.data.get('sender_email', '?')),
                (tags, '>' + name),
                (tags | {'right'}, timestamp),
                ])

        @classmethod
        def format(self, msg, tags=set()):
            if '_html' not in msg.data:
                body = msg.data.get('content', '')
                body = body.replace('\r\n', '\n')  # conform to local custom
                msg.data['_html'] = text.markdown_to_xhtml(body)
            if '_rendered' not in msg.data:
                msg.data['_rendered'] = text.xhtml_to_chunk(msg.data['_html'])
            # XXX what if there is color in the rendered data
            return chunks.Chunk(
                (tags | set(x), y) for (x, y) in msg.data['_rendered'])


class ZulipAddress(messages.SnipeAddress):

    def __init__(self, backend, text):
        self.backend = backend
        self.text = text
        super().__init__(backend, [text])

    def __str__(self):
        return self.backend.name + '; ' + self.short()

    def short(self):
        return self.text
