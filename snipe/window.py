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


import logging
import asyncio

from . import interactive
from . import keymap
from . import util


class Window:
    def __init__(self, frontend, prototype=None, destroy=lambda: None, modes=[]):
        self.fe = frontend
        self.renderer = None
        self.keymap = keymap.Keymap()
        self.keymap.interrogate(self)
        for mode in modes:
            self.keymap.interrogate(mode)
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
            self.log.debug('got key %s', repr(self.active_keymap.unkey(k)))
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
                    window = self,
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
                        self.fe.redisplay(self.redisplay_hint())

                    t = asyncio.Task(catch_and_log(ret))

        except Exception as e:
            self.log.exception('executing command from keymap')
            self.whine(k)
            self.active_keymap = self.keymap

    def check_redisplay_hint(self, hint):
        ret = hint.get('window', None) is self
        self.log.debug('redisplay hint %s -> %s', repr(hint), repr(ret))
        return ret

    def redisplay_hint(self):
        self.log.debug('base redisplay_hint')
        return {'window': self}

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

    @keymap.bind('Control-X Control-C')
    def quit(self):
        asyncio.get_event_loop().stop()

    def whine(self, k):
        self.fe.notify()

    @keymap.bind('Control-Z')
    def stop(self):
        self.fe.sigtstp(None, None)

    def view(self, origin=None, direction=None):
        yield 0, [(('visible',), '')]

    @keymap.bind('Control-X 2')
    def split_window(self):
        self.fe.split_window(self.__class__(self.fe, prototype=self))

    @keymap.bind('Control-X 0')
    def delete_window(self):
        self.fe.delete_current_window()

    @keymap.bind('Control-X 1')
    def popdown(self):
        self.fe.popdown_window()

    @keymap.bind('Control-X o')
    def other_window(self):
        self.fe.switch_window(1)

    @keymap.bind('Control-X e')#XXX
    def split_to_editor(self):
        from .editor import Editor
        self.fe.split_window(Editor(self.fe))

    @keymap.bind('Control-X c')#XXX
    def split_to_colordemo(self):
        self.fe.split_window(ColorDemo(self.fe))

    @keymap.bind('Control-X t')#XXX
    def test_ui(self):
        streeng = yield from self.read_string('floop> ', content='zoge')
        self.log.debug(
            'AAAA %s',
            ''.join(reversed(streeng)),
            )

    @keymap.bind('Meta-[ESCAPE]', 'Meta-:')
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

    @keymap.bind('Meta-=')
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

    @keymap.bind(*['Meta-%d' % i for i in range(10)] + ['Meta--'])
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

    @keymap.bind('Control-U')
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

    @keymap.bind('Control-L')
    def reframe(self):
        self.renderer.reframe()


class PagingMixIn:
    @keymap.bind('[ppage]', 'Meta-v')
    def pageup(self):
        self.cursor = self.renderer.display_range()[0]
        self.renderer.reframe(action='pageup')

    @keymap.bind('[npage]', 'Control-v')
    def pagedown(self):
        self.cursor = self.renderer.display_range()[1]
        self.renderer.reframe(action='pagedown')


class ColorDemo(Window):
    def view(self, origin=0, direction='forward'):
        yield 0, [
            (('visible', 'fg:green'), 'green '),
            (('fg:white', 'bg:blue'), 'blue'),
            (('fg:cornflower blue',), ' cornflower'),
            (('fg:bisque',), ' bisque '),
            (('bg:#f00',), '#f00'),
            ]
