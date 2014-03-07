'''
Unit tests for the Editor object
'''

import sys
import unittest

sys.path.append('..')
import snipe.editor

class TestEditor(unittest.TestCase):
    def testEditorSimple(self):
        e = snipe.editor.Editor(None)
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
        e.insert('flam')
        self.assertEqual(e.cursor.point, 4)
        e.cursor.point = 0
        e.insert('flim')
        self.assertEqual(e.text, 'flimflam')
        e.cursor.point += 4
        e.insert('blam')
        self.assertEqual(e.text, 'flimflamblam')

if __name__ == '__main__':
    unittest.main()
