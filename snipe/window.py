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
import math

from . import interactive
from . import keymap
from . import util


HELP = """30
===============================
Common commands in all windows
===============================

.. interrogate_keymap:: Window
"""


class Window:
    """
    Abstract chunk of screen real estate that displays things and can
    potentially take input.

    :param frontend: front-object to be associated with
    :param prototype: Window object to copy state from
    :type prototype: Window or None
    :param destroy: cleanup callback
    :type destroy: function with no arguments
    :param modes: behavior-modifying mixins
    """

    cheatsheet = [
        'You',
        "shouldn't",
        'be',
        'seeing',
        'this',
        '*^X^C* quit',
        '*^Z* suspend',
        '*?* help',
        ]

    def __init__(
            self, frontend, prototype=None, destroy=lambda: None, modes=[]):
        self.fe = frontend
        self.renderer = None  # : associated renderer object
        self.keymap = keymap.Keymap()  # : assciated keymap
        self.keymap.interrogate(self)
        for mode in modes:
            self.keymap.interrogate(mode)
            if hasattr(mode, 'cheatsheet'):
                self.cheatsheet = list(self.cheatsheet) + mode.cheatsheet
        self.active_keymap = self.keymap
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))
        if prototype is None:
            self.cursor = None  # : current location
            self.hints = {}
        else:
            self.cursor = prototype.cursor
            self.hints = prototype.renderer.get_hints()
        self._destroy = destroy
        self.this_command = ''  # : name of currently executing command
        self.last_command = ''  # : name of previous command
        self.last_key = ''  # : last key stroke processed
        self.universal_argument = None  # : current universal argument
        # : callback for completed keysequence in kyempa
        self.keymap_action = interactive.call
        # : callback for keystroke in incomplete keysequence
        self.intermediate_action = None
        # : callback for completed keysequence not in keymap
        self.keyerror_action = None
        # : callback for keymap we just "installed"
        self.activated_keymap = self.maybe_install_cheatsheet

        self.noactive = False  # : don't let this window get focus
        self.noresize = False  # : don't resize this window

        self._normal_cheatsheet = self.cheatsheet
        # : string describing the keystrokes that triggered the current command
        self.keyseq = ''
        # : string that is currently being search for
        self.search_term = None

    def set_cheatsheet(self, cheatsheet):
        self.cheatsheet = cheatsheet
        self._normal_cheatsheet = cheatsheet

    def maybe_install_cheatsheet(self, keymap):
        """Install a cheatsheet if there's one hiding in the keymap"""
        self.cheatsheet = keymap.get_cheatsheet(self._normal_cheatsheet)

    def keyecho(self, keystroke):
        """Echo an in-progress key sequence to the statusline."""
        self.context.keyecho(keystroke)

    # Programmatic interface:

    def __repr__(self):
        return '<%s %x>' % (self.__class__.__name__, id(self))

    def destroy(self):
        """Called by the frontend when the window is removed from the UI.
        Calls the cleanup callback."""

        self._destroy()

    def focus(self):
        """Called by the frontend when the window is focused.
        Returns False."""

        return not self.noactive

    @property
    def context(self):
        """The global context object."""

        if self.fe is None:
            return None
        return self.fe.context

    def input_char(self, k):
        """Called by the frontend for every keystroke from the user.

        :param k: The incoming keystroke."""

        self.context.clear()
        try:
            self.log.debug(
                'got key %s = %s', repr(self.active_keymap.unkey(k)), repr(k))

            if self.intermediate_action is not None:
                self.intermediate_action(keystroke=k)

            try:
                v = self.active_keymap[k]
            except KeyError:
                if self.keyerror_action is not None:
                    self.keyerror_action(k)
                else:
                    self.context.message('unknown command')
                    self.active_keymap = self.keymap
                    self.keyseq = ''
                    self.log.error('no such key in map')
                    self.whine(k)
                return

            self.keyseq = (
                self.keyseq + self.keymap.unkey(k, compact=True) + ' ')

            if not callable(v):
                self.active_keymap = v
            else:
                self.active_keymap = self.keymap
                keyseq = self.keyseq
                self.keyseq = ''
                arg, self.universal_argument = self.universal_argument, None
                self.this_command = getattr(v, '__name__', '?')
                try:
                    self.before_command()
                    ret = self.keymap_action(
                        v,
                        context=self.context,
                        window=self,
                        keystroke=k,
                        argument=arg,
                        keyseq=keyseq,
                        keymap=self.keymap,
                        )
                finally:
                    self.after_command()
                    self.last_command = self.this_command
                    self.last_key = k

                if asyncio.iscoroutine(ret):
                    asyncio.Task(self.catch_and_log(ret))

        except Exception as e:
            self.context.message(str(e))
            self.log.exception('executing command from keymap')
            self.whine(k)
            self.active_keymap = self.keymap
        finally:
            if self.activated_keymap is not None:
                self.activated_keymap(self.active_keymap)
            if self.keyseq:
                self.keyecho(self.keyseq)

    @asyncio.coroutine
    def catch_and_log(self, coro):
        try:
            yield from coro
        except Exception as e:
            self.context.message(str(e))
            self.log.exception('Executing complex command')
            self.whine('')
        self.redisplay()

    def check_redisplay_hint(self, hint):
        """See if a redisplay hint dict applies to this window.  Called by the
        frontend to see if something has triggered an applicable redisplay.

        :param dict hint: The hint in question
        """

        ret = hint.get('window', None) is self
        return ret

    def redisplay(self):
        self.fe.redisplay(self.redisplay_hint())

    def redisplay_hint(self):
        """Return an appropriate redisplay hint."""

        self.log.debug('base redisplay_hint')
        return {'window': self}

    def view(self, origin=None, direction=None):
        """Called by the frontend to iterate through the visible contents of the
        window.

        :param origin: a cursor object saying where to start
        :param direction: which direction to walk
        :type direction: 'forward' or 'backward'

        Yields tuple pairs of ``cursor, chunk``

        Where ``cursor`` is a possible value for ``origin`` or the ``cursor``
        instance variable, and chunk is a list of tuple-pairs of lists of
        attributes (themselves) represented as strings, and strings to be
        displayed, e.g.

        .. code-block:: python

             [(('bold', 'visible'), 'some bold text, '), ((), 'Some normal text\\n')]

        Each chunk may be assumed to end a line.
        """  # noqa: E501
        yield 0, [(('visible',), '')]

    def before_command(self):
        """Executed before an interactive command."""
        pass

    def after_command(self):
        """Executed after an interactive command."""
        pass

    def quit_hook(self):
        """Called on visible windows just before quitting."""
        pass

    def title(self):
        return self.__class__.__name__

    def modeline(self):
        return [((), self.title())], \
          [(('right',), '%d' % (self.context.backends.count(),))]

    # Convenience functions for interacting with the user

    def whine(self, k=''):
        """Tell the frontend to flash the screen."""
        self.fe.notify()

    def read_string(
            self,
            prompt,
            content=None,
            height=1,
            window=None,
            name='Prompt',
            validate=None,
            near=False,
            **kw):
        """Pop a prompt window to read a string from the user.

        :param str prompt: The prompt string
        :param str content: The initial contents of the input
        :param int height: Height of the input area
        :param Window window: Type of window object to use
        :param str name: Name for the editor buffer
        """

        f = asyncio.Future()

        w = None  # for the following to capture

        def done_callback(result):
            if validate is not None:
                if not validate(result):
                    raise util.SnipeException('unspecified validation error')
            f.set_result(result)
            self.fe.delete_window_window(w)

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
            name=name,
            )
        wkw.update(kw)

        w = window(self.fe, **wkw)
        self.fe.popup_window(w, height=height, whence=self, near=near)
        w.renderer.reframe(-1)
        self.fe.redisplay()

        yield from f

        return f.result()

    def read_filename(self, prompt, content=None, name='filename'):
        """Use self.read_string to read a filename from the user.

        :param str prompt: The prompt string
        :param str content: The initial contents of the input
        """

        result = yield from self.read_string(
            prompt,
            content=content,
            completer=interactive.FileCompleter(),
            name=name,
            )

        return result

    def read_keyseq(self, prompt, keymap, name='key sequence'):
        """Read a keymap key sequence from the user.

        :param str prompt: The prompt string
        :param str keymap: The keymap read the sequence for
        """
        from .prompt import KeySeqPrompt
        return (yield from self.read_string(
            prompt, window=KeySeqPrompt, keymap=keymap, name=name))

    def show(self, string, what='what'):
        """Display a string in a popup Viewer window."""
        from .editor import PopViewer
        self.fe.split_window(
            PopViewer(self.fe, content=string, name=what), True)

    # Commands the user can run that should be more or less present in
    # all windows.

    @keymap.bind('Control-X Control-C')
    def quit(self):
        """Quit snipe."""

        for w in self.fe.get_windows():
            w.quit_hook()

        asyncio.get_event_loop().stop()

    @keymap.bind('Control-Z')
    def stop(self):
        """Suspend snipe."""
        self.fe.sigtstp(None, None)

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

    @keymap.bind('Control-X e')  # XXX
    def split_to_editor(self):
        """Split to a new editor window."""

        from .editor import Editor
        self.fe.split_window(Editor(self.fe), True)

    @keymap.bind('Control-X 4 m')
    def split_to_messager(self, filter_new=None):
        """Split to a new messager window."""

        from .messager import Messager
        self.fe.split_window(
            Messager(
                self.fe,
                prototype=self if isinstance(self, Messager) else None,
                filter_new=filter_new,
                ),
            True,
            )

    @keymap.bind('Control-X 4 :')
    def split_to_repl(self):
        """Split to a new REPL window"""

        from .repl import REPL
        self.fe.split_window(REPL(self.fe), True)

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
            'Filter expression (^C^C when finished):\n',
            content=s,
            height=5,
            name='filter expression',
            )

        self.split_to_messager(filter_new=filters.makefilter(s))

    @keymap.bind('Control-X c')  # XXX
    def split_to_colordemo(self):
        """Split to a color demo window."""

        self.fe.split_window(ColorDemo(self.fe))

    def setup_playground(self):
        import sys

        if not hasattr(self, '_playground'):
            self._playground = {}
            self._playground.update(sys.modules)
            self._playground['window'] = self
            self._playground['context'] = self.context

    @keymap.bind('Meta-[ESCAPE]', 'Meta-:')
    def replhack(self):
        """Evaluate python expressions.   Mostly useful for debugging."""

        from .prompt import ShortPrompt

        self.log.debug('entering replhack')

        self.setup_playground()

        out = ''
        while True:
            expr = yield from self.read_string(
                out + '>>> ',
                height=len(out.splitlines()) + 2,
                window=ShortPrompt,
                name='*python*'
                )
            if not expr.strip():
                break
            self.log.debug('got expr %s', expr)
            out = util.eval_output(expr, self._playground)
            if out is None:
                out = 'Incomplete command\n'
            self.log.debug('result: %s', out)

    @keymap.bind('Meta-=')
    def set_config(self, arg: interactive.argument):
        """Set a config key.  With a prefix-argument, dump the current
        configuration dict to a window."""

        if not arg:
            key = yield from self.read_oneof(
                'Key: ',
                util.Configurable.registry.keys(),
                height=2,
                name='configuration key',
                )
            if util.Configurable.registry[key].oneof:
                value = yield from self.read_oneof(
                    'Value: ',
                    util.Configurable.registry[key].oneof,
                    content=str(util.Configurable.get(self, key)),
                    name='configuration value',
                    )
            else:
                value = yield from self.read_string(
                    'Value: ',
                    content=str(util.Configurable.get(self, key)),
                    name='configuration value',
                    )
            util.Configurable.set(self, key, value)
            self.context.conf_write()
        else:
            import pprint
            self.show(pprint.pformat(self.context.conf))

    @asyncio.coroutine
    def read_oneof(
            self, prompt, candidates, content=None, height=1, name='Prompt'):
        from .prompt import ShortPrompt

        return (yield from self.read_string(
            prompt,
            window=ShortPrompt,
            height=height,
            content=content,
            completer=interactive.Completer(candidates),
            name=name,
            ))

    @keymap.bind(*['Meta-%d' % i for i in range(10)] + ['Meta--'])
    def decimal_argument(
            self,
            key: interactive.keystroke,
            keyseq: interactive.keyseq,
            arg: interactive.argument = 0):
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
        self.keyseq = keyseq

    @keymap.bind('Control-U')
    def start_universal_argument(
            self,
            arg: interactive.argument,
            keyseq: interactive.keyseq,
            key: interactive.keystroke):
        """Universal argument.  Followed by digits sets an integer argument.
        Without digits is interpreted as a four when an integer is needed.
        More ^Us multiply by four each time."""  # XXX revisit this

        if isinstance(arg, int):
            self.universal_argument = arg  # shouldn't do this the second time?

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
        self.keyseq = keyseq

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

    @keymap.bind('Control-S')
    def search_forward(self, string=None):
        """Search forwards."""
        self.log.error('search_forward')
        yield from self.search(string, forward=True)

    @keymap.bind('Control-R')
    def search_backward(self, string=None):
        """Search backwards."""
        yield from self.search(string, forward=False)

    @asyncio.coroutine
    def search(self, string=None, forward=True):
        self.match('')  # probe to make sure this is supported here
        if string is None:
            from .prompt import Search
            self.log.error('search: string is none')
            string = yield from self.read_string(
                'search ',
                name='search',
                history='search',
                window=Search,
                target=self,
                forward=forward,
                start=self.make_mark(self.cursor),
                near=True,
                )
        else:
            self.find(string, forward)

    def find(self, string, forward=True):
        raise NotImplementedError

    def match(self, string, forward=True):
        raise NotImplementedError

    def beginning(self):
        raise NotImplementedError

    def end(self):
        raise NotImplementedError

    def make_mark(self, where):
        return None

    def go_mark(self, where):
        pass


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
    KEYTAGS = ('bold',)
    CHEATSHEET_SPLITCOLS = 160

    show_cheatsheet = util.Configurable(
        'cheatsheet',
        True,
        'show the cheatsheet',
        action=lambda context, value: context.ui.resize_statuswindow(),
        coerce=util.coerce_bool,
        )

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.noactive = True
        self.noresize = True
        self.clear()

    def view(self, origin=0, direction='forward'):
        # this is a "friend" class to the stuff in ttyfe for now
        try:
            active = self.fe.windows[self.fe.output].window
        except IndexError:
            active = self
        left, right = active.modeline()

        renderer = self.renderer

        if not left:
            left = []

        if self._message:
            left = self._message

        rightwidth = sum(
            util.glyphwidth(text) for (tags, text) in right)

        offset = 0
        for (i, (tags, text)) in enumerate(left):
            textwidth = util.glyphwidth(text)
            remaining = renderer.width - rightwidth - offset - 1
            if textwidth > remaining:
                # XXX bugs on wide characters, need fe.truncate
                left[i:] = [(tags, '…' + text[len(text) - remaining + 1:])]
                break
            offset += textwidth

        left = [(('visible',), '')] + left

        yield 0, left + right + self.do_cheatsheet(active)

    def do_cheatsheet(self, w):
        if not self.show_cheatsheet:
            return []

        sheet = [
            self.cheatsheetify(x) for x in getattr(w, 'cheatsheet', ['*?*'])]

        widths = [
            sum(util.glyphwidth(text) for (tags, text) in item)
            for item in sheet]

        rows = 2 if self.fe.maxx < self.CHEATSHEET_SPLITCOLS else 1
        cols = math.ceil(len(sheet) / rows)

        colwidth = max(widths) + 1
        colwidth = colwidth + max(self.fe.maxx - colwidth * cols, 0) // cols

        out = []

        sheetrows = [sheet[i::rows] for i in range(rows)]
        widthrows = [widths[i::rows] for i in range(rows)]

        for (row, widths) in zip(sheetrows, widthrows):
            pads = [((), ' ' * (colwidth - w))
                    for w in widths[:-1]] + [((), '\n')]
            out += sum((x + [p] for (x, p) in zip(row, pads)), [])

        return out

    def message(self, s, tags=('fg:white', 'bg:red')):
        self._message = [(tags, str(s))]
        self.redisplay()

    def clear(self):
        self._message = []

    def check_redisplay_hint(self, hint):
        return True

    def height(self):
        sheet_height = 1
        if self.fe.maxx < self.CHEATSHEET_SPLITCOLS:
            self.log.debug('maxx = %d', self.fe.maxx)
            sheet_height = 2
        if self.show_cheatsheet:
            return 1 + sheet_height
        else:
            return 1

    @classmethod
    def cheatsheetify(klass, s):
        def untag(t):
            return () if t else klass.KEYTAGS
        out = [((), '')]
        while s != '':
            if s[0] == '*':
                if len(out) == 1 and out[-1][1] == '':
                    out = [(untag(out[-1][0]), '')]
                elif out[-1][1] == '':
                    del out[-1]
                else:
                    out.append((untag(out[-1][0]), ''))
            else:
                if s[0] == '\\':
                    s = s[1:]
                out[-1] = (out[-1][0], out[-1][1] + s[0])
            s = s[1:]
        if out[-1][1] == '':
            del out[-1]
        return out
