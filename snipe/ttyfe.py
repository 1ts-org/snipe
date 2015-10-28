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


import os
import curses
import locale
import signal
import logging
import itertools
import contextlib
import unicodedata
import array
import termios
import fcntl
import textwrap
import ctypes
import select

from . import util
from . import ttycolor


class TTYRenderer:
    def __init__(self, ui, y, h, window):
        self.log = logging.getLogger('TTYRender.%x' % (id(self),))
        self.curses_log = logging.getLogger('TTYRender.curses.%x' %  (id(self),))
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

        self.head = self.window.hints.get('head')
        self.sill = self.window.hints.get('sill')
        self.window.hints = {}

        self.reframe_state = 'hard'
        self.old_cursor = None

    def get_hints(self):
        return {'head': self.head, 'sill': self.sill}

    @property
    def active(self):
        return self.ui.windows[self.ui.active] == self

    def write(self, s):
        self.log.debug('someone used write(%s)', repr(s))

    def redisplay(self):
        if self.head is None:
            self.log.debug('redisplay with no frame, firing reframe')
            self.reframe()
        visible = self.redisplay_internal()
        if not visible:
            self.log.warning('redisplay, no visibility, firing reframe')
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
                self.log.error('redisplay, no visibility after clever reframe')
                self.reframe()
            visible = self.redisplay_internal()
            if not visible:
                self.log.error('no visibility after hail-mary reframe, giving up')

        self.w.noutrefresh()

    @staticmethod
    def width(s):
        return sum(wcwidth(c) for c in s)

    @staticmethod
    @util.listify
    def doline(s, width, remaining, tags=()):
        '''string, window width, remaining width, tags ->
        iter([(displayline, remaining), ...])'''
        # turns tabs into spaces at n*8 cell intervals

        right = 'right' in tags

        if 'fill' in tags and s:
            nl = s.endswith('\n')
            ll = textwrap.wrap(s, remaining)
            s = '\n'.join([ll[0]] + textwrap.wrap(' '.join(ll[1:]), width))
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
                l = TTYRenderer.width(c)
                if col + l > width:
                    if right and line == 0:
                        yield '', -1
                        col = remaining
                    else:
                        yield out, 0
                        out = ''
                        col = 0
                    line += 1
                    if len(c) > 1: # it's a TAB
                        continue
                out += c
                col += l
            # non printing characters... don't
        if out:
            yield out, width - col

    def compute_attr(self, tags):
        #A_BLINK A_DIM A_INVIS A_NORMAL A_STANDOUT A_REVERSE A_UNDERLINE
        attrs = {
            'bold': curses.A_BOLD,
            'standout': (
                curses.A_REVERSE | (curses.A_BOLD if self.active else 0)
                ),
            'reverse': curses.A_REVERSE,
            'underline': curses.A_UNDERLINE,
            }
        attr = 0
        fg, bg = '', ''
        for t in tags:
            attr |= attrs.get(t, 0)
            if t.startswith('fg:'):
                fg = t[3:]
            if t.startswith('bg:'):
                bg = t[3:]
        if 'standout' in tags and not self.active:
            fg = self.ui.color_assigner.dim(fg)
        attr |= self.ui.color_assigner(fg, bg)
        return attr

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
        self.w.move(0,0)

        visible = False
        cursor = None
        screenlines = self.height + self.head.offset
        remaining = None

        for mark, chunk in self.window.view(self.head.cursor):
            if screenlines <= 0:
                break
            self.sill = Location(self, mark)
            chunkat = screenlines

            for tags, text in chunk:
                if screenlines <= 0:
                    break
                attr = self.compute_attr(tags)
                if 'cursor' in tags:
                    cursor = self.w.getyx()
                if 'visible' in tags and (
                        screenlines <= self.height
                        or self.reframe_state == 'soft'):
                    visible = True
                if 'right' in tags:
                    text = text.rstrip('\n') #XXX chunksize

                textbits = self.doline(text, self.width, remaining, tags)
                if not textbits:
                    x = 0 if remaining is None else remaining
                    textbits = [('', self.width if x <= 0 else x)]
                for line, remaining in textbits:
                    if screenlines == 1 and self.y + self.height < self.ui.maxy:
                        attr |= curses.A_UNDERLINE
                    self.attrset(attr)
                    self.bkgdset(attr)

                    if 'right' in tags:
                        line = ' '*remaining + line
                        remaining = 0
                    if screenlines <= self.height:
                        try:
                            self.w.addstr(line)
                        except curses.error:
                            if screenlines != 1 or remaining != 0:
                                raise
                        self.chgat(attr)

                    if remaining <= 0:
                        screenlines -= 1
                    if screenlines <= 0:
                        break
                    if remaining == -1:
                        if screenlines > 0 and screenlines < self.height:
                            try:
                                self.addstr('\n')
                            except:
                                self.log.exception(
                                    'adding newline,'
                                    ' screenlines=%d, remaining=%d',
                                    screenlines,
                                    remaining)
                    elif remaining == 0 and self.height >= screenlines: #XXX
                        self.move(self.height - screenlines, 0)
            # XXX I'm not sure the following is _correct_ but it produces the
            # correct result
            self.sill.offset = max(0, chunkat - screenlines - 1)

        if screenlines > 1 and self.y + self.height < self.ui.maxy:
            self.chgat(self.height - 1, 0, self.width, curses.A_UNDERLINE)

        self.attrset(0)
        self.bkgdset(0)
        self.w.leaveok(1)
        self.w.noutrefresh()

        self.cursorpos = cursor

        self.log.debug(
            'redisplay internal exiting, cursor=%s, visible=%s',
            repr(cursor),
            repr(visible),
            )
        return visible

    def place_cursor(self):
        if self.active:
            if self.cursorpos is not None:
                self.log.debug('placing cursor %s', repr(self.cursorpos))
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
                    self.move(self.height - 1, self.width -1)
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
            except Exception as e:
                self.log.exception(
                    '%s(%s) raised', name, ', '.join(repr(x) for x in args))
                raise
        return _
    for func in 'addstr', 'move', 'chgat', 'attrset', 'bkgdset':
        locals()[func] = makefunc(func)

    del func, makefunc

    def reframe(self, target=None, action=None):
        self.log.debug('reframe(target=%s, action=%s)', repr(target), repr(action))

        cursor, chunk = next(self.window.view(self.window.cursor, 'backward'))

        if action == 'pagedown':
            self.head = self.sill
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
        else: # target < 0
            screenlines = max(self.height + target, 0)

        self.log.debug('reframe, previous frame=%s', repr(self.head))
        self.log.debug('reframe, height=%d, target=%d', self.height, screenlines)

        self.head = Location(self, cursor)
        self.log.debug('reframe, initial,     mark=%x: %s', id(cursor), repr(self.head))

        view = self.window.view(self.window.cursor, 'backward')

        mark, chunk = next(view)
        chunk = itertools.takewhile(
            lambda x: 'visible' not in x[0],
            chunk)
        chunklines = self.chunksize(chunk)
        self.log.debug('reframe cursor chunk, screenlines=%d, len(chunklines)=%s', screenlines, chunklines)
        screenlines -= chunklines
        self.log.debug('reframe cursor chunk, loop bottom, mark=%x, /offset=%d', id(mark), max(0, -screenlines))

        if screenlines <= 0:
            self.head = Location(self, mark, max(0, -screenlines - 1))
        else:
            for mark, chunk in view:
                chunklines = self.chunksize(chunk)
                self.log.debug('reframe, screenlines=%d, len(chunklines)=%s', screenlines, chunklines)
                screenlines -= chunklines
                if screenlines <= 0:
                    break
                self.log.debug('reframe, loop bottom, mark=%x, /offset=%d', id(mark), max(0, -screenlines))
            self.head = Location(self, mark, max(0, -screenlines))

        self.log.debug('reframe, post-loop,   mark=%x, /offset=%d', id(mark), max(0, -screenlines))
        self.log.debug('reframe, post-loop, screenlines=%d, head=%s', screenlines, repr(self.head))

    def chunksize(self, chunk):
        lines = 0
        remaining = None
        #self.log.debug('chunksize(%s) self.width=%d', repr(chunk), self.width)
        for tags, text in chunk:
            for line, remaining in self.doline(text, self.width, remaining, tags):
                #self.log.debug('lines=%d, doline() => (%s, %d)', lines, line, remaining)
                if 'right' in tags:
                    remaining = 0
                if remaining < 1:
                    lines += 1
        if remaining and remaining > 0 and remaining != self.width:
            lines += 1
            #self.log.debug('partial line, rounding up, lines=%d', lines)
        #self.log.debug('chunksize() => %d', lines)
        return lines

    def focus(self):
        self.window.focus()

    def display_range(self):
        return self.head.cursor, self.sill.cursor


