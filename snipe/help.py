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
snipe.help
----------
'''

import bisect
import inspect
import sys
import logging

from typing import (Dict, Tuple, List)

import docutils.core
import docutils.nodes

from . import chunks
from . import editor
from . import interactive
from . import keymap
from . import text
from . import util


@keymap.bind('?', 'Control-H')
def halp(window: interactive.window):
    if util.Configurable.get(window, 'cheatsheet') and \
      not isinstance(window, HelpBrowser):
        browsehelp(window)
    else:
        util.Configurable.set(window, 'cheatsheet', True)
        window.active_keymap = help_keymap


@keymap.bind('L')
def license(window: interactive.window):
    """Display the license."""

    window.show(util.LICENSE, "*Help*")


@keymap.bind('b')
def describe_bindings(window: interactive.window, keymap: interactive.keymap):
    """Describe the bindings of the window we entered help from."""

    window.show(str(keymap), '*Help*')


@keymap.bind('k')
async def describe_key(window: interactive.window, keymap: interactive.keymap):
    """Read a keysequence and display its documentation."""

    keystrokes, func = await window.read_keyseq(
        'Describe key? ', keymap)
    keyseq = ' '.join(keymap.unkey(k) for k in keystrokes)
    if func is None:
        out = '"%s" is not bound to anything' % (keyseq,)
    else:
        out = '"%s" is bound to %s' % (
            keyseq, getattr(func, '__name__', '???'))
        if hasattr(func, '__doc__'):
            out += '\n\n' + inspect.getdoc(func)
    window.show(out, '*Help*')


@keymap.bind('i')
def browsehelp(window: interactive.window):
    """Start the help browser"""
    window.fe.split_window(HelpBrowser(window.fe), True)


@keymap.bind('c')
def toggle_cheatsheet(window: interactive.window):
    util.Configurable.set(
        window, 'cheatsheet', not util.Configurable.get(window, 'cheatsheet'))
    window.context.conf_write()


class HelpBrowser(editor.PopViewer):
    """Commit assorted sins against docutils in order to present a help browser
    """

    pages: Dict[
        str,
        Tuple[
            Tuple[int, chunks.Chunk],
            str,
            Dict[str, int],
            List[Tuple[int, int, str]]]] = {}
    toc: List[str] = []
    toclines: List[str] = []
    base_module = None

    cheatsheet = [
        '*]* next "page"',
        '*[* prev "page"',
        '*<* 1st "page"',
        '*>* last "page"',
        '*Tab* next link',
        '*S-Tab* prev link',
        '*Enter* follow',
        '*m* go to "page"',
        '*q*uit viewer',
        '*Space* scroll',
        ]

    _title = 'Help Browser'

    loglevel = util.Level(
        'log.help', 'HelpBrowser', doc='loglevel for help browser')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))
        if not self.pages:
            self.load_pages()

        self.load(self.toc[0])

    def title(self):
        return 'Help: ' + self._title

    def load_pages(self):
        inpages = {}
        for name, module in sys.modules.items():
            split = name.split('.')
            if split[0] != 'snipe':
                continue
            if any(s for s in split if s.startswith('_')):
                continue

            for attr in dir(module):
                if attr.startswith('HELP'):
                    pagename = name
                    if len(attr) > 4:
                        pagename += attr[4:]
                    self.log.debug('found help: %s.%s', name, attr)
                    inpages[pagename] = (getattr(module, attr), module)

        self.toc[:] = sorted(inpages.keys(), key=lambda x: inpages[x])

        self.toclines[:] = []
        for label in reversed(self.toc):
            # go through them backwards so we can put the table of contents
            # on the first page
            text_, module = inpages[label]
            flags, text_ = text_.split('\n', 1)
            HelpBrowser.base_module = module
            _, pub = docutils.core.publish_programmatically(
                docutils.io.StringInput, text_, None, docutils.io.NullOutput,
                None, None, None, 'standalone', None, 'restructuredtext', None,
                'null', None, None, {}, None, None)

            renderer = text.RSTRenderer()
            renderer.process(pub.writer.document)

            self.pages[label] = (
                renderer.output,
                renderer.flat(),
                renderer.targets,
                renderer.links,
                pub.writer.document.get('title', 'Help Browser'),
                )
            self.toclines[:0] = self.gettoclines(pub.writer.document, label)

    @staticmethod
    def gettoclines(doc, label):
        def tocify(node):
            if isinstance(node, docutils.nodes.title):
                return node.astext()

            return list(filter(None, (tocify(x) for x in node.children)))

        def lines(toc, offset=0):
            out = [
                '| %s* `%s <%s#%s>`_' % (
                    ' ' * offset, toc[0], label, toc[0]), '']
            for entry in toc[1:]:
                out += lines(entry, offset+2)
            return out

        return lines(tocify(doc))

    def load(self, name):
        anchor = ''
        if '#' in name:
            name, anchor = name.split('#')
        self.cursor.point = 0
        self.log.debug('loading: %s', name)
        self.chunks, flat, self.refs, self.links, self._title = \
            self.pages[name]
        self.log.debug('refs: %s', repr(self.refs))
        self.log.debug('links: %s', repr(self.links))
        self.replace(len(self.buf), flat)

        self.beginning_of_buffer()
        self.log.debug('looking for %s in %s', repr(anchor), repr(self.refs))
        if anchor and anchor in self.refs:
            self.cursor.point = self.refs[anchor]
        self.page = name

    def view(self, origin, direction='forward'):
        l = len(self.chunks) - 1
        i = min(
            bisect.bisect_left([x.mark for x in self.chunks], int(origin)),
            l)

        self.log.debug('helpbrowser.view: cursor=%d', int(self.cursor))
        while True:
            if i < 0 or i >= len(self.chunks):
                return

            self.log.debug(
                'helpbrowser.view: i=%d, off=%d', i, self.chunks[i].mark)

            if self.chunks[i].mark <= int(self.cursor) and (
                    i == l or
                    int(self.cursor) < self.chunks[i + 1].mark):
                off, chunk = self.chunks[i]
                chunk = chunks.Chunk(chunk).at_add(
                    int(self.cursor) - off, {'cursor', 'visible'})
                yield chunks.View(self.buf.mark(off), chunk)
            else:
                yield chunks.View(
                    self.buf.mark(self.chunks[i].mark), self.chunks[i].chunk)

            if direction == 'forward':
                i += 1
            else:
                i -= 1

    @keymap.bind(']')
    def next_page(self):
        "Go to the next page in the documentation"
        self.skip_page(1)

    @keymap.bind('[')
    def prev_page(self):
        "Go to the previous page in the documentation"
        self.skip_page(-1)

    def skip_page(self, off):
        nth = (self.toc.index(self.page) + off) % len(self.toc)
        self.load(self.toc[nth])

    @keymap.bind('<')
    def first_page(self):
        "Go to the first page in the documentation"
        self.load(self.toc[0])

    @keymap.bind('>')
    def last_page(self):
        "Go to the last page in the documentation"
        self.load(self.toc[-1])

    @keymap.bind('m')
    async def load_page(self):
        page = await self.read_oneof('Page: ', self.toc)
        if page in self.toc:
            self.load(page)

    @keymap.bind('[tab]')
    def next_link(self):
        """Move to the next link"""
        offs = [off for (off, length, ref) in self.links]
        i = bisect.bisect(offs, int(self.cursor)) % len(offs)
        self.cursor.point = offs[i]

    @keymap.bind('[btab]')
    def prev_link(self):
        """Move to the previous link"""
        offs = [off for (off, length, ref) in self.links]
        i = (bisect.bisect_left(offs, int(self.cursor)) - 1) % len(offs)
        self.cursor.point = offs[i]

    @keymap.bind('[return]')
    def follow_link(self):
        offs = [off for (off, length, ref) in self.links]
        i = bisect.bisect(offs, int(self.cursor)) - 1
        if i < 0:
            return
        off, length, link = self.links[i]
        if off <= int(self.cursor) <= (off + length):
            self.load(link)


HELP = """05
=================
Help browser
=================

All the behaviors of `normal snipe windows <snipe.window>`_ plus:

.. interrogate_keymap:: HelpBrowser
"""

HELP_intro = """00
=========
snipe
=========

snipe is a text-oriented (currently curses-based) "instant" messaging
client intended for services with persistence.

It is known that there are bugs and missing features everywhere.  I
would mostly characterize this as "demoable" but not yet "usable".  As
always, if it breaks you get to keep both pieces.

.. toc::
"""

CHEATSHEET = [
    '*?* more help',
    '*c*heatsheet toggle',
    '*i* info browser',
    'all *b*indings',
    '*L*icense',
    '*k*ey description',
    ]
help_keymap = keymap.Keymap()
help_keymap.interrogate(sys.modules[__name__])
help_keymap.set_cheatsheet(CHEATSHEET)
