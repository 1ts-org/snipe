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

import inspect
import sys
import bisect
import pprint
import logging

import docutils.core
import docutils.io
import docutils.nodes
import docutils.parsers.rst
import docutils.parsers.rst.directives

from . import window
from . import keymap
from . import interactive
from . import util
from . import editor


@keymap.bind('?')
def halp(window: interactive.window):
    if util.Configurable.get(window, 'cheatsheet'):
        browsehelp(window)
    else:
        util.Configurable.set(window, 'cheatsheet', True)
        window.active_keymap = keymap


@keymap.bind('L')
def license(window: interactive.window):
    """Display the license."""

    window.show(util.LICENSE, "*Help*")


@keymap.bind('b')
def describe_bindings(window: interactive.window, keymap: interactive.keymap):
    """Describe the bindings of the window we entered help from."""

    window.show(str(keymap), '*Help*')


@keymap.bind('k')
def describe_key(window: interactive.window, keymap: interactive.keymap):
    """Read a keysequence and display its documentation."""

    keystrokes, func = yield from window.read_keyseq(
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
    pages = {}
    toc = []
    toclines = []
    base_mode = None

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
            text, module = inpages[label]
            flags, text = text.split('\n', 1)
            HelpBrowser.base_module = module
            _, pub = docutils.core.publish_programmatically(
                docutils.io.StringInput, text, None, docutils.io.NullOutput,
                None, None, None, 'standalone', None, 'restructuredtext', None,
                'null', None, None, {}, None, None)

            renderer = Renderer()
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
                '%s* `%s <%s#%s>`_' % (' ' * offset, toc[0], label, toc[0]), '']
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
        self.chunks, flat, self.refs, self.links, self._title = self.pages[name]
        self.log.debug('refs: %s', repr(self.refs))
        self.log.debug('links: %s', repr(self.links))
        self.replace(len(self.buf), flat)

        self.beginning_of_buffer()
        self.log.debug('looking for %s in %s', repr(anchor), repr(self.refs))
        if anchor and anchor in self.refs:
            self.cursor.point = self.refs[anchor]
        self.page = name

    def view(self, origin, direction='forward'):
        l = len(self.chunks) -1
        i = min(bisect.bisect_left([x[0] for x in self.chunks], int(origin)), l)

        self.log.debug('helpbrowser.view: cursor=%d', int(self.cursor))
        while True:
            if i < 0 or i >= len(self.chunks):
                return
            self.log.debug(
                'helpbrowser.view: i=%d, off=%d', i, self.chunks[i][0])

            if self.chunks[i][0] <= int(self.cursor) and (
                    i == l or
                    int(self.cursor) < self.chunks[i + 1][0]):
                off = self.chunks[i][0]
                c = int(self.cursor)
                for (j, (tags, text)) in enumerate(self.chunks[i][1]):
                    self.log.debug('helpbrowser.view: j=%d', j)
                    if off <= c < off + len(text):
                        yield self.buf.mark(self.chunks[i][0]), (
                            self.chunks[i][1][:j] +
                            ([(tags, text[:c - off])] if c > off else []) +
                            [(tags + ('cursor', 'visible'), text[c - off:])] +
                            self.chunks[i][1][j + 1:])
                        break
                    off += len(text)
            else:
                yield self.buf.mark(self.chunks[i][0]), self.chunks[i][1]

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
    def load_page(self):
        page = yield from self.read_oneof('Page: ', self.toc)
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
        i = min(bisect.bisect_left(offs, int(self.cursor)), len(offs) - 1)
        off, length, link = self.links[i]
        if off <= self.cursor.point < (off + length):
            self.load(link)


