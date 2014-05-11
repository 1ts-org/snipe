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

from . import context


CHUNKSIZE = 4096


class Mark(object):
    def __init__(self, editor, point):
        self.editor = editor
        self.editor.marks.add(self)
        self.pos = self.editor.pointtopos(point)

    @property
    def point(self):
        """The value of the mark in external coordinates"""
        return self.editor.postopoint(self.pos)

    @point.setter
    def point(self, val):
        self.pos = self.editor.pointtopos(val)

    def __repr__(self):
        return '<%s:%s %d (%d)>' % (
            self.__class__.__name__,
            repr(self.editor),
            self.pos,
            self.point,
            )

    def __int__(self):
        return self.point


class Editor(context.Window):
    EOL = '\n'

    def __init__(self, frontend, prototype=None, chunksize=CHUNKSIZE):
        super(Editor, self).__init__(frontend, None) #XXX need share buffer

        for x in range(ord(' '), ord('~') + 1):
            self.keymap[chr(x)] = self.insert

        self.keymap.update({
            '[carriage return]': self.insert,
            '[tab]': self.insert,
            '[linefeed]': self.insert,
            'Control-A': self.beginning_of_line,
            'Control-B': lambda k: self.move(-1),
            'Control-E': self.end_of_line,
            'Control-F': lambda k: self.move(1),
            'Control-N': lambda k: self.line_move(1),
            'Control-P': lambda k: self.line_move(-1),

            'Control-T': self.insert_test_content,
            })

        self.chunksize = chunksize

        self.marks = weakref.WeakSet()

        self.buf = self._array(self.chunksize)
        self.gapstart = 0
        self.gapend = len(self.buf)

        self.cursor = Mark(self, 0)
        self.log = logging.getLogger('Editor.%x' % (id(self),))

        self.cache = {}

    def insert_test_content(self, k):
        import itertools
        for i in range(32):
            self.insert(''.join(itertools.islice(
                itertools.cycle(
                    [chr(x) for x in range(ord('A'), ord('Z') + 1)] +
                    [chr(x) for x in range(ord('0'), ord('9') + 1)]),
                i,
                i + 72)) + '\n')

    def set_content(self, s):
        self.cursor.point = 0
        self.replace(self.size, s)

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
        beg = int(beg)
        end = int(end)
        l = []
        if beg <= self.gapstart:
            l.append(self.buf[beg:min(self.gapstart, end)].tounicode())
        if end > self.gapstart:
            l.append(self.buf[self.gapend:self.pointtopos(end)].tounicode())
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

    def replace(self, size, string):
        where = self.cursor.pos
        self.movegap(where, len(string) - size)
        self.gapend += size
        newstart = self.gapstart + len(string)
        self.buf[self.gapstart:newstart] = array.array('u', unicode(string))
        self.gapstart = newstart
        self.cursor.pos = where + len(string)
        self.cache = {}

    def insert(self, s):
        self.replace(0, s)

    def delete(self, count):
        self.replace(count, '')

    def move(self, delta):
        '''.move(delta, mark=None) -> actual distance moved
        Move the point by delta.
        '''
        z = self.cursor.point
        self.cursor.point += delta # the setter does appropriate clamping
        return self.cursor.point - z

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
        r = self.cache.setdefault('extract_current_line', {}).get(p)
        if r is not None:
            return r

        with self.save_excursion():
            self.beginning_of_line()
            start=self.cursor.point
            self.end_of_line()
            self.move(1)
            result = (start, self.textrange(start, self.cursor))
            self.cache['extract_current_line'][p] = result
            return result

    def view(self, origin, direction='forward'):
        # this is the right place to do special processing of
        # e.g. control characters
        m = Mark(self, origin)

        if direction not in ('forward', 'backward'):
            raise ValueError('invalid direction', direction)

        while True:
            with self.save_excursion(m):
                p, s = self.extract_current_line()
            l = len(s)
            if (p <= self.cursor.point < p + l) or (self.cursor.point == p + l == self.size):
                yield (
                    Mark(self, p),
                    [
                        ((), s[:self.cursor.point - p]),
                        (('cursor', 'visible'), s[self.cursor.point - p:]),
                        ],
                    )
            else:
                yield Mark(self, p), [((), s)]
            if direction == 'forward':
                if p == self.size or s[-1] != '\n':
                    break
                m.point += l
            else:
                if p == 0:
                    break
                m.point = p - 1

    def character_at_point(self):
        return self.textrange(self.cursor.point, self.cursor.point + 1)

    def find_character(self, cs, delta=1):
        while self.move(delta):
            x = self.character_at_point()
            if x and x in cs:
                return x
        return ''

    def beginning_of_line(self, k=None):
        if self.cursor.point == 0:
            return
        with self.save_excursion():
            self.move(-1)
            if self.character_at_point() == self.EOL:
                return
        if self.find_character(self.EOL, -1):
            self.move(1)

    def end_of_line(self, k=None):
        if not self.character_at_point() == self.EOL:
            self.find_character(self.EOL)

    @contextlib.contextmanager
    def save_excursion(self, mark=None):
        cursor = Mark(self, self.cursor)
        if mark is not None:
            self.cursor.point = mark
        yield
        if mark is not None:
            mark.point = self.cursor
        self.cursor.point = cursor

try:
    unicode('foo')
except NameError:
    unicode = lambda x: x # glue for python 3
