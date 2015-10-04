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
snipe.help
----------
'''

import inspect

from . import window
from . import keymap
from . import interactive
from . import util
from . import editor


class Help(editor.Viewer):
    START = (
        '?: top  b: key bindings  k: describe key  L: License\n' +
        'q: back to what you were doing')
    BANNER = '[pageup/pagedown to scroll, q to quit]\n'

    def __init__(self, *args, caller=None, **kw):
        self.caller = caller
        kw.setdefault('name', '*help*')
        super().__init__(*args, **kw)
        self.start()

    def display(self, text):
        # should adjust window size or whatnot
        self.cursor.point = 0
        self.replace(len(self.buf), text)

    @keymap.bind('?', '[escape] ?') # really should give increasingly basic help
    def start(self):
        """Go to the help splash screen."""

        self.display(self.START)

    @keymap.bind('L')
    def license(self):
        """Display the license."""

        self.display(self.BANNER + util.LICENSE)

    @keymap.bind('q', 'Q', '[Escape] [Escape]')
    def exit_help(self):
        """Exit help."""

        self.fe.popdown_window()

    @keymap.bind('b')
    def describe_bindings(self):
        """Describe the bindings of the window we entered help from."""

        self.display(self.BANNER + str(self.caller.keymap))

    @keymap.bind('k')
    def describe_key(self):
        """Read a keysequence and display its documentation."""

        keystrokes, func = yield from self.read_keyseq(
            'Describe key? ', self.caller.keymap)
        keyseq = ' '.join(self.keymap.unkey(k) for k in keystrokes)
        if func is None:
            out = '"%s" is not bound to anything' % (keyseq,)
        else:
            out = '"%s" is bound to %s' % (
                keyseq, getattr(func, '__name__', '???'))
            if hasattr(func, '__doc__'):
                out += '\n\n' + inspect.getdoc(func)
        self.display(self.BANNER + out)



@keymap.bind('?', '[escape] ?')
def help(window: interactive.window):
    """Help."""

    window.fe.popup_window(Help(window.fe, caller=window), height=10)
    window.fe.redisplay()


