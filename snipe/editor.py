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
from . import interactive


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
        super().__init__()
        self.log = logging.getLogger(
            '%s.%x' % ('GapBuffer', id(self),))
        self.chunksize = chunksize or CHUNKSIZE
        self.marks = weakref.WeakSet()
        self.buf = self._array(self.chunksize)
        self.gapstart = 0
        self.gapend = len(self.buf)
        self.cache = {}

        if content is not None:
            self.replace(0, 0, content)

    def __repr__(self):
        return '<%s size=%d:%d left=%s (%d-%d) right=%s>' % (
            self.__class__.__name__,
            self.size, len(self.buf),
            repr(self.buf[:self.gapstart].tounicode()),
            self.gapstart, self.gapend,
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
        assert size >= 0
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


class UndoableGapBuffer(GapBuffer):
    def __init__(self, *args, **kw):
        self.undolog = []
        super().__init__(*args, **kw)

    def replace(self, where, size, string, collapsible=False):
        self.log.debug('collapsible %s %d %d %s', collapsible, where, size, repr(string))
        if self.undolog:
            self.log.debug('self.undolog[-1] %s', repr(self.undolog[-1]))
        if collapsible and self.undolog \
          and where == self.undolog[-1][0] + self.undolog[-1][1] \
          and string != '' and self.undolog[-1][2] == '':
            #XXX only "collapses" inserts
            self.log.debug('collapse %s', repr(self.undolog[-1]))
            self.undolog[-1] = (self.undolog[-1][0], len(string) + self.undolog[-1][1], '')
        else:
            self.undolog.append(
                (int(where), len(string), self.textrange(where, int(where) + size)))
        return super().replace(where, size, string)

    def undo(self, which):
        if not self.undolog:
            return None
        if which is not None:
            off = which
        else:
            off = len(self.undolog) - 1
        where, size, string = self.undolog[off]
        self.replace(where, size, string)
        return (off - 1) % len(self.undolog), where + len(string)


class Editor(context.Window, context.PagingMixIn):
    EOL = '\n'

    def __init__(
        self, *args, chunksize=CHUNKSIZE, prompt=None, content=None, **kw):

        self.buf = UndoableGapBuffer(content=content, chunksize=chunksize)
        self.prompt = prompt

        super().__init__(*args, **kw) #XXX need share buffer?

        self.log = logging.getLogger('Editor.%x' % (id(self),))

        self.cursor = self.buf.mark(0)
        self.the_mark = None
        self.mark_ring = []

        self.yank_state = 1
        self.undo_state = None

        self.goal_column = None

    def mark(self, where=None):
        if where is None:
            where = self.cursor
        return self.buf.mark(where)

    @context.bind('Meta-T')
    def insert_test_content(
            self, count: interactive.positive_integer_argument=80):
        import itertools
        self.insert(''.join(
            itertools.islice(itertools.cycle('1234567890'), count)))

    @context.bind(
        '[tab]', '[linefeed]',
        *(chr(x) for x in range(ord(' '), ord('~') + 1)))
    def self_insert(
            self,
            key: interactive.keystroke,
            count: interactive.positive_integer_argument=1):
        collapsible = True
        if self.last_command == 'self_insert':
            if (not self.last_key.isspace()) and key.isspace():
                collapsible=False
        for _ in range(count):
            self.insert(key, collapsible)

    def insert(self, s, collapsible=False):
        self.cursor.point += self.replace(0, s, collapsible)

    @context.bind('[carriage return]', 'Control-J')
    def insert_newline(self, count: interactive.positive_integer_argument=1):
        self.insert('\n' * count)

    def delete(self, count):
        self.log.debug('delete %d', count)
        self.replace(count, '')

    def replace(self, count, string, collapsible=False):
        return self.buf.replace(self.cursor, count, string, collapsible)

    @context.bind('Control-D', '[dc]')
    def delete_forward(self, count: interactive.integer_argument=1):
        if count < 0:
            moved = self.move(count)
            count = -moved
        self.delete(count)

    @context.bind('Control-H', 'Control-?', '[backspace]')
    def delete_backward(self, count: interactive.integer_argument=1):
        self.delete_forward(-count)

    @context.bind('Control-F', '[right]')
    def move_forward(self, count: interactive.integer_argument=1):
        self.move(count)

    @context.bind('Control-B', '[left]')
    def move_backward(self, count: interactive.integer_argument=1):
        self.move(-count)

    def move(self, delta):
        '''.move(delta, mark=None) -> actual distance moved
        Move the point by delta.
        '''
        z = self.cursor.point
        self.cursor.point += delta # the setter does appropriate clamping
        self.goal_column = None
        return self.cursor.point - z

    @context.bind('Control-N', '[down]')
    def line_next(self, count: interactive.integer_argument=1):
        self.line_move(count)

    @context.bind('Control-P', '[up]')
    def line_previous(self, count: interactive.integer_argument=1):
        self.line_move(-count)

    def line_move(self, delta, track_column=True):
        count = abs(delta)
        goal_column = self.goal_column
        if goal_column is None:
            with self.save_excursion():
                p = self.cursor.point
                self.beginning_of_line()
                goal_column = p - self.cursor.point
        for _ in range(count):
            if delta < 0:
                self.beginning_of_line()
                self.move(-1)
                self.beginning_of_line()
            elif delta > 0:
                self.end_of_line()
                if not self.move(1):
                    self.beginning_of_line()
        with self.save_excursion():
            p = self.cursor.point
            self.end_of_line()
            line_length = self.cursor.point - p
        if track_column:
            self.move(min(goal_column, line_length))
            self.goal_column = goal_column

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
    def beginning_of_line(self, count: interactive.integer_argument=None):
        if count is not None:
            self.line_move(count - 1)
        if self.cursor.point == 0:
            return
        with self.save_excursion():
            self.move(-1)
            if self.character_at_point() == self.EOL:
                return
        if self.find_character(self.EOL, -1):
            self.move(1)

    @context.bind('Control-E', '[end]')
    def end_of_line(self, count: interactive.integer_argument=None):
        if count is not None:
            self.line_move(count - 1)
        if not self.character_at_point() == self.EOL:
            self.find_character(self.EOL)

    @contextlib.contextmanager
    def save_excursion(self, where=None):
        cursor = self.mark()
        mark = self.mark(self.the_mark)
        mark_ring = self.mark_ring
        self.mark_ring = list(self.mark_ring)
        goal_column = self.goal_column
        if where is not None:
            self.cursor.point = where
        yield
        if where is not None:
            where.point = self.cursor
        self.cursor.point = cursor
        self.the_mark = mark
        self.mark_ring = mark_ring
        self.goal_column = goal_column

    @context.bind('[HOME]', 'Shift-[HOME]', '[SHOME]', 'Meta-<')
    def beginning_of_buffer(self, pct: interactive.argument):
        self.log.debug('beginning_of_buffer: pct=%s', repr(pct))
        oldpoint = self.cursor.point
        if not isinstance(pct, int):
            pct = 0
        if pct < 0:
            return self.end_of_buffer(-pct)
        self.cursor.point = min(pct * self.buf.size // 10, self.buf.size)
        self.beginning_of_line()
        if oldpoint != self.cursor.point:
            self.set_mark(oldpoint)

    @context.bind('[END]', 'Shift-[END]', '[SEND]', 'Meta->')
    def end_of_buffer(self, pct: interactive.argument):
        oldpoint = self.cursor.point
        if not isinstance(pct, int):
            pct = 0
        if pct < 0:
            return self.beginning_of_buffer(-pct)
        self.cursor.point = max((10 - pct) * self.buf.size // 10, 0)
        self.beginning_of_line()
        if oldpoint != self.cursor.point:
            self.set_mark(oldpoint)

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
    def word_forward(self, count: interactive.integer_argument=1):
        if count < 0:
            return self.word_backward(-count)
        for _ in range(count):
            while not self.isword():
                if not self.move(1):
                    return
            while self.isword():
                if not self.move(1):
                    return

    @context.bind('Meta-b')
    def word_backward(self, count: interactive.integer_argument=1):
        if count < 0:
            return self.word_forward(-count)
        for _ in range(count):
            while not self.isword(-1):
                if not self.move(-1):
                    return
            while self.isword(-1):
                if not self.move(-1):
                    return

    @context.bind('Control-k')
    def kill_to_end_of_line(self, count: interactive.integer_argument):
        m = self.mark()
        if count is None: #"normal" case
            self.end_of_line()
            if m == self.cursor:
                # at the end of a line, move past it
                self.move(1)
            if m == self.cursor:
                # end of buffer
                return
        elif count == 0: # kill to beginning of line?
            self.beginning_of_line()
        else:
            self.line_move(count, False)
        self.kill_region(mark=m, append=self.last_command.startswith('kill_'))

    def region(self, mark=None):
        if mark is None:
            mark = self.mark
        if mark is None:
            return None
        return self.buf.textrange(
            min(self.cursor, self.the_mark),
            max(self.cursor, self.the_mark))

    @context.bind('Control-W')
    def kill_region(self, mark=None, append=False):
        if mark is None:
            mark = self.the_mark
        if mark is None:
            self.whine('no mark is set')
            return
        self.log.debug('kill region %d-%d', self.cursor.point, mark.point)

        if not append:
            self.context.copy(self.region(mark))
        else:
            self.context.copy(self.region(mark), mark < self.cursor)

        count = abs(mark.point - self.cursor.point)
        self.cursor = min(self.cursor, mark)
        self.delete(count)

        self.yank_state = 1

    @context.bind('Meta-w')
    def copy_region(self):
        if self.the_mark is None:
            self.whine('no mark is set')
            return
        self.context.copy(self.region())
        self.yank_state = 1

    @context.bind('Control-[space]')
    def set_mark(self, where=None, prefix: interactive.argument=None):
        if prefix is None:
            self.mark_ring.append(self.the_mark)
            self.the_mark = self.mark(where)
        else:
            self.mark_ring.insert(0, self.mark(where))
            where = self.the_mark
            self.the_mark = self.mark_ring.pop()
            self.cursor = where

    @context.bind('Control-X Control-X')
    def exchange_point_and_mark(self):
        self.cursor, self.the_mark = self.the_mark, self.cursor

    def insert_region(self, s):
        self.set_mark()
        self.insert(s)

    @context.bind('Control-Y')
    def yank(self, arg: interactive.argument=None):
        if arg and isinstance(arg, int):
            self.yank_state += arg - 1
        self.insert_region(self.context.yank(self.yank_state))
        if arg is not None and not isinstance(nth, int):
            self.exchange_point_and_mark()

    @context.bind('Meta-y')
    def yank_pop(self, arg: interactive.integer_argument=1):
        if self.last_command not in ('yank', 'yank_pop'):
            self.whine('last command was not a yank')
            return
        self.yank_state += arg
        if self.cursor > self.the_mark:
            self.exchange_point_and_mark()
        self.delete(abs(self.the_mark.point - self.cursor.point))
        self.insert_region(self.context.yank(self.yank_state))

    @context.bind('Control-_', 'Control-x u')
    def undo(self, count: interactive.positive_integer_argument=1):
        if self.last_command != 'undo':
            self.undo_state = None
        for _ in range(count):
            self.undo_state, where = self.buf.undo(self.undo_state)
            self.cursor.point = where
            if self.undo_state == None:
                self.whine('Nothing to undo')
                break

    @context.bind('Control-T')
    def transpose_chars(self):
        off = 1
        p = self.cursor.point
        if p == self.buf.size:
            off = 2
        if self.move(-off) != -off:
            self.cursor.point = p
            self.whine('At beginning')
            return
        s = self.buf.textrange(self.cursor, int(self.cursor) + 2)
        s = ''.join(reversed(s)) # *sigh*
        self.replace(2, s)
        self.move(2)

    @context.bind('Control-O')
    def open_line(self, count: interactive.positive_integer_argument=1):
        with self.save_excursion():
            self.insert('\n' * count)

    @context.bind(
        'Meta-[backspace]', 'Meta-Control-H', 'Meta-[dc]', 'Meta-[del]')
    def kill_word_backward(self, count: interactive.integer_argument=1):
        mark = self.mark()
        self.word_backward(count)
        self.kill_region(mark, append=self.last_command.startswith('kill_'))

    @context.bind('Meta-d')
    def kill_word_forward(self, count: interactive.integer_argument=1):
        mark = self.mark()
        self.word_forward(count)
        self.kill_region(mark, append=self.last_command.startswith('kill_'))


class LongPrompt(Editor):
    def __init__(self, *args, callback=lambda x: None, **kw):
        super().__init__(*args, **kw)
        self.callback = callback
        self.keymap['Control-J'] = self.runcallback
        self.keymap['Control-C Control-C'] = self.runcallback
        self.cursor = self.buf.mark(self.buf.size)

    def runcallback(self):
        self.callback(self.buf.text)


class ShortPrompt(LongPrompt):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.keymap['[carriage return]'] = self.runcallback
