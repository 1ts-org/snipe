# -*- encoding: utf-8 -*-
# Copyright © 2017 the Snipe contributors
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
snipe.repl
------------

Editor subclass for a python REPL
'''


import sys

from . import editor
from . import keymap
from . import util


class REPL(editor.Editor):
    def __init__(self, *args, **kw):
        kw.setdefault('name', 'REPL')
        super().__init__(*args, **kw)
        self.high_water_mark = self.buf.mark(0)
        self.ps1 = '>>> '
        self.output(util.SPLASH)
        # YYY
        import _sitebuiltins
        _sitebuiltins._Printer.MAXLINES=99999999999999999
        cprt = (
            'Type "help", "copyright", "credits" or "license" for more'
            ' information.')
        self.output("Python %s on %s\n%s\n" % (
            sys.version, sys.platform, cprt))
        self.output(self.ps1)
        self.environment = {}

    def output(self, s):
        self.high_water_mark.point = len(self.buf)
        self.high_water_mark.insert(s)
        self.cursor.point = self.high_water_mark

    def writable(self):
        return self.cursor >= self.high_water_mark

    def go_eval(self):
        input = self.buf[self.high_water_mark:]
        self.log.error('go: %s', input)
        # XXX should do something to indicate that input was accepted
        with self.save_excursion():
            self.end_of_buffer()
            self.insert('\n')
            self.redisplay()
            self.undo()
        result = util.eval_output(input, self.environment)
        if result is not None:
            self.output('\n')
            self.log.error('go: %s', result)
            self.output(result)
            self.output(self.ps1)
        return result is not None

    @keymap.bind('Control-M')
    def go2(self):
        if not self.go_eval():
            self.insert('\n')

    @keymap.bind('Control-C Control-C', 'Control-J')
    def go(self):
        if not self.go_eval():
            self.message('incomplete input')
