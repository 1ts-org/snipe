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

import os
import unicodedata
import contextlib
import re
import logging
import asyncio
import json

from . import messages
from . import ttyfe
from . import roost
from . import util
from . import interactive


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
            self.hints = {}
        else:
            self.cursor = prototype.cursor
            self.hints = prototype.renderer.get_hints()
        self.destroy = destroy
        self.this_command = None
        self.last_command = None
        self.last_key = None
        self.universal_argument = None

    def __repr__(self):
        return '<%s %x>' % (self.__class__.__name__, id(self))

    def focus(self):
        pass

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
                arg, self.universal_argument = self.universal_argument, None
                self.this_command = getattr(v, '__name__', '?')
                ret = interactive.call(
                    v,
                    context = self.context,
                    keystroke = k,
                    argument = arg,
                    )
                self.last_command = self.this_command
                self.last_key = k
                if asyncio.iscoroutine(ret):
                    def catch_and_log(coro):
                        try:
                            yield from coro
                        except:
                            self.log.exception('Executing complex command')
                            self.whine(k)
                        self.fe.redisplay({'window': self})

                    t = asyncio.Task(catch_and_log(ret))

        except Exception as e:
            self.log.exception('executing command from keymap')
            self.whine(k)
            self.active_keymap = self.keymap

    def check_redisplay_hint(self, hint):
        ret = hint.get('window', None) is self
        self.log.debug('redisplay hint %s -> %s', repr(hint), repr(ret))
        return ret

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
    def quit(self):
        asyncio.get_event_loop().stop()

    def whine(self, k):
        self.fe.notify()

    @bind('Control-Z')
    def stop(self):
        self.fe.sigtstp(None, None)

    def view(self, origin=None, direction=None):
        yield 0, [(('visible',), '')]

    @bind('Control-X 2')
    def split_window(self):
        self.fe.split_window(self.__class__(self.fe, prototype=self))

    @bind('Control-X 0')
    def delete_window(self):
        self.fe.delete_current_window()

    @bind('Control-X 1')
    def popdown(self):
        self.fe.popdown_window()

    @bind('Control-X o')
    def other_window(self):
        self.fe.switch_window(1)

    @bind('Control-X e')#XXX
    def split_to_editor(self):
        from .editor import Editor
        self.fe.split_window(Editor(self.fe))

    @bind('Control-X c')#XXX
    def split_to_colordemo(self):
        self.fe.split_window(ColorDemo(self.fe))

    @bind('Control-X t')#XXX
    def test_ui(self):
        streeng = yield from self.read_string('floop> ', content='zoge')
        self.log.debug(
            'AAAA %s',
            ''.join(reversed(streeng)),
            )

    @bind('Meta-[ESCAPE]', 'Meta-:')
    def replhack(self):
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
    def set_config(self, arg: interactive.argument):
        if not arg:
            key = yield from self.read_string('Key: ')
            value = yield from self.read_string('Value: ')
            util.Configurable.set(self, key, value)
            self.context.conf_write()
        else:
            from . import editor
            import pprint
            self.fe.split_window(editor.Editor(
                self.fe,
                content=pprint.pformat(self.context.conf),
                ))

    @bind(*['Meta-%d' % i for i in range(10)] + ['Meta--'])
    def decimal_argument(
            self, key: interactive.keystroke, arg: interactive.argument = 0):
        self.active_keymap = dict(self.keymap)
        for i in range(10):
            self.active_keymap[str(i)] = self.decimal_argument

        if key == '-':
            self.universal_argument = '-'
        elif arg == '-':
            self.universal_argument = -int(key)
        else:
            if not isinstance(arg, int):
                arg = 0
            self.universal_argument = arg * 10 + int(key)

        # retain status quo
        self.this_command = self.last_command

    @bind('Control-U')
    def start_universal_argument(
            self, arg: interactive.argument, key: interactive.keystroke):
        if isinstance(arg, int):
            self.universal_argument = arg # shouldn't do this the second time?

        self.active_keymap = dict(self.keymap)

        for i in range(10):
            self.active_keymap[str(i)] = self.decimal_argument
        self.active_keymap['-'] = self.decimal_argument

        if arg is None:
            self.universal_argument = [key]
        else:
            self.universal_argument = arg + [key]

        # retain status quo
        self.this_command = self.last_command

    @bind('Control-L')
    def reframe(self):
        self.renderer.reframe()


class PagingMixIn:
    @bind('[ppage]', 'Meta-v')
    def pageup(self):
        self.cursor = self.renderer.display_range()[0]
        self.renderer.reframe(action='pageup')

    @bind('[npage]', 'Control-v')
    def pagedown(self):
        self.cursor = self.renderer.display_range()[1]
        self.renderer.reframe(action='pagedown')


class Context:
    # per-session state and abstact control
    def __init__(self, ui):
        self.conf = {}
        self.context = self
        self.conf_read()
        self.ui = ui
        self.ui.context = self
        self.killring = []
        self.log = logging.getLogger('Snipe')
        #XXX kludge so the kludged sending can find the roost backend
        self.roost = roost.Roost(self)
        self.backends = messages.AggregatorBackend(
            self,
            backends = [
                messages.StartupBackend(self),
#                messages.SyntheticBackend(self, conf={'count': 100}),
                self.roost,
                ],)
        from . import messager # we're importing this here to prevent import loop
        self.ui.initial(messager.Messager(self.ui))

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

    # kill ring
    def copy(self, data, append=None):
        if not self.killring or append is None:
            self.killring.append(data)
        else:
            if append:
                self.killring[-1] = self.killring[-1] + data
            else:
                self.killring[-1] = data + self.killring[-1]

    def yank(self, off=1):
        return self.killring[-(1 + (off - 1) % len(self.killring))]

    def shutdown(self):
        self.backends.shutdown()


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

class ColorDemo(Window):
    def view(self, origin=0, direction='forward'):
        yield 0, [
            (('visible', 'fg:green'), 'green '),
            (('fg:white', 'bg:blue'), 'blue'),
            (('fg:cornflower blue',), ' cornflower'),
            (('fg:bisque',), ' bisque '),
            (('bg:#f00',), '#f00'),
            ]
