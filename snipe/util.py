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


'''
Assorted utility functions.
'''


import logging


class SnipeException(Exception):
    pass


class Configurable:
    registry = {}

    def __init__(
        self, key,
        default=None, doc=None, action=None, coerce=None, validate=None,
        string=None,
        ):
        self.key = key
        self.default = default
        self._action = action
        self._validate = validate
        self._coerce = coerce
        self._string = string
        self.doc = doc
        self.registry[key] = self

    def __get__(self, instance, owner):
        return instance.context.conf.get('set', {}).get(self.key, self.default)

    def __set__(self, instance, v):
        value = self.coerce(v)
        if not self.validate(value):
            raise TypeError('%s invalid for %s' % (repr(v), self.key))
        instance.context.conf.setdefault('set', {})[self.key] = value
        self.action(instance, value)

    def action(self, instance, value):
        if self._action is not None:
            self._action(instance.context, value)

    def coerce(self, value):
        if self._coerce is not None:
            return self._coerce(value)
        return value

    def validate(self, value):
        if self._validate is not None:
            return self._validate(value)
        return True

    def string(self, value):
        if self._string is not None:
            return self._string(value)
        return str(value)

    @classmethod
    def immanentize(self, context):
        for configurable in self.registry.values():
            configurable.action(context, configurable.__get__(context, self))

    @classmethod
    def set(self, instance, key, value):
        obj = self.registry[key]
        obj.__set__(instance, value)


class Level(Configurable):
    def __init__(self, key, logger, default=logging.WARNING, doc=None):
        super().__init__(key, default, doc=doc)
        self.logger = logger

    def action(self, instance, value):
        logging.getLogger(self.logger).setLevel(value)

    names = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

    def coerce(self, value):
        if hasattr(value, 'upper'): # stringish
            v = value.strip().upper()
            if v in self.names:
                return getattr(logging, v)
            try:
                return int(value)
            except ValueError:
                pass
        return value

    def validate(self, value):
        return isinstance(value, int) and value >= 0


# these don't need to actually be properties anywhere
for userspace_name, program_name in [
    ('log.context', 'Snipe'),
    ('log.roost.engine', 'Rooster'),
    ('log.roost', 'Roost'),
    ('log.ttyfrontend', 'TTYFrontend'),
    ('log.ttyrender', 'TTYRender'),
    ('log.curses', 'TTYRender.curses'),
    ('log.messager', 'Messager'),
    ('log.editor', 'Editor'),
    ('log.asyncio', 'asyncio'),
    ('log.gapbuffer', 'GapBuffer'),
    ('log.backend.terminus', 'TerminusBackend'),
    ('log.backend.startup', 'StartupBackend'),
    ]:
    Level(
        userspace_name,
        program_name,
        {'log.context': logging.INFO}.get(userspace_name, logging.WARNING),
        'logging for %s object' % (program_name,)
        )


LICENSE = '''
Copyright © 2014 Karl Ramm
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above
copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided
with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
SUCH DAMAGE.
'''


SPLASH = '''
Welcome to snipe.

  snipe is a messaging client and editor written by Karl Ramm.

  You can type ? for help at this screen, but on some screens you'll
  need to press the escape key first.

  snipe is free/open source software.  Type ? L for relevant lawyerese.
'''
