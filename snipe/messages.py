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
'''
snipe.messages
--------------
Utilities and base classes for dealin with messages.
'''


import itertools
import time
import datetime
import logging
import functools
import bisect
import asyncio
import math

from . import util
from . import filters


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
        return ';'.join([self.backend.name] + self.path)

    def short(self):
        return str(self)

    def reply(self):
        return str(self)

    def __repr__(self):
        return (
            '<' + self.__class__.__name__+ ' '
            + self.backend.name + (' ' if self.path else '')
            + ', '.join(self.path) + '>'
            )


@functools.total_ordering
class SnipeMessage:
    personal = False
    outgoing = False
    noise = False
    omega = False
    error = False

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
            return other # probably will fail :-)

    def __eq__(self, other):
        return self.time == self._coerce(other)

    def __lt__(self, other):
        return self.time < self._coerce(other)

    def reply(self):
        return self.sender.reply()

    def followup(self):
        return self.sender.reply()

    def filter(self, specificity=0):
        """Return a filter that would catch this message and others like it.

        As specificity increases the filter should become more specific,
        if possible.

        In the generic case, it's just specific to the backend.
        """
        # all we can do in the generic case
        return filters.Compare('==', 'backend', self.backend.name)

    def __hash__(self):
        return hash(self.time)

    def __float__(self):
        return self.time


class SnipeBackend:
    # name of concrete backend
    name = None
    # list of messages, sorted by message time
    #  (not all backends will export this, it can be None)
    messages = []
    principal = None

    def __init__(self, context, conf = {}):
        self.context = context
        self.conf = conf
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))
        self.startcache = {}

    def walk(self, start, forward=True, mfilter=None, backfill_to=None,
            search=False):
        """Iterate through a list of messages associated with a backend.

        :param start: Where to start iterating from.
        :type start: integer, SnipeMessage, float or None
        :param bool forward: Whether to go forwards or backwards.
        :param mfilter: Any applicable message filter
        :type mfilter: Filter or None
        :param backfill_to: How far the backend should dig
        :type backfill_to: float or None
        :param bool search: Whether this is being called from a search

        If ``start`` is ``None``, begin at the end ``forward`` would have us
        moving away from.

        ``backfill_to`` potentially triggers the backend to pull in more
        messages, but it doesn't guarantee that they'll be visible in this
        iteration.

        ``search`` lets backends behave differently when not called from the
        redisplay, for data headers and such that want to bypass filters on
        display.
        """
        self.log.debug('walk(%s, %s, [filter], %s, %s)',
            repr(start), forward, util.timestr(backfill_to), search)
        # I have some concerns that that this depends on the self.messages list
        # being stable over the life of the iterator.  This doesn't seem to be a
        # a problem as of when I write this comment, but defensive coding should
        # address this at some point.   (If you are finding this comment because
        # of weird message list behavior, this might be why...)

        if mfilter is not None:
            mfilter = mfilter.simplify({
                'backend': self.name,
                'context': self.context,
                })
            if mfilter == False:
                return
            if mfilter == True:
                mfilter = None

        if mfilter is None:
            mfilter = lambda m: True

        cachekey = (start, forward, mfilter)
        point = self.startcache.get(cachekey, None)

        if (backfill_to is not None and math.isfinite(backfill_to) and
            self.messages and self.messages[0].time > backfill_to):
            self.backfill(mfilter, backfill_to)

        if point is False:
            return

        needcache = False
        if point is None:
            needcache = True
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
            else:
                point = point if point is not None else right - 1

        if forward:
            getnext = lambda x: x + 1
        else:
            getnext = lambda x: x - 1

        #self.log.debug('len(self.messages)=%d, point=%d', len(self.messages), point)

        while self.messages:
            #self.log.debug(', point=%d', point)
            if not 0 <= point < len(self.messages):
                break
            m = self.messages[point]
            if mfilter(m):
                if needcache:
                    self.startcache[cachekey] = point
                    needcache = False
                yield m
            point = getnext(point)

        # specifically catch the situation where we're trying to go off the top
        if point < 0 and backfill_to is not None:
            self.backfill(mfilter, backfill_to)

    def backfill(self, mfilter, target=None):
        pass

    def shutdown(self):
        pass

    def redisplay(self, m1, m2):
        self.context.ui.redisplay({'messages': (m1, m2)})

    def __str__(self):
        return self.name

    def count(self):
        """Return the number of messages stored (locally) in this backend."""
        if self.messages is not None:
            return len(self.messages)
        else:
            return 0


class InfoMessage(SnipeMessage):
    def __str__(self):
        return self.body

    def display(self, decoration):
        return [(self.decotags(decoration) + ('bold',), str(self))]


