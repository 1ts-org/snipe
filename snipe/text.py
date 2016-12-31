# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe contributors
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
snipe.text4
--------------
Text processing stuff.
'''


import logging
import re
import sys
import xml.dom.minidom

import docutils.io
import docutils.parsers.rst
import docutils.parsers.rst.directives
import docutils.nodes
import markdown
import markdown.extensions
import markdown.extensions.codehilite
import markdown.extensions.fenced_code

from . import util


WHITESPACE = re.compile(r'(\s+)')


class RSTRenderer:
    loglevel = util.Level(
        'log.help.renderer', 'Renderer',
        doc = 'logevel for Help text renderer')

    def __init__(self):
        # output will be a list of (offset, [(tags, text), (tags, text)]) items
        self.output = []
        self.tagstack = []
        self.offset = 0
        self.state_space = True
        self.targets = {}
        self.links = []
        self.section_level = 0
        self.fill = True
        self.WRAPWIDTH = 72
        self.col = 0
        self.indent = ''

        self.log = logging.getLogger('%s.%x' % (
            self.__class__.__name__,
            id(self),
            ))

    @staticmethod
    @util.listify
    def split_count(s):
        off = 0
        for word in WHITESPACE.split(s):
            yield off
            off += len(word)

    def add(self, words):
        self.log.debug('add: %s, fill=%s', repr(words), self.fill)
        self.state_space = False

        if not self.notatendofline():
            if self.output:
                lastchunk = self.output[-1][1]
                tag, text = lastchunk[-1]
                tags = set(tag)
                if tags & self.tags(span=True) and text[-1:] == '\n':
                    lastchunk[-1:] = [
                        (tags, text[:-1]),
                        (tuple(tags - self.tags(span=True)), '\n')]
            self.output.append((self.offset, [(self.tags(), self.indent)]))
        line = self.output[-1][1]

        rest = ''

        words = words.replace('\r', '')
        if self.col == 0:
            words = self.indent + words
        if self.fill:
            words = words.strip('\n').replace('\n', ' ')
            self.log.debug('add cleaned: %s', repr(words))
        else:
            newline = words.find('\n')
            if newline >= 0:
                i = newline + 1
                words, rest = words[:i], words[i:]

        width = len(words)

        if self.fill and (self.col + width) > self.WRAPWIDTH:
            offs = self.split_count(words)
            for ind in range(len(offs) - 2, 0, -2):
                self.log.debug('add ind: %d', ind)
                if self.col + offs[ind] < self.WRAPWIDTH:
                    self.log.debug('add splits: %d', len(offs))
                    self.log.debug('add wrap index: %d: %d', ind, offs[ind])
                    self.log.debug('add words 1: %s', repr(words))
                    rest = words[offs[ind + 1]:] + rest
                    words = words[:offs[ind]] + '\n'
                    self.log.debug('add words 2: %s', repr(words))
                    self.log.debug('add rest  : %s', repr(rest))
                    break
            else:
                # no breakpoint
                if self.col > len(self.indent):
                    # punt this to the next line
                    rest = words + rest
                    words = '\n'
                else:
                    if len(offs) > 1:
                        rest = words[offs[2]:]
                        words = words[:offs[1]]

        self.log.debug('words: %s', repr(words))
        if words[-1:] == '\n':
            self.col = len(self.indent)
        else:
            self.col += len(words)

        if line and line[-1][0] == self.tags():
            line[-1] = (line[-1][0], line[-1][1] + words)
        else:
            line.append((self.tags(), words))
        self.offset += len(words)

        if rest:
            self.add(rest)

    def notatendofline(self):
        if self.output:
            self.log.debug('eol? %s', self.output[-1])
        # the frenzy of indexing checks the end of the last line so far
        return self.output and self.output[-1][1][-1][1][-1:] != '\n'

    def notatbeginingofline(self):
        if not self.output:
            return False
        return bool(len(self.output[-1][1]) > 1 or self.output[-1][1][0][1])

    def linebreak(self): # .br
        self.log.debug('.linebreak')
        if self.notatendofline() and self.notatbeginingofline():
            fill, self.fill = self.fill, False
            self.add('\n')
            self.fill = fill

    def space(self): # .sp
        self.log.debug('.space')
        if self.state_space:
            return
        self.linebreak()
        fill, self.fill = self.fill, False
        self.add('\n')
        self.fill = fill
        self.state_space = True

    def tags(self, span=None):
        if not self.tagstack:
            if span is None:
                return ()
            else:
                return set()
        else:
            if span is None:
                return tuple(self.tagstack[-1][0] | self.tagstack[-1][1])
            elif bool(span):
                return self.tagstack[-1][1]
            else:
                return self.tagstack[-1][0]

    def tagpush(self, *tags, span=False):
        if span:
            self.tagstack.append(
                (self.tags(False), self.tags(True) | set(tags)))
        else:
            self.tagstack.append(
                (self.tags(False) | set(tags), self.tags(True)))
        return 1

    def tagpop(self, count):
        del self.tagstack[-count:]

    def process(self, node):
        tagset = 0

        if isinstance(node, docutils.nodes.Text):
            self.log.debug('text: %s', repr(node.astext()))
            self.add(node.astext())
            return
        elif isinstance(node, docutils.nodes.comment):
            self.log.debug('comment: %s', repr(node.astext()))
            return

        self.log.debug('entering: %s', repr(node))

        if isinstance(node, docutils.nodes.title):
            self.targets[''.join(node.astext().split())] = self.offset

        if not isinstance(node, docutils.nodes.Inline) and \
          not isinstance(node, docutils.nodes.line) and \
          not isinstance(node, docutils.nodes.line_block):
            self.linebreak()

        if isinstance(node, docutils.nodes.section):
            self.section_level += 1

        if isinstance(node, docutils.nodes.title):
            self.add('*' * self.section_level)
            if self.section_level:
                self.add(' ')

        if isinstance(node, docutils.nodes.line):
            self.add(' '*node.indent)

        if isinstance(node, docutils.nodes.Titular) or \
          isinstance(node, docutils.nodes.emphasis) or \
          isinstance(node, docutils.nodes.literal) or \
          isinstance(node, docutils.nodes.literal_block):
            tagset += self.tagpush('bold')

        if isinstance(node, docutils.nodes.literal_block):
            self.linebreak()

        if isinstance(node, docutils.nodes.literal_block) or \
          isinstance(node, docutils.nodes.line):
            fill, self.fill = self.fill, False

        if isinstance(node, docutils.nodes.reference):
            tagset += self.tagpush('fg:#6666ff', 'underline')
            link_start = self.offset

        for x in node.children:
            self.process(x)

        if isinstance(node, docutils.nodes.literal_block) or \
          isinstance(node, docutils.nodes.line):
            self.fill = fill

        self.tagpop(tagset)

        if isinstance(node, docutils.nodes.reference):
            self.links.append(
                (link_start, self.offset - link_start, node['refuri']))

        if isinstance(node, docutils.nodes.section):
            self.section_level -= 1

        if not isinstance(node, docutils.nodes.Inline) and \
          not isinstance(node, docutils.nodes.line_block):
            self.linebreak()
            if not isinstance(node, docutils.nodes.term) and \
              not isinstance(node, docutils.nodes.line):
                self.space()

        self.log.debug('leaving: %s', repr(node))


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
        from . import help
        try:
            name = self.arguments[0]
            if '.' not in name:
                obj = getattr(help.HelpBrowser.base_module, self.arguments[0])
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
        from . import help
        self.state_machine.insert_input(help.HelpBrowser.toclines, '<toc>')
        return []


docutils.parsers.rst.directives.register_directive(
    'toc', Toc)


IGNORED_TAGS = {'html', 'body'}
INDENT_TAGS = {'blockquote'}
BLOCK_TAGS = {
    'p', 'li', 'ul', 'pre', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    } | INDENT_TAGS
ANCHOR_TAGS = {'a'}
BOLD_TAGS = {'strong', 'h1', 'em'}
GREY_TAGS = {'code'}
LITERAL_TAGS = {'pre'}
HANDLED_TAGS = (
    IGNORED_TAGS | BLOCK_TAGS | BOLD_TAGS | LITERAL_TAGS | GREY_TAGS |
    ANCHOR_TAGS
    )

class XHTMLRenderer(RSTRenderer):
    def process(self, node):
        tagdepth = 0
        if node.nodeType == node.ELEMENT_NODE:
            tag = node.tagName
            if tag not in HANDLED_TAGS:
                td = self.tagpush('bold')
                self.add('<' + node.tagName + '>')
                self.tagpop(td)
            if tag in BLOCK_TAGS:
                self.log.debug('block tag open linebreak')
                self.linebreak()
            if tag in LITERAL_TAGS:
                self.fill = False
            if tag in BOLD_TAGS:
                tagdepth += self.tagpush('bold')
            if tag in GREY_TAGS:  # PRE > GREY
                tagdepth += self.tagpush('bg:#3d3d3d', span=self.fill)
            if tag in ANCHOR_TAGS:
                tagdepth += self.tagpush('fg:#6666ff', 'underline', span=True)
            if tag in INDENT_TAGS:
                self.indent += ' '

        for child in node.childNodes:
            if child.nodeType == node.TEXT_NODE:
                self.add(child.data)
            else:
                self.process(child)

        if node.nodeType == node.ELEMENT_NODE:
            if tag not in HANDLED_TAGS:
                td = self.tagpush('bold')
                self.add('</' + node.tagName + '>')
                self.tagpop(td)
            if tag in BLOCK_TAGS:
                self.log.debug('block tag close linebreak')
                self.linebreak()
            if tag in LITERAL_TAGS:
                self.fill = True

            if tag in INDENT_TAGS:
                self.indent = self.indent[:-1]

        self.tagpop(tagdepth)


def xhtml_to_chunk(xhtml):
    dom = xml.dom.minidom.parseString('<html><body>' + xhtml + '</body></html>')
    renderer = XHTMLRenderer()
    renderer.process(dom.documentElement)
    out = []
    for mark, chunk in renderer.output:
        out.extend(chunk)
    return out


def markdown_to_xhtml(s):
    return markdown.markdown(
        s, safe_mode='escape', extensions=[
            SnipeFencedCodeExtension(),
            'markdown.extensions.nl2br',
            ## 'markdown.extensions.tables',
            ])


def markdown_to_chunk(s):
    return xhtml_to_chunk(markdown_to_xhtml(s))


class QuoteHack:
    CODE_WRAP = '<pre><code%s>%s</code></pre>'
    def __init__(self):
        self.reset()

    def reset(self):
        self.langtag = None
        self.content = None

    def __mod__(self, other):
        self.langtag, self.content = other
        return self.CODE_WRAP % (self.langtag, self.content)


class SnipeFBP(markdown.extensions.fenced_code.FencedBlockPreprocessor):
    CODE_WRAP = QuoteHack()

    def run(self, lines):
        self.CODE_WRAP.reset()
        lines = super().run(lines)
        logging.debug('%s', repr(self.CODE_WRAP.langtag))
        if self.CODE_WRAP.langtag == ' class="quote"':
            lines = []
            content = self.CODE_WRAP.content
            for para in content.split('\n\n'):
                for line in para.split('\n'):
                    if line:
                        lines.append('> ' + line)
                lines.append('\n')
        return lines


class SnipeFencedCodeExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.registerExtension(self)
        md.preprocessors.add(
            'fenced_code_block',
            SnipeFBP(md),
            ">normalize_whitespace")
