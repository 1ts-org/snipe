#!/usr/bin/python3
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
Unit tests for various filter-related things
'''

import sys
import unittest

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.filters                                           # noqa: E402
from snipe.filters import (
    And, Compare, Identifier, Lexer, No, Parser, RECompare,
    SnipeFilterError, Yes, makefilter,
    )                                                          # noqa: E402


class TestFilters(unittest.TestCase):
    def testLexer(self):
        lexer = Lexer()
        self.assertEqual(
            list(lexeme.type for lexeme in lexer.test(
                '= == != < <= > >= 17')),
            ['EQ', 'EQEQ', 'NE', 'LT', 'LTE', 'GT', 'GTE', 'NUMBER'])
        self.assertEqual(
            list(lexeme.type for lexeme in lexer.test(
                '"EXTERMINATE" /ALL/ $"HUMANS" IMMEDIATELY')),
            ['STRING', 'REGEXP', 'PYTHON', 'ID'])
        self.assertEqual(
            list(lexeme.type for lexeme in lexer.test(
                'filter yes no ( )')),
            ['FILTER', 'YES', 'NO', 'LPAREN', 'RPAREN'])
        self.assertEqual(
            list(lexeme.type for lexeme in lexer.test(
                'and or xor not')),
            ['AND', 'OR', 'XOR', 'NOT'])
        self.assertRaises(
            SnipeFilterError,
            lambda: list(lexer.test("'foo'")))

        self.assertEqual(
            next(snipe.filters.lexer.test(r'"foo\\\"bar"')).value,
            'foo\\"bar')

    def testParser(self):
        snipe.filters.parser = Parser(debug=True)
        self.assertEqual(
            makefilter('yes'),
            Yes())
        self.assertEqual(
            makefilter('yes and no'),
            And(Yes(), No()))
        self.assertEqual(
            makefilter('foo = "bar"'),
            Compare('=', 'foo', 'bar'))
        self.assertEqual(
            makefilter('"bar" = foo'),
            Compare('=', 'foo', 'bar'))
        self.assertEqual(
            makefilter('foo = bar'),
            Compare('=', 'foo', Identifier('bar')))
        self.assertEqual(
            makefilter('foo = /bar/'),
            RECompare('=', 'foo', 'bar'))
        self.assertEqual(
            makefilter('/bar/ = foo'),
            RECompare('=', 'foo', 'bar'))
        self.assertEqual(
            makefilter('1 = 1'),
            Yes())
        self.assertEqual(
            makefilter('1 = 2'),
            No())
        self.assertEqual(
            makefilter('"foo" = /foo/'),
            Yes())
        self.assertEqual(
            makefilter('"foo" = /bar/'),
            No())

        self.assertTrue(makefilter('foo = "bar"')(mocks.Message(foo='bar')))
        self.assertFalse(makefilter('foo = "bar"')(mocks.Message(foo='baz')))

        self.assertTrue(makefilter('foo = /b.*/')(mocks.Message(foo='bar')))
        self.assertTrue(makefilter('foo = /b.*/')(mocks.Message(foo='baz')))
        self.assertFalse(makefilter('foo = /b.*/')(mocks.Message(foo='quux')))

        self.assertTrue(
            makefilter('foo = bar')(mocks.Message(
                foo='quux',
                bar='quux')))

        self.assertFalse(
            makefilter('foo = bar')(mocks.Message(
                foo='quux',
                bar='quuux')))

        self.assertTrue(
            makefilter('foo = "bar"')(mocks.Message(
                foo='Bar',
                Foo='bar',
                )))
        self.assertFalse(
            makefilter('not foo = "bar"')(mocks.Message(
                foo='Bar',
                Foo='bar',
                )))
        self.assertFalse(
            makefilter('foo == "bar"')(mocks.Message(
                foo='Bar',
                Foo='bar',
                )))
        self.assertTrue(
            makefilter('foo = /bar/')(mocks.Message(
                foo='Bar',
                Foo='bar',
                )))
        self.assertFalse(
            makefilter('foo == /bar/')(mocks.Message(
                foo='Bar',
                Foo='bar',
                )))

        self.assertEqual(
            str(makefilter('foo == "bar"')),
            'foo == "bar"')
        self.assertEqual(
            str(makefilter('"bar" == foo')),
            'foo == "bar"')

        self.assertEqual(
            str(makefilter('yes and yes and yes')),
            'yes and yes and yes')

        self.assertEqual(
            str(makefilter('no and yes and yes')),
            'no and yes and yes')

        self.assertEqual(
            str(makefilter('yes and no and yes')),
            'yes and no and yes')

        self.assertEqual(
            str(makefilter('yes and yes and no')),
            'yes and yes and no')

        self.assertTrue(makefilter('foo')(mocks.Message(foo=True)))
        self.assertFalse(makefilter('foo')(mocks.Message(foo=0)))
        self.assertFalse(makefilter('foo')(mocks.Message(foo=0)))

        self.assertIs(makefilter(''), None)

        self.assertFalse(makefilter('filter foo')(mocks.Message()))

    def test_parser_python(self):
        snipe.filters.parser = Parser(debug=True)
        self.assertEqual(
            str(makefilter("$'True'")),
            "$'True'")
        self.assertEqual(
            str(makefilter('$"True"')),
            "$'True'")
        self.assertEqual(
            str(makefilter('$"True"')),
            "$'True'")
        self.assertEqual(
            str(makefilter('$"True or \'flase\'"')),
            "$\"True or 'flase'\"")


if __name__ == '__main__':
    unittest.main()
