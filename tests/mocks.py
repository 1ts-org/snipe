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

import sys

sys.path.append('..')
sys.path.append('../lib')

import snipe.ttycolor  # noqa: E402


class Backend:
    name = 'mock'


class Aggregator:
    def __init__(self):
        self._backends = [Backend()]

    def __iter__(self):
        yield from self._backends

    def walk(self, *args, **kw):
        yield Message()


class Context:
    def __init__(self, *args, **kw):
        self._message = ''
        self.conf = {}
        self.backends = Aggregator()
        self.context = self
        self.erasechar = chr(8)

    def message(self, s):
        self._message = s

    def copy(*args, **kw):
        pass


class FE:
    context = Context()
    called = set()

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

    def ungetch(self, *args, **kw):
        self.markcalled()


class Renderer:
    def get_hints(self):
        return {}


class Message:
    def __init__(self, **kw):
        self.dict = kw
        self.backend = self
        self.context = self
        self.conf = {}
        self.data = {}

    def field(self, name, canon=True):
        if canon and name.capitalize() in self.dict:
            return self.dict[name.capitalize()]
        return self.dict.get(name, '')

    def display(self, decoration):
        return []


class CursesWindow:
    def subwin(self, *args):
        return self

    def idlok(self, *args):
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
    hints = {}
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
            yield i, self.chunks[i]
