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
import time
import asyncio
import json
import datetime

from . import messages
from . import ttyfe
from . import roost
from . import filters
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
            self.frame = None
            self.sill = None
        else:
            self.cursor = prototype.cursor
            self.frame = prototype.frame
            self.sill = prototype.sill
        self.destroy = destroy
        self.last_command = None
        self.last_key = None

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
                ret = interactive.call(v, self.context, k)
                self.last_command = getattr(v, '__name__', '?')
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
    def set_config(self):
        key = yield from self.read_string('Key: ')
        value = yield from self.read_string('Value: ')
        util.Configurable.set(self, key, value)
        self.context.conf_write()


class PagingMixIn:
    @bind('[ppage]', 'Meta-v')
    def pageup(self):
        self.cursor = self.frame
        self.renderer.reframe(-1)

    @bind('[npage]', 'Control-v')
    def pagedown(self):
        self.cursor = self.sill
        self.renderer.reframe(1)


class Messager(Window, PagingMixIn):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cursor = next(self.fe.context.backends.walk(time.time(), False))
        self.frame = self.cursor
        self.filter_reset()
        self.secondary = None
        self.keymap['[space]'] = self.pagedown
        self.rules = []
        for (filt, decor) in self.context.conf.get('rules', []):
            try:
                self.rules.append((filters.makefilter(filt), decor))
            except:
                self.log.exception(
                    'error in filter %s for decor %s', filt, decor)

    def focus(self):
        if self.secondary is not None:
            self.cursor = self.secondary
            self.secondary = None

    def walk(self, origin, direction):
        return self.fe.context.backends.walk(origin, direction, self.filter)

    def view(self, origin, direction='forward'):
        it = self.walk(origin, direction != 'forward')
        try:
            next(it)
            prev = next(it)
        except StopIteration:
            prev = None

        for x in self.walk(origin, direction == 'forward'):
            decoration = {}
            for filt, decor in self.rules:
                if filt(x):
                    decoration.update(decor)
            chunk = x.display(decoration)

            def dateof(m):
                if m is None or m.time in (float('inf'), float('-inf')):
                    return None
                return datetime.datetime.fromtimestamp(m.time).date()

            if x.time != float('inf') and (dateof(prev) != dateof(x)):
                    yield x, [(
                    ('bold',),
                    time.strftime('\n%A, %B %d, %Y\n\n', time.localtime(x.time)))]

            if x is self.cursor or x is self.secondary:
                if not chunk:
                    # this is a bug so it will do the wrong thing sometimes
                    yield x, [(('visible', 'standout'), '\n')]
                    continue

                # carve off the first line
                first = []
                while True:
                    if not chunk:
                        # we ran out of chunks without hitting a \n
                        first[-1] = (first[-1][0], first[-1][1] + '\n')
                        break
                    tags, text = chunk[0]
                    if '\n' not in text:
                        first.append((tags, text))
                        chunk = chunk[1:]
                    else:
                        line, rest = text.split('\n', 1)
                        first.append((tags, line + '\n'))
                        chunk = [(tags, rest)] + chunk[1:]
                        break

                if x is self.cursor:
                    first = (
                        [(first[0][0] + ('visible',), first[0][1])] + first[1:])
                if x is self.secondary or self.secondary is None:
                    first = [
                        (tags + ('standout',), text) for (tags, text) in first]
                yield x, first + chunk
            else:
                yield x, chunk

            prev = x

    def check_redisplay_hint(self, hint):
        if super().check_redisplay_hint(hint):
            return True
        mrange = hint.get('messages')
        if mrange:
            m1, m2 = mrange
            self.log.debug('frame=%s, sill=%s', repr(self.frame), repr(self.sill))
            self.log.debug('m1=%s, m2=%s', repr(m1), repr(m2))
            self.log.debug('max(frame, m1)=%s', repr(max(self.frame, m1)))
            self.log.debug('min(sill, m2)=%s', repr(min(self.sill, m2)))
            if max(self.frame, m1) <= min(self.sill, m2):
                self.log.debug('True!')
                return True
        self.log.debug("Fals.e")
        return False

    @bind('n', 'j', '[down]')
    def next_message(self):
        self.move(True)

    @bind('p', 'k', '[up]')
    def prev_message(self):
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
    def send(self, recipient=''):
        if self.sill.time == float('inf'): #XXX omega message is visible
            self.secondary = self.cursor
            self.cursor = self.sill
        message = yield from self.read_string(
            '[roost] send --> ',
            height=10,
            content=recipient + '\n' if recipient else '',
            )
        params, body = message.split('\n', 1)
        yield from self.fe.context.roost.send(params, body)

    def replymsg(self):
        replymsg = self.cursor
        if replymsg.time == float('inf'):
            it = self.walk(self.cursor, False)
            next(it)
            replymsg = next(it)
        return replymsg

    @bind('f')
    def followup(self):
        yield from self.send(self.replymsg().followupstr())

    @bind('r')
    def reply(self, k):
        yield from self.send(self.replymsg().replystr())

    @bind('[END]', 'Shift-[END]', '[SEND]', 'Meta->', '>')
    def last(self):
        self.cursor = next(self.walk(float('inf'), False))

    @bind('[HOME]', 'Shift-[HOME]', '[SHOME]', 'Meta-<', '<')
    def first(self):
        self.cursor = next(self.walk(float('-inf'), True))

    @bind('Meta-/ 0')
    def filter_reset(self):
        self.filter = None
        self.filter_stack = []

    @bind('Meta-/ =')
    def filter_edit(self):
        s = '' if self.filter is None else str(self.filter)

        s = yield from self.read_string('Filter expression:\n', s, 5)

        self.filter = filters.makefilter(s)

        self.cursor = next(self.walk(self.cursor, True))

    @bind('Meta-/ -')
    def filter_everything(self):
        self.filter_push_and_replace(filters.No())

    def filter_clear_decorate(self, decoration):
        self.rules = [
            (filt, decor) for (filt, decor) in self.rules if filt != self.filter]
        self.rules.append((self.filter, decoration))
        self.context.conf['rules'] = [
            (filts, decor)
            for (filts, decor) in self.context.conf.get('rules', [])
            if filts != str(self.filter)
            ]
        self.context.conf['rules'].append((str(self.filter), decoration))
        self.context.conf_write()
        self.filter = None

    @bind('Meta-/ g')
    def filter_foreground_background(self):
        fg = yield from self.read_string('Foreground: ')
        bg = yield from self.read_string('Background: ')
        self.filter_clear_decorate({'foreground': fg, 'background': bg})

    @bind('Meta-/ f')
    def filter_foreground(self):
        fg = yield from self.read_string('Foreground: ')
        self.filter_clear_decorate({'foreground': fg})

    @bind('Meta-/ b')
    def filter_background(self):
        bg = yield from self.read_string('Background: ')
        self.filter_clear_decorate({'background': bg})

    def filter_push_and_replace(self, new_filter):
        if self.filter is not None:
            self.filter_stack.append(self.filter)
        self.filter = new_filter

        self.cursor = next(self.walk(self.cursor, True))

    def filter_push(self, new_filter):
        if self.filter is None:
            self.filter_push_and_replace(new_filter)
        else:
            self.filter_push_and_replace(filters.And(self.filter, new_filter))

    @bind('Meta-/ c')
    def filter_class(self):
        class_ = yield from self.read_string(
            'Class: ', self.cursor.field('class'))
        self.filter_push(filters.Compare('=', 'class', class_))

    @bind('Meta-/ C')
    def filter_class_exactly(self):
        class_ = yield from self.read_string(
            'Class: ', self.cursor.field('class', False))
        self.filter_push(filters.Compare('==', 'class', class_))

    @bind('Meta-/ p')
    def filter_personals(self):
        self.filter_push(filters.Truth('personal'))

    @bind('Meta-/ s')
    def filter_sender(self):
        sender = yield from self.read_string(
            'Sender: ', self.cursor.field('sender'))
        self.filter_push(filters.Compare('=', 'sender', sender))

    @bind('Meta-/ /')
    def filter_cleverly(self):
        message = self.cursor
        if message.personal:
            if str(message.sender) == message.backend.principal:
                conversant = message.field('recipient')
            else:
                conversant = message.field('sender')
            self.filter_push(
                filters.And(
                    filters.Truth('personal'),
                    filters.Or(
                        filters.Compare('=', 'sender', conversant),
                        filters.Compare('=', 'recipient', conversant))))
        elif message.field('class'):
            self.filter_push(
                filters.Compare('=', 'class', message.field('class')))
        else:
            self.whine("Can't deduce what to filter on")

    @bind("Meta-/ Meta-/")
    def filter_pop(self):
        if not self.filter_stack:
            self.filter = None
        else:
            self.filter = self.filter_stack.pop()

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
