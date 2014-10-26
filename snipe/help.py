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


from . import window
from . import keymap
from . import interactive
from . import util


class Help(window.Window, window.PagingMixIn):
    START = '?: top  b: key bindings  L: License  q: back to what you were doing'
    BANNER = '[pageup/pagedown to scroll]\n'

    def __init__(self, *args, **kw):
        self.caller = kw['caller']
        del kw['caller']
        super().__init__(*args, **kw)
        self.start()

    def view(self, origin=0, direction='forward'):
        yield 0, [(('visible'), self.content)]

    def display(self, text):
        # should adjust window size or whatnot
        self.content = text

    @keymap.bind('?', '[escape] ?') # really should give increasingly basic help
    def start(self):
        self.content = self.START

    @keymap.bind('L')
    def license(self):
        self.content = self.BANNER + util.LICENSE

    @keymap.bind('q', 'Q', '[Escape] [Escape]')
    def exit_help(self):
        self.fe.popdown_window()

    @keymap.bind('b')
    def describe_bindings(self):
        self.content = self.BANNER + str(self.caller.keymap)



@keymap.bind('?', '[escape] ?')
def help(window: interactive.window):
    window.fe.popup_window(Help(window.fe, caller=window), height=10)
    window.fe.redisplay()

