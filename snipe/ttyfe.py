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


import os
import curses
import locale
import signal
import logging
import itertools


class TTYRenderer(object):
    def __init__(self, ui, y, h, window):
        self.log = logging.getLogger('TTYRender.%x' % (id(self),))
        self.ui, self.y, self.height = ui, y, h
        self.x = 0
        self.width = ui.maxx
        self.window = window
        self.window.renderer = self
        self.log.debug(
            'subwin(%d, %d, %d, %d)', self.height, self.width, self.y, self.x)
        self.w = ui.stdscr.subwin(self.height, self.width, self.y, self.x)
        self.w.idlok(1)
        #self.w.scrollok(1)
        self.context = None

    @property
    def active(self):
        return self.ui.windows[self.ui.active] == self

    def write(self, s):
        self.log.debug('someone used write(%s)', repr(s))

    def redisplay(self):
        if self.window.frame is None:
            self.log.debug('redisplay with no frame, firing reframe')
            self.reframe()
        visible = self.redisplay_internal()
        if not visible:
            self.log.debug('redisplay, no visibility, firing reframe')
            self.reframe()
            visible = self.redisplay_internal()
            if not visible:
                self.log.debug('redisplay, no visibility after reframe')
        self.w.noutrefresh()

    @staticmethod
    def doline(s, width, remaining):
        '''string, window width, remaining width ->
        iter([(displayline, remaining), ...])'''
        # turns tabs into spaces at n*8 cell intervals
        #XXX needs initial offset for tab stops
        #and for width after newline
        out = ''
        col = 0 if remaining is None or remaining <= 0 else width - remaining
        for c in s:
            # XXX Unicode width, combining characters, etc.
            if c == '\n':
                yield out, -1
                out = ''
                col = 0
            elif ' ' <= c <= '~': #XXX should look up unicode category
                if col >= width:
                    yield out, 0
                    out = ''
                    col = 0
                out += c
                col += 1
            elif c == '\t':
                n = (8 - col % 8)
                if col + n >= width:
                    yield out, 0
                    out = ''
                    col = 0
                else:
                    col += n
                    out += ' ' * n
            # non printing characters... don't
        if out:
            yield out, width - col

    def redisplay_internal(self):
        self.log.debug(
            'in redisplay_internal: w=%d, h=%d, frame=%s',
            self.width,
            self.height,
            repr(self.window.frame),
            )

        self.w.erase()
        self.w.move(0,0)

        visible = False
        cursor = None
        screenlines = self.height
        remaining = None

        for mark, chunk in self.window.view(self.window.frame):
            for tags, text in chunk:
                if screenlines <= 0:
                    break
                if 'cursor' in tags:
                    cursor = self.w.getyx()
                if 'visible' in tags:
                    visible = True
                for line, remaining in self.doline(text, self.width, remaining):
                    try:
                        self.w.addstr(line)
                    except:
                        self.log.exception(
                            'in addstr; line=%s, remaining=%d, screenlines=%d',
                            line, remaining, screenlines)
                    if remaining <= 0:
                        screenlines -= 1
                    if screenlines <= 0:
                        break
                    if remaining == -1:
                        if screenlines > 0:
                            try:
                                self.w.addstr('\n')
                            except:
                                self.log.exception(
                                    'adding newline,'
                                    ' screenlines=%d, remaining=%d',
                                    screenlines,
                                    remaining)
                        else:
                            break
                    elif remaining == 0:
                        self.w.move(self.height - screenlines, 0)
        if self.y + self.height < self.ui.maxy:
            self.w.chgat(self.height - 1, 0, self.width, curses.A_UNDERLINE)
        if cursor is not None and self.active:
            self.w.leaveok(0)
            self.w.move(*cursor)
        else:
            self.w.leaveok(1)
        self.log.debug(
            'redisplay internal exiting, cursor=%s, visible=%s',
            repr(cursor),
            repr(visible),
            )
        return visible

    def reframe(self):
        screenlines = self.height / 2
        ## view = iter(self.window.view(self.cursor, 'backward'))
        ## mark, chunk = view.next()
        ## self.window.frame = mark
        ## chunk = itertools.takewhile(
        ##     lambda: 'visible' not in x[0],
        ##     chunk)
        ## chunklines = list(self.doline(''.join(c[1] for c in chunk)))
        ## # if len(chunklines) - 1 > self.height: *sob*
        self.log.debug('reframe, previous frame=%s', repr(self.window.frame))
        for mark, chunk in self.window.view(self.window.cursor, 'backward'):
            self.window.frame = mark
            # this should only drop stuff off the first chunk...
            chunk = itertools.takewhile(
                lambda x: 'visible' not in x[0],
                chunk)
            chunklines = list(self.doline(''.join(c[1] for c in chunk), self.width, self.width))
            screenlines -= len(chunklines)
            if screenlines <= 0:
                break

