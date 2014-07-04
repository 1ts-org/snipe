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

import array
import weakref
import contextlib
import logging
import functools
import unicodedata

from . import context


CHUNKSIZE = 4096


@functools.total_ordering
class Mark:
    def __init__(self, buf, point):
        self.buf = buf
        self.buf.marks.add(self)
        self.pos = self.buf.pointtopos(point)

    @property
    def point(self):
        """The value of the mark in external coordinates"""
        return self.buf.postopoint(self.pos)

    @point.setter
    def point(self, val):
        self.pos = self.buf.pointtopos(val)

    def __repr__(self):
        return '<%s:%s %d (%d)>' % (
            self.__class__.__name__,
            repr(self.buf),
            self.pos,
            self.point,
            )

    def __int__(self):
        return self.point

    def __eq__(self, other):
        return self.point == int(other)

    def __lt__(self, other):
        return self.point < int(other)

    def __hash__(self):
        # this is technically a nono
        return id(self)


class GapBuffer:
    def __init__(self, content=None, chunksize=None):
        self.chunksize = chunksize or CHUNKSIZE
        self.marks = weakref.WeakSet()
        self.buf = self._array(self.chunksize)
        self.gapstart = 0
        self.gapend = len(self.buf)
        self.cache = {}

        if content is not None:
            self.replace(0, 0, content)

    def __repr__(self):
        return '<%s size=%d:%d left=%s right=%s>' % (
            self.__class__.__name__,
            self.size, len(self.buf),
            repr(self.buf[:self.gapstart].tounicode()),
            repr(self.buf[self.gapend:].tounicode()),
            )

    def _array(self, size):
        return array.array('u', u' ' * size)

    @property
    def size(self):
        return len(self.buf) - self.gaplength

    @property
    def text(self):
        return (
            self.buf[:self.gapstart].tounicode()
            + self.buf[self.gapend:].tounicode())

    def textrange(self, beg, end):
        beg = self.pointtopos(beg)
        end = self.pointtopos(end)
        l = []
        if beg <= self.gapstart:
            l.append(self.buf[beg:min(self.gapstart, end)].tounicode())
        if end > self.gapstart:
            l.append(self.buf[max(self.gapend, beg):end].tounicode())
        return ''.join(l)

    @property
    def gaplength(self):
        return self.gapend - self.gapstart

    def pointtopos(self, point):
        point = int(point)
        if point < 0:
            return 0
        if point <= self.gapstart:
            return point
        if point < self.size:
            return point + self.gaplength
        return len(self.buf)

    def postopoint(self, pos):
        if pos < self.gapstart:
            return pos
        elif pos <= self.gapend:
            return self.gapstart
        else:
            return pos - self.gaplength

    def movegap(self, pos, size):
        # convert marks to point coordinates
        for mark in self.marks:
            mark.pos = mark.point
        point = self.postopoint(pos)

        # expand the gap if necessary
        if size > self.gaplength:
            increase = (
                ((size - self.gaplength) // self.chunksize + 1) * self.chunksize)
            self.buf[self.gapstart:self.gapstart] = self._array(increase)
            self.gapend += increase

        pos = self.pointtopos(point)
        # okay, now we move the gap.
        if pos < self.gapstart:
            # If we're moving it towards the top of the buffer
            newend = pos + self.gaplength
            self.buf[newend:self.gapend] = self.buf[pos:self.gapstart]
            self.gapstart = pos
            self.gapend = newend
        elif pos > self.gapend:
            # towards the bottom
            newstart = pos - self.gaplength
            self.buf[self.gapstart:newstart] = self.buf[self.gapend:pos]
            self.gapstart = newstart
            self.gapend = pos
        # turns marks back to pos coordinates
        for mark in self.marks:
            mark.point = mark.pos

    def replace(self, where, size, string):
        if hasattr(where, 'pos'):
            where = where.pos
        else:
            where = self.pointtopos(where)
        length = len(string)
        self.movegap(where, length - size)
        self.gapend += size
        newstart = self.gapstart + length
        self.buf[self.gapstart:newstart] = array.array('u', string)
        self.gapstart = newstart
        self.cache = {}
        return length

    def mark(self, where):
        return Mark(self, where)


class Editor(context.Window, context.PagingMixIn):
    EOL = '\n'

    def __init__(
        self, *args, chunksize=CHUNKSIZE, prompt=None, content=None, **kw):

        self.buf = GapBuffer(content=content, chunksize=chunksize)
        self.prompt = prompt

        super().__init__(*args, **kw) #XXX need share buffer?

        self.log = logging.getLogger('Editor.%x' % (id(self),))

        self.cursor = self.buf.mark(self.buf.size)

    def mark(self, where=None):
        if where is None:
            where = self.cursor
        return self.buf.mark(where)

    @context.bind('Control-T')
    def insert_test_content(self, k):
        import itertools
        for i in range(32):
            self.insert(''.join(itertools.islice(
                itertools.cycle(
                    [chr(x) for x in range(ord('A'), ord('Z') + 1)] +
                    [chr(x) for x in range(ord('0'), ord('9') + 1)]),
                i,
                i + 72)) + '\n')

    @context.bind(
        '[tab]', '[linefeed]',
        *(chr(x) for x in range(ord(' '), ord('~') + 1)))
    def insert(self, s):
        self.cursor.point += self.buf.replace(self.cursor, 0, s)

    @context.bind('[carriage return]', 'Control-J')
    def insert_newline(self, k):
        self.insert('\n')

    def delete(self, count):
        self.buf.replace(self.cursor, count, '')

    @context.bind('Control-D', '[dc]')
    def delete_forward(self, k):
        self.delete(1)

    @context.bind('Control-H', 'Control-?', '[backspace]')
    def delete_backward(self, k):
        if self.move(-1):
            self.delete(1)

    @context.bind('Control-F', '[right]')
    def move_forward(self, k):
        self.move(1)

    @context.bind('Control-B', '[left]')
    def move_backward(self, k):
        self.move(-1)

    def move(self, delta):
        '''.move(delta, mark=None) -> actual distance moved
        Move the point by delta.
        '''
        z = self.cursor.point
        self.cursor.point += delta # the setter does appropriate clamping
        return self.cursor.point - z

    @context.bind('Control-N', '[down]')
    def line_next(self, k):
        self.line_move(1)

    @context.bind('Control-P', '[up]')
    def line_previous(self, k):
        self.line_move(-1)

    def line_move(self, delta):
        count = abs(delta)
        for _ in range(count):
            if delta < 0:
                self.beginning_of_line()
                self.move(-1)
                self.beginning_of_line()
            elif delta > 0:
                self.end_of_line()
                if not self.move(1):
                    self.beginning_of_line()

    def extract_current_line(self):
        p = self.cursor.point
        r = self.buf.cache.setdefault('extract_current_line', {}).get(p)
        if r is not None:
            return r

        with self.save_excursion():
            self.beginning_of_line()
            start = self.cursor.point
            self.end_of_line()
            self.move(1)
            result = (start, self.buf.textrange(start, self.cursor))
            self.buf.cache['extract_current_line'][p] = result
            return result

    def view(self, origin, direction='forward'):
        # this is the right place to do special processing of
        # e.g. control characters
        m = self.mark(origin)

        if direction not in ('forward', 'backward'):
            raise ValueError('invalid direction', direction)

        while True:
            with self.save_excursion(m):
                p, s = self.extract_current_line()
            l = len(s)
            if p == 0 and self.prompt: # first line  "this could be a callback"
                prefix = [(('bold',), self.prompt)]
            else:
                prefix = []
            if ((p <= self.cursor.point < p + l)
                or (self.cursor.point == p + l == self.buf.size)):
                yield (
                    self.mark(p),
                    prefix + [
                        ((), s[:self.cursor.point - p]),
                        (('cursor', 'visible'), s[self.cursor.point - p:]),
                        ],
                    )
            else:
                yield self.mark(p), prefix + [((), s)]
            if direction == 'forward':
                if p == self.buf.size or s[-1] != '\n':
                    break
                m.point += l
            else:
                if p == 0:
                    break
                m.point = p - 1

    def character_at_point(self):
        return self.buf.textrange(self.cursor.point, self.cursor.point + 1)

    def find_character(self, cs, delta=1):
        while self.move(delta):
            x = self.character_at_point()
            if x and x in cs:
                return x
        return ''

    @context.bind('Control-A', '[home]')
    def beginning_of_line(self, k=None):
        if self.cursor.point == 0:
            return
        with self.save_excursion():
            self.move(-1)
            if self.character_at_point() == self.EOL:
                return
        if self.find_character(self.EOL, -1):
            self.move(1)

    @context.bind('Control-E', '[end]')
    def end_of_line(self, k=None):
        if not self.character_at_point() == self.EOL:
            self.find_character(self.EOL)

    @contextlib.contextmanager
    def save_excursion(self, mark=None):
        cursor = self.mark()
        if mark is not None:
            self.cursor.point = mark
        yield
        if mark is not None:
            mark.point = self.cursor
        self.cursor.point = cursor

    @context.bind('[HOME]', 'Shift-[HOME]', '[SHOME]', 'Meta-<')
    def beginning_of_buffer(self, k):
        self.cursor.point = 0

    @context.bind('[END]', 'Shift-[END]', '[SEND]', 'Meta->')
    def end_of_buffer(self, k):
        self.cursor.point = self.buf.size

    def input_char(self, k):
        self.log.debug('before command %s', self.cursor)
        super().input_char(k)
        self.log.debug('after command  %s', self.cursor)

    def isword(self, delta=0):
        with self.save_excursion():
            if delta and not self.move(delta):
                return None
            c = self.character_at_point()
            if not c:
                return False
            cat = unicodedata.category(c)
            return cat[0] == 'L' or cat == 'Pc'

    @context.bind('Meta-f')
    def word_forward(self, k):
        while not self.isword():
            if not self.move(1):
                return
        while self.isword():
            if not self.move(1):
                return

    @context.bind('Meta-b')
    def word_backward(self, k):
        while not self.isword(-1):
            if not self.move(-1):
                return
        while self.isword(-1):
            if not self.move(-1):
                return

class LongPrompt(Editor):
    def __init__(self, *args, callback=lambda x: None, **kw):
        super().__init__(*args, **kw)
        self.callback = callback
        self.keymap['Control-J'] = self.runcallback
        self.keymap['Control-C Control-C'] = self.runcallback

    def runcallback(self, k):
        self.callback(self.buf.text)

class ShortPrompt(LongPrompt):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.keymap['[carriage return]'] = self.runcallback
