# -*- encoding: utf-8 -*-


import os
import curses
import locale
import signal
import logging

from . import mux


class TTYRenderer(object):
    def __init__(self, ui, y, x, w, h, window):
        self.ui, self.y, self.x, self.w, self.h = ui, y, x, w, h
        self.window = window
        self.window.renderer = self
        self.w = ui.stdscr.subwin(w, h, y, x)
        self.w.idlok(1)
        #self.w.scrollok(1)
        self.log = logging.getLogger('TTYRender.%x' % (id(self),))
        self.frame = None

    def write(self, s):
        self.log.debug('someone used write(%s)', repr(s))

    def redisplay(self):
        self.w.erase()
        off = 0, 0
        cursor = None
        self.w.move(*off)
        if self.frame is None:
            self.reframe()
        cursor = self.redisplay_internal()
        if cursor is not None:
            self.w.move(*cursor)
            self.w.noutrefresh()
            return
        self.reframe()
        cursor = self.redisplay_internal()
        if cursor is not None:
            self.w.noutrefresh()

    @staticmethod
    def doline(s, width):
        '''string, window width -> iter([(displayline, width), ...])'''
        # turns tabs into spaces at n*8 cell intervals
        out = ''
        col = 0
        for c in s:
            # XXX Unicode width, combining characters, etc.
            if c == '\n':
                yield out + '\n', col
                out = ''
                col = 0
            elif ' ' <= c <= '~':
                if col + 2 >= width:
                    yield out, col
                    out = ''
                    col = 0
                out += c
                col += 1
            elif c == '\t':
                n = (8 - col % 8)
                if col + n + 1 >= width:
                    yield out, col
                    out = ''
                    col = 0
                else:
                    col += n
                    out += ' ' * n
            # non printing characters... don't for now
        if out:
            yield out, col

    def redisplay_internal(self):
        cursor = None
        for tags, chunk in self.frame.point: #XXX
            if 'cursor' in tags: #XXX conflating "cursor" with "visible area"
                # sometimes the cursor won't be visible.
                # Also, there are going to be situations where you might
                # want to be able to see the header of the message and a chunk
                # later in the message.
                # You must think carefully on this
                cursor = self.w.getyx()
            self.w.addstr(chunk)
        return cursor


    def reframe(self):
        self.frame = self.window.view()

class TTYFrontend(mux.Muxable):
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
        self.active = TTYRenderer(self, 0, 0, self.maxy, self.maxx, win)
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
        pass #XXX put a warning here or a debug log or something

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
        self.redisplay()

    def redisplay(self):
        for w in self.windows:
            if w is not self.active:
                w.redisplay()
        self.active.redisplay()
        curses.doupdate()

    def notify(self):
        if self.notify_silent:
            curses.flash()
        else:
            curses.beep()