unkey = dict(
    (getattr(curses, k), k[len('KEY_'):])
    for k in dir(curses)
    if k.startswith('KEY_'))
key = dict(
    (k[len('KEY_'):], getattr(curses, k))
    for k in dir(curses)
    if k.startswith('KEY_'))


class TTYFrontend(object):
    def __init__(self):
        self.stdscr, self.maxy, self.maxx, self.active = (None,)*4
        self.windows = []
        self.notify_silent = True
        self.log = logging.getLogger('%s.%x' % (
            self.__class__.__name__,
            id(self),
            ))
        self.popstack = []

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
        if self.windows or self.active is not None:
            raise ValueError
        self.active = 0
        self.windows = [TTYRenderer(self, 0, self.maxy, win)]
        self.windows[self.active].w.refresh()
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
        if c in unkey:
            return unkey[c]
        return c

    def readable(self):
        k = self.getch()
        if self.active is not None:
            self.windows[self.active].window.input_char(k)
        self.redisplay()

    def redisplay(self):
        self.log.debug('windows = %s:%d', repr(self.windows), self.active)
        active = None
        for i, w in enumerate(self.windows):
            if i == self.active:
                active = w
            else:
                w.redisplay()
        if active is not None:
            active.redisplay()
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

    def delete_window(self, n):
        if len(self.windows) == 1:
            raise Exception('attempt to delete only window')

        victim = self.windows[n]
        del self.windows[n]
        if n == 0:
            u = self.windows[0]
            self.windows[0] = TTYRenderer(
                self, 0, victim.height + u.height, u.window)
        else:
            u = self.windows[n-1]
            self.windows[n-1] = TTYRenderer(
                self, u.y, victim.height + u.height, u.window)
            if self.active == n:
                self.active -= 1

    def delete_current_window(self):
        self.delete_window(self.active)

    def popup_window(self, new, height=1):
        r = self.windows[-1]

        if r.height <= height and r.window != self.popstack[-1][0]:
            self.popstack.append((r.window, r.height))

        if self.popstack and r.window == self.popstack[-1][0]:
            # update the height
            self.popstack[-1] = (r.window, r.height)
            self.windows[-1] = TTYRenderer(
                self, r.y, r.height, new)
        else:
            # shrink bottom window
            self.windows[-1] = TTYRenderer(
                self, r.y, r.height - height, r.window)
            # add; should be in the rotation right active active
            self.windows.append(TTYRenderer(
                self, r.y + r.height - height, height, new))

        self.popstack.append((new, height))

    def popdown_window(self):
        victim_window, _ = self.popstack.pop()
        victim = self.windows.pop()
        adj = self.windows[-1]
        if self.popstack:
            new_window, new_height = self.popstack[-1]
            dheight = new_height - victim.height
            self.windows[-1:] = [
                TTYRenderer(self, adj.y, adj.height - dheight, adj.window),
                TTYRenderer(self, victim.y - dheight, new_height, new_window),
                ]
        else:
            self.windows[-1] = TTYRenderer(
                self, adj.y, adj.height + victim.height, adj.window)
        if self.active >= len(self.windows):
            self.active = len(self.windows) - 1

    def switch_window(self, adj):
        self.active = (self.active + adj) % len(self.windows)
