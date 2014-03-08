# -*- encoding: utf-8 -*-

import array

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

class Editor(context.Window):
    def __init__(self, frontend, chunksize=CHUNKSIZE):
        super(Editor, self).__init__(frontend)
        for x in range(ord(' '), ord('~') + 1):
            self.keymap[chr(x)] = self.insert
        for x in ['\n', '\t', '\j']:
            self.keymap['\n'] = self.insert

        self.chunksize = chunksize

        self.marks = set()

        self.buf = self._array(self.chunksize)
        self.gapstart = 0
        self.gapend = len(self.buf)

        self.cursor = Mark(self, 0)

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

    @property
    def gaplength(self):
        return self.gapend - self.gapstart

    def pointtopos(self, point):
        if point < 0:
            return 0
        if point < self.gapstart:
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
        self.movegap(self.cursor.pos, len(string) - size)
        self.gapend += size
        newstart = self.gapstart + len(string)
        self.buf[self.gapstart:newstart] = array.array('u', unicode(string))
        self.gapstart = newstart

    def insert(self, s):
        self.replace(0, s)

    def delete(self, count):
        self.replace(count, '')

    def view(self):
        return context.ViewStub([
            ((), self.text[:self.cursor.point]),
            (('cursor',), self.text[self.cursor.point:]),
            ])
