# -*- encoding: utf-8 -*-


import itertools
import time


class SnipeAddress(object):
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


class SnipeMessage(object):
    def __init__(self, backend, body='', mtime=None):
        self._sender = None
        self.backend = backend
        self.time = time.time() if mtime is None else mtime
        self.body = body

    @property
    def sender(self):
        if self._sender is None:
            self._sender = SnipeAddress(self.backend)
        return self._sender

    def __str__(self):
        return 'From: %s at %s\n%s' % (
            self.sender, time.ctime(self.time), self.body)

    def __repr__(self):
        return (
            '<' + self.__class__.__name__ + ' '
            + repr(self.time) + ' '
            + repr(self.sender) + ' '
            + repr(self.body) + '>'
            )


class SnipeBackend(object):
    # name of concrete backend
    name = None
    # list of messages, sorted by message time
    #  (not all backends will export this, it can be None)
    messages = []

    def __init__(self, conf = {}):
        self.conf = conf

    def walk(self, start, forward=True, filter=None):
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
            l = reversed(l)
        if start:
            l = itertools.dropwhile(pred, l)
        if filter is not None:
            l = (m for m in l if filter(m))
        return l

    def shutdown(self):
        pass


class StartupBackend(SnipeBackend):
    name = 'startup'

    def __init__(self, conf = {}):
        super(StartupBackend, self).__init__(conf)
        self.messages = [SnipeMessage(self, 'Welcome to snipe.')]


class SyntheticBackend(SnipeBackend):
    name = 'synthetic'

    def __init__(self, conf = {}):
        super(SyntheticBackend, self).__init__(conf)
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
            d[it] = it.next()
        except StopIteration:
            pass

    while d:
        it, v = min(d.iteritems(), key=lambda x: key(x[1]))
        try:
            d[it] = it.next()
        except StopIteration:
            del d[it]
        yield v


class AggregatorBackend(SnipeBackend):
    # this won't be used as a /backend/ most of the time, but there's
    # no reason that it shouldn't expose the same API for now
    messages = None

    def __init__(self, backends = [], conf = {}):
        super(AggregatorBackend, self).__init__(conf)
        self.backends = []
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
