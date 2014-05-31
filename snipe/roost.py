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

from . import messages
from . import _rooster


class Roost(messages.SnipeBackend):
    name = 'roost'

    def __init__(self, conf = {}):
        super().__init__(conf)
        self.messages = collections.deque()
        url = os.environ['ROOST_API'] #XXX should provide a default? maybe?
        # the configuration monster strikes again
        service_names = {
            'ordinator.1ts.org': 'daemon',
            }
        hostname = urllib.parse.urlparse(url).hostname
        service = service_names.get(hostname, 'HTTP') + '@' + hostname
        self.r = _rooster.Rooster(url, service)
        self.chunksize = 128
        self.loaded = False
        self.backfilling = False
        asyncio.Task(self.r.newmessages(self.new_message))


    def redisplay(self, message):
        self.conf['context'].ui.redisplay() # XXX figure out how to inform the
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

    @asyncio.coroutine
    def do_backfill(self, start, mfilter, count=0):
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
            if start is None and ms:
                start = ms[0].time
            for m in ms:
                self.messages.appendleft(m)
                if mfilter(m):
                    count += 1
            self.log.debug('%d messages, total %d', count, len(self.messages))
            if count < 8: #XXX this should configurable
                self.trigger_backfill(mfilter, count)
            self.redisplay(ms[0]) # XXX should actually be a time range, or a
                                  # pair of messages
            self.log.debug('done backfilling')

    def backfill_trigger(self, iterable, filter):
        yield from iterable
        self.trigger_backfill(filter)

    def trigger_backfill(self, filter, count=0):
        if not self.loaded:
            self.log.debug('triggering backfill')
            msgid = self.messages[0].data['id'] if self.messages else None
            asyncio.Task(self.do_backfill(msgid, filter, count))

    def walk(self, start, forward=True, filter=None):
        #XXX nearly a straight copy of the superclass
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
            date=time.ctime(self.data['time']),
            body=self.body + ('' if self.body and self.body[-1] == '\n' else '\n'),
            )

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
