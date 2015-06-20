#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2014 the Snipe contributors
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
snipe.window
------------
'''

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
        self._destroy = destroy
        self.this_command = ''
        self.last_command = ''
        self.last_key = ''
        self.universal_argument = None
        self.keymap_action = interactive.call
        self.intermediate_action = None
        self.keyerror_action = None

        self.noactive = False
        self.noresize = False

    def __repr__(self):
        return '<%s %x>' % (self.__class__.__name__, id(self))

    def destroy(self):
        self._destroy()

    def focus(self):
        return not self.noactive

    @property
    def context(self):
        if self.fe is None:
            return None
        return self.fe.context

    def input_char(self, k):
        self.context.clear()
        try:
            self.log.debug('got key %s', repr(self.active_keymap.unkey(k)))
            try:
                v = self.active_keymap[k]
            except KeyError:
                if self.keyerror_action is not None:
                    self.keyerror_action()
                else:
                    self.context.message('no such key in map')
                    self.active_keymap = self.keymap
                    self.log.error('no such key in map')
                    self.whine(k)
                return

            if self.intermediate_action is not None:
                self.intermediate_action(keystroke = k)
            if not callable(v):
                self.active_keymap = v
            else:
                self.active_keymap = self.keymap
                arg, self.universal_argument = self.universal_argument, None
                self.this_command = getattr(v, '__name__', '?')
                ret = self.keymap_action(
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
                        except Exception as e:
                            self.context.message(str(e))
                            self.log.exception('Executing complex command')
                            self.whine(k)
                        self.fe.redisplay(self.redisplay_hint())

                    t = asyncio.Task(catch_and_log(ret))

        except Exception as e:
            self.context.message(str(e))
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

    def read_string(self, prompt, content=None, height=1, window=None, **kw):
        f = asyncio.Future()

        def done_callback(result):
            f.set_result(result)
            self.fe.popdown_window()#XXX might not always be the right one

        def destroy_callback():
            if not f.done():
                f.set_exception(Exception('Operation Aborted'))

        if window is None:
            from .prompt import ShortPrompt, LongPrompt
            if height > 2:
                window = LongPrompt
            else:
                window = ShortPrompt

        wkw = dict(
            prompt=prompt,
            content=content,
            callback=done_callback,
            destroy=destroy_callback,
            history=self.this_command,
            )
        wkw.update(kw)

        w = window(self.fe, **wkw)
        self.fe.popup_window(w, height=height)
        w.renderer.reframe(-1)
        self.fe.redisplay()

        yield from f

        return f.result()

    def read_filename(self, prompt, content=None):
        result = yield from self.read_string(
            prompt, complete=interactive.complete_filename)

        return result

    def read_keyseq(self, prompt, keymap):
        from .prompt import KeySeqPrompt
        return (yield from self.read_string(
            prompt, window=KeySeqPrompt, keymap=keymap))

    @keymap.bind('Control-X Control-C')
    def quit(self):
        """Quiet snipe."""

        asyncio.get_event_loop().stop()

    def whine(self, k):
        self.fe.notify()

    @keymap.bind('Control-Z')
    def stop(self):
        """Suspend snipe."""
        self.fe.sigtstp(None, None)

    def view(self, origin=None, direction=None):
        yield 0, [(('visible',), '')]

    @keymap.bind('Control-X 2')
    def split_window(self):
        """Split current window."""

        self.fe.split_window(self.__class__(self.fe, prototype=self))

    @keymap.bind('Control-X 0')
    def delete_window(self):
        """Delete the current window."""

        self.fe.delete_current_window()

    @keymap.bind('Control-X 1')
    def delete_other_windows(self):
        """Delete windows that aren't the current window."""

        self.fe.delete_other_windows()

    @keymap.bind('Control-X o')
    def other_window(self):
        """Switch to other window."""

        self.fe.switch_window(1)

    @keymap.bind('Control-X e')#XXX
    def split_to_editor(self):
        """Split to a new editor window."""

        from .editor import Editor
        self.fe.split_window(Editor(self.fe))

    @keymap.bind('Control-X 4 m')
    def split_to_messager(self, filter_new=None):
        """Split to a new messager window."""

        from .messager import Messager
        self.fe.split_window(Messager(
            self.fe,
            prototype = self if isinstance(self, Messager) else None,
            filter_new = filter_new,
            ))

    @keymap.bind('Control-X 4 /')
    def split_to_messager_filter(self):
        """Split to a new messager window with a specified filter."""

        from . import filters
        f = getattr(self, 'filter', None)
        if isinstance(f, filters.Filter):
            s = str(f)
        else:
            s = ''

        s = yield from self.read_string(
            'Filter expression (Control-J when finished):\n', s, 5)

        self.split_to_messager(filter_new=filters.makefilter(s))

    @keymap.bind('Control-X c')#XXX
    def split_to_colordemo(self):
        """Split to a color demo window."""

        self.fe.split_window(ColorDemo(self.fe))

    @keymap.bind('Meta-[ESCAPE]', 'Meta-:')
    def replhack(self):
        """Evaluate python expressions.   Mostly useful for debugging."""

        import traceback
        import pprint
        from .prompt import ShortPrompt

        self.log.debug('entering replhack')

        out = ''
        while True:
            expr = yield from self.read_string(
                out + ':>> ',
                height = len(out.splitlines()) + 2,
                window = ShortPrompt,
                )
            if not expr.strip():
                break
            self.log.debug('got expr %s', expr)
            try:
                ret = eval(expr, globals(), locals())
                out = pprint.pformat(ret)
            except:
                out = traceback.format_exc()
            if out[:-1] != '\n':
                out += '\n'
            self.log.debug('result: %s', out)

    @keymap.bind('Meta-=')
    def set_config(self, arg: interactive.argument):
        """Set a config key.  With a prefix-argument, dump the corrent
        configuration dict to a window."""

        if not arg:
            key = yield from self.read_string(
                'Key: ',
                complete=interactive.completer(
                    util.Configurable.registry.keys()))
            value = yield from self.read_string(
                'Value: ',
                content=str(util.Configurable.get(self, key)))
            util.Configurable.set(self, key, value)
            self.context.conf_write()
        else:
            import pprint
            self.show(pprint.pformat(self.context.conf))

    @keymap.bind(*['Meta-%d' % i for i in range(10)] + ['Meta--'])
    def decimal_argument(
            self, key: interactive.keystroke, arg: interactive.argument = 0):
        """Start a decimal argument."""

        self.active_keymap = keymap.Keymap(self.keymap)
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
        """Universal argument.  Followed by digits sets an integer argument.
        Without digits is interpreted as a four when an integer is needed.  More
        ^Us multiply by four each time.""" #XXX revisit this
        if isinstance(arg, int):
            self.universal_argument = arg # shouldn't do this the second time?

        self.active_keymap = keymap.Keymap(self.keymap)

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
        """Reframe so that the cursor is in the middle of the window.  Repeating
        it tries to put the cursor in the at the top, then the bottom, and then
        cycles."""

        if getattr(self, 'renderer', False):
            if self.last_command != 'reframe':
                self.reframe_state = 0
            self.log.debug('reframe_state=%d', self.reframe_state)
            if self.reframe_state == 0:
                self.renderer.reframe(None)
            elif self.reframe_state == 1:
                self.renderer.reframe(0)
            elif self.reframe_state == 2:
                self.renderer.reframe(-1)
            self.reframe_state = (self.reframe_state + 1) % 3
        self.fe.force_repaint()

    def show(self, string):
        from .editor import Viewer
        self.fe.split_window(Viewer(self.fe, content=string))


class PagingMixIn:
    @keymap.bind('[ppage]', 'Meta-v')
    def pageup(self):
        """Scroll up a windowful."""
        self.cursor = self.renderer.display_range()[0]
        self.renderer.reframe(action='pageup')

    @keymap.bind('[npage]', 'Control-v')
    def pagedown(self):
        """Scroll down a windowful."""
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


class StatusLine(Window):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.noactive = True
        self.noresize = True
        self.clear()

    def view(self, origin=0, direction='forward'):
        yield 0, [
            (('visible', ), self._message),
            (('right', ), '%d' % (self.context.backends.count(),)),
            ]

    def message(self, s):
        self._message = str(s)
        self.fe.redisplay(self.redisplay_hint())

    def clear(self):
        self.message('')

    def check_redisplay_hint(self, hint):
        return True
