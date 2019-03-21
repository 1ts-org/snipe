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
Unit tests for the Editor object
'''


import array
import itertools
import random
import unittest
import unittest.mock

import mocks

import snipe.chunks
import snipe.editor
import snipe.imbroglio


class TestEditor(unittest.TestCase):
    def test_constructor(self):
        e = snipe.editor.Editor(None)
        self.assertEqual(e.fill_column, 0)

        e = snipe.editor.Editor(None, fill=True)
        self.assertEqual(
            e.fill_column, e.default_fill_column)

        self.assertTrue(e._writable)
        e.toggle_writable()
        self.assertFalse(e._writable)

        e.renderer = mocks.Renderer()

        f = snipe.editor.Editor(None, prototype=e)
        self.assertFalse(f._writable)

    def test_inserter(self):
        e = snipe.editor.Editor(None)
        insert_a = e._inserter('a')
        insert_a()
        self.assertEqual('a', str(e.buf))

    def testEditorSimple(self):
        e = snipe.editor.Editor(None)
        e.insert('flam')
        self.assertEqual(e.cursor.point, 4)
        e.cursor.point = 0
        e.insert('flim')
        self.assertEqual(str(e.buf), 'flimflam')
        e.cursor.point += 4
        e.insert('blam')
        self.assertEqual(str(e.buf), 'flimflamblam')

    def testEditorExpansion(self):
        e = snipe.editor.Editor(None, chunksize=1)
        e.insert('flam')
        self.assertEqual(e.cursor.point, 4)
        e.cursor.point = 0
        e.insert('flim')
        self.assertEqual(str(e.buf), 'flimflam')
        e.cursor.point += 4
        e.insert('blam')
        self.assertEqual(str(e.buf), 'flimflamblam')

    def test_mark(self):
        e = snipe.editor.Editor(None)
        e.insert('ac')
        m = e.buf.mark(1)
        m2 = e.buf.mark(1, right=True)
        e.cursor.point = 1
        e.insert('b')
        self.assertEqual(m.point, 1)
        self.assertEqual(m2.point, 2)
        self.assertEqual(str(e.buf), 'abc')

    def testEditorMore(self):
        e = snipe.editor.Editor(None)
        e.insert('bar')
        self.assertEqual(str(e.buf), 'bar')
        self.assertEqual(len(e.buf), 3)
        m = e.buf.mark(1)
        self.assertEqual(m.point, 1)
        e.cursor.point = 0
        e.insert('foo')
        self.assertEqual(str(e.buf), 'foobar')
        self.assertEqual(m.point, 4)
        e.cursor.point = 6
        e.insert('baz')
        self.assertEqual(str(e.buf), 'foobarbaz')
        self.assertEqual(m.point, 4)
        e.cursor.point = 6
        e.insert('quux')
        self.assertEqual(str(e.buf), 'foobarquuxbaz')
        self.assertEqual(m.point, 4)
        e.cursor.point = 3
        e.insert('Q' * 8192)
        self.assertEqual(str(e.buf), 'foo' + 'Q'*8192 + 'barquuxbaz')
        self.assertEqual(m.point, 8196)
        e.cursor.point = 3
        e.delete(8192)
        self.assertEqual(e.cursor.point, 3)
        self.assertEqual(str(e.buf), 'foobarquuxbaz')
        self.assertEqual(len(e.buf), 13)
        self.assertEqual(m.point, 4)
        e.cursor.point = 3
        e.insert('honk')
        e.delete(3)
        self.assertEqual(str(e.buf), 'foohonkquuxbaz')
        self.assertEqual(m.point, 7)
        e.cursor.point = 4
        e.insert('u')
        e.delete(1)
        self.assertEqual(str(e.buf)[4], 'u')
        e.cursor.point = 4
        e.delete(1)
        self.assertEqual(str(e.buf), 'foohnkquuxbaz')
        e.cursor.point = 3
        e.delete(3)
        self.assertEqual(str(e.buf), 'fooquuxbaz')

    def testFindchar(self):
        e = snipe.editor.Editor(None)
        e.insert('abcdefghji')
        e.cursor.point = 0
        self.assertEqual(e.find_character('c'), 'c')
        self.assertEqual(e.cursor.point, 2)
        self.assertEqual(e.find_character('a', 1), '')
        self.assertEqual(e.cursor.point, 10)
        self.assertEqual(e.find_character('a', -1), 'a')
        self.assertEqual(e.cursor.point, 0)
        self.assertEqual(e.find_character('z', -1), '')
        self.assertEqual(e.cursor.point, 0)
        self.assertEqual(e.find_character('c'), 'c')
        self.assertEqual(e.cursor.point, 2)

    def testIsPred(self):
        e = snipe.editor.Editor(None)
        e.insert('abcdefghji')
        e.cursor.point = 0
        self.assertTrue(e.ispred(lambda c: c == 'a'))
        self.assertFalse(e.ispred(lambda c: c == 'b'))
        self.assertFalse(e.ispred(lambda c: c == 'a', 1))
        self.assertTrue(e.ispred(lambda c: c == 'b', 1))

    def testview(self):
        e = snipe.editor.Editor(None)
        lines = [
            ''.join(itertools.islice(
                itertools.cycle(
                    [chr(x) for x in range(ord('A'), ord('Z') + 1)] +
                    [chr(x) for x in range(ord('0'), ord('9') + 1)]),
                i,
                i + 72))+'\n'
            for i in range(256)]
        e.insert(''.join(lines))
        with self.assertRaises(ValueError):
            list(e.view(0, 'pants'))
        c = e.cursor.point
        forward = [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')]
        self.assertEqual(e.cursor.point, c)
        backward = [
            (int(m), l.tagsets()) for (m, l) in e.view(len(e.buf), 'backward')]
        self.assertEqual(e.cursor.point, c)
        self.assertEqual(len(forward), 257)
        self.assertEqual(forward, list(reversed(backward)))
        self.assertEqual(
            backward[0],
            (len(e.buf), [({'cursor', 'visible'}, '')]))
        self.assertEqual(len(forward), 257)
        c = e.cursor.point
        it = iter(e.view(0, 'forward'))
        next(it)
        self.assertEqual(e.cursor.point, c)
        next(it)
        self.assertEqual(e.cursor.point, c)
        it = iter(e.view(len(e.buf), 'backward'))
        next(it)
        self.assertEqual(e.cursor.point, c)
        next(it)
        self.assertEqual(e.cursor.point, c)

    def testviewedge(self):
        e = snipe.editor.Editor(None)
        e.insert('abc')
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [((), 'abc'), ({'cursor', 'visible'}, '')])])

    def test_view_search(self):
        e = snipe.editor.Editor(None)
        e.insert('abcdefghi')
        e.search_term = 'def'
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'abc'),
                ({'reverse'}, 'def'),
                ((), 'ghi'),
                ({'cursor', 'visible'}, ''),
            ])])

    def test_view_control(self):
        e = snipe.editor.Editor(None)
        e.insert('abcdef\007hi')
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'abcdef'),
                (snipe.chunks.Chunk.SHOW_CONTROL, '^G'),
                ((), 'hi'),
                ({'cursor', 'visible'}, ''),
            ])])
        e.move(-3, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'abcdef'),
                (snipe.chunks.Chunk.SHOW_CONTROL | {'cursor', 'visible'},
                    '^G'),
                ((), 'hi'),
            ])])

    def test_view_explode_combining(self):
        e = snipe.editor.Editor(None)
        e.insert('aa\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}a')
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'aa\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}a'),
                ({'cursor', 'visible'}, ''),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'aa\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}'),
                ({'cursor', 'visible'}, 'a'),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'a'),
                (e.SHOW_COMBINING, 'a \N{COMBINING DIAERESIS}'),
                (e.SHOW_COMBINING | {'cursor', 'visible'},
                    ' \N{COMBINING CEDILLA}'),
                ((), 'a'),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'a'),
                (e.SHOW_COMBINING, 'a'),
                (e.SHOW_COMBINING | {'cursor', 'visible'},
                    ' \N{COMBINING DIAERESIS} \N{COMBINING CEDILLA}'),
                ((), 'a'),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'a'),
                (e.SHOW_COMBINING | {'cursor', 'visible'},
                    'a \N{COMBINING DIAERESIS} \N{COMBINING CEDILLA}'),
                ((), 'a'),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ({'cursor', 'visible'},
                    'aa\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}a'),
            ])])
        e.delete_forward()
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ({'cursor', 'visible'}, ''),
                (e.SHOW_COMBINING,
                    'a \N{COMBINING DIAERESIS} \N{COMBINING CEDILLA}'),
                ((), 'a'),
            ])])
        e.insert('a')
        e.end_of_line()
        e.delete_backward()
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'aa\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}'),
                ({'cursor', 'visible'}, ''),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'a'),
                (e.SHOW_COMBINING, 'a \N{COMBINING DIAERESIS}'),
                (e.SHOW_COMBINING | {'cursor', 'visible'},
                    ' \N{COMBINING CEDILLA}'),
                ((), ''),
            ])])
        e.move(-1, False)
        self.assertEqual(
            [(int(m), l.tagsets()) for (m, l) in e.view(0, 'forward')],
            [(0, [
                ((), 'a'),
                (e.SHOW_COMBINING, 'a'),
                (e.SHOW_COMBINING | {'cursor', 'visible'},
                    ' \N{COMBINING DIAERESIS} \N{COMBINING CEDILLA}'),
                ((), ''),
            ])])

    def test_fuzz(
            self,
            iterations=10000,
            max_len=74,
            max_op_len=10,
            show_delay=0.01,
            ):
        # For many <iterations> randomly either insert or delete up to
        # <max_op_len> chars or just move the gap around.
        #
        # Make sure the entire thing is never more than max_len chars long.
        #
        # Make a parallel array and confirm after each operation that
        # the gap buffer's contents are the same as the array's.
        #
        # If show_delay is > 0, then the gap buffer will be shown each
        # iteration.  If it's 0 then nothign will display during
        # iteration, but the operations will be dumped after all
        # iterations.

        contents = (
            u'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

        g = snipe.editor.Editor(None)
        a = array.array('u')
        for n in range(iterations):
            pos = len(g.buf) and random.randint(0, len(g.buf) - 1)
            # A 1 in 3 chance to delete, unless we're at max length,
            # then delete regardless
            if not random.randint(0, 2) or len(g.buf) >= max_len:
                howmany = min(len(g.buf) - pos, random.randint(1, max_op_len))
                g.cursor.point = pos
                g.delete(howmany)
                for d in range(howmany):
                    a.pop(pos)
            else:
                g.cursor.point = pos
                # A 1 in 2 chance to insert instead of just moving th gap
                if not random.randint(0, 1):
                    howmany = random.randint(
                        1, max(max_op_len, max_len - len(g.buf)))
                    char = random.choice(contents)
                    g.insert(char * howmany)
                    for i in range(howmany):
                        a.insert(pos, char)
            self.assertEqual(a.tounicode(), str(g.buf))

    def test_character_at_point(self):
        # really testing textrange
        e = snipe.editor.Editor(None)
        e.insert('one\ntwo\nthree\nfour\n')
        e.line_previous()
        e.line_previous()
        self.assertEqual(e.character_at_point(), 't')
        e.insert('x')
        self.assertEqual(e.character_at_point(), 't')
        e.move(10)
        self.assertEqual(e.character_at_point(), '\n')

    def test_extract_current_line(self):
        e = snipe.editor.Editor(None)
        shouldchange = e.extract_current_line()
        e.insert('x')
        e.cursor.point = 0
        self.assertNotEqual(e.extract_current_line(), shouldchange)

    def test_delete_char_at_end_of_buffer(self):
        e = snipe.editor.Editor(None)
        e.insert('x')
        self.assertEqual(e.cursor.point, 1)
        e.delete_forward()
        self.assertEqual(e.cursor.point, 1)
        self.assertEqual(len(e.buf), 1)

    def test_view_cursor(self):
        w = snipe.editor.Editor(None)
        w.insert('> m; foobar')
        w.insert_newline()

        self.assertEqual([
            (0, [((), '> m; foobar\n')]),
            (12, [({'cursor', 'visible'}, '')]),
            ],
            [(int(mark), chunk.tagsets()) for (mark, chunk) in w.view(0)])

        w.move_backward()
        self.assertEqual(
            [(0, [
                ((), '> m; foobar'),
                ({'cursor', 'visible'}, '\n'),
                ]),
             (12, [
                ((), '')]),
             ],
            [(int(mark), chunk.tagsets()) for (mark, chunk) in w.view(0)])

        w.move_forward()

        w.insert('x')
        self.assertEqual(
            [(0, [
                ((), '> m; foobar\n')]),
             (12, [
                ((), 'x'),
                ({'cursor', 'visible'}, ''),
                ]),
             ],
            [(int(mark), chunk.tagsets()) for (mark, chunk) in w.view(0)])

    def test_find(self):
        w = snipe.editor.Editor(None)
        w.insert('abc.def.ghi')
        w.cursor.point = 0
        self.assertIsNone(w.find('', True))
        self.assertEqual(w.cursor.point, 0)
        self.assertTrue(w.find('def', True))
        self.assertEqual(w.cursor.point, 4)
        self.assertTrue(w.find('ghi', True))
        self.assertEqual(w.cursor.point, 8)
        self.assertTrue(w.find('abc', False))
        self.assertEqual(w.cursor.point, 0)
        self.assertFalse(w.find('jkl', True))

    def test_match(self):
        w = snipe.editor.Editor(None)
        w.insert('abc.def.ghi')
        w.cursor.point = 0
        self.assertFalse(w.match('foo'))
        self.assertTrue(w.match('abc'))

    def test_writable(self):
        e = snipe.editor.Editor(None)
        e.insert('abc')
        e.insert('def', prop={'mutable': False})
        e.insert('ghi')
        self.assertTrue(e.writable(0, 0))
        self.assertTrue(e.writable(3, 0))
        self.assertFalse(e.writable(0, 3))
        self.assertFalse(e.writable(4, 3))
        self.assertTrue(e.writable(0, 6))
        e.toggle_writable()
        self.assertFalse(e.writable(0, 6))
        e.fe = unittest.mock.Mock()
        e.insert('jkl')
        e.fe.notify.assert_called()

    def test_self_insert(self):
        e = snipe.editor.Editor(None, fill=True)
        e.self_insert('a')
        self.assertEqual('a', str(e.buf))
        self.assertEqual(1, e.column)
        e.self_insert(5)
        self.assertEqual('a', str(e.buf))

    @snipe.imbroglio.test
    async def test_self_insert_auto_fill_undo(self):
        e = snipe.editor.Editor(None)
        await e.set_fill_column(5)
        e.last_command = 'self_insert'
        for c in 'abc def ghi jik ':
            e.self_insert(c)
        self.assertEqual('abc\ndef\nghi\njik ', str(e.buf))
        e.undo(3)
        self.assertEqual('abc\ndef\nghi ', str(e.buf))

    @snipe.imbroglio.test
    async def test_do_auto_fill_prompt(self):
        e = snipe.editor.Editor(None)
        e.insert('>', prop=dict(mutable=False, navigable=False))
        await e.set_fill_column(5)
        e.last_command = 'self_insert'
        for c in 'abc def ghi jik ':
            e.self_insert(c)
        self.assertEqual('>abc def ghi jik ', str(e.buf))

    @snipe.imbroglio.test
    async def test_do_auto_fill_long(self):
        e = snipe.editor.Editor(None)
        await e.set_fill_column(5)
        e.last_command = 'self_insert'
        for c in 'sassafras ':
            e.self_insert(c)
        self.assertEqual('sassafras\n', str(e.buf))

    @snipe.imbroglio.test
    async def test_set_fill_column(self):
        response = '5'

        async def my_read_string(*args, **kw):
            nonlocal response
            return response

        e = snipe.editor.Editor(None)

        e.read_string = my_read_string
        self.assertNotEqual(5, e.fill_column)
        await e.set_fill_column()
        self.assertEqual(5, e.fill_column)

        response = 'plants'
        e.whine = unittest.mock.Mock()
        await e.set_fill_column()
        self.assertEqual(5, e.fill_column)
        e.whine.assert_called_with(
            "invalid literal for int() with base 10: 'plants'")

        e.insert('abcdef')
        await e.set_fill_column([])
        self.assertEqual(6, e.fill_column)

    def test_kill_to_end_of_line(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.insert('abcdef')
        e.move_backward(3)
        e.kill_to_end_of_line()
        self.assertEqual('abc', str(e.buf))
        e.kill_to_end_of_line()
        self.assertEqual('abc', str(e.buf))
        e.kill_to_end_of_line(0)
        self.assertEqual('', str(e.buf))
        e.insert_region('1\n2\n3\n4\n5\n6\n7\n8\n9\n')
        e.exchange_point_and_mark()
        e.kill_to_end_of_line(5)
        self.assertEqual('6\n7\n8\n9\n', str(e.buf))

    def test_kill_region(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.whine = unittest.mock.Mock()
        e.kill_region()
        e.whine.assert_called_with('no mark is set')
        e.insert('abcdef')
        e.cursor.point = 0
        e.set_mark()
        e.move_forward(3)
        e.kill_region()
        self.assertEqual('def', str(e.buf))
        e.move_forward(3)
        e.kill_region(append=True)
        self.assertEqual('', str(e.buf))
        self.assertEqual(e.context.kill_log, [('abc', None), ('def', True)])

    def test_yank(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.insert_region('foo')
        self.assertEqual('foo', str(e.buf))
        e.kill_region()
        self.assertEqual('', str(e.buf))
        e.yank()
        self.assertEqual('foo', str(e.buf))
        e.kill_region()
        self.assertEqual('', str(e.buf))
        e.insert_region('bar')
        self.assertEqual('bar', str(e.buf))
        e.kill_region()
        self.assertEqual('', str(e.buf))
        e.yank(2)
        self.assertEqual('foo', str(e.buf))
        self.assertEqual(3, e.cursor)
        self.assertEqual(0, e.the_mark)
        e.kill_region()
        e.yank([])
        self.assertEqual('foo', str(e.buf))
        self.assertEqual(0, e.cursor)
        self.assertEqual(3, e.the_mark)
        e.kill_region()
        e.yank()
        self.assertEqual('foo', str(e.buf))
        e.whine = unittest.mock.Mock()
        e.yank_pop()
        e.whine.assert_called()
        e.last_command = 'yank'
        e.yank_pop(2)
        self.assertEqual('bar', str(e.buf))

    def test_undo(self):
        e = snipe.editor.Editor(None)
        e.whine = unittest.mock.Mock()
        e.undo()
        self.assertEqual('', str(e.buf))
        e.whine.assert_called()
        e.insert('abc')
        e.insert('def')
        self.assertEqual('abcdef', str(e.buf))
        e.undo()
        self.assertEqual('abc', str(e.buf))
        e.last_command = 'undo'
        e.undo()
        self.assertEqual('', str(e.buf))
        e.insert('foo')
        e._writable = False
        e.whine = unittest.mock.Mock()
        e.undo()
        self.assertEqual('foo', str(e.buf))
        e.whine.assert_called()

    def test_transpose_chars(self):
        e = snipe.editor.Editor(None)
        e.whine = unittest.mock.Mock()
        e.transpose_chars()
        e.whine.assert_called()
        e.insert('ba')
        self.assertEqual('ba', str(e.buf))
        e.cursor.point = 1
        e.transpose_chars()
        self.assertEqual('ab', str(e.buf))
        self.assertEqual(2, e.cursor)

    def test_open_line(self):
        e = snipe.editor.Editor(None)
        e.open_line()
        self.assertEqual('\n', str(e.buf))
        self.assertEqual(0, e.cursor)

    def test_kill_word(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.insert('foo ')
        e.insert_region('bar')
        self.assertEqual('foo bar', str(e.buf))
        e.exchange_point_and_mark()
        e.kill_word_forward()
        self.assertEqual('foo ', str(e.buf))
        e.undo()
        e.cursor.point = 4
        e.kill_word_backward()
        self.assertEqual('bar', str(e.buf))

    @snipe.imbroglio.test
    async def test_insert_file(self):
        e = snipe.editor.Editor(None)
        e.read_filename = unittest.mock.Mock()
        e.read_filename.return_value = mocks.promise(__file__)
        await e.insert_file()
        self.assertEqual(
            '# -*- encoding: utf-8 -*-', str(e.buf).splitlines()[0])

    def test_quote_insert(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.quote_insert()
        e.input_char(chr(ord('P') - ord('@')))
        self.assertEqual(chr(ord('P') - ord('@')), str(e.buf))

    @snipe.imbroglio.test
    async def test_unicode_insert(self):
        e = snipe.editor.Editor(None)
        e.read_string = unittest.mock.Mock()
        e.read_string.return_value = mocks.promise(
            'LATIN CAPITAL LETTER A')
        await e.insert_unicode()
        self.assertEqual('A', str(e.buf))
        e.read_string.return_value = mocks.promise(
            '42')
        await e.insert_unicode()
        self.assertEqual('AB', str(e.buf))


class TestBuffer(unittest.TestCase):
    def testRegister(self):
        b = snipe.editor.Buffer(name='foo')
        self.assertEqual(b.name, 'foo')
        self.assertIs(snipe.editor.Buffer.registry['foo'], b)

        b = snipe.editor.Buffer(name='foo')
        self.assertEqual(b.name, 'foo[1]')
        self.assertIs(snipe.editor.Buffer.registry['foo[1]'], b)

        b = snipe.editor.Buffer(name='foo')
        self.assertEqual(b.name, 'foo[2]')
        self.assertIs(snipe.editor.Buffer.registry['foo[2]'], b)

        del b
        del snipe.editor.Buffer.registry['foo[2]']

        b = snipe.editor.Buffer(name='foo')
        self.assertEqual(b.name, 'foo[2]')
        self.assertIs(snipe.editor.Buffer.registry['foo[2]'], b)

        del snipe.editor.Buffer.registry['foo[1]']

        b = snipe.editor.Buffer(name='foo')
        self.assertEqual(b.name, 'foo[3]')
        self.assertIs(snipe.editor.Buffer.registry['foo[3]'], b)

        b.unregister()
        self.assertTrue(b.name not in b.registry)

    def test_Mark(self):
        b = snipe.editor.Buffer()
        m = b.mark(0)
        self.assertRegex(
            repr(m),
            r'^<Mark [0-9a-f]+ <GapMark [0-9a-f]+ \([0-9a-f]+\) 0 \(0\)>>$')
        self.assertTrue(m == 0)
        self.assertFalse(m == 1)
        self.assertFalse(m == 'dogs')
        self.assertTrue(m < 1)
        self.assertFalse(m < 0)

        self.assertEqual(b[:], '')
        m.insert('foo')
        self.assertEqual(b[:], 'foo')
        m.point = 0
        m.delete(3)
        self.assertEqual(b[:], '')

    def test_getitem(self):
        b = snipe.editor.Buffer()
        m = b.mark(0)
        TEXT = 'abcdef'
        m.insert(TEXT)

        self.assertEqual(b[:], TEXT)
        self.assertEqual(b[3], TEXT[3])
        self.assertEqual(b[-3], TEXT[-3])
        self.assertEqual(b[:-1], TEXT[:-1])
        self.assertEqual(b[:-2], TEXT[:-2])
        self.assertEqual(b[-1:], TEXT[-1:])
        self.assertEqual(b[-2:], TEXT[-2:])
        self.assertEqual(b[1:], TEXT[1:])
        self.assertEqual(b[2:], TEXT[2:])
        self.assertRaises(ValueError, lambda: b[::2])

    def test_undo(self):
        b = snipe.editor.Buffer()
        m = b.mark(0)
        TEXT = 'abcdef'
        m.insert(TEXT)
        self.assertEqual(b[:], TEXT)
        b.undo(None)
        self.assertEqual(b[:], '')

    def test__find_prop(self):
        b = snipe.editor.Buffer()

        b.props = [(0, 0)]

        self.assertEqual(b._find_prop(0), (0, 0, 0))
        self.assertEqual(b._find_prop(1), (0, 0, 0))

        b.props = [(1, 1), (3, 3)]

        self.assertEqual(b._find_prop(0), (-1, -1, {}))
        self.assertEqual(b._find_prop(1), (0, 1, 1))
        self.assertEqual(b._find_prop(2), (0, 1, 1))
        self.assertEqual(b._find_prop(3), (1, 3, 3))
        self.assertEqual(b._find_prop(4), (1, 3, 3))

        b.props = [(2, 1), (4, 3)]

        self.assertEqual(b._find_prop(0), (-1, -1, {}))
        self.assertEqual(b._find_prop(1), (-1, -1, {}))
        self.assertEqual(b._find_prop(2), (0, 2, 1))
        self.assertEqual(b._find_prop(3), (0, 2, 1))
        self.assertEqual(b._find_prop(4), (1, 4, 3))
        self.assertEqual(b._find_prop(5), (1, 4, 3))

    def test_replace_prop(self):
        b = snipe.editor.Buffer()
        TEXT = 'one two three'
        b.replace(0, 0, TEXT)
        self.assertEqual([({}, TEXT)], list(b.propter()))

        b.replace(4, 4, TEXT[4:8].upper(), prop={'name': 'value'})

        self.assertEqual(
            [
                ({}, TEXT[:4]),
                ({'name': 'value'}, TEXT[4:8].upper()),
                ({}, TEXT[8:]),
            ],
            list(b.propter()))

        b.replace(0, 1, TEXT[:1].upper(), prop={'name': 'value'})

        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:1].upper()),
                ({}, TEXT[1:4]),
                ({'name': 'value'}, TEXT[4:8].upper()),
                ({}, TEXT[8:]),
            ],
            list(b.propter()))

        b.replace(1, 3, TEXT[1:4].upper(), prop={'name': 'value'})

        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:8].upper()),
                ({}, TEXT[8:]),
            ],
            list(b.propter()))

        b.replace(8, 5, TEXT[8:].upper(), prop={'name': 'value'})

        self.assertEqual(
            [
                ({'name': 'value'}, TEXT.upper()),
            ],
            list(b.propter()))

        b.replace(b.mark(4), 1, TEXT[4], prop={})

        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:4].upper()),
                ({}, TEXT[4:5]),
                ({'name': 'value'}, TEXT[5:].upper()),
            ],
            list(b.propter()))

        b.replace(4, 1, TEXT[4].upper(), prop={'name': 'value'})
        self.assertEqual(
            [({'name': 'value'}, TEXT.upper())],
            list(b.propter()))

        b.replace(4, 0, '1.5 ', prop={})
        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:4].upper()),
                ({}, '1.5 '),
                ({'name': 'value'}, TEXT[4:].upper()),
            ],
            list(b.propter()))

        b.replace(4, 4, '')
        self.assertEqual(
            [({'name': 'value'}, TEXT.upper())],
            list(b.propter()))

        b.replace(4, 0, '1.5 ', prop={})
        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:4].upper()),
                ({}, '1.5 '),
                ({'name': 'value'}, TEXT[4:].upper()),
            ],
            list(b.propter()))

        b.replace(4, 2, '', prop={})
        self.assertEqual(
            [
                ({'name': 'value'}, TEXT[:4].upper()),
                ({}, '5 '),
                ({'name': 'value'}, TEXT[4:].upper()),
            ],
            list(b.propter()))

    def test_propter_offset(self):
        b = snipe.editor.Buffer()
        TEXT = 'one two three'
        b.replace(0, 0, TEXT)
        self.assertEqual([({}, TEXT)], list(b.propter()))

        b.replace(4, 4, TEXT[4:8].upper(), prop={'name': 'value'})

        self.assertEqual(
            [
                ({}, TEXT[:4]),
                ({'name': 'value'}, TEXT[4:8].upper()),
                ({}, TEXT[8:]),
            ],
            list(b.propter()))

        self.assertEqual(
            [
                ({}, TEXT[1:4]),
                ({'name': 'value'}, TEXT[4:8].upper()),
                ({}, TEXT[8:]),
            ],
            list(b.propter(1)))

    def test_propter_boundary(self):
        b = snipe.editor.Buffer()
        b.replace(0, 0, 'foo', prop={'key': 'value'})

        self.assertEqual([({'key': 'value'}, 'foo')], list(b.propter(0)))


class TestViewer(unittest.TestCase):
    def test_constructor_misc(self):
        e = snipe.editor.Viewer(None)
        e.renderer = mocks.Renderer()
        f = snipe.editor.Viewer(None, prototype=e)
        self.assertIs(e.buf, f.buf)
        e = snipe.editor.Viewer(None)
        e.renderer = mocks.Renderer()
        e.set_mark()
        self.assertIsNotNone(e.the_mark)
        f = snipe.editor.Viewer(None, prototype=e)
        self.assertIs(e.buf, f.buf)
        self.assertEqual(e.the_mark, f.the_mark)

    def test_misc(self):
        snipe.editor.Buffer.registry.clear()
        e = snipe.editor.Viewer(None, name='foo')
        self.assertEqual(e.title(), 'foo')

        self.assertTrue(e.check_redisplay_hint(e.redisplay_hint()))
        self.assertFalse(e.check_redisplay_hint({}))

        e.renderer = mocks.Renderer()
        f = snipe.editor.Viewer(None, prototype=e)
        self.assertTrue(e.check_redisplay_hint(f.redisplay_hint()))

    def test_line_movement(self):
        e = snipe.editor.Viewer(None)
        e.insert('abc\ndef\nghi\nklm\nnop\nqrs\ntuv\nwxyz')
        e.cursor.point = 0
        e.line_next()
        self.assertEqual(e.cursor.point, 4)
        e.line_previous()
        self.assertEqual(e.cursor.point, 0)
        e.line_next(6)
        self.assertEqual(e.cursor.point, 24)
        e.line_next()
        self.assertEqual(e.cursor.point, 28)
        e.line_next()
        self.assertEqual(e.cursor.point, 28)

    def test_prototype(self):
        with mocks.mocked_up_actual_fe_window(snipe.editor.Viewer) as w:
            w.split_window()
            for x in w.fe.windows:
                self.assertIs(w.buf, x.window.buf)

    def test_toggle_writable(self):
        e = snipe.editor.Editor(None)
        self.assertTrue(e._writable)
        e.toggle_writable()
        self.assertFalse(e._writable)
        e.toggle_writable()
        self.assertTrue(e._writable)

    def test_beginning_end_of_line(self):
        e = snipe.editor.Editor(None)
        e.insert('abc\ndef\nghi\nklm\nnop\nqrs\ntuv\nwxyz')
        e.cursor.point = 0
        e.end_of_line()
        self.assertEqual(e.cursor.point, 3)
        e.beginning_of_line()
        self.assertEqual(e.cursor.point, 0)
        e.end_of_line(2)
        self.assertEqual(e.cursor.point, 7)
        e.beginning_of_line()
        self.assertEqual(e.cursor.point, 4)
        e.end_of_line()
        self.assertEqual(e.cursor.point, 7)
        e.beginning_of_line()
        self.assertEqual(e.cursor.point, 4)
        e.beginning_of_line(2)
        self.assertEqual(e.cursor.point, 8)

    def test_beginning_end_of_buffer_0(self):
        e = snipe.editor.Editor(None)
        e.insert('abc')
        e.cursor.point = 0
        self.assertEqual(3, e.end_of_buffer())
        self.assertEqual(e.cursor.point, 3)
        self.assertEqual(-3, e.beginning_of_buffer())
        self.assertEqual(e.cursor.point, 0)

    def test_beginning_end_of_buffer_1(self):
        e = snipe.editor.Editor(None)
        e.insert('\n' * 10)
        e.beginning_of_buffer(3)
        self.assertEqual(e.cursor.point, 3)
        self.assertEqual(e.the_mark.point, 10)
        e.end_of_buffer(3)
        self.assertEqual(e.cursor.point, 7)
        self.assertEqual(e.the_mark.point, 3)
        e.end_of_buffer(-3)
        self.assertEqual(e.cursor.point, 3)
        self.assertEqual(e.the_mark.point, 7)
        e.beginning_of_buffer(-3)
        self.assertEqual(e.cursor.point, 7)
        self.assertEqual(e.the_mark.point, 3)

    def test_input_char(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.input_char('x')
        self.assertEqual(str(e.buf), 'x')

    def test_word_forward_backward(self):
        e = snipe.editor.Editor(None)
        e.insert('abc def ghi\nhij klm nop\n')
        e.cursor.point = 0
        e.word_forward()
        self.assertEqual(e.cursor.point, 3)
        e.word_forward(-1)
        self.assertEqual(e.cursor.point, 0)
        e.word_forward(4)
        self.assertEqual(e.cursor.point, 15)
        e.word_backward(3)
        self.assertEqual(e.cursor.point, 4)
        e.word_backward(-1)
        self.assertEqual(e.cursor.point, 7)
        e.word_forward(9000)
        self.assertEqual(e.cursor.point, len(e.buf))
        x = len(e.buf)
        e.insert('q')
        e.insert('rs', prop={'navigable': False})
        self.assertEqual(e.cursor.point, len(e.buf))
        e.word_backward(9000)
        self.assertEqual(e.cursor.point, 0)
        e.word_forward(9000, interactive=True)
        self.assertEqual(e.cursor.point, x)
        e.word_backward(9000)
        self.assertEqual(e.cursor.point, 0)
        e.insert('0', prop={'navigable': False})
        e.word_backward(interactive=True)
        self.assertEqual(e.cursor.point, 1)

    def test_region_yank(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()

        self.assertIsNone(e.region())

        TEXT = 'abc def ghi'
        e.insert(TEXT)
        e.cursor.point = 0

        self.assertIsNone(e.the_mark)
        e.copy_region()
        self.assertIn('notify', e.fe.called)

        e.end_of_buffer()
        self.assertEqual(e.region(), TEXT)
        e.copy_region()
        self.assertEqual(e.context.kill_log[-1], (TEXT, None))

    def test_mark_region(self):
        e = snipe.editor.Editor(None)
        e.insert('abc def ghi')
        e.cursor.point = 4
        e.set_mark()
        e.cursor.point = 7
        self.assertEqual(e.region(), 'def')
        e.set_mark(prefix=['x'])
        self.assertEqual(e.cursor.point, 4)
        self.assertEqual(e.region(), 'def')
        e.set_mark(prefix=['x'])
        self.assertEqual(e.cursor.point, 7)

    def test_make_go_mark(self):
        e = snipe.editor.Editor(None)
        m = e.make_mark(0)

        self.assertEqual(m, e.cursor)
        self.assertIsNot(m, e.cursor)

        e.insert('foo')

        self.assertNotEqual(m, e.cursor)
        e.go_mark(m)
        self.assertEqual(m, e.cursor)

    def test_insert_region(self):
        e = snipe.editor.Editor(None)
        e.insert('foo')

        self.assertEqual('foo', str(e.buf))
        e.insert_region('bar')
        self.assertEqual('foobar', str(e.buf))
        self.assertEqual('bar', e.region())

    def test_exchange_point_and_mark(self):
        e = snipe.editor.Editor(None)
        e.insert_region('foo')
        self.assertEqual(3, int(e.cursor))
        self.assertEqual(0, int(e.the_mark))

        e.exchange_point_and_mark()
        self.assertEqual(0, int(e.cursor))
        self.assertEqual(3, int(e.the_mark))

    def test_evaller_0(self):
        e = snipe.editor.Editor(None)
        e.insert_region('print(2 + 2)')
        e.exec_region(arg=['x'])
        self.assertEqual('print(2 + 2)\n4\n', str(e.buf))

    def test_evaller_1(self):
        e = snipe.editor.Editor(None)
        e.set_mark()
        e.insert('2 + 2')
        self.assertEqual('2 + 2', str(e.buf))
        e.eval_region(arg=['x'])
        self.assertEqual('2 + 2\n4\n', str(e.buf))
        e.set_mark()
        e.insert('#foo')
        e.eval_region(arg=['x'])
        self.assertEqual('2 + 2\n4\n#foo', str(e.buf))

    def test_evaller_2(self):
        e = snipe.editor.Editor(None)
        e.fe = mocks.FE()
        e.set_mark()
        e.insert('if True:\n')
        self.assertEqual('if True:\n', str(e.buf))
        e.eval_region(arg=['x'])
        self.assertIn('notify', e.fe.called)
        self.assertEqual('if True:\n', str(e.buf))

    def test_evaller_3(self):
        with unittest.mock.patch('snipe.editor.Editor.show'):
            e = snipe.editor.Editor(None)
            e.insert_region('print(2 + 2)')
            e.exec_buffer(None)
            e.show.assert_called()
            e.show.assert_called_with('4\n')
            self.assertEqual('print(2 + 2)', str(e.buf))

    def test_evaller_4(self):
        with unittest.mock.patch('snipe.editor.Editor.show'):
            e = snipe.editor.Editor(None)
            e.set_mark()
            self.assertEqual('', str(e.buf))
            e.exec_buffer(None)
            e.show.assert_not_called()
            self.assertEqual('', str(e.buf))

    def test_movable(self):
        e = snipe.editor.Viewer(None)
        e.insert('abc\n')
        e.insert('def\n', prop={'navigable': False})
        e.insert('ghi\n')
        self.assertEqual('def\n', e.buf[4:8])
        self.assertEqual(e.movable(5, True), 8)
        e.cursor.point = 0
        self.assertEqual(e.movable(5, True), 3)


class TestPopViewer(unittest.TestCase):
    def test(self):
        fe = mocks.FE()
        v = snipe.editor.PopViewer(fe, content='', name='test')
        v.renderer = mocks.Renderer()
        v.renderer._range = [0, 0]
        self.assertEqual(
            (([(set(), '- test')]), ([({'right'}, '1')])), v.modeline())
        name = v.buf.name
        self.assertIn(name, v.buf.registry)
        v.destroy()
        self.assertNotIn(name, v.buf.registry)


class TestMisc(unittest.TestCase):
    def test_isspace(self):
        self.assertEqual(True, snipe.editor.isspace(' '))
        self.assertEqual(False, snipe.editor.isspace('X'))
        self.assertEqual(False, snipe.editor.isspace(None))


if __name__ == '__main__':
    unittest.main()
