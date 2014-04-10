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

        with self.assertRaises(KeyError):
            split('frob')

        with self.assertRaises(KeyError):
            split('[IPHONE 5C WITH DECORATIVE CASE]')

        self.assertEquals(split('Hyper-[latin capital letter a]'), (None, None))
        self.assertEquals(split('Meta-[escape]'), ('\x1b', '[ESCAPE]'))
        self.assertEquals(split('Control-C Control-D'), ('\x03', 'Control-D'))
        self.assertEquals(split('[latin capital letter a]'), ('A', None))
        self.assertEquals(split('Shift-a'), ('A', None))
        self.assertEquals(split('[F1]'), (curses.KEY_F1, None))
        self.assertEquals(split('Control-[F1]'), (None, None)) #XXX
        self.assertEquals(split('Shift-[F1]'), (None, None)) #XXX
        self.assertEquals(split('Control-?'), ('\x7f', None))
        self.assertEquals(split('Control-$'), (None, None))
        self.assertEquals(
            split('Meta-Control-x'),
            ('\x1b', 'Control-[LATIN CAPITAL LETTER X]'))
        self.assertEquals(
            split('Meta-[escape] oogledyboo'),
            ('\x1b', '[ESCAPE] oogledyboo'))
        self.assertEquals(
            split('Control-C Control-D oogledyboo'),
            ('\x03', 'Control-D oogledyboo'))
        self.assertEquals(split(-5), (-5, None))

