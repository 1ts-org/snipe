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

import contextlib
import inspect
import os

from typing import (NewType, Union, List, Optional, TYPE_CHECKING)

from . import util

if TYPE_CHECKING:  # pragma: nocover
    from . import window as _window  # noqa: F401
    from . import keymap as _keymap  # noqa: F401


def _keyword(name):
    def __get_keyword(*args, **kw):
        return kw.get(name, None)
    return __get_keyword


if not TYPE_CHECKING:
    window = _keyword('window')
    keystroke = _keyword('keystroke')
    keyseq = _keyword('keyseq')
    keymap = _keyword('keymap')
    argument = _keyword('argument')
else:  # pragma: nocover
    window = NewType('window', '_window.Window')
    keystroke = Union[int, str]
    keyseq = str
    keymap = NewType('keymap', '_keymap.Keymap')
    argument = Union[None, int, str, List[keystroke]]


if not TYPE_CHECKING:
    def integer_argument(*args, **kw):
        arg = kw.get('argument', None)
        if isinstance(arg, int) or arg is None:
            return arg
        if arg == '-':
            return -1
        return 4**len(arg)
else:  # pragma: nocover
    integer_argument = Optional[int]


if not TYPE_CHECKING:
    def positive_integer_argument(*args, **kw):
        arg = integer_argument(*args, **kw)
        if not isinstance(arg, int):  # coercion happens in integer_argument
            return arg
        return abs(arg)
else:  # pragma: nocover
    positive_integer_argument = Optional[int]


if not TYPE_CHECKING:
    def isinteractive(*args, **kw):
        return True
else:  # pragma: nocover
    isinteractive = bool


def call(callable, *args, **kw):
    d = {}
    parameters = inspect.signature(callable).parameters
    for (name, arg) in parameters.items():
        if arg.annotation != inspect.Parameter.empty:
            val = arg.annotation(*args, **kw)
            if val is None and arg.default != inspect.Parameter.empty:
                val = arg.default
            d[name] = val
        elif arg.default == inspect.Parameter.empty:
            raise Exception(
                'insufficient defaults for %s calling %s' % (
                    name, repr(callable),))
    return callable(**d)


class UnCompleter:
    def __init__(self):
        self.candidates = []
        self.live = False

    def matches(self, sofar=''):
        return []

    def roll(self, p):
        pass

    def roll_to(self, s):
        pass

    @staticmethod
    def check(x, y):
        return False

    def expand(self, value):
        return None, None


class Completer:
    def __init__(self, iterable):
        self.candidates = sorted(iterable)
        self.live = bool(self.candidates)

    def matches(self, value=''):
        return [
            (n, c, c)
            for n, c in enumerate(self.candidates)
            if not value or self.check(value, c)]

    def roll(self, p):
        self.candidates = self.candidates[p:] + self.candidates[:p]

    def roll_to(self, s):
        with contextlib.suppress(ValueError):
            i = self.candidates.index(s)
            self.roll(i)

    @staticmethod
    def check(x, y):
        return x in y

    def expand(self, value):
        # should expand e.g. 'a' out of [ 'aaa', 'aaab', 'caaa'] to 'aaa'
        # but...
        m = self.matches(value)
        if m:
            result = m[0][1]
            return result
        return value


class FileCompleter(Completer):
    def __init__(self):
        self.live = True
        self.directory = ''
        self.candidates = sorted(self.listdir(self.directory))

    @staticmethod
    def listdir(directory):
        if not directory:
            directory = os.curdir
        files = os.listdir(directory)
        for n, filename in enumerate(files):
            if os.path.isdir(filename):
                files[n] += os.path.sep
        return files

    def matches(self, value=''):
        directory, filename = os.path.split(value)
        if directory != self.directory:
            self.candidates = self.listdir(directory)
            self.directory = directory
        return [
            (i, name, os.path.join(directory, name))
            for (i, name, _) in super().matches(filename)]

    def expand(self, value):
        directory, filename = os.path.split(value)
        if directory != self.directory:
            self.candidates = self.listdir(directory)
            self.directory = directory
        return os.path.join(
            directory, Completer(self.candidates).expand(filename))


class DestCompleter(Completer):
    enable = util.Configurable(
        'completer.fancy',
        True,
        'enable the fancy destination completer',
        coerce=util.coerce_bool,
        )

    def __init__(self, candidates, context):
        self.context = context
        super().__init__(candidates)
        self.backends = [b.name for b in self.context.backends]
        if not self.enable:  # pragma: nocover
            self.live = False

    def check(self, x, y):
        if ';' not in x:
            return x in y
        xbackend, xaddress = x.split(';', 1)
        xbackend = xbackend.strip()
        xaddress = xaddress.lstrip()

        ybackend, yaddress = [s.strip() for s in y.split(';', 1)]

        if xbackend:
            backends = [b for b in self.backends if b.startswith(xbackend)]
            return any(
                (b == ybackend and xaddress in yaddress) for b in backends)
        else:
            return xaddress in y.split(';', 1)[1]
