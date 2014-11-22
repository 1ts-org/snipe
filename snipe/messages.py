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


import itertools
import time
import logging
import functools
import bisect

from . import util


class SnipeAddress:
    backend = None
    path = []

    def __init__(self, backend, path=[]):
        self.backend = backend
        self.path = path

    @property
    def address(self):
        return [self.backend] + self.path

    def __str__(self):
        return ', '.join([self.backend.name] + self.path)

    def __repr__(self):
        return (
            '<' + self.__class__.__name__+ ' '
            + self.backend.name + (' ' if self.path else '')
            + ', '.join(self.path) + '>'
            )


@functools.total_ordering
class SnipeMessage:
    def __init__(self, backend, body='', mtime=None):
        self._sender = None
        self.backend = backend
        self.time = time.time() if mtime is None else mtime
        self.body = body
        self.data = {}

    @property
    def sender(self):
        if self._sender is None:
            self._sender = SnipeAddress(self.backend)
        return self._sender

    def __str__(self):
        return '%s %s\n%s' % (
            time.strftime('%H:%M', time.localtime(self.time)),
            self.sender,
            self.body,
            )

    def __repr__(self):
        return (
            '<' + self.__class__.__name__ + ' '
            + repr(self.time) + ' '
            + repr(self.sender) + ' '
            + str(len(self.body)) + ' chars>'
            )

    @staticmethod
    def decotags(decoration):
        tags = []
        if 'foreground' in decoration:
            tags.append('fg:' + decoration['foreground'])
        if 'background' in decoration:
            tags.append('bg:' + decoration['background'])
        return tuple(tags)

    def display(self, decoration):
        s = str(self)
        if s and s[-1] != '\n':
            s += '\n'
        return [(self.decotags(decoration), s)]

    @staticmethod
    def canon(field, value):
        return value

    def field(self, name, canon=True):
        val = getattr(self, name, None)
        if val is None:
            val = self.data.get(name, None)

        if hasattr(val, '__int__'):
            val = int(val)
        elif val is not True and val is not False and val is not None:
            val = str(val)

        if canon and val is not None:
            val = self.canon(name, val)
        if val is None:
            val = ''
        return val

    def _coerce(self, other):
        if hasattr(other, 'time'):
            return other.time
        elif hasattr(other, '__float__'):
            return float(other)
        elif hasattr(other, '__int__'):
            return int(other)
        else:
            logging.error('comparing %s with %s?', repr(self), repr(other))
            raise NotImplemented

    def __eq__(self, other):
        return self.time == self._coerce(other)

    def __lt__(self, other):
        return self.time < self._coerce(other)


class SnipeBackend:
    # name of concrete backend
    name = None
    # list of messages, sorted by message time
    #  (not all backends will export this, it can be None)
    messages = []
    principal = None

    def __init__(self, context,  conf = {}):
        self.context = context
        self.conf = conf
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))

    def walk(self, start, forward=True, filter=None):
        self.log.debug('walk(%s, %s, %s)', start, forward, filter)
        # I have some concerns that that this depends on the self.messages list
        # being stable over the life of the iterator.  This doesn't seem to be a
        # a problem as of when I write this comment, but defensive coding should
        # address this at some point.   (If you are finding this comment because
        # of weird message list behavior, this might be why...)

        if filter is None:
            filter = lambda m: True

        if start is not None:
            left = bisect.bisect_left(self.messages, start)
            right = bisect.bisect_right(self.messages, start)
            try:
                point = self.messages.index(start, left, right)
            except ValueError:
                point = None
        else:
            if forward:
                point = 0
            else:
                point = len(self.messages) - 1

        if forward:
            point = point if point is not None else left
            getnext = lambda x: x + 1
        else:
            point = point if point is not None else right - 1
            getnext = lambda x: x - 1

        self.log.debug('len(self.messages)=%d, point=%d', len(self.messages), point)

        while self.messages:
            self.log.debug(', point=%d')
            if not 0 <= point < len(self.messages):
                break
            m = self.messages[point]
            if filter(m):
                yield m
            point = getnext(point)
        if point < 0:
            self.backfill(filter)

    def backfill(self, filter):
        pass

    def shutdown(self):
        pass

    def redisplay(self, m1, m2):
        self.context.ui.redisplay({'messages': (m1, m2)})

    def __str__(self):
        return self.name


class InfoMessage(SnipeMessage):
    def __str__(self):
        return self.body

    def display(self, decoration):
        return [(self.decotags(decoration) + ('bold',), str(self))]


class TerminusBackend(SnipeBackend):
    name = 'terminus'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = [
            InfoMessage(self, '*', mtime=float('inf')),
            ]

    def walk(self, start, forward=True, filter=None):
        return super().walk(start, forward, None) # ignore any filters


class StartupBackend(SnipeBackend):
    name = 'startup'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = [
            SnipeMessage(self, util.SPLASH + '\n'),
            ]


class SyntheticBackend(SnipeBackend):
    name = 'synthetic'

    def __init__(self, *args, **kw):
        super().__init__(conf)
        self.count = conf.get('count', 1)
        self.string = conf.get('string', '0123456789')
        self.width = conf.get('width', 72)
        self.name = '%s-%d-%s-%d' % (
            self.name, self.count, self.string, self.width)
        now = int(time.time())
        self.messages = [
            SnipeMessage(
                self,
                ''.join(itertools.islice(
                    itertools.cycle(self.string),
                    i,
                    i + self.width)),
                now - self.count + i)
            for i in range(self.count)]


def merge(iterables, key=lambda x: x):
    # get the first item from all the iterables
    d = {}

    for it in iterables:
        it = iter(it)
        try:
            d[it] = next(it)
        except StopIteration:
            pass

    while d:
        it, v = min(d.items(), key=lambda x: key(x[1]))
        try:
            d[it] = next(it)
        except StopIteration:
            del d[it]
        yield v


class AggregatorBackend(SnipeBackend):
    # this won't be used as a /backend/ most of the time, but there's
    # no reason that it shouldn't expose the same API for now
    messages = None

    def __init__(self, context, backends = [], conf = {}):
        super().__init__(context, conf)
        self.backends = [TerminusBackend(self.context)]
        for backend in backends:
            self.add(backend)

    def add(self, backend):
        self.backends.append(backend)

    def walk(self, start, forward=True, filter=None):
        # what happends when someone calls .add for an
        # in-progress iteration?
        if hasattr(start, 'backend'):
            startbackend = start.backend
            when = start.time
        else:
            startbackend = None
            when = start
        return merge(
            [
                backend.walk(
                    start if backend is startbackend else when,
                    forward, filter)
                for backend in self.backends
                ],
            key = lambda m: m.time if forward else -m.time)

    def shutdown(self):
        for backend in self.backends:
            backend.shutdown()
        super().shutdown()
