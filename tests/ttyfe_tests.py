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
            list(snipe.ttyfe.TTYRenderer.doline('abc', 80, 80)),
            [('abc', 77)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline("\tabc", 80, 0)),
            [('        abc', 69)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abc\n', 80, 80)),
            [('abc', -1)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('a\01bc', 80, 80)),
            [('abc', 77)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('abcdef', 3, 3)),
            [('abc', 0), ('def', 0)])
        self.assertEqual(
            list(snipe.ttyfe.TTYRenderer.doline('ab\tdef', 3, 3)),
            [('ab', 0), ('def', 0)])


if __name__ == '__main__':
    unittest.main()
