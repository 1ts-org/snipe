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
snipe.messages
--------------
Utilities and base classes for dealin with messages.
'''


import bisect
import contextlib
import datetime
import enum
import functools
import logging
import math
import time

from typing import (List, Optional, Sequence, Union)

from . import chunks
from . import editor
from . import filters
from . import imbroglio
from . import util


class SnipeAddress:
    backend = None
    path: List[str] = []

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
            '<' + self.__class__.__name__ + ' '
            + self.backend.name +
            ((' ' + ', '.join(self.path)) if self.path else '')
            + '>'
            )


@functools.total_ordering
class SnipeMessage:
    personal = False
    outgoing = False
    noise = False
    omega = False
    error = False
    transformed = None

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

    def display(self, decoration):
        decor = self.get_decor(decoration)
        return decor.decorate(self, decoration)

    def get_decor(self, decoration):
        decor = decoration.get('decor')
        if decor is not None:
            try:
                return util.getobj(decor)
            except BaseException:
                self.backend.log.exception('loading decor %s', decor)
        return self.Decor

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

    @staticmethod
    def _coerce(other):
        if hasattr(other, 'time'):
            return other.time
        elif hasattr(other, '__float__'):
            return float(other)
        elif hasattr(other, '__int__'):
            return int(other)
        else:
            return other  # probably will fail :-)

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

    def transform(self, encoding, body):
        self.transformed = encoding
        self.body = body

    class Decor:
        @classmethod
        def decorate(self, msg, decoration):
            tags = self.decotags(decoration)
            return self.headline(msg, tags) + self.body(msg, tags)

        @classmethod
        def headline(self, msg, tags=frozenset()):
            followup = msg.followup()
            chunk = chunks.Chunk([(tags | {'bold'}, followup)])
            sender = str(msg.sender)
            if sender != followup:
                chunk += [(tags, ' : '), (tags | {'bold'}, sender)]
            chunk += [(
                tags | {'right'},
                time.strftime(' %H:%M:%S', time.localtime(msg.time)),
                )]
            return chunk

        @classmethod
        def format(self, msg, tags=frozenset()):
            return chunks.Chunk(
                [(tags, msg.body + ('\n' if msg.body[-1:] != '\n' else ''))])

        @classmethod
        def body(self, msg, tags=frozenset()):
            body = self.format(msg, tags)
            if not msg.backend.indent:
                return body
            return self.prefix_chunk(msg.backend.indent, body)

        @staticmethod
        def prefix_chunk(prefix, chunk):
            if not chunk:
                return chunk

            UNDERLINE = frozenset(['underline'])

            flat = str(chunk)
            new = chunks.Chunk()
            rest = chunk
            for l in (len(s) for s in flat.split('\n')):
                line, rest = rest.slice(l)
                if not line:
                    if rest:
                        if new:
                            t = new[-1].tags
                        else:
                            t = set(rest[-1].tags) - UNDERLINE
                        line = chunks.Chunk([(t, prefix + '\n')])
                else:
                    ltags, ltext = line[0]
                    if 'underline' in ltags:
                        line[0:0] = [(set(ltags) - UNDERLINE, prefix)]
                    else:
                        line[0] = (ltags, prefix + ltext)
                    ltags, ltext = line[-1]
                    if 'underline' in ltags:
                        line += [(set(ltags) - UNDERLINE, '\n')]
                    else:
                        line[-1] = (ltags, ltext + '\n')
                new.extend(line)
                if rest:
                    _, rest = rest.slice(1)
            return new

        @staticmethod
        def decotags(decoration):
            tags = set()
            if 'foreground' in decoration:
                tags.add('fg:' + decoration['foreground'])
            if 'background' in decoration:
                tags.add('bg:' + decoration['background'])
            return tags

    class OnelineDecor(Decor):
        @classmethod
        def body(self, msg, tags=set()):
            return []


class SnipeErrorMessage(SnipeMessage):
    def __init__(self, backend, body, tb=None):
        super().__init__(backend, body)
        self.error = True
        if tb is not None:
            self.data['traceback'] = tb

    def filter(self, specificity=0):
        nfilter = filters.And(
            filters.Compare('==', 'backend', self.backend.name),
            filters.Truth('error'),
            )
        if specificity:
            nfilter = filters.And(
                nfilter,
                filters.Compare('==', 'body', self.body))
        return nfilter


class BackendState(enum.Enum):
    IDLE = enum.auto()
    CONNECTING = enum.auto()
    LOADING = enum.auto()
    BACKFILLING = enum.auto()
    DISCONNECTED = enum.auto()


class SnipeBackend:
    # name of concrete backend
    name: Optional[str] = None
    # list of messages, sorted by message time
    #  (not all backends will export this, it can be None)
    messages: Sequence[SnipeMessage] = ()
    principal = None

    AUTO_FILL = True
    SOFT_NEWLINES = False

    indent = util.Configurable(
        'message.indent_body_string', '',
        'Indent message bodies with this string (barnowl expats may '
        'wish to set it to eight spaces)')

    def __init__(self, context, name=None, conf={}):
        self.context = context
        logname = self.__class__.__name__
        if name is not None:
            self.name = name
            logname += '.' + name
        logpost = '.%x' % (id(self),)
        self.log = logging.getLogger(logname + logpost)
        self.netlog = logging.getLogger(logname + '.network' + logpost)
        self.conf = conf
        self.drop_cache()
        self.tasks = []
        self._destinations = set()
        self._senders = set()
        self._state = BackendState.IDLE

    def state(self):
        return self._state

    def state_set(self, state: BackendState):
        self._state = state
        self.context.ui.redisplay({})

    async def start(self):
        """Actually connect to whatever we're connecting to and start
        retrieving messages."""
        self.supervisor = await imbroglio.get_supervisor()

    def drop_cache(self):
        self.startcache = {}
        self.adjcache = {}

    def walk(
            self, start: Union[SnipeMessage, float], forward=True,
            *, mfilter=None, backfill_to=None, search=False):
        """Iterate through a list of messages associated with a backend.

        :param start: Where to start iterating from.
        :type start: integer, SnipeMessage, float
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
        redisplay, for date headers and such that want to bypass filters on
        display.
        """

        self.log.debug(
            '%s.walk(%s, %s, ...)', self.__class__.__name__, start, forward)
        # I have some concerns that that this depends on the
        # self.messages list being stable over the life of the
        # iterator.  This doesn't seem to be a a problem as of when I
        # write this comment, but defensive coding should address this
        # at some point.  (If you are finding this comment because of
        # weird message list behavior, this might be why...)

        if mfilter is not None:
            mfilter = mfilter.simplify({
                'backend': self.name,
                'context': self.context,
                })
            if mfilter is False:
                return
            if mfilter is True:
                mfilter = None

        if mfilter is None:
            def mfilter(m):
                return True

        cachekey = (start, forward, mfilter)
        point = self.startcache.get(cachekey, None)

        if backfill_to is not None and math.isfinite(backfill_to):
            self.backfill(mfilter, backfill_to)

        needcache = False
        if point is None:
            needcache = True
            left = bisect.bisect_left(self.messages, start)
            right = bisect.bisect_right(self.messages, start)
            try:
                point = self.messages.index(start, left, right)
            except ValueError:
                point = None

            if forward:
                point = point if point is not None else left
            else:
                point = point if point is not None else right - 1

        if forward:
            def getnext(x):
                return x + 1
        else:
            def getnext(x):
                return x - 1

        # self.log.debug(
        #     'len(self.messages)=%d, point=%d', len(self.messages), point)

        adjkey = None
        while self.messages:
            # self.log.debug(', point=%d', point)
            if not 0 <= point < len(self.messages):
                break
            m = self.messages[point]
            if mfilter(m):
                if needcache:
                    self.startcache[cachekey] = point
                    needcache = False
                yield m
                if adjkey is not None:
                    self.adjcache[adjkey] = point
                adjkey = (m, forward, mfilter)
            point = self.adjcache.get(adjkey, getnext(point))

        if adjkey is not None:
            self.adjcache[adjkey] = point

        # specifically catch the situation where we're trying to go off the top
        if point < 0 and backfill_to is not None:
            self.backfill(mfilter, backfill_to)

    def earliest(self):
        """Probably returns the earliest message in the backend.  Might return
        a magic cookie saying start from the beginning."""

        if not self.messages:  # pragma: nocover
            return None
        return self.messages[0]

    def latest(self):
        """Probably returns the latest message in the backend.  Might return
        a magic cookie saying start from the end."""

        if not self.messages:  # pragma: nocover
            return None
        return self.messages[-1]

    def backfill(self, mfilter, target=None):
        pass

    async def shutdown(self):
        tasks = list(reversed(self.tasks))
        for t in tasks:
            self.log.error('shutting down %s', repr(t))
            try:
                t.cancel()
                await t
                with contextlib.suppress(imbroglio.Cancelled):
                    t.result()
            except BaseException:
                self.log.exception('while shutting down')
        self.tasks = []

    def reap_tasks(self):
        """Remove any tasks that have completed.

        Backends that generate ephemeral tasks (for example, to backfill)
        should occasionally call this method to remove completed tasks from the
        task list.
        """
        self.tasks = [t for t in self.tasks if not t.is_done()]

    def redisplay(self, m1, m2):
        try:
            self.context.ui.redisplay({'messages': (m1, m2)})
        except Exception:
            self.log.exception('triggering redisplay')
            # do not let this propagate into the backend

    def __str__(self):
        return self.name

    def count(self):
        """Return the number of messages stored (locally) in this backend."""
        return len(self.messages)

    async def send(self, recipient, body):
        """Send a message"""
        raise NotImplementedError('No such recipient')

    def destinations(self):
        return self._destinations

    def senders(self):
        return self._senders

    def eldest(self):
        """Return the time of the eldest message or None if there isn't one"""
        if not self.messages:  # pragma: nocover
            return None
        return self.messages[0].time


class SinkBackend(SnipeBackend):
    name = 'sink'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = []

    async def send(self, recipient, body):
        self.messages.append(SnipeMessage(self, body))
        self.drop_cache()


class InfoMessage(SnipeMessage):
    def __str__(self):
        return self.body

    class Decor(SnipeMessage.Decor):
        @classmethod
        def decorate(self, msg, decoration):
            return chunks.Chunk(
                [(self.decotags(decoration) | {'bold'}, msg.body)])


class TerminusBackend(SnipeBackend):
    name = 'terminus'
    loglevel = util.Level('log.terminus', 'TerminusBackend')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        m = InfoMessage(self, '*', mtime=float('inf'))
        m.omega = True
        self.messages = [m]

    def walk(
            self, start, forward=True, *, mfilter=None, backfill_to=None,
            search=False):
        self.log.debug('walk(..., search=%s)', search)
        if search:
            return
        yield from super().walk(
            start, forward, mfilter=None, backfill_to=backfill_to,
            search=search)


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
        self.starting_at = datetime.datetime.now()

    def backfill(self, mfilter, backfill_to):
        eldest = self.context.backends.eldest()
        if eldest is not None:
            self.starting_at = datetime.datetime.fromtimestamp(eldest)

    def walk(
            self, start, forward=True, *, mfilter=None, backfill_to=None,
            search=False):
        # Note that this ignores mfilter
        self.log.debug(
            'walk(%s, %s, [filter], %s, %s)',
            repr(start), forward, util.timestr(backfill_to), search)

        self.backfill(mfilter, backfill_to)

        self.log.debug(
            'self.starting_at = %s',
            util.timestr(self.starting_at.timestamp()))

        if search:
            return

        now = datetime.datetime.now()

        start = float(start)

        if math.isinf(start):
            if start < 0:  # -inf
                start = self.starting_at
            else:  # +inf
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

        self.log.debug(
            't = %s, delta = %s', util.timestr(t.timestamp()), repr(delta))

        while now > t >= self.starting_at:
            self.log.debug('date header at %s', util.timestr(t.timestamp()))
            yield self.make_message(t.timestamp())
            t += delta

        self.log.debug('leaving walk')

    def make_message(self, stamp):
        t = datetime.datetime.fromtimestamp(stamp)
        return InfoMessage(
            self,
            t.strftime('%A, %B %d, %Y\n\n'),
            t.timestamp(),
            )

    def earliest(self):
        t = self.context.backends.eldest()
        if t is None:
            # this is basically here to make the tests work, IRL there
            # should always be a StartupMessage
            t = -2**31
        return self.make_message(t)

    def latest(self):
        return self.make_message(time.time())


def merge(iterables, key=lambda x: x):
    # get the first item from all the iterables
    d = {}

    last = None

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
        if v == last:
            continue
        last = v
        yield v


class AggregatorBackend(SnipeBackend):
    # this won't be used as a /backend/ most of the time, but there's
    # no reason that it shouldn't expose the same API for now
    loglevel = util.Level('log.aggregator', 'AggregatorBackend')

    def __init__(self, context, backends=[], conf={}):
        super().__init__(context, conf=conf)
        self.started = False
        self.backends = [TerminusBackend(self.context)]
        for backend in backends:
            self.backends.append(backend)

    async def start(self):
        self.started = True
        for backend in self.backends:
            await backend.start()

    def walk(
            self, start, forward=True, *, mfilter=None, backfill_to=None,
            search=False):
        self.log.debug(
            'walk(%s, forward=%s, [filter], backfill_to=%s, search=%s',
            repr(start), forward, util.timestr(backfill_to), search)
        # what happens when someone calls .add for an
        # in-progress iteration?
        if hasattr(start, 'backend'):
            startbackend = start.backend
            when = start.time
        else:
            startbackend = None
            when = start
        backend_walks = [
                backend.walk(
                    start if backend is startbackend else when,
                    forward,
                    mfilter=mfilter,
                    backfill_to=backfill_to,
                    search=search,
                    )
                for backend in self.backends
                ]
        for message in merge(
                backend_walks, key=lambda m: m.time if forward else -m.time):
            yield message

    def earliest(self):
        l = list(filter(
            lambda x: x is not None,
            (backend.earliest() for backend in self.backends)))
        try:
            return min(l)
        except ValueError:  # pragma: nocover
            return None

    def latest(self):
        l = list(filter(
            lambda x: x is not None,
            (backend.latest() for backend in self.backends)))
        try:
            return max(l)
        except ValueError:  # pragma: nocover
            return None

    async def shutdown(self):
        await imbroglio.gather(
            *[backend.shutdown() for backend in self.backends],
            return_exceptions=True)
        await super().shutdown()

    def __iter__(self):
        return iter(self.backends)

    async def send(self, paramstr, msg):
        params = [s.strip() for s in paramstr.split(';', 1)]
        backends = [b for b in self if b.name.startswith(params[0])]
        if not params[0]:
            raise util.SnipeException('no backend in query string')
        if len(backends) == 1:
            backend = backends[0]
            if backend.SOFT_NEWLINES:
                msg = msg.replace(editor.SOFT_LINEBREAK, ' ')
            else:
                msg = msg.replace(editor.SOFT_LINEBREAK, '\n')
            await backend.send(''.join(params[1:]), msg)
        elif len(backends) == 0:
            raise util.SnipeException(
                f'{params[0]!r}: backend not found')
        else:
            backend_str = ' '.join(str(backend) for backend in backends)
            raise util.SnipeException(
                f'ambiguous backend {params[0]!r}:'
                f' possibly one of {backend_str}')

    def backfill(self, filter, target=None):
        for backend in self:
            backend.backfill(filter, target)

    def count(self):
        return sum(backend.count() for backend in self.backends)

    def destinations(self):
        return set().union(
            *(backend.destinations() for backend in self.backends))

    def senders(self):
        return set().union(
            *(backend.senders() for backend in self.backends))

    def eldest(self):
        data = [backend.eldest() for backend in self.backends]
        filtered = [t for t in data if t is not None and not math.isinf(t)]
        if filtered:
            return min(filtered)
        else:
            # this really shouldn't happen, but
            return None  # pragma: nocover

    def statusline(self):
        return ' '.join(
            f'[{backend.name} {backend.state().name!s}]'
            for backend in self.backends
            if backend.state() != BackendState.IDLE)
