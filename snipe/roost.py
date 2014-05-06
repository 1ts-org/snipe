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

from . import messages
from . import _rooster


class Roost(messages.SnipeBackend):
    name = 'roost'

    def __init__(self, conf = {}):
        super().__init__(conf)
        self.messages = collections.deque()
        self.r = _rooster.Rooster(
            'https://ordinator.1ts.org', 'daemon@ordinator.1ts.org')
        self.chunksize = 128
        self.loaded = False
        self.backfilling = False
        asyncio.Task(self.r.newmessages(self.new_message))


    def redisplay(self, message):
        self.conf['context'].ui.redisplay() # XXX figure out how to inform the
                                            # redisplay of which messages need
                                            # refreshing

    @asyncio.coroutine
    def new_message(self, m):
        msg = RoostMessage(self, m)
        self.messages.append(msg)
        self.redisplay(msg)

    @asyncio.coroutine
    def do_backfill(self, start):
        if not self.backfilling:
            self.backfilling = True
            self.log.debug('backfilling')
            if self.loaded:
                return
            chunk = yield from self.r.messages(start, self.chunksize)
            import pprint
            self.log.debug('%s', pprint.pformat(chunk))
            if chunk['isDone']:
                self.log.debug('IT IS DONE.')
                self.loaded = True
            ms = [RoostMessage(self, m) for m in chunk['messages']]
            for m in ms:
                self.messages.appendleft(m)
            self.log.debug('now %d messages', len(self.messages))
            self.redisplay(ms[0]) # XXX should actually be a time range, or a
                                  # pair of messages
            self.log.debug('done backfilling')
            self.backfilling = False
        else:
            self.log.debug('already backfilling')

    def backfill_trigger(self, iterable):
        yield from iterable
        if not self.loaded:
            msgid = self.messages[0].data['id'] if self.messages else None
            asyncio.Task(self.do_backfill(msgid))

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
            l = self.backfill_trigger(l)
        if start:
            l = itertools.dropwhile(pred, l)
        if filter is not None:
            l = (m for m in l if filter(m))
        return l

class RoostMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        self.data = m
        super().__init__(backend, m['message'], m['time'] / 1000)
        self._sender = RoostPrincipal(backend, m['sender'])

    def __str__(self):
        return (
            'To: Class: {class_} Instance: {instance} Recipient: {recipient}'
            '{opcode}\n'
            'From: {signature} <{sender}> at {date}\n'
            '{body}').format(
            class_=self.data['class'],
            instance=self.data['instance'],
            recipient=self.data['recipient'],
            opcode=(
                ''
                if not self.data['opcode']
                else ' [{}]'.format(self.data['opcode'])),
            signature=self.data['signature'],
            sender=self.sender,
            date=time.ctime(self.time),
            body=self.body,
            )

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
