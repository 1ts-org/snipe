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
snipe.ttycolor
--------------
Utilities for managing color with curses.
'''


import curses
import re
import logging
import math

from . import util


class NoColorAssigner:
    loglevel = util.Level('log.color', 'ColorAssigner')

    def __init__(self):
        self.reset()
        self.log = logging.getLogger('ColorAssigner.%x' % (id(self),))

    def __call__(self, foreground, background):
        return 0

    def reset(self):
        pass

    def close(self):
        pass  # pragma: nocover


class SimpleColorAssigner(NoColorAssigner):
    colors = {
        x[6:].lower(): getattr(curses, x)
        for x in dir(curses) if x.startswith('COLOR_')
        }

    def __call__(self, fgcolor, bgcolor):
        fg = self.getcolor(fgcolor)
        bg = self.getcolor(bgcolor)

        if fgcolor or bgcolor:
            self.log.debug('fg, bg = %d:%s, %d:%s', fg, fgcolor, bg, bgcolor)

        if (fg, bg) in self.pairs:
            pair = self.pairs[fg, bg]
            if pair:
                self.log.debug('returning cached pair %d', pair)
            return pair
        else:
            self.log.debug('pair cache %s', repr(self.pairs))

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


class CleverColorAssigner(SimpleColorAssigner):
    rgbtxt = '/usr/share/X11/rgb.txt'
    hex_12bit = re.compile(r'^#' + 3*r'([0-9a-fA-F])' + '$')
    hex_24bit = re.compile(r'^#' + 3*'([0-9a-fA-F][0-9a-fA-F])' + '$')
    integer = re.compile(r'^[0-9]+$')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.rgb = {}

        try:
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
                    except:  # pragma: nocover
                        self.log.exception('reading rgb.txt line')
        except FileNotFoundError:  # pragma: nocover
            pass  # cue hyperdrive failure noise

        self.log.debug('read %d entries from %s', len(self.rgb), self.rgbtxt)

        self.colors = {}

    def strtorgb(self, name):
        if name in self.rgb:
            return self.rgb[name]

        m = self.hex_12bit.match(name)
        if m:
            return tuple(int(2*x, 16) for x in m.groups())

        m = self.hex_24bit.match(name)
        if m:
            return tuple(int(x, 16) for x in m.groups())

        m = self.integer.match(name)
        if m and 0 <= int(name) <= 255:
            m = self.hex_24bit.match(
                dict(colors_xterm_256color).get(int(name)))
            if m is None:  # pragma: nocover
                return None
            return tuple(int(x, 16) for x in m.groups())

        return None

    def getcolor(self, name):
        name = name.lower()
        if name in self.colors:
            self.log.debug('returning cached color %s', name)
            return self.colors[name]

        rgb = self.strtorgb(name)

        if rgb is None:
            if name:
                self.log.debug('%s not in color db', repr(name))
            return -1

        if rgb in self.colors:
            self.log.debug('returning cached triplet %s', rgb)
            return self.colors[rgb]

        color = self.findcolor(rgb)

        self.colors[rgb] = color
        self.colors[name] = color

        return color


class DynamicColorAssigner(CleverColorAssigner):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        # it's pretty clear that curses is usually on crack about what
        # it's returning, but OH WELL
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

    def findcolor(self, rgb):
        if self.nextcolor >= curses.COLORS:
            self.log.debug('no colors left')
            return -1

        color = self.nextcolor
        self.nextcolor += 1

        self.log.debug('initializing %d as %s', color, repr(rgb))
        curses.init_color(color, *[int(i * (1000 / 255)) for i in rgb])

        return color


class StaticColorAssigner(CleverColorAssigner):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        if curses.COLORS >= 256:
            initmap = colors_xterm_256color
        elif curses.COLORS >= 88:
            initmap = colors_xterm_88color
        elif curses.COLORS > 8:
            initmap = colors_xterm
        else:
            initmap = colors_simple

        self.map = [(n, self.strtorgb(color)) for (n, color) in initmap]

    def findcolor(self, rgb):
        r1, g1, b1 = rgb
        self.log.debug("%s %s", repr(rgb), repr(self.map))
        xmap = [
            (n, math.sqrt((r2 - r1)**2 + (g2 - g1)**2 + (b2 - b1)**2))
            for (n, (r2, g2, b2)) in self.map
            if n < curses.COLORS]
        return min(
            xmap,
            key=lambda x: x[1])[0]


def get_assigner():
    curses.start_color()
    if curses.has_colors():
        curses.use_default_colors()
        if curses.can_change_color():
            return DynamicColorAssigner()
        else:
            return StaticColorAssigner()
    return NoColorAssigner()


colors_simple = [
    (curses.COLOR_BLACK,   '#000'),
    (curses.COLOR_RED,     '#f00'),
    (curses.COLOR_GREEN,   '#0f0'),
    (curses.COLOR_YELLOW,  '#ff0'),
    (curses.COLOR_BLUE,    '#00f'),
    (curses.COLOR_MAGENTA, '#f0f'),
    (curses.COLOR_CYAN,    '#0ff'),
    (curses.COLOR_WHITE,   '#fff'),
    ]

#  The following was extracted from the xterm v306 source tree as
# distributed by Debian.
#
#  The first set of values were gleaned from a charproc.c (lines
# 613-628), with copyright notices from Thomas E. Dickey
# (1999-2013,2014), the Open Group (1988), and Digital Equipment
# Corporation (1988); by their nature, I don't think they carry
# copyright with them, but I'm going to be sure to cite my sources
# anyway.

colors_xterm = [
    (0, "black"),
    (1, "red3"),
    (2, "green3"),
    (3, "yellow3"),
    (4, "blue2"),
    (5, "magenta3"),
    (6, "cyan3"),
    (7, "gray90"),
    (8, "gray50"),
    (9, "red"),
    (10, "green"),
    (11, "yellow"),
    (12, "#5c5cff"),
    (13, "magenta"),
    (14, "cyan"),
    (15, "white"),
]

# These next two chunks were derived somewhat mechanically from
# 88colres.h and 256colres.h; these appear to have generated, and
# there are no copyright notices on the files.

colors_xterm_88color = colors_xterm + [
    (16, "#000000"),
    (17, "#00008b"),
    (18, "#0000cd"),
    (19, "#0000ff"),
    (20, "#008b00"),
    (21, "#008b8b"),
    (22, "#008bcd"),
    (23, "#008bff"),
    (24, "#00cd00"),
    (25, "#00cd8b"),
    (26, "#00cdcd"),
    (27, "#00cdff"),
    (28, "#00ff00"),
    (29, "#00ff8b"),
    (30, "#00ffcd"),
    (31, "#00ffff"),
    (32, "#8b0000"),
    (33, "#8b008b"),
    (34, "#8b00cd"),
    (35, "#8b00ff"),
    (36, "#8b8b00"),
    (37, "#8b8b8b"),
    (38, "#8b8bcd"),
    (39, "#8b8bff"),
    (40, "#8bcd00"),
    (41, "#8bcd8b"),
    (42, "#8bcdcd"),
    (43, "#8bcdff"),
    (44, "#8bff00"),
    (45, "#8bff8b"),
    (46, "#8bffcd"),
    (47, "#8bffff"),
    (48, "#cd0000"),
    (49, "#cd008b"),
    (50, "#cd00cd"),
    (51, "#cd00ff"),
    (52, "#cd8b00"),
    (53, "#cd8b8b"),
    (54, "#cd8bcd"),
    (55, "#cd8bff"),
    (56, "#cdcd00"),
    (57, "#cdcd8b"),
    (58, "#cdcdcd"),
    (59, "#cdcdff"),
    (60, "#cdff00"),
    (61, "#cdff8b"),
    (62, "#cdffcd"),
    (63, "#cdffff"),
    (64, "#ff0000"),
    (65, "#ff008b"),
    (66, "#ff00cd"),
    (67, "#ff00ff"),
    (68, "#ff8b00"),
    (69, "#ff8b8b"),
    (70, "#ff8bcd"),
    (71, "#ff8bff"),
    (72, "#ffcd00"),
    (73, "#ffcd8b"),
    (74, "#ffcdcd"),
    (75, "#ffcdff"),
    (76, "#ffff00"),
    (77, "#ffff8b"),
    (78, "#ffffcd"),
    (79, "#ffffff"),
    (80, "#2e2e2e"),
    (81, "#5c5c5c"),
    (82, "#737373"),
    (83, "#8b8b8b"),
    (84, "#a2a2a2"),
    (85, "#b9b9b9"),
    (86, "#d0d0d0"),
    (87, "#e7e7e7"),
]

colors_xterm_256color = colors_xterm + [
    (16, "#000000"),
    (17, "#00005f"),
    (18, "#000087"),
    (19, "#0000af"),
    (20, "#0000d7"),
    (21, "#0000ff"),
    (22, "#005f00"),
    (23, "#005f5f"),
    (24, "#005f87"),
    (25, "#005faf"),
    (26, "#005fd7"),
    (27, "#005fff"),
    (28, "#008700"),
    (29, "#00875f"),
    (30, "#008787"),
    (31, "#0087af"),
    (32, "#0087d7"),
    (33, "#0087ff"),
    (34, "#00af00"),
    (35, "#00af5f"),
    (36, "#00af87"),
    (37, "#00afaf"),
    (38, "#00afd7"),
    (39, "#00afff"),
    (40, "#00d700"),
    (41, "#00d75f"),
    (42, "#00d787"),
    (43, "#00d7af"),
    (44, "#00d7d7"),
    (45, "#00d7ff"),
    (46, "#00ff00"),
    (47, "#00ff5f"),
    (48, "#00ff87"),
    (49, "#00ffaf"),
    (50, "#00ffd7"),
    (51, "#00ffff"),
    (52, "#5f0000"),
    (53, "#5f005f"),
    (54, "#5f0087"),
    (55, "#5f00af"),
    (56, "#5f00d7"),
    (57, "#5f00ff"),
    (58, "#5f5f00"),
    (59, "#5f5f5f"),
    (60, "#5f5f87"),
    (61, "#5f5faf"),
    (62, "#5f5fd7"),
    (63, "#5f5fff"),
    (64, "#5f8700"),
    (65, "#5f875f"),
    (66, "#5f8787"),
    (67, "#5f87af"),
    (68, "#5f87d7"),
    (69, "#5f87ff"),
    (70, "#5faf00"),
    (71, "#5faf5f"),
    (72, "#5faf87"),
    (73, "#5fafaf"),
    (74, "#5fafd7"),
    (75, "#5fafff"),
    (76, "#5fd700"),
    (77, "#5fd75f"),
    (78, "#5fd787"),
    (79, "#5fd7af"),
    (80, "#5fd7d7"),
    (81, "#5fd7ff"),
    (82, "#5fff00"),
    (83, "#5fff5f"),
    (84, "#5fff87"),
    (85, "#5fffaf"),
    (86, "#5fffd7"),
    (87, "#5fffff"),
    (88, "#870000"),
    (89, "#87005f"),
    (90, "#870087"),
    (91, "#8700af"),
    (92, "#8700d7"),
    (93, "#8700ff"),
    (94, "#875f00"),
    (95, "#875f5f"),
    (96, "#875f87"),
    (97, "#875faf"),
    (98, "#875fd7"),
    (99, "#875fff"),
    (100, "#878700"),
    (101, "#87875f"),
    (102, "#878787"),
    (103, "#8787af"),
    (104, "#8787d7"),
    (105, "#8787ff"),
    (106, "#87af00"),
    (107, "#87af5f"),
    (108, "#87af87"),
    (109, "#87afaf"),
    (110, "#87afd7"),
    (111, "#87afff"),
    (112, "#87d700"),
    (113, "#87d75f"),
    (114, "#87d787"),
    (115, "#87d7af"),
    (116, "#87d7d7"),
    (117, "#87d7ff"),
    (118, "#87ff00"),
    (119, "#87ff5f"),
    (120, "#87ff87"),
    (121, "#87ffaf"),
    (122, "#87ffd7"),
    (123, "#87ffff"),
    (124, "#af0000"),
    (125, "#af005f"),
    (126, "#af0087"),
    (127, "#af00af"),
    (128, "#af00d7"),
    (129, "#af00ff"),
    (130, "#af5f00"),
    (131, "#af5f5f"),
    (132, "#af5f87"),
    (133, "#af5faf"),
    (134, "#af5fd7"),
    (135, "#af5fff"),
    (136, "#af8700"),
    (137, "#af875f"),
    (138, "#af8787"),
    (139, "#af87af"),
    (140, "#af87d7"),
    (141, "#af87ff"),
    (142, "#afaf00"),
    (143, "#afaf5f"),
    (144, "#afaf87"),
    (145, "#afafaf"),
    (146, "#afafd7"),
    (147, "#afafff"),
    (148, "#afd700"),
    (149, "#afd75f"),
    (150, "#afd787"),
    (151, "#afd7af"),
    (152, "#afd7d7"),
    (153, "#afd7ff"),
    (154, "#afff00"),
    (155, "#afff5f"),
    (156, "#afff87"),
    (157, "#afffaf"),
    (158, "#afffd7"),
    (159, "#afffff"),
    (160, "#d70000"),
    (161, "#d7005f"),
    (162, "#d70087"),
    (163, "#d700af"),
    (164, "#d700d7"),
    (165, "#d700ff"),
    (166, "#d75f00"),
    (167, "#d75f5f"),
    (168, "#d75f87"),
    (169, "#d75faf"),
    (170, "#d75fd7"),
    (171, "#d75fff"),
    (172, "#d78700"),
    (173, "#d7875f"),
    (174, "#d78787"),
    (175, "#d787af"),
    (176, "#d787d7"),
    (177, "#d787ff"),
    (178, "#d7af00"),
    (179, "#d7af5f"),
    (180, "#d7af87"),
    (181, "#d7afaf"),
    (182, "#d7afd7"),
    (183, "#d7afff"),
    (184, "#d7d700"),
    (185, "#d7d75f"),
    (186, "#d7d787"),
    (187, "#d7d7af"),
    (188, "#d7d7d7"),
    (189, "#d7d7ff"),
    (190, "#d7ff00"),
    (191, "#d7ff5f"),
    (192, "#d7ff87"),
    (193, "#d7ffaf"),
    (194, "#d7ffd7"),
    (195, "#d7ffff"),
    (196, "#ff0000"),
    (197, "#ff005f"),
    (198, "#ff0087"),
    (199, "#ff00af"),
    (200, "#ff00d7"),
    (201, "#ff00ff"),
    (202, "#ff5f00"),
    (203, "#ff5f5f"),
    (204, "#ff5f87"),
    (205, "#ff5faf"),
    (206, "#ff5fd7"),
    (207, "#ff5fff"),
    (208, "#ff8700"),
    (209, "#ff875f"),
    (210, "#ff8787"),
    (211, "#ff87af"),
    (212, "#ff87d7"),
    (213, "#ff87ff"),
    (214, "#ffaf00"),
    (215, "#ffaf5f"),
    (216, "#ffaf87"),
    (217, "#ffafaf"),
    (218, "#ffafd7"),
    (219, "#ffafff"),
    (220, "#ffd700"),
    (221, "#ffd75f"),
    (222, "#ffd787"),
    (223, "#ffd7af"),
    (224, "#ffd7d7"),
    (225, "#ffd7ff"),
    (226, "#ffff00"),
    (227, "#ffff5f"),
    (228, "#ffff87"),
    (229, "#ffffaf"),
    (230, "#ffffd7"),
    (231, "#ffffff"),
    (232, "#080808"),
    (233, "#121212"),
    (234, "#1c1c1c"),
    (235, "#262626"),
    (236, "#303030"),
    (237, "#3a3a3a"),
    (238, "#444444"),
    (239, "#4e4e4e"),
    (240, "#585858"),
    (241, "#626262"),
    (242, "#6c6c6c"),
    (243, "#767676"),
    (244, "#808080"),
    (245, "#8a8a8a"),
    (246, "#949494"),
    (247, "#9e9e9e"),
    (248, "#a8a8a8"),
    (249, "#b2b2b2"),
    (250, "#bcbcbc"),
    (251, "#c6c6c6"),
    (252, "#d0d0d0"),
    (253, "#dadada"),
    (254, "#e4e4e4"),
    (255, "#eeeeee"),
    ]
