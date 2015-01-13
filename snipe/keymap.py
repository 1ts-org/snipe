#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2014 Karl Ramm
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
snipe.keymap
------------
'''


import unicodedata
import contextlib
import re
import collections

from . import ttyfe


def bind(*seqs):
    def decorate(f):
        f.snipe_seqs = seqs
        return f
    return decorate


class Keymap(dict):
    def __init__(self, d={}):
        super().__init__()
        self.update(d)

    def interrogate(self, obj):
        if hasattr(obj, 'input_char'): # looks like a Window
            # the following somewhat abstruse code attempts to insure
            # that the bindings of a method in a child class override
            # the bindings in the parent class, both when the method
            # is actually overriden and when the bindings are on a
            # different method.
            methods = collections.OrderedDict()
            for klass in reversed(obj.__class__.mro()):
                for name in dir(klass):
                    unbound = getattr(klass, name)
                    bound = getattr(obj, name)
                    if hasattr(bound, 'snipe_seqs') and \
                      unbound.__qualname__.startswith(klass.__name__ + '.'):
                        if name in methods:
                            del methods[name]
                        methods[name] = bound
            for method in methods.values():
                for seq in method.snipe_seqs:
                    self[seq] = method
        else:
            for f in (getattr(obj, name) for name in dir(obj)):
                if hasattr(f, 'snipe_seqs'):
                    for seq in f.snipe_seqs:
                        self[seq] = f


    def update(self, d):
        for k, v in d.items():
            if hasattr(v, 'items'):
                self[k] = Keymap(v)
            else:
                self[k] = v

    def __repr__(self):
        return (
            self.__class__.__name__
            + '('
            + super().__repr__()
            + ')'
            )

    def __getitem__(self, key):
        if not hasattr(key, 'lower'):
            return super().__getitem__(key)
        else:
            key, rest = self.split(key)
            v = super().__getitem__(key)
            if key is None:
                return None # default?
            if rest:
                return v[rest]
            return v

    def __setitem__(self, key, value):
        if not hasattr(key, 'lower'):
            return super().__setitem__(key, value)
        else:
            key, rest = self.split(key)
            if key is None:
                return
            if rest is None:
                super().__setitem__(key, value)
            else:
                try:
                    v = super().__getitem__(key)
                except KeyError:
                    v = None
                if v is None:
                    v = Keymap()
                    super().__setitem__(key, v)
                if not hasattr(v, '__getitem__'):
                    raise KeyError(repr(key) + 'is not a keymap')
                v[rest] = value

    def __delitem__(self, key):
        if not hasattr(key, 'lower'):
            return super().__delitem__(key)
        else:
            key, rest = self.split(key)
            if rest is None:
                super().__delitem__(key)
            else:
                v = super().__getitem__(key)
                if not hasattr(v, '__getitem__'):
                    raise KeyError(repr(key) + 'is not a keymap')
                del v[rest]

    modifier_aliases = {
        'ctl': 'control',
        'alt': 'meta',
        }
    modifiers = ['control', 'shift', 'meta', 'hyper', 'super']
    all_modifiers = modifiers + list(modifier_aliases.keys())

    keyseq_re = re.compile(
        '^(?P<modifiers>((' + '|'.join(all_modifiers) + ')-)*)'
        + r'((?P<char>.)|\[(?P<name>[^]]+)\])'
        + r'(|(\s+(?P<rest>\S.*)))'
        + '$',
        re.IGNORECASE
        )

    other_keys_spec = [
        (('escape','esc'), '\x1b'),
        (('delete', 'del'), '\x7f'),
        (('line feed', 'linefeed', 'newline'), '\x0a'),
        (('carriage return', 'return'), '\x0d'),
        (('tab',), '\x09'),
        (('space',), ' '),
        ]

    other_keys = {}
    for (names, value) in other_keys_spec:
        for name in names:
            other_keys[name] = value

    unother_keys = {
        value: names[0] for (names, value) in other_keys_spec}

    @staticmethod
    def split(keyseqspec):
        if not hasattr(keyseqspec, 'lower'):
            return keyseqspec, None

        if len(keyseqspec) == 1:
            return keyseqspec, None

        match = Keymap.keyseq_re.match(keyseqspec)

        if not match:
            raise TypeError(
                'Invalid Key Sequence Specification', repr(keyseqspec))

        d = match.groupdict()

        modifiers = d.get('modifiers', '-')[:-1].split('-')
        modifiers = set(
            Keymap.modifier_aliases.get(modifier, modifier).lower()
            for modifier in modifiers if modifier)

        key = d['char']
        rest = d['rest']

        name = d['name']
        if key is None:
            with contextlib.suppress(KeyError):
                key = Keymap.other_keys.get(name.lower())

        if key is None:
            with contextlib.suppress(KeyError):
                key = ttyfe.key.get(name.upper())

        if key is None:
            with contextlib.suppress(KeyError):
                key = unicodedata.lookup(name.upper())

        if key is None:
            raise TypeError('unknown name: %s' % name)

        if 'hyper' in modifiers or 'super' in modifiers:
            return None, None #valid but untypable

        if 'control' in modifiers:
            if not hasattr(key, 'upper'):
                # XXX ignoring control+function keys for now
                return None, None #valid but untypable
            if key == '?':
                key = '\x7f'
            elif ord('@') <= ord(key.upper()) <= ord('_'):
                key = chr(ord(key.upper()) - ord('@'))
            elif key == ' ':
                key = '\0'
            else:
                return None, None #valid but untypable
            modifiers.remove('control')

        if 'shift' in modifiers:
            # XXX ignoring SLEFT et al for now
            if not hasattr(key, 'upper'):
                # XXX ignoring control+function keys for now
                return None, None #valid but untypable
            # XXX ignore e.g. shift-1 (!, on a US keyboard, argh) for now
            key = key.upper()
            modifiers.remove('shift')

        if 'meta' in modifiers:
            if key in Keymap.unother_keys:
                name = '[' + Keymap.unother_keys[key].upper() + ']'
            elif isinstance(key, int):
                name = '[' + ttyfe.unkey.get(key) + ']'
            elif ord(key) < ord(' '):
                name = 'Control-' + chr(ord(key) + ord('@'))
            elif ord(key) < 127:
                name = key
            else:
                name = '[' + unicodedata.name(key) + ']'
            if rest:
                name += ' ' + rest
            rest = name
            key = '\x1b' # ESC
            modifiers.remove('meta')

        assert bool(modifiers) == False

        return key, rest

    @classmethod
    def unkey(self, c):
        if hasattr(c, 'upper'):
            if c in self.unother_keys:
                return '[' + self.unother_keys[c] + ']'
            if ord(c) < ord(' '):
                return 'Control-' + chr(ord('@') + ord(c))
            if ord(c) < ord('\177'):
                return c
            try:
                return '[' + unicodedata.name(c).lower() + ']'
            except ValueError:
                return '[?%x]' % ord(c)
        else: # probably an integer?
            if c in ttyfe.unkey:
                return '[' + ttyfe.unkey[c].lower() + ']'
            else:
                return '[%x?]' % c

    def pairify(self, prefix=''):
        ks = list(sorted(
                self.keys(), key=lambda k: (0 if hasattr(k, 'upper') else 1, k)))
        eliding = None
        for (i, k) in enumerate(ks):
            keyseq = prefix + self.unkey(k)
            if eliding is None and hasattr(k, 'upper') \
              and ks[i + 1:i + 3] == [chr(ord(k) + 1), chr(ord(k) + 2)] \
              and self[k] is self[ks[i+1]] is self[ks[i+2]]:
                eliding = keyseq
                continue
            if eliding is not None and (
              ks[i + 1:i + 2] != [chr(ord(k) + 1)]
              or self[k] is not self[ks[i + 1]]):
                keyseq = eliding + ' .. ' + self.unkey(k)
                eliding = None
            if eliding is None:
                if hasattr(self[k], 'pairify'):
                    yield from self[k].pairify(keyseq + ' ')
                elif hasattr(self[k], '__name__'):
                    yield keyseq, self[k].__name__
                else:
                    yield keyseq, '???'

    def __str__(self):
        mappings = list(self.pairify())
        width = max(len(keyseq) for (keyseq, action) in mappings)
        return '\n'.join(
            '%-*s  %s' % (width, keyseq, action) for (keyseq, action) in mappings)
