#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe Contributors
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
Unit tests for the doc munching stuff in the text module
'''


import docutils.core
import sys
import unittest

sys.path.append('..')

import snipe.text as text


TEXT='''
=============
a Title
=============

Here is some text.  Here is some more text.  Blah blah blah.  Foo.  Bar.  Flarb.
(The previous should get wrapped if everything is good.)

One.
Two.
Three.
(The above shold end up on one line.)

myslack.slack.com).  You
add ``.slack name=myname`` to the ``backends`` configuration variable (which is
``;`` separated), and get an api key from ``https://api.slack.com/web`` and put
it in ``~/.snipe/netrc`` like so: ::

 machine myslack.slack.com login myself@example.com password frob-9782504613-8396512704-9784365210-7960cf


(You need to have already signed up for the relevant slack instance by other
means.)

Lorem ipsum dolor sit amet, consecteturadipiscingelit,seddoeiusmodtemporincididuntutlaboreetdoloremagnaaliqua.Utenimadminimveniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
'''

TEXT_rendered=[(0, [((), ''), (('bold',), 'a Title'), ((), '\n')]),
 (8, [((), '\n')]),
 (9,
  [((),
    'Here is some text.  Here is some more text.  Blah blah blah.  Foo.\n')]),
 (76,
  [((),
    'Bar.  Flarb. (The previous should get wrapped if everything is '
    'good.)\n')]),
 (146, [((), '\n')]),
 (147, [((), 'One. Two. Three. (The above shold end up on one line.)\n')]),
 (202, [((), '\n')]),
 (203,
  [((), 'myslack.slack.com).  You add '),
   (('bold',), '.slack name=myname'),
   ((), ' to the '),
   (('bold',), 'backends'),
   ((), '\n')]),
 (267,
  [((), 'configuration variable (which is'),
   (('bold',), ';'),
   ((), ' separated), and get an api key from '),
   (('bold',), '\n')]),
 (338,
  [(('bold',), 'https://api.slack.com/web'),
   ((), ' and put it in '),
   (('bold',), '~/.snipe/netrc'),
   ((), ' like so:\n')]),
 (402, [((), '\n')]),
 (403,
  [(('bold',),
    'machine myslack.slack.com login myself@example.com password '
    'frob-9782504613-8396512704-9784365210-7960cf'),
   ((), '\n')]),
 (508, [((), '\n')]),
 (509,
  [((),
    '(You need to have already signed up for the relevant slack instance '
    'by\n')]),
 (580, [((), 'other means.)\n')]),
 (594, [((), '\n')]),
 (595, [((), 'Lorem ipsum dolor sit amet,\n')]),
 (623,
  [((),
    'consecteturadipiscingelit,seddoeiusmodtemporincididuntutlaboreetdoloremagnaaliqua.Utenimadminimveniam,\n')]),
 (726,
  [((),
    'quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea '
    'commodo\n')]),
 (798, [((), 'consequat.\n')]),
 (809, [((), '\n')])]

class TestRendering(unittest.TestCase):
    def test_RSTRenderer(self):
        _, pub = docutils.core.publish_programmatically(
            docutils.io.StringInput, TEXT, None, docutils.io.NullOutput,
            None, None, None, 'standalone', None, 'restructuredtext', None,
            'null', None, None, {}, None, None)

        renderer = text.RSTRenderer()
        renderer.process(pub.writer.document)

        import logging
        logging.debug('%s', repr(renderer.output))
        logging.debug('\n%s', renderer.flat())

        self.assertEqual(TEXT_rendered, renderer.output)

    def test_markdown_to_chunk(self):
        self.assertEquals([((), 'some text\n')], text.markdown_to_chunk('some text'))

# So I can cut and paste it into test:
# Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