unkey = dict(
    (getattr(curses, k), k[len('KEY_'):])
    for k in dir(curses)
    if k.startswith('KEY_'))
key = dict(
    (k[len('KEY_'):], getattr(curses, k))
    for k in dir(curses)
    if k.startswith('KEY_'))


class TTYFrontend:
    def __init__(self):
        self.stdscr, self.maxy, self.maxx, self.active = (None,)*4
        self.windows = []
        self.notify_silent = True
        self.log = logging.getLogger('%s.%x' % (
            self.__class__.__name__,
            id(self),
            ))
        self.popstack = []
        self.full_redisplay = False

    def __enter__(self):
        locale.setlocale(locale.LC_ALL, '')
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.nonl()
        curses.raw()
        self.stdscr.keypad(1)
        self.stdscr.nodelay(1)
        curses.start_color()
        self.color = curses.has_colors()
        if not self.color:
            self.color_assigner = ttycolor.NoColorAssigner()
        else:
            curses.use_default_colors()
            if curses.can_change_color():
                self.color_assigner = ttycolor.DynamicColorAssigner()
            else:
                self.color_assigner = ttycolor.StaticColorAssigner()
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.orig_sigtstp = signal.signal(signal.SIGTSTP, self.sigtstp)
        self.main_pid = os.getpid()
        signal.signal(signal.SIGWINCH, self.doresize)
        return self

    def initial(self, winfactory, statusline=None):
        self.default_window=winfactory
        if self.windows or self.active is not None:
            raise ValueError
        if statusline is None:
            self.active = 0
            self.windows = [TTYRenderer(self, 0, self.maxy, win)]
        else:
            self.active = 1
            self.windows = [
                TTYRenderer(self, 0, 1, statusline),
                TTYRenderer(self, 1, self.maxy - 1, winfactory()),
                ]
        for r in self.windows:
            r.w.refresh()
        self.stdscr.refresh()

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
        pass #XXX put a warning here or a debug log or something

    def doresize(self, signum, frame):
        if os.getpid() != self.main_pid:
            return # sigh
        winsz = array.array('H', [0] * 4) # four unsigned shorts per tty_ioctl(4)
        fcntl.ioctl(0, termios.TIOCGWINSZ, winsz, True)
        curses.resizeterm(winsz[0], winsz[1])

        oldy = self.maxy
        self.maxy, self.maxx = self.stdscr.getmaxyx()

        new = []
        orphans = []
        remaining = self.maxy
        for (i, victim) in enumerate(self.windows):
            if victim.window.noresize:
                height = victim.height
            else:
                # should get proportional chunk of remaining? think harder later.
                height = max(1, int(victim.height * (self.maxy / oldy)))
            if height > remaining:
                orphans.append(victim)
            else:
                new.append([
                    victim.window,
                    self.maxy - remaining,
                    height,
                    i == self.active,
                    ])
            remaining -= height
        if remaining:
            new[-1][2] += remaining

        for victim in orphans: # it sounds terrible when you put it that way
            with contextlib.suppress(ValueError):
                self.popstack.remove(victim)
            victim.window.destroy()

        self.active = 0
        self.windows = []
        for (i, (window, y, height, active)) in enumerate(new):
            self.windows.append(TTYRenderer(self, y, height, window))
            if active:
                self.active = i

        self.windows[i].window.focus()
        self.log.debug('RESIZED %d windows', len(self.windows))
        self.redisplay()

    def readable(self):
        while True: # make sure to consume all available input
            try:
                k = self.stdscr.get_wch()
            except curses.error:
                break
            if k == curses.KEY_RESIZE:
                self.log.debug('new size (%d, %d)' % (self.maxy, self.maxx))
            elif self.active is not None:
                #XXX
                state = (list(self.windows), self.active)
                self.windows[self.active].window.input_char(k)
                if state == (list(self.windows), self.active):
                    self.redisplay(self.windows[self.active].window.redisplay_hint())
                else:
                    self.redisplay()

    def force_repaint(self):
        self.stdscr.clearok(1)
        self.stdscr.refresh()
        self.full_redisplay = True

    def redisplay(self, hint=None):
        self.log.debug('windows = %s:%d', repr(self.windows), self.active)

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
        for i, w in enumerate(self.windows):
            if i == self.active:
                active = w
            if not hint or w.check_redisplay_hint(hint):
                self.log.debug('calling redisplay on 0x%x', id(w))
                w.redisplay()
        if active is not None:
            active.place_cursor()
        curses.doupdate()

    def notify(self):
        if self.notify_silent:
            curses.flash()
        else:
            curses.beep()

    def split_window(self, new):
        r = self.windows[self.active]
        nh = r.height // 2

        if nh == 0:
            raise Exception('too small to split')

        self.windows[self.active:self.active + 1] = [
            TTYRenderer(self, r.y, nh, r.window),
            TTYRenderer(self, r.y + nh, r.height - nh, new),
            ]
        self.redisplay({'window': new})

    def delete_window(self, n):
        if len(self.windows) == 2:
            raise Exception('attempt to delete only window')

        if self.windows[n].window == self.context.status:
            raise Exception('attempt to delete status line')

        victim = self.windows[n]

        if self.popstack and self.popstack[-1][0] is victim.window:
            self.popdown_window()
            return

        potentials = [
            (i + n + (1 if n == 0 else -1)) % len(self.windows)
            for i in range(len(self.windows))]
        potentials = [
            i for i in potentials
            if not self.windows[i].window.noresize and i != n]

        if not potentials:
            raise Exception('attempt to delete sole resizeable window')

        beneficiary = potentials[0]

        victim.window.destroy()

        if n < beneficiary:
            tomove = range(n + 1, beneficiary)
            moveby = -victim.height
            bmoveby = -victim.height
        elif n > beneficiary:
            tomove = range(n - 1, beneficiary, -1)
            moveby = victim.height
            bmoveby = 0

        for i in tomove:
            u = self.windows[i]
            self.windows[i] = TTYRenderer(self, u.y + moveby, u.height, u.window)

        u = self.windows[beneficiary]
        self.windows[beneficiary] = TTYRenderer(
            self, u.y + bmoveby, u.height + victim.height, u.window)

        del self.windows[n]

        if n <= self.active:
            self.active -= 1
        if not self.windows[self.active].window.focus():
            self.switch_window(1)

    def delete_current_window(self):
        self.delete_window(self.active)

    def delete_other_windows(self):
        # clear the popstack
        if self.popstack and self.windows[self.active] == self.popstack[-1][0]:
            return
        for window, height in self.popstack[:-1]:
            window.destroy()
        del self.popstack[:-1]
        for n in range(len(self.windows) - 1, -1, -1):
            if (n != self.active
                    and self.windows[n].window != self.context.status):
                self.delete_window(n)

    def popup_window(self, new, height=1, select=True):
        r = self.windows[-1]

        if r.height <= height and self.popstack and \
          r.window != self.popstack[-1][0]:
            self.popstack.append((r.window, r.height))

        if self.popstack and r.window == self.popstack[-1][0]:
            # update the height
            self.popstack[-1] = (r.window, r.height)
            self.windows[-1] = TTYRenderer(
                self, r.y, r.height, new)
        else:
            # don't eat the entire bottom window
            height = min(height, r.height - 1)
            # shrink bottom window
            self.windows[-1] = TTYRenderer(
                self, r.y, r.height - height, r.window)
            # add; should be in the rotation right active active
            self.windows.append(TTYRenderer(
                self, r.y + r.height - height, height, new))

        self.popstack.append((new, height))
        if select:
            self.active = len(self.windows) - 1
            self.windows[self.active].focus()

    def popdown_window(self):
        victim_window, _ = self.popstack.pop()
        try:
            victim_window.destroy()
        except:
            self.log.exception('attempting window destroy callback')
        victim = self.windows.pop()
        adj = self.windows[-1]
        if self.popstack:
            new_window, new_height = self.popstack[-1]
            dheight = new_height - victim.height
            if adj.window.noresize:
                self.window.append(TTYRenderer(
                    self, victim.y, victim.height, new_window))
            else:
                self.windows[-1:] = [
                    TTYRenderer(
                        self, adj.y, adj.height - dheight, adj.window),
                    TTYRenderer(
                        self, victim.y - dheight, new_height, new_window),
                    ]
        else:
            if adj.window.noactive:
                self.windows.append(
                    TTYRenderer(
                        self, victim.y, victim.height, self.default_window()))
            else:
                self.windows[-1] = TTYRenderer(
                    self, adj.y, adj.height + victim.height, adj.window)
        if self.active >= len(self.windows):
            self.active = len(self.windows) - 1
            self.windows[self.active].focus()
        self.redisplay() # XXX force redisplay?

    def switch_window(self, adj):
        current = self.active
        while True:
            self.active = (self.active + adj) % len(self.windows)
            if self.active == current:
                break
            if self.windows[self.active].window.focus():
                break

    def get_windows(self):
        return (w.window for w in self.windows)


