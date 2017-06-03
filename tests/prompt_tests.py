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
Unit tests for prompt windows
'''

import unittest
import sys

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.prompt as prompt            # noqa: E402
import snipe.messages as messages        # noqa: E402
import snipe.keymap as keymap            # noqa: E402
import snipe.interactive as interactive  # noqa: E402


class TestPrompt(unittest.TestCase):
    def test_longprompt0(self):
        result = None

        def cb(s):
            nonlocal result
            result = s

        w = prompt.LongPrompt(None, prompt=': ', history='test0', callback=cb)
        w.insert('data1')

        w.runcallback()
        w.destroy()

        self.assertEqual(result, 'data1')

        result = None
        x = prompt.LongPrompt(None, prompt=': ', history='test0', callback=cb)
        x.previous_history()
        x.runcallback()
        x.destroy()

        self.assertEqual(result, 'data1')

        result = None
        y = prompt.LongPrompt(None, prompt=': ', history='test0', callback=cb)
        y.previous_history()
        y.next_history()
        y.runcallback()

        self.assertEqual(result, '')

        y.insert('frogs')

        result = None
        z = prompt.LongPrompt(None, prototype=y)
        z.runcallback()
        self.assertEqual(result, 'frogs')

        z.previous_history()
        self.assertEqual(w.input(), 'data1')

        x = z.histptr
        z.move_history(-100)
        self.assertEqual(x, z.histptr)

    def test_longprompt1(self):
        ps = ': '
        w = prompt.LongPrompt(mocks.FE(), prompt=ps)
        w.insert('thing')
        w.beginning_of_line(interactive=False)
        self.assertEqual(w.cursor.point, 0)
        w.end_of_line()
        w.beginning_of_line(interactive=True)
        self.assertNotEqual(w.cursor.point, 0)

        w.beginning_of_line(interactive=False)
        self.assertEqual(w.cursor.point, 0)
        w.insert('stuff')  # XXX Someday this should throw an exception
        self.assertEqual(w.buf[:len(ps)], ps)

    def test_longprompt_view(self):
        w = prompt.LongPrompt(None, prompt=': ')
        w.insert('foo')
        self.assertEqual(
            [(0, [
                (('bold',), ': '),
                ((), 'foo'),
                (('cursor', 'visible'), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.inverse_input = True
        self.assertEqual(
            [(0, [
                (('bold',), ': '),
                (('reverse',), 'foo'),
                (('cursor', 'visible', 'reverse'), ''),
                (('reverse',), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.inverse_input = False
        w.insert('\neven more stuff')
        self.assertEqual(
            [(0, [
                (('bold',), ': '),
                ((), 'foo\n')]),
             (6, [
                ((), 'even more stuff'),
                (('cursor', 'visible'), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        x = prompt.LongPrompt(None, prompt='multiline\nprompt: ')
        x.insert('bar')
        self.assertEqual(
            [(0, [(('bold',), 'multiline\n')]),
             (10, [(('bold',), 'prompt: '),
                   ((), 'bar'),
                   (('cursor', 'visible'), ''),
                   ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in x.view(0)])

    def test_keyseqprompt(self):
        result = None

        def cb(s):
            nonlocal result
            result = s

        w = prompt.KeySeqPrompt(
            mocks.FE(),
            prompt=': ',
            keymap=keymap.Keymap({'a': 0}), callback=cb)

        w.keyecho('a')  # how do you test that somethign did nothing?

        w.echo_keystroke('a')
        self.assertEqual(w.keystrokes, ['a'])
        self.assertEqual(w.input(), 'a ')

        w.runcallback()
        self.assertEqual(result, (['a'], None))
        self.assertEqual(
            [(0, [
                (('bold',), ': '),
                ((), 'a '),
                (('cursor', 'visible'), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

    def test_replymode(self):
        w = prompt.LongPrompt(None, modes=[
            prompt.ReplyMode(messages.SnipeMessage(None, 'pants'))])
        w.keymap[chr(ord('C') - ord('@'))][chr(ord('Y') - ord('@'))](w)
        self.assertEqual(w.input(), '> pants')

    def test_leaper(self):
        matches = ['aaa', 'aab', 'abc']
        w = prompt.Leaper(
            None, completer=interactive.Completer(matches))
        w.insert('a')
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'a'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'aaa'),
                ((), '|aab|abc}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.roll_forward()
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'a'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'aab'),
                ((), '|abc|aaa}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.roll_backward()
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'a'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'aaa'),
                ((), '|aab|abc}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.insert('bc')
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'abc'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'abc'),
                ((), '}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.roll_forward()
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'abc'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'abc'),
                ((), '}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.roll_backward()
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'abc'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'abc'),
                ((), '}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.delete_backward(2)

        w.insert('\n')
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'a'),
                ((), ' {}\n'),
                ]),
             (4, [
                ((), ''),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {}\n')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.delete_backward()

        w.state_normal()
        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'a'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        self.assertEqual('a', w.input())
        w.clear_input()
        self.assertEqual('', w.input())

        w.insert('ab')
        w.complete_command(key='\t')
        self.assertEqual(w.input(), 'aab')

        w.clear_input()
        self.assertEqual('', w.input())
        w.complete_command(key='\t')
        self.assertEqual('\t', w.input())

        w.clear_input()
        self.assertEqual('', w.input())

        w.insert('b')
        self.assertEqual('b', w.input())
        w.this_command = 'insert_stuff'
        w.state = 'preload'
        w.before_command()
        self.assertEqual('', w.input())
        self.assertEqual(
            [(i, s, s) for (i, s) in enumerate(matches)],
            w.matches())

        w.insert('blob')
        self.assertEqual('blob', w.input())
        self.assertEqual(w.state, 'preload')
        w.delete_backward()
        self.assertEqual('', w.input())

        w.insert('blob')
        self.assertEqual('blob', w.input())
        w.state = 'normal'
        w.delete_backward()
        self.assertEqual('blo', w.input())

    def test_leaper2(self):
        w = prompt.Leaper(
            None,
            prompt='multiline prompt\n: ',
            completer=interactive.Completer([]))

        self.assertEqual(
            [(0, [
                (('bold',), 'multiline prompt\n')]),
             (17, [
                (('bold',), ': '),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

    def test_shortprompt(self):
        result = None

        def cb(s):
            nonlocal result
            result = s

        w = prompt.ShortPrompt(
            None,
            content='foobaz',
            completer=interactive.Completer(['foobar', 'foobaz', 'fooquux']),
            callback=cb)

        self.assertEqual(w.input(), 'foobaz')
        w.delete_backward()
        self.assertEqual(w.input(), '')

        w.after_command()
        self.assertEqual(w.state, 'complete')
        self.assertEqual(w.inverse_input, False)

        w.insert('fooq')
        w.complete_and_finish()
        self.assertEqual(result, 'fooquux')

        w.insert('uoz')
        w.complete_and_finish()
        self.assertEqual(result, 'fooquoz')

    def test_composer(self):
        result = None

        def cb(s):
            nonlocal result
            result = s

        fe = mocks.FE()
        mockirc = mocks.Backend()
        mockirc.name = 'irccloud'
        fe.context.backends._backends.append(mockirc)

        w = prompt.Composer(
            fe,
            content='mock; foobar',
            completer=interactive.Completer([
                'mock; foobar', 'mock; foobaz', 'mock; fooquux']),
            callback=cb)

        w.beginning_of_line(interactive=True)
        w.kill_to_end_of_line(None)
        self.assertEqual(w.input(), '')
        w.after_command()

        w.insert('irccloud; foo bar')
        w.after_command()
        w.insert_newline()
        w.after_command()
        self.assertEqual(w.fill_column, 0)
        w.insert_newline()
        w.after_command()
        self.assertEqual(w.fill_column, 0)

        w.beginning_of_buffer(interactive=True)
        w.after_command()
        w.kill_to_end_of_line(count=None)
        w.after_command()
        w.insert('m; foobar')
        w.after_command()
        w.end_of_buffer()
        w.after_command()
        self.assertEqual(w.fill_column, w.default_fill_column)
        w.insert('blob')

        w.destroy()
        del w

        w = prompt.Composer(
            fe,
            content='mock; foobaz',
            completer=interactive.Completer([
                'mock; foobar', 'mock; foobaz', 'mock; fooquux']),
            callback=cb)

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'mock; foobaz'),
                (('cursor', 'visible'), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.previous_history_full()

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'm; foobar\n')]),
             (12, [((), '\n')]),
             (13, [
                ((), 'blob'),
                (('cursor', 'visible'), ''),
                ((), '')]),
             ],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.next_history_full()

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'mock; foobaz'),
                (('cursor', 'visible'), ''),
                ((), '')])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.beginning_of_buffer(interactive=True)
        p0 = w.cursor.point
        w.end_of_line()
        self.assertEqual(w.buf[p0:w.cursor.point], 'mock; foobaz')
        w.cursor.point = p0
        w.previous_history()
        w.end_of_line()
        self.assertEqual(w.buf[p0:w.cursor.point], 'm; foobar')
        w.previous_history()
        self.assertEqual(w.buf[p0:w.cursor.point], 'm; foobar')
        w.cursor.point = p0
        w.next_history()
        w.end_of_line()
        self.assertEqual(w.buf[p0:w.cursor.point], 'mock; foobaz')

        w.previous_history_full()
        w.line_next()
        w.next_history()

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'm; foobar\n'),
                ]),
             (12, [
                ((), ''),
                (('cursor', 'visible'), ''),
                ((), '')]),
             ],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.destroy()
        del w

        w = prompt.Composer(
            fe,
            completer=interactive.Completer([
                'mock; foobar', 'mock; foobaz', 'mock; fooquux']),
            callback=cb)

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {'),
                (('bold',), 'mock; foobar'),
                ((), '|mock; foobaz|mock; fooquux}\n'),
                ])],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])
        w.previous_history()

        self.assertEqual(
            [(0, [
                (('bold',), '> '),
                ((), 'm; foobar'),
                (('cursor', 'visible'), ''),
                ((), ''),
                ((), ' {}\n'), ]),
             (12, [
                ((), '')]),
             ],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])


if __name__ == '__main__':
    unittest.main()
