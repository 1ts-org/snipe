'''
Unit tests for the Editor object
'''

import array
import random
import sys
import unittest
import itertools

sys.path.append('..')
import snipe.editor


class TestEditor(unittest.TestCase):
    def testEditorSimple(self):
        e = snipe.editor.Editor(None)
        e.set_content('')
        e.insert('flam')
        self.assertEqual(e.cursor.point, 4)
        e.cursor.point = 0
        e.insert('flim')
        self.assertEqual(e.text, 'flimflam')
        e.cursor.point += 4
        e.insert('blam')
        self.assertEqual(e.text, 'flimflamblam')
    def testEditorExpansion(self):
        e = snipe.editor.Editor(None, chunksize=1)
        e.set_content('')
        e.insert('flam')
        self.assertEqual(e.cursor.point, 4)
        e.cursor.point = 0
        e.insert('flim')
        self.assertEqual(e.text, 'flimflam')
        e.cursor.point += 4
        e.insert('blam')
        self.assertEqual(e.text, 'flimflamblam')
    def testEditorMore(self):
        e = snipe.editor.Editor(None)
        e.set_content('')
        e.insert('bar')
        self.assertEquals(e.text, 'bar')
        self.assertEquals(e.size, 3)
        m = snipe.editor.Mark(e, 1)
        self.assertEquals(m.point, 1)
        e.cursor.point = 0
        e.insert('foo')
        self.assertEquals(e.text, 'foobar')
        self.assertEquals(m.point, 4)
        e.cursor.point=6
        e.insert('baz')
        self.assertEquals(e.text, 'foobarbaz')
        self.assertEquals(m.point, 4)
        e.cursor.point=6
        e.insert('quux')
        self.assertEquals(e.text, 'foobarquuxbaz')
        self.assertEquals(m.point, 4)
        e.cursor.point=3
        e.insert('Q'*8192)
        self.assertEquals(e.text, 'foo' + 'Q'*8192 + 'barquuxbaz')
        self.assertEquals(m.point, 8196)
        e.cursor.point=3
        e.delete(8192)
        self.assertEquals(e.cursor.point, 3)
        self.assertEquals(e.text, 'foobarquuxbaz')
        self.assertEquals(e.size, 13)
        self.assertEquals(m.point, 4)
        e.cursor.point=3
        e.replace(3, 'honk')
        self.assertEquals(e.text, 'foohonkquuxbaz')
        self.assertEquals(m.point, 7)
        e.cursor.point=4
        e.replace(1, 'u')
        self.assertEquals(e.text[4], 'u')
        e.cursor.point=4
        e.delete(1)
        self.assertEquals(e.text, 'foohnkquuxbaz')
        e.cursor.point=3
        e.delete(3)
        self.assertEquals(e.text, 'fooquuxbaz')
    def testFindchar(self):
        e = snipe.editor.Editor(None)
        e.set_content('')
        e.insert('abcdefghji')
        e.cursor.point = 0
        self.assertEquals(e.find_character('c'), 'c')
        self.assertEquals(e.cursor.point, 2)
        self.assertEquals(e.find_character('a', 1), '')
        self.assertEquals(e.cursor.point, 10)
        self.assertEquals(e.find_character('a', -1), 'a')
        self.assertEquals(e.cursor.point, 0)
        self.assertEquals(e.find_character('z', -1), '')
        self.assertEquals(e.cursor.point, 0)
        self.assertEquals(e.find_character('c'), 'c')
        self.assertEquals(e.cursor.point, 2)
    def testview(self):
        e = snipe.editor.Editor(None)
        e.set_content('')
        lines = [
            ''.join(itertools.islice(
                itertools.cycle(
                    [chr(x) for x in range(ord('A'), ord('Z') + 1)] +
                    [chr(x) for x in range(ord('0'), ord('9') + 1)]),
                i,
                i + 72))+'\n'
            for i in xrange(256)]
        e.insert(''.join(lines))
        with self.assertRaises(ValueError):
            list(e.view(0, 'pants'))
        c = e.cursor.point
        forward = [(int(m), l) for (m, l) in e.view(0, 'forward')]
        self.assertEqual(e.cursor.point, c)
        backward = [(int(m), l) for (m, l) in e.view(e.size, 'backward')]
        self.assertEqual(e.cursor.point, c)
        self.assertEquals(len(forward), 257)
        self.assertEquals(forward, list(reversed(backward)))
        self.assertEquals(
            backward[0],
            (e.size, [((), u''), (('cursor', 'visible'), u'')]))
        self.assertEquals(len(forward), 257)
        c = e.cursor.point
        it = iter(e.view(0, 'forward'))
        it.next()
        self.assertEquals(e.cursor.point, c)
        it.next()
        self.assertEquals(e.cursor.point, c)
        it = iter(e.view(e.size, 'backward'))
        it.next()
        self.assertEquals(e.cursor.point, c)
        it.next()
        self.assertEquals(e.cursor.point, c)
    def testviewedge(self):
        e = snipe.editor.Editor(None)
        e.set_content('')
        e.insert('abc')
        self.assertEqual(
            [(int(m), l) for (m, l) in e.view(0, 'forward')],
            [(0, [((), u'abc'), (('cursor', 'visible'), u'')])])
    def testfuzz(
        self,
        iterations=10000,
        max_len=74,
        max_op_len=10,
        show_delay=0.01,
        ):
        """
        For many <iterations> randomly either insert or delete up to
        <max_op_len> chars or just move the gap around.

        Make sure the entire thing is never more than max_len chars long.

        Make a parallel array and confirm after each operation that
        the gap buffer's contents are the same as the array's.

        If show_delay is > 0, then the gap buffer will be shown each
        iteration.  If it's 0 then nothign will display during
        iteration, but the operations will be dumped after all
        iterations.
        """

        contents = (
            u'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

        g = snipe.editor.Editor(None)
        g.set_content(u'')
        a = array.array('u')
        for n in range(iterations):
            pos = g.size and random.randint(0, g.size-1)
            # A 1 in 3 chance to delete, unless we're at max length,
            # then delete regardless
            if not random.randint(0, 2) or g.size >= max_len:
                howmany = min(g.size - pos, random.randint(1, max_op_len))
                g.cursor.point = pos
                g.delete(howmany)
                for d in range(howmany):
                    a.pop(pos)
            else:
                g.cursor.point = pos
                # A 1 in 2 chance to insert instead of just moving th gap
                if not random.randint(0, 1):
                    howmany = random.randint(
                        1, max(max_op_len, max_len - g.size))
                    char = random.choice(contents)
                    g.insert(char * howmany)
                    for i in range(howmany):
                        a.insert(pos, char)
            self.assertEqual(a.tounicode(), g.text)
            print g.text


if __name__ == '__main__':
    unittest.main()