class Location:
    """Abstraction for a pointer into whatever the window is displaying."""
    def __init__(self, fe, cursor, offset=0):
        self.fe = fe
        self.cursor = cursor
        self.offset = offset
    def __repr__(self):
        return '<Location %x: %s, %s +%d>' % (id(self), repr(self.fe), repr(self.cursor), self.offset)
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
        else: # 'backward', delta < 0
            print (self.cursor, self.offset)
            delta += self.offset - 1
            for cursor, chunks in view:
                lines = self.fe.chunksize(chunks)
                if -delta <= lines:
                    break
                delta += lines
                print (cursor, lines, delta)
            print (cursor, lines, delta)
            return Location(self.fe, cursor, max(0, lines + delta))


def setup_wcwidth():
    LIBC='libc.so.6' # XXX current versions of linux
    try:
        ctypes.cdll.LoadLibrary(LIBC)
        libc = ctypes.CDLL(LIBC)
        os_wcwidth = libc.wcwidth
        def wcwidth(c):
            return os_wcwidth(ord(c))
    except (OSError, AttributeError):
        def wcwidth(c):
            # from http://bugs.python.org/msg155361
            # http://bugs.python.org/issue12568
            if (
                (c < ' ') or
                (u'\u1160' <= c <= u'\u11ff') or # hangul jamo
                (unicodedata.category(c) in ('Mn', 'Me', 'Cf')
                    and c != u'\u00ad') # 00ad = soft hyphen
                ):
                return 0
            if unicodedata.east_asian_width(c) in ('F', 'W'):
                return 2
            return 1
    return wcwidth

wcwidth = setup_wcwidth()
