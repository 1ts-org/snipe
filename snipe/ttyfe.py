#!/usr/bin/python3
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
snipe.ttyfe
-----------
UNIX tty frontend.
'''


import array
import asyncio
import asyncio.unix_events
import collections
import contextlib
import curses
import fcntl
import itertools
import locale
import logging
import os
import select
import signal
import termios
import textwrap
import unittest.mock as mock


from . import ttycolor
from . import util


class TTYRenderer:
    def __init__(self, ui, y, h, window, hints=None, whence=None):
        self.log = logging.getLogger('TTYRender.%x' % (id(self),))
        self.curses_log = logging.getLogger(
            'TTYRender.curses.%x' % (id(self),))
        self.ui, self.y, self.height = ui, y, h
        self.x = 0
        self.width = ui.maxx
        self.window = window
        self.window.renderer = self
        self.log.debug(
            'subwin(%d, %d, %d, %d)', self.height, self.width, self.y, self.x)
        self.w = ui.stdscr.subwin(self.height, self.width, self.y, self.x)
        self.w.idlok(1)
        self.cursorpos = None
        self.context = None
        self.whence = whence

        if hints is None:
            hints = self.window.hints
        self.head = hints.get('head')
        self.sill = hints.get('sill')
        self.window.hints = {}

        self.reframe_state = 'hard'
        self.old_cursor = None

        self.minheight = min(h, 3)

    def resize(self, y, h):
        return TTYRenderer(
            self.ui, y, h, self.window, hints=self.get_hints(),
            whence=self.whence)

    def get_hints(self):
        return {'head': self.head, 'sill': self.sill}

    def active(self):
        return self.ui.windows[self.ui.output] == self

    def write(self, s):
        self.log.debug('someone used write(%s)', repr(s))

    def redisplay(self):
        if self.head is None:
            self.log.debug('redisplay with no frame, firing reframe')
            self.reframe()
        visible = self.redisplay_internal()
        if not visible:
            self.log.debug('redisplay, no visibility, firing reframe')
            if (self.window.cursor, 0) < (self.head.cursor, self.head.offset):
                self.reframe(0)
            elif self.window.cursor > self.head.cursor:
                self.reframe(action='clever-down')
            else:
                self.log.warning(
                    '%s, %s: ==? %s',
                    repr(self.window.cursor), repr(self.head.cursor),
                    self.window.cursor == self.head.cursor,
                    )
            visible = self.redisplay_internal()
            if not visible:
                self.log.warning(
                    'redisplay, no visibility after clever reframe')
                self.reframe()
            visible = self.redisplay_internal()
            if not visible:
                self.log.error(
                    'no visibility after hail-mary reframe, giving up')

        self.w.noutrefresh()

    @staticmethod
    @util.listify
    def doline(s, width, remaining, tags=()):
        '''string, window width, remaining width, tags ->
        [(displayline, remaining), ...]'''
        # turns tabs into spaces at n*8 cell intervals

        right = 'right' in tags

        if 'fill' in tags and s:
            nl = s.endswith('\n')
            if remaining:
                ll = textwrap.wrap(s, remaining)
                s = '\n'.join(
                    ll[:1] + textwrap.wrap(' '.join(ll[1:]), width))
            else:
                s = '\n'.join(textwrap.wrap(s, width))
            if nl:
                s += '\n'

        out = ''
        line = 0
        col = 0 if remaining is None or remaining <= 0 else width - remaining
        for c in s:
            # XXX combining characters, etc.
            if c == '\n':
                if not right:
                    yield out, -1 if col < width else 0
                else:
                    yield out, width - col
                out = ''
                col = 0
                line += 1
            elif c >= ' ' or c == '\t':
                if c == '\t':
                    c = ' ' * (8 - col % 8)
                l = util.glyphwidth(c)
                if not l:
                    # non printing characters... don't
                    continue
                if col + l > width:
                    if right and line == 0:
                        yield '', -1
                        col = remaining
                    else:
                        yield out, 0
                        out = ''
                        col = 0
                    line += 1
                    if len(c) > 1:  # it's a TAB
                        continue
                out += c
                col += l
        if out:
            yield out, width - col

    def compute_attr(self, tags):
        # A_BLINK A_DIM A_INVIS A_NORMAL A_STANDOUT A_REVERSE A_UNDERLINE
        attrs = {
            'bold': curses.A_BOLD,
            'reverse': curses.A_REVERSE,
            'underline': curses.A_UNDERLINE,
            'dim': curses.A_DIM,
            }
        attr = 0
        fg, bg = '', ''
        for t in tags:
            attr |= attrs.get(t, 0)
            if t.startswith('fg:'):
                fg = t[3:]
            if t.startswith('bg:'):
                bg = t[3:]
        attr |= self.ui.color_assigner(fg, bg)
        return attr

    def redisplay_calculate(self):
        self.log.debug(
            'in redisplay_calculate: w=%d, h=%d, frame=%s',
            self.width,
            self.height,
            repr(self.head),
            )

        if self.window.cursor != self.old_cursor:
            self.reframe_state = 'hard'
            self.old_cursor = self.window.cursor

        visible = None
        cursor = None
        screenlines = self.height + self.head.offset
        remaining = None
        sill = None
        bars = []

        output = [[]]
        y, x = -self.head.offset, 0

        for mark, chunk in self.window.view(self.head.cursor):
            if screenlines <= 0:
                break
            sill = Location(self, mark)
            chunkat = screenlines

            for tags, text in chunk:
                attr = self.compute_attr(tags)
                if 'cursor' in tags:
                    cursor = (y, x)
                if 'bar' in tags:
                    bars.append(y)
                if 'visible' in tags and (
                        screenlines <= self.height
                        or self.reframe_state == 'soft'):
                    visible = y
                if 'right' in tags:
                    text = text.rstrip('\n')  # XXX chunksize

                textbits = self.doline(text, self.width, remaining, tags)
                if not textbits:
                    if remaining is None or remaining <= 0:
                        remaining = self.width
                    textbits = [('', remaining)]
                for line, remaining in textbits:
                    if 'right' in tags:
                        line = ' ' * remaining + line
                        x += remaining
                        remaining = 0
                    output[-1].append((attr, line))
                    x += util.glyphwidth(line)
                    if remaining < 0:
                        output[-1].append((attr, '\n'))

                    if remaining <= 0:
                        screenlines -= 1
                        y, x = y + 1, 0
                        output.append([])
                    if screenlines <= 0:
                        break
            sill.offset = max(0, chunkat - screenlines - 1)

        self.log.debug('r_c visible=%s bars=%s', visible, bars)
        if visible is not None and visible < 0:
            l = output[self.head.offset + visible]
            output[self.head.offset] = l
            if l:
                a, t = l[-1]
                if t == '\n':
                    w = sum(util.glyphwidth(s) for (a, s) in l[:-1])
                    if w < (self.width - 1):
                        l[-1] = (a, '…\n')
                    else:
                        l[-1] = (a, '…')
                else:  # likely, wrapped
                    l[-1] = (a, t[:-1] + '…')
            else:
                l.append((0, '…'))
            if visible in bars:
                bars[bars.index(visible)] = 0
            self.log.debug('r_c switching to visible, 2 bars=%s', bars)

        output = output[self.head.offset:self.head.offset + self.height]
        output += [[] for _ in range(self.height - len(output))]

        if self.y + self.height < self.ui.maxy:
            if not output[-1]:
                output[-1] = [(0, '')]
            output[-1] = [(a | curses.A_UNDERLINE, t) for (a, t) in output[-1]]

        for y in bars:
            if y < 0:
                continue
            if not output[y]:
                output[y] = [(0, '')]
            actbold = curses.A_BOLD if self.active() else curses.A_DIM
            output[y] = [
                ((a ^ curses.A_REVERSE) | actbold, t) for (a, t) in output[y]]

        self.log.debug(
            'redisplay_calculate exiting, cursor=%s, visible=%s',
            repr(cursor),
            repr(visible),
            )
        return (
            visible is not None and visible < self.height,
            cursor,
            sill,
            output)

    def redisplay_internal(self):
        self.log.debug(
            'in redisplay_internal: w=%d, h=%d, frame=%s',
            self.width,
            self.height,
            repr(self.head),
            )

        if self.window.cursor != self.old_cursor:
            self.reframe_state = 'hard'
            self.old_cursor = self.window.cursor

        self.w.erase()

        visible, self.cursorpos, self.sill, output = self.redisplay_calculate()
        import pprint
        self.log.debug(
            'redisplay_internal: %s, %s, %s %d\n%s',
            visible,
            self.cursorpos,
            self.sill,
            len(output),
            pprint.pformat(output))
        for y, line in enumerate(output):
            self.move(y, 0)
            x = 0
            attr = 0
            for attr, text in line:
                self.bkgdset(attr)
                if line == '\n':
                    self.clrtoeol()
                try:
                    self.w.addstr(y, x, text, attr)
                except curses.error:
                    self.log.debug(
                        'addstr(%d, %d, %s, %d) errored.  *yawn*',
                        y, x, repr(text), attr)
                x += util.glyphwidth(text)
            else:
                if line != '\n':
                    self.clrtoeol()
            self.bkgdset(0)

        self.log.debug(
            'redisplay_internal exiting, cursor=%s, visible=%s',
            repr(self.cursorpos),
            repr(visible),
            )
        return visible

    def place_cursor(self):
        if self.active():
            if self.cursorpos is not None:
                self.log.debug(
                    'placing cursor(%s): %s',
                    repr(self.window), repr(self.cursorpos))
                self.w.leaveok(0)
                with contextlib.suppress(curses.error):
                    curses.curs_set(1)
                self.move(*self.cursorpos)
                self.w.cursyncup()
                self.w.noutrefresh()
            else:
                self.log.debug('not placing')
                try:
                    curses.curs_set(0)
                except curses.error:
                    self.move(self.height - 1, self.width - 1)
        else:
            self.log.debug('place_cursor called on inactive window')
            self.w.leaveok(1)

    def check_redisplay_hint(self, hint):
        return self.window.check_redisplay_hint(hint)

    def makefunc(name):
        def _(self, *args):
            import inspect
            self.curses_log.debug(
                '%d:%s%s',
                inspect.currentframe().f_back.f_lineno,
                name,
                repr(args))
            try:
                return getattr(self.w, name)(*args)
            except Exception:
                self.log.error(
                    '%s(%s) raised', name, ', '.join(repr(x) for x in args))
                raise
        return _
    for func in 'addstr', 'move', 'chgat', 'attrset', 'bkgdset', 'clrtoeol':
        locals()[func] = makefunc(func)

    del func, makefunc

    def reframe(self, target=None, action=None):
        self.log.debug(
            'reframe(target=%s, action=%s) window=%s',
            repr(target), repr(action), repr(self.window))

        cursor, chunk = next(self.window.view(self.window.cursor, 'backward'))

        if action == 'pagedown':
            self.head = self.sill
            if self.head.offset > 0:
                self.head.offset -= 1
            self.log.debug('reframe pagedown to %s', self.head)
            self.reframe_state = 'soft'
            self.old_cursor = self.window.cursor
            return
        elif action == 'pageup':
            screenlines = self.height - 1 - self.head.offset
            self.log.debug('reframe pageup, screenline=%d', screenlines)
        elif action == 'clever-down':
            screenlines = max(self.height - self.chunksize(chunk), 0)
        elif target is None:
            screenlines = self.height // 2
        elif target >= 0:
            screenlines = min(self.height - 1, target)
        else:  # target < 0
            screenlines = max(self.height + target, 0)

        self.log.debug('reframe, previous frame=%s', repr(self.head))
        self.log.debug(
            'reframe, height=%d, target=%d', self.height, screenlines)

        self.head = Location(self, cursor)
        self.log.debug(
            'reframe, initial, mark=%x: %s', id(cursor), repr(self.head))

        view = self.window.view(self.window.cursor, 'backward')

        mark, chunk = next(view)
        self.log.debug(
            'reframe looking for cursor, mark=%s, chunk=%s',
            repr(mark), repr(chunk))
        chunk = itertools.takewhile(
            lambda x: 'visible' not in x[0],
            chunk)
        chunk = list(chunk)
        chunklines = self.chunksize(chunk)
        self.log.debug(
            'reframe cursor chunk, screenlines=%d, chunklines=%s',
            screenlines, chunklines)
        if not chunklines:
            self.log.debug('reframe, not chunklines, chunk=%s', chunk)
        screenlines -= chunklines
        self.log.debug(
            'reframe cursor chunk, loop bottom, mark=%x, /offset=%d',
            id(mark), max(0, -screenlines))

        if screenlines <= 0:
            self.head = Location(self, mark, max(0, -screenlines - 1))
        else:
            for mark, chunk in view:
                chunklines = self.chunksize(chunk)
                self.log.debug(
                    'reframe, screenlines=%d, len(chunklines)=%s',
                    screenlines, chunklines)
                screenlines -= chunklines
                if screenlines <= 0:
                    break
                self.log.debug(
                    'reframe, loop bottom, mark=%x, /offset=%d',
                    id(mark), max(0, -screenlines))
            self.head = Location(self, mark, max(0, -screenlines))

        self.log.debug(
            'reframe, post-loop,   mark=%x, /offset=%d',
            id(mark), max(0, -screenlines))
        self.log.debug(
            'reframe, post-loop, screenlines=%d, head=%s',
            screenlines, repr(self.head))

    def chunksize(self, chunk):
        lines = 0
        remaining = None

        for tags, text in chunk:
            for line, remaining in self.doline(
                    text, self.width, remaining, tags):
                if 'right' in tags:
                    remaining = 0
                if remaining < 1:
                    lines += 1
        if remaining and remaining > 0 and remaining != self.width:
            lines += 1

        return lines

    def focus(self):
        self.window.focus()

    def display_range(self):
        if self.head:
            return self.head.cursor, self.sill.cursor
        return None, None


unkey = dict(
    (getattr(curses, k), k[len('KEY_'):])
    for k in dir(curses)
    if k.startswith('KEY_'))
key = dict(
    (k[len('KEY_'):], getattr(curses, k))
    for k in dir(curses)
    if k.startswith('KEY_'))


class RedisplayInProgress(Exception):
    pass


Whence = collections.namedtuple(
    'Whence', [
        'window', 'stole_lines', 'stole_from', 'stole_entire', 'stole_hints'])


class TTYFrontend:
    INTCHAR = 7  # Control-G # XXX

    def __init__(self):
        self.stdscr, self.maxy, self.maxx, self.input, self.output = (None,)*5
        self.windows = []
        self.notify_silent = True
        self.log = logging.getLogger('%s.%x' % (
            self.__class__.__name__,
            id(self),
            ))
        self.full_redisplay = False
        self.in_redisplay = False

    def __enter__(self):
        locale.setlocale(locale.LC_ALL, '')
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.nonl()
        curses.raw()

        termstate = termios.tcgetattr(0)
        termstate[6][termios.VINTR] = bytes([self.INTCHAR])
        nope = bytes([0])  # to disable a character
        termstate[6][termios.VQUIT] = nope
        termstate[6][termios.VSUSP] = nope
        if hasattr(termios, 'VDSUSP'):
            termstate[6][termios.VDSUSP] = nope  # pragma: nocover
        termstate[3] |= termios.ISIG
        termios.tcsetattr(0, termios.TCSANOW, termstate)

        self.stdscr.keypad(1)
        self.stdscr.nodelay(1)
        self.color_assigner = ttycolor.get_assigner()
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.orig_sigtstp = signal.signal(signal.SIGTSTP, self.sigtstp)
        self.main_pid = os.getpid()
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGWINCH, self.sigwinch, loop)

        with mock.patch(
                'asyncio.unix_events._sighandler_noop', self.sighandler_op):
            loop.add_signal_handler(signal.SIGINT, self.sigint)

        return self

    def renderer(self, *args, **kw):
        return TTYRenderer(self, *args, **kw)

    def sigwinch(self, loop):
        loop.call_soon(self.perform_resize)

    def sigint(self):
        self.ungetch(chr(self.INTCHAR))

    def ungetch(self, k):
        curses.ungetch(k)
        self.readable()

    def sighandler_op(self, signum, frame):
        from . import window

        if signum != signal.SIGINT:
            return
        f = frame.f_back
        while f is not None:
            if (f.f_code is TTYFrontend.readable_int.__code__
                    or f.f_code is window.Window.catch_and_log_int.__code__):
                raise KeyboardInterrupt
            f = f.f_back

    def initial(self, winfactory, statusline=None):
        self.default_window = winfactory
        if self.windows or self.input is not None or self.output is not None:
            raise ValueError
        if statusline is None:
            self.set_active(0)
            self.windows = [self.renderer(0, self.maxy, winfactory())]
        else:
            self.set_active(1)
            self.windows = [
                self.renderer(0, statusline.height(), statusline),
                self.renderer(
                    statusline.height(), self.maxy - statusline.height(),
                    winfactory()),
                ]
        for r in reversed(self.windows):
            r.w.refresh()
        self.stdscr.refresh()

    def set_active(self, i):
        self.input = i
        self.output = i

    def set_active_input(self):
        self.set_active(self.input)

    def set_active_output(self, w):
        for i, fe in enumerate(self.windows):
            if fe.window is w:
                self.output = i
                return True
        return False

    def __exit__(self, type, value, tb):
        # go to last line of screen, maybe cause scrolling?
        self.color_assigner.close()
        self.stdscr.keypad(0)
        curses.noraw()
        curses.nl()
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
        pass  # XXX put a warning here or a debug log or something

    def perform_resize(self):
        self.log.debug('perform_resize: in_redisplay=%s', self.in_redisplay)
        if os.getpid() != self.main_pid:
            return  # sigh
        # four unsigned shorts per tty_ioctl(4)
        winsz = array.array('H', [0] * 4)
        fcntl.ioctl(0, termios.TIOCGWINSZ, winsz, True)
        curses.resizeterm(winsz[0], winsz[1])

        oldy = self.maxy
        self.maxy, self.maxx = self.stdscr.getmaxyx()

        new = []
        orphans = []
        remaining = self.maxy
        for (i, victim) in enumerate(self.windows):
            if hasattr(victim.window, 'height'):
                height = victim.window.height()
            elif victim.window.noresize:
                height = victim.height
            else:
                # should get proportional chunk of remaining?
                # think harder later.
                height = max(1, int(victim.height * (self.maxy / oldy)))
                height = min(height, remaining)
            if height > remaining:
                orphans.append(victim)
            else:
                new.append([
                    victim.window,
                    self.maxy - remaining,
                    height,
                    i == self.input,
                    i == self.output,
                    victim.get_hints(),
                    victim.whence,
                    ])
            remaining -= height
        if remaining:
            new[-1][2] += remaining

        for victim in orphans:
            # it sounds terrible when I put it that way
            if victim.whence is not None:
                _destroy_whence(victim.whence)
                victim.window.destroy()

        self.set_active(None)
        self.windows = []
        for (i, (window, y, height, input, output, hints, whence)) \
                in enumerate(new):
            self.windows.append(
                self.renderer(y, height, window, hints=hints, whence=whence))
            if input:
                self.input = i
            if output:
                self.output = i

        for candidate in (self.output, self.input, 1):
            if candidate is not None:
                self.set_active(candidate)
                break

        self.windows[i].window.focus()
        self.log.debug('RESIZED %d windows', len(self.windows))
        self.redisplay()

    def readable(self):
        while True:  # make sure to consume all available input
            try:
                k = self.stdscr.get_wch()
            except curses.error as e:
                if e.args == ('no input',):
                    break
                raise
            if k == curses.KEY_RESIZE:
                self.log.debug('new size (%d, %d)' % (self.maxy, self.maxx))
            elif self.input is not None:
                if self.input >= len(self.windows):
                    self.input = 1
                # XXX
                state = (list(self.windows), self.input, self.output)
                try:
                    self.readable_int(k)
                except KeyboardInterrupt:
                    pass
                if state == (list(self.windows), self.input, self.output):
                    self.redisplay(
                        self.windows[self.output].window.redisplay_hint())
                else:
                    self.redisplay()

    def readable_int(self, k):
        self.windows[self.input].window.input_char(k)

    def force_repaint(self):
        self.stdscr.clearok(1)
        self.stdscr.refresh()
        self.full_redisplay = True

    def redisplay(self, hint=None):
        self.log.debug('windows = %s:%d', repr(self.windows), self.output)

        if self.in_redisplay:
            raise RedisplayInProgress

        while True:
            try:
                self.in_redisplay = True
                # short circuit the redisplay if there's pending input.
                readable, _, _ = select.select([0], [], [], 0)
                if readable:
                    self.full_redisplay = True
                    return

                if self.full_redisplay:
                    hint = None
                    self.full_redisplay = False

                if hint is None:
                    # only reset the color map if we're redrawing everything
                    self.color_assigner.reset()

                active = None
                for i in range(len(self.windows) - 1, -1, -1):
                    w = self.windows[i]
                    if i == self.output:
                        active = w
                    if not hint or w.check_redisplay_hint(hint):
                        self.log.debug('calling redisplay on 0x%x', id(w))
                        w.redisplay()
                if active is not None:
                    active.place_cursor()
                curses.doupdate()
                break
            except RedisplayInProgress:
                pass
            finally:
                self.in_redisplay = False

    def notify(self):
        if self.notify_silent:
            curses.flash()
        else:
            curses.beep()

    def split_window(self, new, select=False):
        r = self.windows[self.output]
        nh = r.height // 2

        if nh < r.minheight:
            raise Exception('too small to split')

        self.windows[self.output:self.output + 1] = [
            r.resize(r.y, nh),
            self.renderer(r.y + nh, r.height - nh, new),
            ]
        if select:
            self.switch_window(1)
        self.redisplay({'window': new})

    def delete_window_window(self, w):
        for i, fe in enumerate(self.windows):
            if fe.window is w:
                return self.delete_window(i)
        else:
            pass  # walk the whence tree and clean up

    def delete_window(self, n):
        if len(self.windows) == (2 if self.context.status is not None else 1):
            raise Exception('attempt to delete only window')

        if self.windows[n].window == self.context.status:
            raise Exception('attempt to delete status line')

        wmap = {self.windows[i].window: i for i in range(len(self.windows))}
        victim = self.windows[n]

        victim.window.destroy()

        if victim.whence is not None and victim.whence.stole_entire:
            # there's something that replaces this window
            self.windows[n] = self.renderer(
                victim.y,
                victim.whence.stole_lines,
                victim.whence.stole_from,
                hints=victim.whence.stole_hints,
                whence=victim.whence.stole_entire,
                )
        else:
            future = self.windows[:n] + self.windows[n + 1:]
            # figure out who gets the real estate
            if victim.whence is not None and victim.whence.stole_from in wmap:
                beneficiary = wmap[victim.whence.stole_from]
            else:
                potentials = [
                    (i + n + (1 if n == 0 else -1)) % len(future)
                    for i in range(len(future))]
                potentials = [
                    i for i in potentials
                    if not future[i].window.noresize]

                if not potentials:
                    raise Exception('attempt to delete sole resizeable window')

                beneficiary = potentials[0]

            del self.windows[n]

            if n <= beneficiary:
                tomove = range(n, beneficiary)
                moveby = -victim.height
                bmoveby = -victim.height
            elif n > beneficiary:
                tomove = range(n - 1, beneficiary, -1)
                moveby = victim.height
                bmoveby = 0

            for i in tomove:
                u = self.windows[i]
                self.windows[i] = u.resize(u.y + moveby, u.height)

            # perform the resize
            u = self.windows[beneficiary]
            self.windows[beneficiary] = u.resize(
                u.y + bmoveby, u.height + victim.height)

        # fix focus
        if victim.whence is not None and victim.whence.window in wmap:
            self.set_active(wmap[victim.whence.window])
        else:
            if n <= self.input:
                self.input = max(self.input - 1, 0)
            if n <= self.output:
                self.output = max(self.output - 1, 0)
        if not self.windows[self.output].window.focus():
            self.switch_window(1)

        self.full_redisplay = True

    def delete_current_window(self):
        self.delete_window(self.output)

    def delete_other_windows(self):
        for n in range(len(self.windows) - 1, -1, -1):
            if (n != self.input
                    and self.windows[n].window != self.context.status):
                if self.windows[n].whence is not None:
                    _destroy_whence(self.windows[n].whence)
                self.delete_window(n)

    def popup_window(self, new, height=1, whence=None, near=False):
        if near:
            which = self.output
        else:
            which = len(self.windows) - 1
        r = self.windows[which]

        if r.whence is not None and not near:
            self.windows[which] = self.renderer(
                r.y, r.height, new,
                whence=Whence(
                    whence, r.height, r.window, r.whence, r.get_hints()))
        else:
            # don't eat the entire bottom window
            height = min(height, r.height - 1)
            # shrink bottom window
            self.windows[which:which + 1] = [
                r.resize(r.y, r.height - height),
                self.renderer(
                    r.y + r.height - height, height, new,
                    whence=Whence(whence, height, r.window, None, None)),
                ]
            which += 1

        self.set_active(which)
        self.windows[self.output].focus()

    def switch_window(self, adj):
        current = self.output
        while True:
            self.set_active((self.output + adj) % len(self.windows))
            if self.output == current:
                break
            if self.windows[self.output].window.focus():
                break

    def get_windows(self):
        return (w.window for w in self.windows)

    def resize_statuswindow(self):
        if len(self.windows) < 2 or self.context.status is None:
            return False

        statusr, datar = self.windows[:2]

        height = statusr.window.height()
        delta = height - statusr.height

        if datar.height < delta:
            return False

        self.windows[:2] = [
            statusr.resize(0, height),
            datar.resize(height, datar.height - delta),
            ]

    def get_erasechar(self):
        return curses.erasechar()


class Location:
    """Abstraction for a pointer into whatever the window is displaying."""
    def __init__(self, fe, cursor, offset=0):
        self.fe = fe
        self.cursor = cursor
        self.offset = offset

    def __repr__(self):
        return '<Location %x: %s, %s +%d>' % (
            id(self), repr(self.fe), repr(self.cursor), self.offset)

    def shift(self, delta):
        if delta == 0:
            return self
        if delta <= 0 and -delta < self.offset:
            return Location(self.fe, self.cursor, self.offset + delta)

        direction = 'forward' if delta > 0 else 'backward'

        view = self.fe.window.view(self.cursor, direction)
        cursor, chunks = next(view)
        lines = self.fe.chunksize(chunks)
        if direction == 'forward':
            if self.offset + delta < lines:
                return Location(self.fe, self.cursor, self.offset + delta)
            delta -= lines - self.offset
            for cursor, chunks in view:
                lines = self.fe.chunksize(chunks)
                if delta < lines:
                    break
                delta -= lines
            return Location(self.fe, cursor, min(lines + delta, lines))
        else:  # 'backward', delta < 0
            delta += self.offset - 1
            for cursor, chunks in view:
                lines = self.fe.chunksize(chunks)
                if -delta <= lines:
                    break
                delta += lines
            return Location(self.fe, cursor, max(0, lines + delta))


# clear the ~popstack
def _destroy_whence(whence):
    whence.window.destroy()
    if whence.stole_entire is not None:
        _destroy_whence(whence.stole_entire)