class Renderer:
    def __init__(self):
        # output will be a list of (offset, [(tags, text), (tags, text)]) items
        self.output = []
        self.tagstack = []
        self.offset = 0
        self.state_space = True
        self.targets = []
        self.links = []

    def add(self, words):
        self.state_space = False

        if not self.notatendofline():
            self.output.append((self.offset, []))

        line = self.output[-1][1]

        rest = ''
        if '\n' in words:
            i = words.index('\n') + 1
            words, rest = words[:i], words[i:]
        if line and line[-1][0] == self.tags():
            line[-1] = (line[-1][0], line[-1][1] + words)
        else:
            line.append((self.tags(), words))
        self.offset += len(words)

        if rest:
            self.add(rest)

    def notatendofline(self):
        # the frenzy of indexing checks the end of the last line so far
        return self.output and self.output[-1][1][-1][1][-1:] != '\n'

    def linebreak(self): # .br
        if self.notatendofline():
            self.add('\n')

    def space(self): # .sp
        if self.state_space:
            return
        self.linebreak()
        self.add('\n')
        self.state_space = True

    def tags(self):
        if not self.tagstack:
            return ()
        else:
            return tuple(self.tagstack[-1])

    def tagpush(self, *tags):
        self.tagstack.append(set(self.tags()) | set(tags))
        return 1

    def tagpop(self, count):
        del self.tagstack[-count:]

    def process(self, node):
        tagset = 0

        if isinstance(node, docutils.nodes.Text):
            self.add(node.astext())
            return
        elif isinstance(node, docutils.nodes.comment):
            return

        if isinstance(node, docutils.nodes.title):
            self.targets.append((self.offset, ''.join(node.astext().split())))

        if not isinstance(node, docutils.nodes.Inline):
            self.linebreak()

        if isinstance(node, docutils.nodes.Titular) or \
          isinstance(node, docutils.nodes.emphasis) or \
          isinstance(node, docutils.nodes.literal) or \
          isinstance(node, docutils.nodes.literal_block):
            tagset += self.tagpush('bold')

        if isinstance(node, docutils.nodes.reference):
            tagset += self.tagpush('fg:#6666ff', 'underline')
            link_start = self.offset

        for x in node.children:
            self.process(x)

        self.tagpop(tagset)

        if isinstance(node, docutils.nodes.reference):
            self.links.append(
                (link_start, self.offset - link_start, node['refuri']))

        if not isinstance(node, docutils.nodes.Inline):
            self.linebreak()
            if not isinstance(node, docutils.nodes.term):
                self.space()

    def flat(self):
        return ''.join(
            ''.join(text for (tags, text) in x[1])
            for x in self.output)


class Interrogator(docutils.parsers.rst.Directive):
    required_arguments = 1
    optional_arguments = 0
    has_content = True
    def run(self):
        import traceback
        try:
            name = self.arguments[0]
            if '.' not in name:
                obj = getattr(HelpBrowser.base_module, self.arguments[0])
            else:
                module, name = name.rsplit('.', 1)
                obj = getattr(sys.modules[module], name)

            self.state_machine.insert_input(self.process(obj), '<code>')
            return []
        except Exception as e:
            text = str(e)
            text = traceback.format_exc()
            return [docutils.nodes.Text(text + '\n')]

    def process(self, _):
        raise NotImplementedError


class InterrogateKeymap(Interrogator):
    def process(self, obj):
        text = ''
        for attr in dir(obj):
            prop = getattr(obj, attr)
            if not hasattr(prop, 'snipe_seqs'):
                continue
            if not (hasattr(prop, '__doc__') and prop.__doc__):
                continue
            if not getattr(prop, '__qualname__', '').startswith(
                    obj.__name__ + '.'):
                continue
            text += '\n%s *%s*\n' % (
                ' '.join('``%s``' % (s,) for s in prop.snipe_seqs), attr)
            #XXX if this faceplants on any of the relevant docstrings,
            #It's a bug in the docstring, really
            # Strip the leading indentation off of all but the first
            # line of the docstring
            l = prop.__doc__.splitlines()
            if len(l) > 1:
                s = l[1].lstrip(' ')
                off = len(l[1]) - len(s)
                l[1:] = [s[off:] for s in l[1:]]
            # reindent and append
            text += ''.join('  ' + s + '\n' for s in l)
            text += '\n'
        return text.splitlines()


docutils.parsers.rst.directives.register_directive(
    'interrogate_keymap', InterrogateKeymap)


class InterrogateConfig(Interrogator):
    def process(self, obj):
        lines = ['']
        for name in dir(obj):
            attr = getattr(obj, name)
            if isinstance(attr, util.Configurable):
                lines.append('``%s``' % (attr.key,))
                lines.append('  %s' % (attr.doc,))
                lines.append('')
        return lines


docutils.parsers.rst.directives.register_directive(
    'interrogate_config', InterrogateConfig)


class Toc(docutils.parsers.rst.Directive):
    required_arguments = 0
    optional_arguments = 0
    has_content = True
    def run(self):
        self.state_machine.insert_input(HelpBrowser.toclines, '<toc>')
        return []


docutils.parsers.rst.directives.register_directive(
    'toc', Toc)


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
    '*c*heatshet toggle',
    '*i* info browser',
    'all *b*indings',
    '*L*icense',
    '*k*ey description',
    ]
_keymap = keymap.Keymap()
_keymap.interrogate(sys.modules[__name__])
_keymap.set_cheatsheet(CHEATSHEET)
keymap = _keymap
