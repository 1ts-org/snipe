'''
Unit tests for various context-related things
'''


import unittest
import sys
import curses

sys.path.append('..')
import snipe.context


class TestKeymap(unittest.TestCase):
    def testkeyseq_re(self):
        self.assertFalse(snipe.context.Keymap.keyseq_re.match('frob'))
        s = 'control-Shift-META-hyper-SUPER-aLT-ctl-[LATIN CAPITAL LETTER A]'
        m = snipe.context.Keymap.keyseq_re.match(s)
        self.assertTrue(m, msg='Keymap.keyseq_re.match(' + s + ')')
        d = m.groupdict()
        self.assertEqual(
            m.groupdict(),
            {
                'char': None,
                'modifiers': 'control-Shift-META-hyper-SUPER-aLT-ctl-',
                'name': 'LATIN CAPITAL LETTER A',
                'rest': None,
                })

    def testsplit(self):
        split = snipe.context.Keymap.split

        with self.assertRaises(TypeError):
            split('frob')

        with self.assertRaises(TypeError):
            split('[IPHONE 5C WITH DECORATIVE CASE]')

        self.assertEqual(split('Hyper-[latin capital letter a]'), (None, None))
        self.assertEqual(split('Meta-[escape]'), ('\x1b', '[ESCAPE]'))
        self.assertEqual(split('Control-C Control-D'), ('\x03', 'Control-D'))
        self.assertEqual(split('[latin capital letter a]'), ('A', None))
        self.assertEqual(split('Shift-a'), ('A', None))
        self.assertEqual(split('[F1]'), (curses.KEY_F1, None))
        self.assertEqual(split('Control-[F1]'), (None, None)) #XXX
        self.assertEqual(split('Shift-[F1]'), (None, None)) #XXX
        self.assertEqual(split('Control-?'), ('\x7f', None))
        self.assertEqual(split('Control-$'), (None, None))
        self.assertEqual(
            split('Meta-Control-x'),
            ('\x1b', 'Control-[LATIN CAPITAL LETTER X]'))
        self.assertEqual(
            split('Meta-[escape] oogledyboo'),
            ('\x1b', '[ESCAPE] oogledyboo'))
        self.assertEqual(
            split('Control-C Control-D oogledyboo'),
            ('\x03', 'Control-D oogledyboo'))
        self.assertEqual(split(-5), (-5, None))

    def testdict(self):
        k = snipe.context.Keymap()
        k['a b'] = 1
        self.assertEqual(k['a b'], 1)
        l = snipe.context.Keymap(k)
        self.assertEqual(k['a b'], 1)
        self.assertIsNot(k, l)
        self.assertIsNot(k['a'], l['a'])
        del k['a b']
        with self.assertRaises(KeyError):
            k['c']
        k['c'] = 2
        with self.assertRaises(KeyError):
            k['c d'] = 3
        k['\n'] = 4
        self.assertEqual(k['\n'], 4)
        del k['\n']
        with self.assertRaises(KeyError):
            k['\n']


if __name__ == '__main__':
    unittest.main()
