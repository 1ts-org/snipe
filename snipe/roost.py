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
import collections
import itertools
import time
import shlex
import os
import urllib.parse
import contextlib
import re

from . import messages
from . import _rooster
from . import util


class Roost(messages.SnipeBackend):
    name = 'roost'

    backfill_count = util.Configurable(
        'roost.backfill_count', 8,
        'Keep backfilling until you have this many messages'
        ' unless you hit the time limit')
    backfill_length = util.Configurable(
        'roost.backfill_length', 24 * 3600 * 7,
        'only backfill this looking for roost.backfill_count messages')
    url = util.Configurable(
        'roost.url', 'https://roost-api.mit.edu')
    service_name = util.Configurable(
        'roost.servicename', 'HTTP',
        "Kerberos servicename, you probably don't need to change this")
    realm = util.Configurable(
        'roost.realm', 'ATHENA.MIT.EDU',
        'Zephyr realm that roost is fronting for')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = []
        self.r = _rooster.Rooster(self.url, self.service_name)
        self.chunksize = 128
        self.loaded = False
        self.backfilling = False
        asyncio.Task(self.r.newmessages(self.new_message))


    def redisplay(self, message):
        self.context.ui.redisplay() # XXX figure out how to inform the
                                    # redisplay of which messages need
                                    # refreshing

    @asyncio.coroutine
    def send(self, paramstr, body):
        import getopt
        import pwd
        import os

        self.log.debug('send paramstr=%s', paramstr)

        flags, recipients = getopt.getopt(shlex.split(paramstr), 'c:i:O:')

        flags = dict(flags)
        self.log.debug('send flags=%s', repr(flags))

        if not recipients:
            recipients=['']

        for recipient in recipients:
            message = {
                'class': flags.get('-c', 'MESSAGE'),
                'instance': flags.get('-i', 'PERSONAL'),
                'recipient': recipient,
                'opcode': flags.get('-O', ''),
                'signature': pwd.getpwuid(os.getuid()).pw_gecos.split(',')[0],#XXX
                'message': body,
                }

            self.log.debug('sending %s', repr(message))

            result = yield from self.r.send(message)
            self.log.info('sent to %s: %s', recipient, repr(result))

    @asyncio.coroutine
    def new_message(self, m):
        msg = RoostMessage(self, m)
        self.messages.append(msg)
        self.redisplay(msg)

    def backfill_trigger(self, iterable, filter):
        yield from iterable
        self.trigger_backfill(filter)

    def trigger_backfill(self, filter, count=0, origin=None):
        if not self.loaded:
            self.log.debug('triggering backfill')
            msgid = None
            if self.messages:
                msgid = self.messages[0].data['id']
                if origin is None:
                    origin = self.messages[0].time
            asyncio.Task(self.do_backfill(msgid, filter, count, origin))

    @asyncio.coroutine
    def do_backfill(self, start, mfilter, count, origin):
        yield from asyncio.sleep(.0001)

        @contextlib.contextmanager
        def backfillguard():
            if self.backfilling:
                yield True
            else:
                self.log.debug('entering guard')
                self.backfilling = True
                yield False
                self.backfilling = False
                self.log.debug('leaving guard')

        with backfillguard() as already:
            if already:
                self.log.debug('already backfiling')
                return

            if mfilter is None:
                mfilter = lambda m: True

            if self.loaded:
                self.log.debug('no more messages to backfill')
                return
            self.log.debug('backfilling')
            chunk = yield from self.r.messages(start, self.chunksize)

            if chunk['isDone']:
                self.log.info('IT IS DONE.')
                self.loaded = True
            ms = [RoostMessage(self, m) for m in chunk['messages']]
            count += len([m for m in ms if mfilter(m)])
            ms.reverse()
            self.messages = ms + self.messages
            self.log.warning('%d messages, total %d', count, len(self.messages))
            if (count < self.backfill_count
                and ms and ms[0].time > (origin - self.backfill_length)):
                self.trigger_backfill(mfilter, count, origin)
            self.redisplay(ms[0]) # XXX should actually be a time range, or a
                                  # pair of messages
            self.log.debug('done backfilling')

    def walk(self, start, forward=True, filter=None):
        #XXX nearly a straight copy of the superclass
        self.log.debug('walk(%s, %s, %s)', start, forward, filter)
        if start is None:
            pred = lambda x: False
        elif getattr(start, 'backend', None) is self:
            # it's a message object that belongs to us
            pred = lambda x: x != start
        else:
            if hasattr(start, 'time'):
                start = start.time
            # it's a time
            if forward:
                pred = lambda x: x.time < start
            else:
                pred = lambda x: x.time > start
        l = self.messages
        if not forward:
            l = iter(reversed(l))
            l = self.backfill_trigger(l, filter)
        if start:
            l = itertools.dropwhile(pred, l)
        if filter is not None:
            l = (m for m in l if filter(m))
        return l

class RoostMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        super().__init__(backend, m['message'], m['receiveTime'] / 1000)
        self.data = m
        self._sender = RoostPrincipal(backend, m['sender'])

    @property
    def personal(self):
        return self.data['recipient'] and self.data['recipient'][0] != '@'

    def __str__(self):
        return (
            'Class: {class_} Instance: {instance} Recipient: {recipient}'
            '{opcode}\n'
            'From: {signature} <{sender}> at {date}\n'
            '{body}\n').format(
            class_=self.data['class'],
            instance=self.data['instance'],
            recipient=self.data['recipient'],
            opcode=(
                ''
                if not self.data['opcode']
                else ' [{}]'.format(self.data['opcode'])),
            signature=self.data['signature'],
            sender=self.sender,
            date=time.ctime(self.data['time'] / 1000),
            body=self.body + ('' if self.body and self.body[-1] == '\n' else '\n'),
            )

    def display(self, decoration):
        tags = self.decotags(decoration)
        chunk = [
            (tags + ('bold',), self.field('sender')),
            ]
        instance = self.data['instance']
        instance = instance or "''"
        if self.personal:
            chunk += [(tags + ('bold',), ' (personal)')]
        if not self.personal or self.data['class'].lower() != 'message':
            chunk += [
                (tags, ' -c '),
                (tags + ('bold',), self.data['class']),
                ]
        if instance.lower() != 'personal':
            chunk += [
                (tags, ' -i '),
                (tags + ('bold',), instance),
                ]

        if self.data['recipient'] and self.data['recipient'][0] == '@':
            chunk += [(tags + ('bold',), ' ' + self.data['recipient'])]

        if self.data['opcode']:
            chunk += [(tags, ' [' + self.data['opcode'] + ']')]
        chunk += [(tags, ' ' + time.ctime(self.data['time'] / 1000) + '\n')]
        if self.data['signature'].strip():
            chunk += [
                (tags, ' '),
                (tags + ('bold',), self.data['signature'].strip()),
                (tags, '\n'),
                ]
        body = self.body
        if body[-1:] != '\n':
            body += '\n'
        chunk += [(tags, body)]

        return chunk

    class_un = re.compile(r'^(un)*')
    class_dotd = re.compile(r'(\.d)*$')
    def canon(self, field, value):
        if field == 'sender':
            value = str(value)
            atrealmlen = len(self.backend.realm) + 1
            if value[-atrealmlen:] == '@' + self.backend.realm:
                return value[:-atrealmlen]
        elif field == 'class':
            value = value.lower() #XXX do proper unicode thing
            x1, x2 = self.class_un.search(value).span()
            value = value[x2:]
            x1, x2 = self.class_dotd.search(value).span()
            value = value[:x1]
        elif field == 'instance':
            value = value.lower() #XXX do proper unicode thing
        elif field == 'opcode':
            value = value.lower().strip()
        return value

    def replystr(self):
        l = []
        if self.data['recipient']:
            if self.data['class'].upper() != 'MESSAGE':
                l += ['-c', self.data['class']]
            if self.data['instance'].upper() != 'PERSONAL':
                l += ['-i', self.data['instance']]
        l.append(str(self.sender))

        return ' '.join(shlex.quote(s) for s in l)

    def followupstr(self):
        l = []
        if self.data['recipient']:
            return self.replystr()
        if self.data['class'].upper() != 'MESSAGE':
            l += ['-c', self.data['class']]
        if self.data['instance'].upper() != 'PERSONAL':
            l += ['-i', self.data['instance']]
        return ' '.join(shlex.quote(s) for s in l)

class RoostPrincipal(messages.SnipeAddress):
    def __init__(self, backend, principal):
        self.principal = principal
        super().__init__(backend, [principal])

    def __str__(self):
        return self.principal

class RoostTriplet(messages.SnipeAddress):
    def __init__(self, backend, class_, instance, recipient):
        self.class_ = class_
        self.instance = instance
        self.recipient = recipient
        super().__init__(backend, [class_, instance, recipient])
