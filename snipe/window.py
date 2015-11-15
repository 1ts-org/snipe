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
import itertools
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

    def __init__(self, frontend, prototype=None, destroy=lambda: None, modes=[]):
        self.fe = frontend
        self.renderer = None #: associated renderer object
        self.keymap = keymap.Keymap() #: assciated keymap
        self.keymap.interrogate(self)
        for mode in modes:
            self.keymap.interrogate(mode)
        self.active_keymap = self.keymap
        self.log = logging.getLogger(
            '%s.%x' % (self.__class__.__name__, id(self),))
        if prototype is None:
            self.cursor = None #: current location
            self.hints = {}
        else:
            self.cursor = prototype.cursor
            self.hints = prototype.renderer.get_hints()
        self._destroy = destroy
        self.this_command = '' #: name of currently executing command
        self.last_command = '' #: name of previous command
        self.last_key = '' #: last key stroke processed
        self.universal_argument = None #: current universal argument
        #: callback for completed keysequence in kyempa
        self.keymap_action = interactive.call
        #: callback for keystroke in incomplete keysequence
        self.intermediate_action = None
        #: callback for completed keysequence not in keymap
        self.keyerror_action = None

        self.noactive = False #: don't let this window get focus
        self.noresize = False #: don't resize this window

    # Programmatic interface:

    def __repr__(self):
        return '<%s %x>' % (self.__class__.__name__, id(self))

    def destroy(self):
        """Called by the frontend when the window is removed from the UI.
        Calls the cleanup callback."""

        self._destroy()

    def focus(self):
        """Called by the frontend when the window is focused.  Returns False."""

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
            self.log.debug('got key %s', repr(self.active_keymap.unkey(k)))

            if self.intermediate_action is not None:
                self.intermediate_action(keystroke = k)

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

            if not callable(v):
                self.active_keymap = v
            else:
                self.active_keymap = self.keymap
                arg, self.universal_argument = self.universal_argument, None
                self.this_command = getattr(v, '__name__', '?')
                try:
                    ret = self.keymap_action(
                        v,
                        context = self.context,
                        window = self,
                        keystroke = k,
                        argument = arg,
                        )
                finally:
                    self.after_command()
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
        """See if a redisplay hint dict applies to this window.  Called by the
        frontend to see if something has triggered an applicable redisplay.

        :param dict hint: The hint in question
        """

        ret = hint.get('window', None) is self
        self.log.debug('redisplay hint %s -> %s', repr(hint), repr(ret))
        return ret

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
        """
        yield 0, [(('visible',), '')]

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

    def whine(self, k):
        """Tell the frontend to flash the screen."""
        self.fe.notify()

    def read_string(
            self,
            prompt,
            content=None,
            height=1,
            window=None,
            name='Prompt',
            **kw):
        """Pop a prompt window to read a string from the user.

        :param str prompt: The prompt string
        :param str content: The initial contents of the input
        :param int height: Height of the input area
        :param Window window: Type of window object to use
        :param str name: Name for the editor buffer
        """

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
            name=name,
            )
        wkw.update(kw)

        w = window(self.fe, **wkw)
        self.fe.popup_window(w, height=height)
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
            prompt, complete=interactive.complete_filename, name=name)

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
        from .editor import Viewer
        self.fe.split_window(Viewer(self.fe, content=string, name=what), True)

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

    @keymap.bind('Control-X e')#XXX
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
                prototype = self if isinstance(self, Messager) else None,
                filter_new = filter_new,
                ),
            True,
            )

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
            'Filter expression (Control-J when finished):\n',
            content=s,
            height=5,
            name='filter expression',
            )

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
                name = '*python*'
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
            key = yield from self.read_oneof(
                'Key: ',
                util.Configurable.registry.keys(),
                height=2,
                name='configuration key',
                )
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
    def read_oneof(self, prompt, these, height=1, name='Prompt'):
        from .prompt import LeapPrompt

        return (yield from self.read_string(
            prompt,
            window=LeapPrompt,
            height=height,
            candidates=these,
            complete=interactive.completer(these),
            name=name,
            ))

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
    KEYTAGS = ('bg:grey24', 'bold')
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
        active = self.fe.windows[self.fe.active].window
        left, right = active.modeline()
        renderer = self.renderer

        if not left:
            left = []

        if self._message:
            left = [(('fg:white', 'bg:red'), self._message)]

        rightwidth = sum(
                self.renderer.glyphwidth(text) for (tags, text) in right)

        offset = 0
        for (i, (tags, text)) in enumerate(left):
            textwidth = self.renderer.glyphwidth(text)
            remaining = renderer.width - rightwidth - offset
            if textwidth > remaining:
                #XXX bugs on wide characters, need fe.truncate
                left[i:] = [(tags, text[:remaining - 1] + '…')]
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
            sum(self.renderer.glyphwidth(text) for (tags, text) in item)
            for item in sheet]


        rows = 2 if self.fe.maxx < self.CHEATSHEET_SPLITCOLS else 1
        cols = math.ceil(len(sheet) / rows)

        colwidth = max(widths) + 1
        colwidth = colwidth + max(self.fe.maxx - colwidth * cols, 0) // cols

        out = []

        sheetrows = [sheet[i::rows] for i in range(rows)]
        widthrows = [widths[i::rows] for i in range(rows)]

        for (row, widths) in zip(sheetrows, widthrows):
            pads = [((), ' ' * (colwidth - w)) for w in widths[:-1]] + [((), '\n')]
            out += sum((x + [p] for (x, p) in zip(row, pads)), [])

        return out

    def message(self, s):
        self._message = str(s)
        self.fe.redisplay(self.redisplay_hint())

    def clear(self):
        self.message('')

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
        untag = lambda t: () if t else klass.KEYTAGS
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
