#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2017 the Snipe contributors
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
Unit tests for REPL window
'''

import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.repl as repl  # noqa: E402


class TestREPL(unittest.TestCase):
    def test_output0(self):
        w = repl.REPL(None)
        self.assertEqual(len(w.state['stakes']), 2)
        self.assertEqual(w.state['stakes'][0][1], repl.OUTPUT_START)
        self.assertEqual(w.state['stakes'][1][1], repl.OUTPUT_END)
        w.cursor.insert('foo\n')
        w.output('bar ')
        w.output('baz: ')
        self.assertEqual(len(w.state['stakes']), 4)
        self.assertEqual(w.state['stakes'][2][1], repl.OUTPUT_START)
        self.assertEqual(w.state['stakes'][3][1], repl.OUTPUT_END)

    def test_bracket(self):
        w = repl.REPL(None)
        self.assertEqual(w.brackets(5), tuple(w.state['stakes'][0:2]))
        self.assertEqual(
            w.brackets(len(w.buf)), (w.state['stakes'][-1], (None, None)))
        self.assertEqual(w.brackets(0), tuple(w.state['stakes'][0:2]))
        l = len(w.buf)
        w.cursor.insert('data')
        m = len(w.buf)
        w.output('output')
        OUTPUT = [repl.OUTPUT_START, repl.OUTPUT_END]
        INPUT = [repl.OUTPUT_END, repl.OUTPUT_START]
        TAIL = [repl.OUTPUT_END, None]
        self.assertEqual([x[1] for x in w.brackets(0)], OUTPUT)
        self.assertEqual([x[1] for x in w.brackets(1)], OUTPUT)
        self.assertEqual([x[1] for x in w.brackets(l)], INPUT)
        self.assertEqual([x[1] for x in w.brackets(l + 1)], INPUT)
        self.assertEqual([x[1] for x in w.brackets(m)], OUTPUT)
        self.assertEqual([x[1] for x in w.brackets(m + 1)], OUTPUT)
        self.assertEqual([x[1] for x in w.brackets(len(w.buf))], TAIL)
        w.cursor.point = len(w.buf)
        self.assertTrue(w.writable(0))
        w.cursor.point = l
        self.assertTrue(w.writable(0))
        w.cursor.point = 0
        self.assertFalse(w.writable(0))

    def test_go(self):
        w = repl.REPL(mocks.FE())
        w.cursor.insert('2 + 2')
        earlier = w.cursor.point
        w.go()
        result = '\n' + str(4) + '\n' + w.state['ps1']
        self.assertEqual(w.buf[-len(result):], result)
        self.assertEqual(w.state['in'][0], '2 + 2')
        self.assertEqual(w.state['out'][0], 4)

        t = 'def flurb():'
        w.cursor.insert(t)
        w.go()
        self.assertEqual(w.context._message, 'incomplete input')
        w.go2()
        self.assertEqual(w.buf[-(len(t) + 1):], t + '\n')

        w.cursor.point = earlier
        w.go()
        result = result + t + '\n'
        self.assertEqual(w.buf[-len(result):], result)
        self.assertEqual(w.state['in'][1], '2 + 2')
        self.assertEqual(w.state['out'][1], 4)

    def test_bol(self):
        w = repl.REPL(None)
        w.insert('foo')
        w.beginning_of_line()
        bol = w.cursor.point
        self.assertEqual(w.buf[bol:], w.state['ps1'] + 'foo')
        w.end_of_line()
        w.electric_beginning_of_line()
        self.assertEqual(w.cursor.point, bol)
        w.end_of_line()
        w.electric_beginning_of_line(interactive=True)
        self.assertEqual(w.cursor.point, bol + len(w.state['ps1']))
        w.electric_beginning_of_line(interactive=True)
        self.assertEqual(w.cursor.point, bol)
        w.electric_beginning_of_line(interactive=True)
        self.assertEqual(w.cursor.point, bol)

    def test_title(self):
        w = repl.REPL(None)
        self.assertRegex(w.title(), r'^REPL\[\d\]+ \[0\]$')

    def test_result(self):
        w = repl.REPL(mocks.FE())
        w.insert('import sys')
        w.go()
        self.assertEqual(w.state['out'][0], None)

    def test_func(self):
        w = repl.REPL(mocks.FE())
        w.insert('def func():\n return 2+2\n')
        w.go()
        w.insert('func()')
        w.go()
        self.assertEqual(w.state['out'][1], 4)
        w.insert('''def fib(n):
            if n < 2:
                return n
            return fib(n - 2) + fib(n - 1)
''')
        w.go()
        w.insert('fib(6)')
        w.go()
        self.assertEqual(w.state['out'][3], 8)


if __name__ == '__main__':
    unittest.main()
