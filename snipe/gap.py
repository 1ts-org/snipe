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
snipe.gap
----------

Data structure for efficiently storing a mutable string that grows and shrinks.
'''


import logging
import weakref
import array


class GapBuffer:
    CHUNKSIZE = 4096

    def __init__(self, content=None, chunksize=None):
        super().__init__()
        self.log = logging.getLogger(
            '%s.%x' % ('GapBuffer', id(self),))
        self.chunksize = chunksize or self.CHUNKSIZE
        self.marks = weakref.WeakSet()
        self.buf = self._array(self.chunksize)
        self.gapstart = 0
        self.gapend = len(self.buf)

        if content is not None:
            self.replace(0, 0, content)

    def __repr__(self):
        return '<%s size=%d:%d %d-%d>' % (
            self.__class__.__name__,
            self.size, len(self.buf),
            self.gapstart, self.gapend,
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

    def pointtopos(self, point, right=False):
        point = int(point)
        if point < 0:
            return 0
        if point < self.gapstart:
            return point
        if point == self.gapstart:
            if right:
                return point + self.gaplength
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
                ((size - self.gaplength) // self.chunksize + 1)
                * self.chunksize)
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

    def replace(self, where, size, string, collapsible=None):
        assert size >= 0
        assert int(where) <= self.size
        size = min(size, self.size - int(where))
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
        return length

    def mark(self, where, right=False):
        if where is None:
            return None
        return GapMark(self, where, right)


class UndoableGapBuffer(GapBuffer):
    def __init__(self, *args, **kw):
        self.undolog = []
        super().__init__(*args, **kw)

    def replace(self, where, size, string, collapsible=False):
        self.log.debug(
            'collapsible %s %d %d %s', collapsible, where, size, repr(string))
        if self.undolog:
            self.log.debug('self.undolog[-1] %s', repr(self.undolog[-1]))
        if (collapsible and self.undolog
                and where == self.undolog[-1][0] + self.undolog[-1][1]
                and string != '' and self.undolog[-1][2] == ''):
            # XXX only "collapses" inserts
            self.log.debug('collapse %s', repr(self.undolog[-1]))
            self.undolog[-1] = (
                self.undolog[-1][0],
                len(string) + self.undolog[-1][1], '',
                )
        else:
            self.undolog.append((
                int(where),
                len(string),
                self.textrange(where, int(where) + size),
                ))
        return super().replace(where, size, string)

    def undo_entry(self, which):
        if not self.undolog:
            return None, None, None
        if which is not None:
            off = which
        else:
            off = len(self.undolog) - 1
        return self.undolog[off]

    def undo(self, which):
        if not self.undolog:
            return None, None
        if which is not None:
            off = which
        else:
            off = len(self.undolog) - 1
        where, size, string = self.undo_entry(off)
        self.replace(where, size, string)
        return (off - 1) % len(self.undolog), where + len(string)


class GapMark:
    def __init__(self, buf, point, right):
        self.buf = buf
        self.buf.marks.add(self)
        self.pos = self.buf.pointtopos(point, right)
        self.right = right

    @property
    def point(self):
        """The value of the mark in external coordinates"""
        return self.buf.postopoint(self.pos)

    @point.setter
    def point(self, val):
        self.pos = self.buf.pointtopos(val, self.right)

    def __repr__(self):
        return '<%s %x (%x) %d (%d)>' % (
            self.__class__.__name__,
            id(self),
            id(self.buf),
            self.pos,
            self.point,
            )

    def __int__(self):
        return self.point
