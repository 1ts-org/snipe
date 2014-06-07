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

import os
import unicodedata
import contextlib
import re
import logging
import time
import asyncio
import json

from . import messages
from . import ttyfe
from . import roost
from . import filters
from . import util


def bind(*seqs):
    def decorate(f):
        f.snipe_seqs = seqs
        return f
    return decorate


class Window:
    def __init__(self, frontend, prototype=None, destroy=lambda: None):
        self.fe = frontend
        self.keymap = {}
        self.renderer = None
        self.keymap = Keymap()
        #XXX should really be walking the inheritance tree so the stuff
        #lower in the tree wins
        for f in (getattr(self, name) for name in dir(self)):
            if hasattr(f, 'snipe_seqs'):
                for seq in f.snipe_seqs:
                    self.keymap[seq] = f
        self.active_keymap = self.keymap
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))
        if prototype is None:
            self.cursor = None
            self.frame = None
        else:
            self.cursor = prototype.cursor
            self.frame = prototype.frame
        self.destroy = destroy

    @property
    def context(self):
        if self.fe is None:
            return None
        return self.fe.context

    def input_char(self, k):
        try:
            self.log.debug('got key %s', repr(k))
            try:
                v = self.active_keymap[k]
            except KeyError:
                self.active_keymap = self.keymap
                self.log.error('no such key in map')
                self.whine(k)
                return

            if not callable(v):
                self.active_keymap = v
            else:
                self.active_keymap = self.keymap
                ret = v(k)
                if asyncio.iscoroutine(ret):
                    def catch_and_log(coro):
                        try:
                            yield from coro
                        except:
                            self.log.exception('Executing complex command')
                            self.whine(k)
                        self.fe.redisplay()

                    t = asyncio.Task(catch_and_log(ret))

        except Exception as e:
            self.log.exception('executing command from keymap')
            self.whine(k)
            self.active_keymap = self.keymap

    def read_string(self, prompt, content=None, height=1, window=None):
        f = asyncio.Future()

        def done_callback(result):
            f.set_result(result)
            self.fe.popdown_window()#XXX might not always be the right one

        def destroy_callback():
            if not f.done():
                f.set_exception(Exception('Operation Aborted'))

        if window is None:
            from .editor import ShortPrompt, LongPrompt
            if height > 2:
                window = LongPrompt
            else:
                window = ShortPrompt
        self.fe.popup_window(
            window(
                self.fe,
                prompt=prompt,
                content=content,
                callback=done_callback,
                destroy=destroy_callback,
                ),
            height=height,
            )
        self.fe.redisplay()

        yield from f

        return f.result()

    @bind('Control-X Control-C')
    def quit(self, k):
        asyncio.get_event_loop().stop()

    def whine(self, k):
        self.fe.notify()

    @bind('Control-Z')
    def stop(self, k):
        self.fe.sigtstp(None, None)

    def view(self, origin=None, direction=None):
        yield 0, [(('visible',), '')]

    @bind('Control-X 2')
    def split_window(self, k):
        self.fe.split_window(self.__class__(self.fe, prototype=self))

    @bind('Control-X 0')
    def delete_window(self, k):
        self.fe.delete_current_window()

    @bind('Control-X 1')
    def popdown(self, k):
        self.fe.popdown_window()

    @bind('Control-X o')
    def other_window(self, k):
        self.fe.switch_window(1)

    @bind('Control-X e')#XXX
    def split_to_editor(self, k):
        from .editor import Editor
        self.fe.split_window(Editor(self.fe))

    @bind('Control-X c')#XXX
    def split_to_colordemo(self, k):
        self.fe.split_window(ColorDemo(self.fe))

    @bind('Control-X t')#XXX
    def test_ui(self, k):
        streeng = yield from self.read_string('floop> ', content='zoge')
        self.log.debug(
            'AAAA %s',
            ''.join(reversed(streeng)),
            )

    @bind('Meta-[ESCAPE]', 'Meta-:')
    def replhack(self, k):
        import traceback
        from . import editor

        self.log.debug('entering replhack')

        out = ''
        while True:
            expr = yield from self.read_string(
                out + ':>> ',
                height = len(out.splitlines()) + 1,
                window = editor.ShortPrompt,
                )
            if not expr.strip():
                break
            self.log.debug('got expr %s', expr)
            try:
                ret = eval(expr, globals(), locals())
                out = repr(ret)
            except:
                out = traceback.format_exc()
            if out[:-1] != '\n':
                out += '\n'
            self.log.debug('result: %s', out)

    @bind('Meta-=')
    def set_config(self, k):
        key = yield from self.read_string('Key: ')
        value = yield from self.read_string('Value: ')
        util.Configurable.set(self, key, value)
        self.context.conf_write()


