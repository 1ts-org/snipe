#!/usr/bin/python3
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


import curses
import re
import logging

from . import util


class NoColorAssigner:
    loglevel = util.Level('log.color', 'ColorAssigner')

    def __init__(self):
        self.reset()
        self.log = logging.getLogger('ColorAssigner')

    def __call__(self, foreground, background):
        return 0

    def reset(self):
        pass

    def close(self):
        pass


class StaticColorAssigner(NoColorAssigner):
    colors = {
        x[6:].lower(): getattr(curses, x)
        for x in dir(curses) if x.startswith('COLOR_')
        }

    def __call__(self, fgcolor, bgcolor):
        fg = self.getcolor(fgcolor)
        bg = self.getcolor(bgcolor)

        self.log.debug('fg, bg = %d:%s, %d:%s', fg, fgcolor, bg, bgcolor)

        if (fg, bg) in self.pairs:
            pair = self.pairs[fg, bg]
            self.log.debug('returning cached pair %d', pair)
            return pair

        if self.next >= curses.COLOR_PAIRS:
            return 0

        pair = self.next
        self.next += 1
        self.log.debug('initializing %d as %d, %d', pair, fg, bg)
        curses.init_pair(pair, fg, bg)
        colorpair = curses.color_pair(pair)
        self.pairs[fg, bg] = colorpair
        return colorpair

    def getcolor(self, name):
        return self.colors.get(name.lower(), -1)

    def reset(self):
        self.pairs = {(-1, -1): 0}
        self.next = 1

class DynamicColorAssigner(StaticColorAssigner):
    rgbtxt = '/usr/share/X11/rgb.txt'
    hex_12bit = re.compile(r'^#' + 3*r'([0-9a-fA-F])' + '$')
    hex_24bit = re.compile(r'^#' + 3*'([0-9a-fA-F][0-9a-fA-F])' + '$')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.rgb = {}

        with open(self.rgbtxt) as fp:
            for line in fp:
                if '!' in line:
                    line = line[:line.find('!')]
                line = line.strip()
                if not line:
                    continue
                try:
                    items = line.split(maxsplit=3)
                    r, g, b = [int(x) for x in items[:3]]
                    self.rgb[items[3].strip()] = (r, g, b)
                except:
                    self.log.exception('reading rgb.txt line')

        self.log.debug('read %d entries from %s', len(self.rgb), self.rgbtxt)

        self.saved = [curses.color_content(i) for i in range(curses.COLORS)]

        self.reset()

    def close(self):
        super().close()
        for (i, rgb) in enumerate(self.saved):
            curses.init_color(i, *rgb)

    def reset(self):
        super().reset()
        self.colors = {}
        self.nextcolor = 0

    def strtorgb(self, name):
        if name in self.rgb:
            return self.rgb[name]

        m = self.hex_12bit.match(name)
        if m:
            return tuple(int(2*x, 16) for x in m.groups())

        m = self.hex_24bit.match(name)
        if m:
            return tuple(int(x, 16) for x in m.groups())

        return None

    def getcolor(self, name):
        name = name.lower()
        if name in self.colors:
            self.log.debug('returning cached color %s', name)
            return self.colors[name]

        rgb = self.strtorgb(name)

        if rgb is None:
            self.log.debug('%s not in color db', repr(name))
            return -1

        if rgb in self.colors:
            self.log.debug('returning cached triplet %s', rgb)
            return self.colors[rgb]

        if self.nextcolor >= curses.COLORS:
            self.log.debug('no colors left')
            return -1

        color = self.nextcolor
        self.nextcolor += 1

        self.log.debug('initializing %d as %s', color, repr(rgb))
        curses.init_color(color, *[int(i * (1000 / 255)) for i in rgb])

        self.colors[rgb] = color
        self.colors[name] = color
        return color

