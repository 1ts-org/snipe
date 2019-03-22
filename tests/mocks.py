#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2017 the Snipe contributors
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
Various mocks for testing purposes
'''

import contextlib
import curses
import functools
import itertools
import sys

from typing import (Dict, Any, List, Optional, Tuple)
from unittest.mock import (patch)

import snipe.chunks
import snipe.filters
import snipe.ttycolor
import snipe.ttyfe
import snipe.window


class Backend:
    name = 'mock'
    index = ''


class Aggregator:
    def __init__(self):
        self._backends = [Backend()]
        self._messages = [Message()]
        self._target = None
        self._sent = []

    def __iter__(self):
        yield from self._backends

    def walk(
            self, origin, direction, filter=None, backfill_to=None,
            search=False,
            ):
        if backfill_to is not None:
            self._target = backfill_to
        if direction:
            for m in self._messages:
                if origin is not None and float(origin) > float(m.time):
                    continue
                yield m
        else:
            for m in reversed(self._messages):
                if origin is not None and float(origin) < float(m.time):
                    continue
                yield m

    def count(self):
        return len(self._messages)

    async def send(self, params, body):
        self._sent.append((params, body))

    def destinations(self):
        return ()

    def senders(self):
        return ()


@functools.total_ordering
class Message:
    time_counter = itertools.count()

    def __init__(self, **kw):
        self.dict = kw
        self.backend = self
        self.indent = ''
        self.context = kw.get('context', self)
        self.time = next(self.time_counter)
        self.conf = {}
        self.data = kw.get('data', {})
        self._display = snipe.chunks.Chunk()
        self.omega = False
        self.personal = False
        self.outgoing = False
        self.noise = False
        self.error = False
        self.sender = None
        self.body = ''
        self.transformed = None

    def field(self, name, canon=True):
        if canon and name.capitalize() in self.dict:
            return self.dict[name.capitalize()]
        return self.dict.get(name, '')

    def display(self, decoration):
        return self._display

    def __eq__(self, other):
        return other and self.time == other.time

    def __lt__(self, other):
        return self.time < other.time

    def __float__(self):
        return float(self.time)

    def filter(self, cleverness):
        return snipe.filters.Yes()

    def followup(self):
        return 'followup'

    def reply(self):
        return 'reply'

    def __repr__(self):
        return (
            '<' + self.__class__.__module__
            + '.' + self.__class__.__name__ + '>')

    def __str__(self):
        return self.body

    def transform(self, encoding, body):
        self.transfored = encoding
        self.body = body

    def __hash__(self):
        return id(self)


class Context:
    def __init__(self, *args, **kw):
        self.conf = {}
        self.backends = Aggregator()
        self.context = self
        self.erasechar = chr(8)
        self.starks = []
        self.status = None
        self.keys = []
        self.clear()
        self.kill_log = []

    def clear(self):
        self._message = ''

    def message(self, s):
        self._message = s

    def copy(self, data, append=None):
        self.kill_log.append((data, append))

    def write_starks(self):
        pass

    def conf_write(self):
        pass

    def keyecho(self, keystroke):
        self.keys.append(keystroke)

    def yank(self, off=1):
        if self.kill_log:
            return self.kill_log[-(1 + (off - 1) % len(self.kill_log))][0]
        else:
            return ''


class FE:
    def __init__(self):
        self.context = Context()
        self.called = set()

    def markcalled(self):
        self.called |= {sys._getframe().f_back.f_code.co_name}

    def redisplay(self, *args, **kw):
        self.markcalled()

    def notify(self, *args, **kw):
        self.markcalled()

    def force_repaint(self, *args, **kw):
        self.markcalled()

    def set_active_output(self, *args, **kw):
        self.markcalled()

    def set_active_input(self, *args, **kw):
        self.markcalled()

    def delete_current_window(self, *args, **kw):
        self.markcalled()

    def balance_windows(self, *args, **kw):
        self.markcalled()

    def resize_current_window(self, *args, **kw):
        self.markcalled()

    def ungetch(self, *args, **kw):
        self.markcalled()


class Renderer:
    def __init__(self, range=(None, None)):
        self._range = range

    def get_hints(self):
        return {}

    def display_range(self):
        return self._range

    def reframe(self, *args, **kw):
        pass


class UI:
    def __init__(self, maxx=80, maxy=24):
        self.stdscr = CursesWindow()
        self.maxx = maxx
        self.maxy = maxy
        self.windows = []
        self.active = 0
        self.color_assigner = snipe.ttycolor.NoColorAssigner()


class Window:
    hints: Dict[str, Any] = {}
    cursor = 0

    def __init__(self, chunks):
        self.chunks = chunks
        self.match_string = None
        self.match_forward = None
        self.find_string = None
        self.find_forward = None
        self.find_ret = True
        self.match_ret = False

    def match(self, string, forward=True):
        self.match_string = string
        self.match_forward = forward
        return self.match_ret

    def find(self, string, forward=True):
        self.find_string = string
        self.find_forward = forward
        return self.find_ret

    def redisplay(*args, **kw):
        pass

    def view(self, origin, direction='forward'):
        assert direction in ('forward', 'backward')
        if direction == 'forward':
            r = range(origin, len(self.chunks))
        elif direction == 'backward':
            r = range(origin, -1, -1)
        for i in r:
            yield snipe.chunks.View(i, self.chunks[i])


class CursesWindow:
    def __init__(self, height=0, width=0, y=0, x=0):
        self.height = height
        self.width = width
        self.y = y
        self.x = x

    def subwin(self, height, width, y, x):
        return CursesWindow(height, width, y, x)

    def idlok(self, *args):
        pass

    def erase(self):
        pass

    def move(self, *args):
        pass

    def bkgdset(self, *args):
        pass

    def addstr(self, *args):
        pass

    def clrtoeol(self):
        pass

    def noutrefresh(self):
        pass

    def refresh(self):
        pass

    def leaveok(self, *args):
        pass

    def cursyncup(self):
        pass

    def clearok(self, *args):
        pass


class Curses:
    A_ALTCHARSET = curses.A_ALTCHARSET
    A_ATTRIBUTES = curses.A_ATTRIBUTES
    A_BLINK = curses.A_BLINK
    A_BOLD = curses.A_BOLD
    A_CHARTEXT = curses.A_CHARTEXT
    A_COLOR = curses.A_COLOR
    A_DIM = curses.A_DIM
    A_HORIZONTAL = curses.A_HORIZONTAL
    A_INVIS = curses.A_INVIS
    A_LEFT = curses.A_LEFT
    A_LOW = curses.A_LOW
    A_NORMAL = curses.A_NORMAL
    A_PROTECT = curses.A_PROTECT
    A_REVERSE = curses.A_REVERSE
    A_RIGHT = curses.A_RIGHT
    A_STANDOUT = curses.A_STANDOUT
    A_TOP = curses.A_TOP
    A_UNDERLINE = curses.A_UNDERLINE
    A_VERTICAL = curses.A_VERTICAL
    COLOR_BLACK = curses.COLOR_BLACK
    COLOR_RED = curses.COLOR_RED
    COLOR_GREEN = curses.COLOR_GREEN
    COLOR_YELLOW = curses.COLOR_YELLOW
    COLOR_BLUE = curses.COLOR_BLUE
    COLOR_MAGENTA = curses.COLOR_MAGENTA
    COLOR_CYAN = curses.COLOR_CYAN
    COLOR_WHITE = curses.COLOR_WHITE

    COLOR_PAIRS = None
    COLORS = None
    dynamic = None
    pairs: List[Optional[Tuple[int, int]]] = []

    COLUMNS = 80
    LINES = 24

    error = Exception

    def __init__(self, colors=0, dynamic=False, color_pairs=256):
        self.COLORS = colors
        self.COLOR_PAIRS = color_pairs
        self.dynamic = dynamic
        self.pairs = [None] * self.COLOR_PAIRS
        self.stdscr = CursesWindow(self.LINES, self.COLUMNS, 0, 0)

    def init_pair(self, pair, fg, bg):
        self.pairs[pair] = (fg, bg)

    def color_pair(self, pair):
        return pair

    def color_content(self, number):
        return None, None, None

    def init_color(self, color, r, g, b):
        pass

    def has_colors(self):
        return bool(self.COLORS)

    def start_color(self):
        pass

    def use_default_colors(self):
        pass

    def can_change_color(self):
        return self.dynamic

    def doupdate(self):
        pass

    def flash(self):
        pass


@contextlib.contextmanager
def mocked_up_actual_fe(window_factory=None, statusline_factory=None):
    curses = Curses()
    with patch('snipe.ttyfe.curses', curses):
        fe = snipe.ttyfe.TTYFrontend()
        # emulating fe.__enter_
        fe.stdscr = curses.stdscr
        fe.maxy = curses.LINES
        fe.maxx = curses.COLUMNS
        fe.context = Context()
        fe.color_assigner = snipe.ttycolor.NoColorAssigner()
        fe.running = True

        if window_factory is None:
            window_factory = snipe.window.Window

        fe.initial(window_factory, statusline_factory)

        yield fe


@contextlib.contextmanager
def mocked_up_actual_fe_window(window_factory=None, statusline_factory=None):
    with mocked_up_actual_fe(window_factory, statusline_factory) as fe:
        yield fe.windows[fe.output].window


def promise(val=None):
    async def f(*args, **kw):
        return val

    return f()
