"""
Unit tests for the TTY frontend objects

(hard because we haven't mocked curses yet.)
"""

import sys
import unittest

sys.path.append('..')
import snipe.ttyfe


class TestTTYFE(unittest.TestCase):
    def testTTYRendererDoline(self):
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abc', 80)),
            [('abc', 3)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline("\tabc", 80)),
            [('        abc', 11)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abc\n', 80)),
            [('abc\n', 3)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('a\01bc', 80)),
            [('abc', 3)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abcdef', 3)),
            [('abc', 3), ('def', 3)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('ab\tdef', 3)),
            [('ab', 2), ('def', 3)])


if __name__ == '__main__':
    unittest.main()