class TerminusBackend(SnipeBackend):
    name = 'terminus'
    loglevel = util.Level('log.terminus', 'TerminusBackend')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        m = InfoMessage(self, '*', mtime=float('inf'))
        m.omega = True
        self.messages = [m]

    def walk(self, start, forward=True, mfilter=None, backfill_to=None,
            search=False):
        self.log.debug('walk(..., search=%s)', search)
        if search:
            return
        yield from super().walk(start, forward, None, backfill_to, search)


class StartupBackend(SnipeBackend):
    name = 'startup'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = [
            SnipeMessage(self, util.SPLASH + '\n'),
            ]


class DateBackend(SnipeBackend):
    name = 'date'
    loglevel = util.Level('log.date', 'DateBackend')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = None
        self.start = datetime.datetime.now()

    def backfill(self, mfilter, backfill_to):
        if backfill_to is not None and not math.isinf(float(backfill_to)):
            self.log.debug('backfill([filter], %s)', util.timestr(backfill_to))
            self.start = min(
                self.start,
                datetime.datetime.fromtimestamp(backfill_to))

    def walk(self, start, forward=True, mfilter=None, backfill_to=None,
            search=False):
        # Note that this ignores mfilter
        self.log.debug('walk(%s, %s, [filter], %s, %s)',
            repr(start), forward, util.timestr(backfill_to), search)

        self.backfill(mfilter, backfill_to)

        self.log.debug('self.start = %s', util.timestr(self.start.timestamp()))

        if search:
            return

        now = datetime.datetime.now()

        if start is None:
            if forward:
                start = self.start
            else:
                start = now
        else:
            start = float(start)

            if math.isinf(start):
                if start < 0: #-inf
                    start = self.start
                else: # +inf
                    start = now
            else:
                start = datetime.datetime.fromtimestamp(start)

        self.log.debug('start = %s', util.timestr(start.timestamp()))

        if forward:
            t = start
            if t.time() != datetime.time():
                # compute the next midnight
                d = start.date() + datetime.timedelta(days=1)
                t = datetime.datetime.combine(d, datetime.time())
            delta = datetime.timedelta(days=1)
        else:
            # "today" midnight
            d = start.date()
            t = datetime.datetime.combine(d, datetime.time())
            delta = datetime.timedelta(days=-1)

        self.log.debug('t = %s, delta = %s', util.timestr(t.timestamp()), repr(delta))

        while now > t >= self.start:
            self.log.debug('date header at %s', util.timestr(t.timestamp()))
            yield InfoMessage(
                self,
                t.strftime('%A, %B %d, %Y\n\n'),
                t.timestamp(),
                )
            t += delta

        self.log.debug('leaving walk')


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


def logiter(log, x):
    for n, y in enumerate(x):
        log.debug('%s[%d]: %s', repr(x), n, repr(y))
        yield y


class AggregatorBackend(SnipeBackend):
    # this won't be used as a /backend/ most of the time, but there's
    # no reason that it shouldn't expose the same API for now
    messages = None
    loglevel = util.Level('log.aggregator', 'AggregatorBackend')

    def __init__(self, context, backends = [], conf = {}):
        super().__init__(context, conf)
        self.backends = [TerminusBackend(self.context)]
        for backend in backends:
            self.add(backend)

    def add(self, backend):
        self.backends.append(backend)

    def walk(self, start, forward=True, filter=None, backfill_to=None,
            search=False):
        self.log.debug(
            'walk(%s, forward=%s, [filter], backfill_to=%s, search=%s',
            repr(start), forward, util.timestr(backfill_to), search)
        # what happends when someone calls .add for an
        # in-progress iteration?
        if hasattr(start, 'backend'):
            startbackend = start.backend
            when = start.time
        else:
            startbackend = None
            when = start
        return logiter(self.log, merge(
            [
                backend.walk(
                    start if backend is startbackend else when,
                    forward,
                    filter,
                    backfill_to,
                    search,
                    )
                for backend in self.backends
                ],
            key = lambda m: m.time if forward else -m.time))

    def shutdown(self):
        for backend in self.backends:
            backend.shutdown()
        super().shutdown()

    def __iter__(self):
        return iter(self.backends)

    @asyncio.coroutine
    def send(self, paramstr, msg):
        params = [s.strip() for s in paramstr.split(';', 1)]
        backends = [b for b in self if b.name.startswith(params[0])]
        if len(backends) != 1:
            raise util.SnipeException(
                'backend query string %s results in %s' % (params[0], backends))
        yield from backends[0].send(''.join(params[1:]), msg)

    def backfill(self, filter, target=None):
        for backend in self:
            backend.backfill(filter, target)

    def count(self):
        return sum(backend.count() for backend in self.backends)