class Messager(Window):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        #SPACE
        #^n ^p j k NEXT PREV
        self.cursor = next(self.fe.context.backends.walk(time.time(), False))
        self.frame = self.cursor
        self.filter = None

    def walk(self, origin, direction):
        return self.fe.context.backends.walk(origin, direction, self.filter)

    def view(self, origin, direction='forward'):
        for x in self.walk(origin, direction == 'forward'):
            s = str(x)
            if s and s[-1] != '\n':
                s += '\n'
            if x is self.cursor:
                lines = s.splitlines()
                yield x, [
                    (('visible', 'standout'), lines[0] + '\n'),
                    ((), '\n'.join(lines[1:]) + '\n'),
                    ]
            else:
                yield x, [((), s)]

    @bind('n', '[down]')
    def next_message(self, k):
        self.move(True)

    @bind('p', '[up]')
    def prev_message(self, k):
        self.move(False)

    def move(self, forward):
        it = iter(self.walk(self.cursor, forward))
        try:
            intermediate = next(it)
            self.log.debug(
                'move %s: intermediate: %s',
                'forward' if forward else 'backward',
                repr(intermediate),
                )
            self.cursor = next(it)
            self.log.debug(
                'move %s: cursor: %s',
                'forward' if forward else 'backward',
                repr(self.cursor),
                )
        except StopIteration:
            self.whine('No more messages')

    @bind('s')
    def send(self, k, recipient=''):
        message = yield from self.read_string(
            '[roost] send --> ',
            height=10,
            content=recipient + '\n' if recipient else '',
            )
        params, body = message.split('\n', 1)
        yield from self.fe.context.roost.send(params, body)

    @bind('f')
    def followup(self, k):
        yield from self.send(k, self.cursor.followupstr())

    @bind('r')
    def reply(self, k):
        yield from self.send(k, self.cursor.replystr())

    @bind('[END]', 'Shift-[END]', '[SEND]', 'Meta->')
    def last(self, k):
        self.cursor = next(self.walk(float('inf'), False))

    @bind('[HOME]', 'Shift-[HOME]', '[SHOME]', 'Meta-<')
    def first(self, k):
        self.cursor = next(self.walk(float('-inf'), True))

    @bind('Meta-/ 0')
    def filter_rest(self, k):
        self.filter = None

    @bind('Meta-/ =')
    def filter_edit(self, k):
        s = '' if self.filter is None else str(self.filter)

        s = yield from self.read_string('Filter expression:\n', s, 5)

        self.filter = filters.makefilter(s)

        self.cursor = next(self.walk(self.cursor, True))


class Context:
    # per-session state and abstact control
    def __init__(self, ui):
        self.conf = {}
        self.context = self
        self.conf_read()
        self.ui = ui
        self.ui.context = self
        self.log = logging.getLogger('Snipe')
        self.log.warning('snipe starting')
        #XXX kludge so the kludged sending can find the roost backend
        self.roost = roost.Roost(self)
        self.backends = messages.AggregatorBackend(
            self,
            backends = [
                messages.StartupBackend(self),
#                messages.SyntheticBackend(self, conf={'count': 100}),
                self.roost,
                ],)
        self.ui.initial(Messager(self.ui))

    def conf_read(self):
        path = os.path.join(os.path.expanduser('~'), '.snipe', 'config')
        try:
            if os.path.exists(path):
                self.conf = json.load(open(path))
        finally:
            util.Configurable.immanentize(self)

    def conf_write(self):
        directory = os.path.join(os.path.expanduser('~'), '.snipe')
        name = 'config'
        path = os.path.join(directory, name)
        tmp = os.path.join(directory, ',' + name)
        backup = os.path.join(directory, name + '~')

        if not os.path.isdir(directory):
            os.mkdir(directory)

        fp = open(tmp, 'w')
        json.dump(self.conf, fp)
        fp.write('\n')
        fp.close()
        if os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(backup)
            os.link(path, backup)
        os.rename(tmp, path)


class Keymap(dict):
    def __init__(self, d={}):
        super().__init__()
        self.update(d)

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

class ColorDemo(Window):
    def __init__(self, *args, **kw):
        self.cursor = 0
        self.frame = 0
    def view(self, origin=0, direction='Forward'):
        yield 0, [(('visible', 'fg:green'), 'foo')]
