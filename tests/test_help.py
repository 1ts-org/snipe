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
Unit tests for help system
'''

import unittest

import snipe.help as help

from snipe.chunks import (Chunk, View)


class TestHelp(unittest.TestCase):
    def test_follow_link(self):
        w = help.HelpBrowser(None)

        called = []

        w.load = lambda link: called.append(link)
        w.links = [(10, 10, 'one'), (30, 10, 'two')]

        w.cursor = 5
        w.follow_link()
        self.assertFalse(called)
        w.cursor = 25
        w.follow_link()
        self.assertFalse(called)
        w.cusor = 45
        w.follow_link()
        self.assertFalse(called)
        w.cursor = 10
        w.follow_link()
        self.assertEqual(called[-1], 'one')
        w.cursor = 35
        w.follow_link()
        self.assertEqual(called[-1], 'two')
        w.cursor = 20
        w.follow_link()
        self.assertEqual(called[-1], 'one')

    def test_view(self):
        w = help.HelpBrowser(None)

        w.pages['TESTPAGE'] = PAGE
        w.load('TESTPAGE')

        self.assertEqual([
            (0, Chunk([
                (('cursor', 'visible'), ''),
                (('bold',), 'snipe'),
                ((), '\n')])),
            (6, Chunk([((), '\n')])),
            (7, Chunk([
                ((), 'snipe is a text-oriented (currently curses-based)'
                     ' "instant" messaging\n')])),
            (77, Chunk([
                ((), 'client intended for services with persistence.\n')])),
            (124, Chunk([
                ((), '\n')])),
            (125, Chunk([
                ((), 'It is known that there are bugs and missing features'
                     ' everywhere.  I\n')])),
            (193, Chunk([
                ((), 'would mostly characterize this as "demoable" but not'
                     ' yet "usable".  As\n')])),
            (264, Chunk([
                ((), 'always, if it breaks you get to keep both pieces.\n')])),
            (314, Chunk([((), '\n')])),
            (315, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'), 'Help browser'),
                ((), '\n')])),
            (330, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'),
                    'Common commands in all windows'),
                ((), '\n')])),
            (363, Chunk([((), '\n')])),
            ],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.line_next()
        self.assertEqual([
            (0, Chunk([
                ((), ''),
                (('bold',), 'snipe'),
                ((), '\n')])),
            (6, Chunk([(('cursor', 'visible'), '\n')])),
            (7, Chunk([
                ((), 'snipe is a text-oriented (currently curses-based)'
                     ' "instant" messaging\n')])),
            (77, Chunk([
                ((), 'client intended for services with persistence.\n')])),
            (124, Chunk([
                ((), '\n')])),
            (125, Chunk([
                ((), 'It is known that there are bugs and missing features'
                     ' everywhere.  I\n')])),
            (193, Chunk([
                ((), 'would mostly characterize this as "demoable" but not'
                     ' yet "usable".  As\n')])),
            (264, Chunk([
                ((), 'always, if it breaks you get to keep both pieces.\n')])),
            (314, Chunk([((), '\n')])),
            (315, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'), 'Help browser'),
                ((), '\n')])),
            (330, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'),
                    'Common commands in all windows'),
                ((), '\n')])),
            (363, Chunk([((), '\n')])),
            ],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])

        w.end_of_buffer()
        self.assertEqual([
            (0, Chunk([
                ((), ''),
                (('bold',), 'snipe'),
                ((), '\n')])),
            (6, Chunk([((), '\n')])),
            (7, Chunk([
                ((), 'snipe is a text-oriented (currently curses-based)'
                     ' "instant" messaging\n')])),
            (77, Chunk([
                ((), 'client intended for services with persistence.\n')])),
            (124, Chunk([
                ((), '\n')])),
            (125, Chunk([
                ((), 'It is known that there are bugs and missing features'
                     ' everywhere.  I\n')])),
            (193, Chunk([
                ((), 'would mostly characterize this as "demoable" but not'
                     ' yet "usable".  As\n')])),
            (264, Chunk([
                ((), 'always, if it breaks you get to keep both pieces.\n')])),
            (314, Chunk([((), '\n')])),
            (315, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'), 'Help browser'),
                ((), '\n')])),
            (330, Chunk([
                ((), '* '),
                (('fg:#6666ff', 'underline'),
                    'Common commands in all windows'),
                ((), '\n')])),
            (363, Chunk([((), '\n'), (('cursor', 'visible'), '')]))],
            [(int(mark), chunk) for (mark, chunk) in w.view(0)])


PAGE = ([
    View(0, Chunk([((), ''), (('bold',), 'snipe'), ((), '\n')])),
    View(6, Chunk([((), '\n')])),
    View(7, Chunk([
        ((), 'snipe is a text-oriented (currently curses-based) "instant"'
             ' messaging\n')])),
    View(77, Chunk([
        ((), 'client intended for services with persistence.\n')])),
    View(124, Chunk([((), '\n')])),
    View(125, Chunk([
        ((), 'It is known that there are bugs and missing features'
             ' everywhere.  I\n')])),
    View(193, Chunk([
        ((), 'would mostly characterize this as "demoable" but not yet'
             ' "usable".  As\n')])),
    View(264, Chunk([
        ((), 'always, if it breaks you get to keep both pieces.\n')])),
    View(314, Chunk([((), '\n')])),
    View(315, Chunk([
        ((), '* '),
        (('fg:#6666ff', 'underline'), 'Help browser'),
        ((), '\n')])),
    View(330, Chunk([
        ((), '* '),
        (('fg:#6666ff', 'underline'), 'Common commands in all windows'),
        ((), '\n')])),
    View(363, Chunk([((), '\n')])),
    ],
    'snipe\n'
    '\n'
    'snipe is a text-oriented (currently curses-based) "instant" messaging\n'
    'client intended for services with persistence.\n'
    '\n'
    'It is known that there are bugs and missing features everywhere.  I\n'
    'would mostly characterize this as "demoable" but not yet "usable".  As\n'
    'always, if it breaks you get to keep both pieces.\n'
    '\n'
    '* Help browser\n'
    '* Common commands in all windows\n'
    '\n',
    {'snipe': 0},
    [(317, 12, 'snipe.help#Helpbrowser'),
     (332, 30, 'snipe.window#Commoncommandsinallwindows')],
    'snipe')


if __name__ == '__main__':
    unittest.main()
