#!/usr/bin/python
# -*- encoding: utf-8 -*-

import os
import logging


import select


class Mux(object):
    def __init__(self):
        self.muxables = {}
    def add(self, muxable):
        self.muxables[muxable.handle] = muxable
    def remove(self, muxable):
        del self.muxables[muxable.handle]
    def wait(self, timeout=None):
        readers = [x for x in self.muxables if self.muxables[x].reader]
        writers = [x for x in self.muxables if self.muxables[x].writer]
        if not (readers or writers):
            raise ValueError('No one is listening')
        readable, writable, errant = select.select(
            readers, writers, set(readers + writers), timeout)
        for x in errant:
            self.muxables[x].error()
        for x in writable:
            self.muxables[x].writable()
        for x in readable:
            self.muxables[x].readable()
    def wait_forever(self):
        while True:
            self.wait()


class Muxable(object):
    '''Abstract parent of things you can had to the Mux'''
    reader = False
    writer = False
    handle = None

    def readable(self):
        '''Callback for when the fileno is readable'''
        raise NotImplementedError

    def writable(self):
        '''Callback for when the fileno is writable'''
        raise NotImplementedError

    def error(self):
        '''Callback for when the fileno is errant'''
        raise NotImplementedError


import curses
import locale
import signal


class Renderer(object):
    def __init__(self, ui, y, x, w, h, window):
        self.ui, self.y, self.x, self.w, self.h = ui, y, x, w, h
        self.window = window
        self.window.renderer = self
        self.w = ui.stdscr.subwin(w, h, y, x)
        self.w.idlok(1)
        self.w.scrollok(1)


    def write(self, s):
        self.w.addstr(s)
        self.w.move(*self.w.getyx())
        self.w.refresh()
        ## self.ui.stdscr.move(*self.w.getyx())
        ## self.ui.stdscr.refresh()

class Window(object):
    def __init__(self, frontend):
        self.fe = frontend
        self.keymap = {}
        self.renderer = None

        self.keymap[chr(ord('Q') - ord('@'))] = self.quit
        self.keymap[chr(ord('Z') - ord('@'))] = self.stop

    def input_char(self, k):
        if k in self.keymap:
            self.keymap[k](k)
        else:
            self.whine(k)

    def quit(self, k):
        exit()

    def whine(self, k):
        self.fe.notify()

    def stop(self, k):
        self.fe.sigtstp(None, None)

class Messager(Window):
    def __init__(self, frontend):
        super(Messager, self).__init__(frontend)
        #SPACE
        #n, p, ^n ^p ↓ ↑ j k

class Editor(Window):
    def __init__(self, frontend):
        super(Editor, self).__init__(frontend)
        for x in range(ord(' '), ord('~') + 1):
            self.keymap[chr(x)] = self.self_insert_command
        for x in ['\n', '\t', '\j']:
            self.keymap['\n'] = self.self_insert_command

    def self_insert_command(self, k):
        self.fe.write(k)


class Context(object):
    # per-session state and abstact control
    def __init__(self, mux, ui):
        self.mux = mux
        self.ui = ui
        self.backends = AggregatorBackend(
            backends = [
                StartupBackend(),
                SyntheticBackend(conf={'count': 100}),
                ],)
        self.ui.initial(Editor(self.ui))

class UI(Muxable):
    reader = True
    handle = 0 # stdin

    def __init__(self):
        self.stdscr, self.maxy, self.maxx, self.active = (None,)*4
        self.windows = []
        self.unkey = dict(
            (getattr(curses, k), k[len('KEY_'):])
            for k in dir(curses)
            if k.startswith('KEY_'))
        self.notify_silent = True

    def __enter__(self):
        locale.setlocale(locale.LC_ALL, '')
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.raw()
        self.stdscr.keypad(1)
        curses.start_color()
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.orig_sigtstp = signal.signal(signal.SIGTSTP, self.sigtstp)
        return self

    def initial(self, win):
        if self.windows or self.active:
            raise ValueError
        self.active = Renderer(self, 0, 0, self.maxy, self.maxx, win)
        self.windows = [self.active]
        self.active.w.refresh()
        self.stdscr.refresh()

    def __exit__(self, type, value, tb):
        # go to last line of screen, maybe cause scrolling?
        self.stdscr.keypad(0)
        curses.noraw()
        curses.echo()
        curses.endwin()
        signal.signal(signal.SIGTSTP, self.orig_sigtstp)

    def sigtstp(self, signum, frame):
        curses.def_prog_mode()
        curses.endwin()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)
        signal.signal(signal.SIGTSTP, self.sigtstp)
        self.stdscr.refresh()

    def write(self, s):
        if self.active:
            self.active.write(s)

    def doresize(self):
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        # rearrange windows as appropriate and trigger redisplays

    def getch(self):
        c = self.stdscr.getch()
        #XXX do something clever with UTF-8 (IFF we are in a UTF-8 locale)
        if c == curses.KEY_RESIZE:
            self.doresize()
            ## self.write('(%d, %d)\n' % (self.maxy, self.maxx))
        if -1 < c < 256:
            return chr(c)
        if c in self.unkey:
            return self.unkey[c]
        return c

    def readable(self):
        k = self.getch()
        if self.active:
            self.active.window.input_char(k)

    def notify(self):
        if self.notify_silent:
            curses.flash()
        else:
            curses.beep()

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


def main():
    with UI() as ui:
        mux = Mux()
        context = Context(mux, ui)
        mux.add(ui)
        mux.wait_forever()


if __name__ == '__main__':
    main()
