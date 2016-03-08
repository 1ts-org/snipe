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
        lambda: ('emit',), __merge({
            '@': ('save', '>@',)
            },
            {c: ('pop?', 'emit') for c in RIGHT},
            )),
    '@': collections.defaultdict(
        lambda: ('emit', '>start'), __merge(
            {'@': ('clear', 'emit', '>start')},
            {c: ('save',) for c in IDCHARS},
            {c: ('pop?', 'emit', '>start') for c in RIGHT},
            {c: ('push', 'clear', '>start') for c in LEFT},
            )),
    }


def tree(s):
    state = 'start'
    stack = []
    saved = ''
    out = ['', '']
    cur = out
    for c in s:
        #print(c, end=' ')
        for action in machine[state][c]:
            #print(action, end=' ')
            if action[0] == '>':
                state = action[1:]
            elif action == 'emit':
                if not hasattr(cur[-1], 'upper'):
                    cur.append('')
                cur[-1] += saved + c
                saved = ''
            elif action == 'save':
                saved += c
            elif action == 'clear':
                saved = ''
            elif action == 'push':
                if cur[-1] == '':
                    del cur[-1]
                stack.append((MATCH[c], cur))
                cur.append([saved, ''])
                cur = cur[-1]
            elif action == 'pop?':
                if stack and c == stack[-1][0]:
                    if cur[-1] == '':
                        del cur[-1]
                    _, cur = stack.pop()
                    c = ''
            else:
                #print('unknown action', action)
                raise AssertionError('unknown action in state table')
        #print()
    out += saved
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
