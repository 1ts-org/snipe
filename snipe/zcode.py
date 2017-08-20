#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe contributors
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

import collections
import logging

from . import chunks


IDCHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
LEFT, RIGHT = '({[<', ')}]>'
MATCH = dict(zip(LEFT, RIGHT))


def __merge(*args):
    r = {}
    for d in args:
        r.update(d)
    return r


machine = {
    'start': collections.defaultdict(
        lambda: ('emit', 'clear'), __merge({
            '@': ('save', '>@',),
            '': ('emit', 'tidy',)
            },
            {c: ('pop?', 'emit') for c in RIGHT},
            )),
    '@': collections.defaultdict(
        lambda: ('emit', 'clear', '>start'), __merge({
            '@': ('clear', 'emit', '>start'),
            '': ('emit', 'tidy',),
            },
            {c: ('save',) for c in IDCHARS},
            {c: ('pop?', 'emit', 'clear', '>start') for c in RIGHT},
            {c: ('tidy', 'push', 'clear', '>start') for c in LEFT},
            )),
    }


log = logging.getLogger('zcode')


def tree(s):
    state = 'start'
    stack = []
    saved = ''
    out = ['', '']
    cur = out
    for c in list(s) + ['']:
        log.debug('processing %s in state %s', repr(c), state)
        for action in machine[state][c]:
            if action[0] == '>':
                state = action[1:]
            elif action == 'emit':
                if not hasattr(cur[-1], 'upper'):
                    cur.append('')
                cur[-1] += saved + c
            elif action == 'save':
                saved += c
            elif action == 'clear':
                saved = ''
            elif action == 'tidy':
                if cur[-1] == '':
                    del cur[-1]
            elif action == 'push':
                stack.append((MATCH[c], cur))
                cur.append([saved, ''])
                cur = cur[-1]
            elif action == 'pop?':
                if stack and c == stack[-1][0]:
                    cur[-1] += saved
                    saved = ''
                    if cur[-1] == '':
                        del cur[-1]
                    _, cur = stack.pop()
                    c = ''
            else:
                raise AssertionError(
                    'unknown action in state table')  # pragma: nocover
            log.debug(' %s %s %s %s', action, out, repr(saved), cur)
    return out


def tree_to_string(t, ignore=('@font', '@color')):
    out = []
    if t[0] in ignore:
        return ''
    for e in t[1:]:
        if hasattr(e, 'upper'):
            out.append(e)
        else:
            out.append(tree_to_string(e, ignore))
    return ''.join(out)


def strip_simple(s):
    return tree_to_string(tree(s), ignore=())


def strip(s):
    return tree_to_string(tree(s))


def ctags(otags, fg):
    tags = set(otags)
    if fg:
        tags.add('fg:' + fg)
    return tags


def tag_tree(t, tags, fg=None, otags=None):
    if otags is None:
        otags = set()
        for tag in tags:
            if tag.startswith('fg:'):
                fg = tag[3:]
            else:
                otags.add(tag)

    out = chunks.Chunk()
    name = t[0].lower()
    if name in {'@i', '@italic'}:
        otags.add('underline')
    elif name in {'@b', '@bold'}:
        otags.add('bold')
    elif name == '@roman':
        otags -= {'underline', 'bold'}
    tags = ctags(otags, fg)
    for e in t[1:]:
        if hasattr(e, 'upper'):
            if 'underline' in tags and '\n' in e:
                buf = []
                for f in e.split('\n'):
                    buf.append((tags, f))
                    buf.append((tags - {'underline'}, '\n'))
                del buf[-1]
                out.extend(buf)
            else:
                out.append((tags, e))
        else:  # a list
            name = e[0].lower()
            if name == '@color':
                fg = tree_to_string([''] + e[1:])
                tags = ctags(otags, fg)
            elif name == '@font':
                pass  # nope
            else:
                out += tag_tree(e, tags, fg, otags)
    return out


def tag(s, tags):
    return tag_tree(tree(s), tags)
