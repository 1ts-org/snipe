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


class Help(editor.Viewer):
    START = (
        '?: top  b: key bindings  k: describe key  L: License\n' +
        'q: back to what you were doing')
    BANNER = '[pageup/pagedown to scroll, q to quit]\n'

    def __init__(self, *args, caller=None, **kw):
        self.caller = caller
        kw.setdefault('name', '*help*')
        super().__init__(*args, **kw)
        self.start()

    def display(self, text):
        # should adjust window size or whatnot
        self.cursor.point = 0
        self.replace(len(self.buf), text)

    @keymap.bind('?', '[escape] ?') # really should give increasingly basic help
    def start(self):
        """Go to the help splash screen."""

        self.display(self.START)

    @keymap.bind('L')
    def license(self):
        """Display the license."""

        self.display(self.BANNER + util.LICENSE)

    @keymap.bind('q', 'Q', '[Escape] [Escape]')
    def exit_help(self):
        """Exit help."""

        self.fe.popdown_window()

    @keymap.bind('b')
    def describe_bindings(self):
        """Describe the bindings of the window we entered help from."""

        self.display(self.BANNER + str(self.caller.keymap))

    @keymap.bind('k')
    def describe_key(self):
        """Read a keysequence and display its documentation."""

        keystrokes, func = yield from self.read_keyseq(
            'Describe key? ', self.caller.keymap)
        keyseq = ' '.join(self.keymap.unkey(k) for k in keystrokes)
        if func is None:
            out = '"%s" is not bound to anything' % (keyseq,)
        else:
            out = '"%s" is bound to %s' % (
                keyseq, getattr(func, '__name__', '???'))
            if hasattr(func, '__doc__'):
                out += '\n\n' + inspect.getdoc(func)
        self.display(self.BANNER + out)



@keymap.bind('?', '[escape] ?')
def help(window: interactive.window):
    """Help."""

    window.fe.popup_window(Help(window.fe, caller=window), height=10)
    window.fe.redisplay()


@keymap.bind('!')
def browsehelp(window: interactive.window):
    window.fe.split_window(HelpBrowser(window.fe), True)


class HelpBrowser(editor.Viewer):
    """Commit assorted sins against docutils in order to present a help browser
    """
    pages = {}
    toc = []
    toclines = []
    base_mode = None

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        if not self.pages:
            self.load_pages()

        self.load(self.toc[0])

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
                docutils.io.StringInput, text, None, docutils.io.NullOutput, None, None,
                None, 'standalone', None, 'restructuredtext', None, 'null', None, None,
                {}, None, None)
            allchunks = self.render(pub.writer.document)

            refs = {}
            off = 0
            chunks = []
            links = []

            for tags, text in allchunks:
                if 'section' in tags:
                    refs[text] = off
                elif 'link' in tags:
                    (lengthtag,) = [t for t in tags if t.startswith('length:')]
                    length = int(lengthtag[len('length:'):])
                    links.append((off, length, text))
                else:
                    off += len(text)
                    chunks.append((tags, text))

            flat = ''.join(text for (tags, text) in chunks)
            self.pages[label] = (chunks, flat, refs, links)
            self.toclines[:0] = self.gettoclines(pub.writer.document, label)

    @staticmethod
    def render(node):
        #XXX this function (render) is terrible and more importantly
        # its output is terrible

        def addtag(chunk, tag):
            result = []
            for tags, text in chunk:
                if tag not in tags:
                    tags += (tag,)
                result.append((tags, text))
            return result

        if isinstance(node, docutils.nodes.Text):
            return [((), node.astext())]
        elif isinstance(node, docutils.nodes.comment):
            return []

        chunks = []

        if isinstance(node, docutils.nodes.title):
            chunks += [(('section',), ''.join(node.astext().split()))]

        for x in node.children:
            chunks += HelpBrowser.render(x)

        if chunks and isinstance(node, docutils.nodes.reference):
            chunks = addtag(chunks, 'fg:#6666ff')
            chunks = addtag(chunks, 'underline')
            l = sum(len(txt) for (tags, txt) in chunks if 'section' not in tags)
            chunks = [(('link', 'length:%d' % (l,)), node['refuri'])] + chunks

        if chunks and isinstance(node, docutils.nodes.Titular):
            #chunks = addtag(chunks, 'fill')
            chunks = addtag(chunks, 'bold')
            chunks += [((), '\n\n')]

        if node.__class__.__name__ in ('emphasis', 'literal_block'):
            chunks = addtag(chunks, 'bold')

        if isinstance(node, docutils.nodes.literal_block):
            chunks += [((), '\n\n')]

        if isinstance(node, docutils.nodes.paragraph):
            #chunks = addtag(chunks, 'fill')
            chunks += [((), '\n\n')]

        if isinstance(node, docutils.nodes.term):
            chunks += [((), '\n')]

        #result.append(((node.__class__.__name__,), ''))

        result, oldtags = [], None
        for tags, text in chunks + [((), '')]:
            tags = tuple(sorted(tags))
            if tags != oldtags:
                if (tags, text) != ((), ''):
                    result.append((tags, text))
            else:
                result[-1] = (tags, result[-1][1] + text)

        return result

    @staticmethod
    def gettoclines(doc, label):
        def tocify(node):
            if isinstance(node, docutils.nodes.title):
                return node.astext()

            return list(filter(None, (tocify(x) for x in node.children)))

        def lines(toc, offset=0):
            out = ['%s* `%s <%s#%s>`_' % (' ' * offset, toc[0], label, toc[0]), '']
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
        self.chunks, flat, self.refs, self.links = self.pages[name]
        self.log.debug('refs: %s', repr(self.refs))
        self.log.debug('links: %s', repr(self.links))
        self.replace(len(self.buf), flat)
        self.index = []
        off = 0
        for tags, text in self.chunks:
            self.index.append(off)
            off += len(text)
        self.beginning_of_buffer()
        self.log.debug('looking for %s in %s', repr(anchor), repr(self.refs))
        if anchor and anchor in self.refs:
            self.cursor.point = self.refs[anchor]
        self.page = name

    def view(self, origin, direction='forward'):
        # Bunch of complexity to place the cursor properly
        i = bisect.bisect(self.index, int(self.cursor)) - 1
        left = self.chunks[:i]
        right = self.chunks[i:]
        if not right:
            right = [((), '')]
        offset = int(self.cursor) - self.index[i]
        right = [
            (right[0][0], right[0][1][:offset]),
            ((right[0][0] + ('cursor', 'visible')), right[0][1][offset:]),
            ] + right[1:]

        yield self.buf.mark(0), left + right

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
            if not getattr(prop, '__qualname__', '').startswith(obj.__name__ + '.'):
                continue
            text += '\n' + ' '.join('``' + s + '``' for s in prop.snipe_seqs) + ' *' + attr + '*\n'
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
                lines.append('*``%s``*' % (attr.key,))
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
