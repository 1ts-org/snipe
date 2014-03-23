'''
Unit tests for the Editor object
'''

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
    def testNview(self):
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
            list(e.Nview(0, 'pants'))
        c = e.cursor.point
        forward = [(int(m), l) for (m, l) in e.Nview(0, 'forward')]
        self.assertEqual(e.cursor.point, c)
        backward = [(int(m), l) for (m, l) in e.Nview(e.size, 'backward')]
        self.assertEqual(e.cursor.point, c)
        self.assertEquals(len(forward), 257)
        self.assertEquals(forward, list(reversed(backward)))
        self.assertEquals(backward[0], (e.size, u''))
        for (i, s) in enumerate(lines):
            self.assertEquals(forward[i][1], lines[i])
        self.assertEquals(len(forward), 257)


if __name__ == '__main__':
    unittest.main()
