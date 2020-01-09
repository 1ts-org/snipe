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

import re
import unittest

import mocks

import snipe.filters

from snipe.filters import (
    And, Compare, Identifier, Lexer, No, Not, Or, Parser, RECompare,
    SnipeFilterError, Truth, Yes, Xor, makefilter,
    )


class TestFilters(unittest.TestCase):
    def test_Lexer(self):
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

    def test_Parser(self):
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
            makefilter('foo < "bar"'),
            Compare('<', 'foo', 'bar'))
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
        self.assertEqual(
            makefilter('"Foo" = /foo/i'),
            Yes())
        self.assertEqual(
            makefilter('"Foo" != /foo/i'),
            No())
        self.assertEqual(
            makefilter('(yes or no) and yes'),
            And(Or(Yes(), No()), Yes()))
        self.assertEqual(
            makefilter('yes xor no'),
            Xor(Yes(), No()))

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
        self.assertFalse(
            makefilter('foo == /bar[/')(mocks.Message(
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

    def test_Filter(self):
        f = snipe.filters.Filter()
        self.assertRaises(NotImplementedError, lambda: f._check(None))
        self.assertIs(f, f.simplify({}))
        self.assertEqual(repr(f), 'Filter()')

    def test_Certitude(self):
        yes = Yes()
        no = No()
        self.assertTrue(yes._check(None))
        self.assertTrue(yes.simplify({}))
        self.assertFalse(no._check(None))
        self.assertFalse(no.simplify({}))
        self.assertEqual(hash(Yes()), hash(yes))
        self.assertEqual(hash(No()), hash(no))
        self.assertNotEqual(hash(yes), hash(no))

    def test_Not(self):
        self.assertEqual(str(Not(Yes())), 'not yes')
        self.assertEqual(repr(Not(Yes())), 'Not(Yes())')
        self.assertEqual(Not(Yes()), Not(Yes()))
        self.assertNotEqual(Not(Yes()), Not(No()))
        self.assertEqual(hash(Not(Yes())), hash(Not(Yes())))
        self.assertNotEqual(hash(Not(Yes())), hash(Not(No())))
        self.assertTrue(Not(No()).simplify({}))
        self.assertFalse(
            makefilter('not foo == "bar"').simplify({'foo': 'bar'}))
        self.assertEqual(
            makefilter('not foo == "bar"').simplify({}),
            Not(Compare('==', 'foo', 'bar')))
        self.assertEqual(str(Not(And(Yes(), No()))), 'not (yes and no)')

    def test_Truth(self):
        self.assertEqual(str(Truth('foo')), 'foo')
        self.assertEqual(repr(Truth('foo')), "Truth('foo')")
        self.assertEqual(Truth('foo'), Truth('foo'))
        self.assertNotEqual(hash(Truth('foo')), hash(Truth('bar')))
        self.assertEqual(hash(Truth('foo')), hash(Truth('foo')))

    def test_And(self):
        self.assertEqual(repr(And(None, Yes(), No())), 'And(Yes(), No())')
        self.assertTrue(And(Yes(), Yes())._check(None))
        self.assertFalse(And(Yes(), No())._check(None))
        self.assertTrue(And(Yes(), Yes()).simplify({}))
        self.assertFalse(And(Yes(), No()).simplify({}))
        self.assertFalse(And(Truth('foo'), No()).simplify({}))
        self.assertEqual(And(Yes(), Truth('foo')).simplify({}), Truth('foo'))
        self.assertEqual(
            And(Yes(), Truth('foo'), Truth('bar')).simplify({}),
            And(Truth('foo'), Truth('bar')).simplify({}))
        self.assertTrue(And().simplify(None))
        self.assertEqual(hash(And(Yes(), No())), hash(And(Yes(), No())))

    def test_Or(self):
        self.assertEqual(repr(Or(None, Yes(), No())), 'Or(Yes(), No())')
        self.assertTrue(Or(Yes(), Yes())._check(None))
        self.assertTrue(Or(Yes(), No())._check(None))
        self.assertFalse(Or(No(), No())._check(None))
        self.assertTrue(Or(Yes(), Yes()).simplify({}))
        self.assertTrue(Or(Yes(), No()).simplify({}))
        self.assertTrue(Or(Yes(), Truth('foo')).simplify({}))
        self.assertEqual(Or(Truth('foo'), No()).simplify({}), Truth('foo'))
        self.assertEqual(
            Or(No(), Truth('foo'), Truth('bar')).simplify({}),
            Or(Truth('foo'), Truth('bar')).simplify({}))
        self.assertFalse(Or().simplify(None))

    def test_Xor(self):
        self.assertTrue(
            snipe.filters.Xor(No(), No(), Yes())._check(None))
        self.assertFalse(
            snipe.filters.Xor(No(), No(), No())._check(None))
        self.assertFalse(
            snipe.filters.Xor(No(), Yes(), Yes())._check(None))

    def test_Python(self):
        self.assertTrue(snipe.filters.Python('True')._check(None))
        self.assertFalse(snipe.filters.Python('something wrong')._check(None))
        self.assertEqual(
            snipe.filters.Python('True'), snipe.filters.Python('True'))
        self.assertNotEqual(
            snipe.filters.Python('True'), snipe.filters.Python('False'))
        self.assertNotEqual(
            hash(snipe.filters.Python('True')),
            hash(snipe.filters.Python('False')))
        self.assertEqual(
            hash(snipe.filters.Python('True')),
            hash(snipe.filters.Python('True')))
        self.assertEqual(
            repr(snipe.filters.Python('True')), "Python('True')")

    def test_FilterLookup(self):
        self.assertEqual(
            snipe.filters.FilterLookup('foo'),
            snipe.filters.FilterLookup('foo'))
        self.assertEqual(
            hash(snipe.filters.FilterLookup('foo')),
            hash(snipe.filters.FilterLookup('foo')))
        self.assertNotEqual(
            snipe.filters.FilterLookup('foo'),
            snipe.filters.FilterLookup('bar'))
        self.assertNotEqual(
            hash(snipe.filters.FilterLookup('foo')),
            hash(snipe.filters.FilterLookup('bar')))
        m = mocks.Message()
        self.assertFalse(
            snipe.filters.FilterLookup('default')(m))
        m.conf['filter'] = {'default': 'yes'}
        self.assertTrue(
            snipe.filters.FilterLookup('default')(m))
        # naughty
        m.conf['filter']['self_reference'] = 'filter self_reference'
        self.assertFalse(
            snipe.filters.FilterLookup('self_reference')(m))
        m.conf['filter']['bad'] = '== == =='
        self.assertFalse(
            snipe.filters.FilterLookup('bad')(m))

        self.assertFalse(
            snipe.filters.FilterLookup('nonexistent').simplify({'context': m}))
        self.assertFalse(
            snipe.filters.FilterLookup(
                'self_reference').simplify({'context': m}))

        m.conf['filter']['wrong'] = 'and and and nope'
        self.assertFalse(
            snipe.filters.FilterLookup('wrong').simplify({'context': m}))
        self.assertEqual(
            repr(snipe.filters.FilterLookup('foo')), "FilterLookup('foo')")
        self.assertEqual(
            str(snipe.filters.FilterLookup('foo')), 'filter foo')

    def test_validate(self):
        self.assertTrue(snipe.filters.validatefilter('yes'))
        self.assertFalse(snipe.filters.validatefilter('and and and nope'))

    def test_misc(self):
        self.assertEqual(
            repr(Compare('=', 'foo', 'bar')), "Compare('=', 'foo', 'bar')")
        self.assertEqual(
            hash(Compare('=', 'foo', 'bar')), hash(Compare('=', 'foo', 'bar')))
        self.assertEqual(
            str(Compare('=', 'foo', 'bar')), 'foo = "bar"')
        self.assertEqual(
            str(Compare('=', 'foo', Identifier('bar'))), 'foo = bar')
        self.assertEqual(
            str(Compare('=', 'foo', 5)), 'foo = 5')

        self.assertEqual(
            repr(Identifier('bar')), "Identifier('bar')")

        self.assertFalse(Compare.do('<=', 15, 'pants'))

        self.assertEqual(RECompare.deflag('s'), re.DOTALL)
        self.assertEqual(RECompare.deflag('7'), 0)
        self.assertEqual(RECompare.static('==', '[', ''), No())

        self.assertEqual(
            str(RECompare('=', 'key', 'value', flags='i')), 'key = /value/i')


if __name__ == '__main__':
    unittest.main()
