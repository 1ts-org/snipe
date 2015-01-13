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
'''
snipe.context
-------------
'''


import os
import contextlib
import logging
import json
import time
import collections
import asyncio

from . import messages
from . import ttyfe
from . import roost
from . import util
from . import window
from . import messager
from . import irccloud


class Context:
    '''
    Wherein we keep our global state.
    '''
    # per-session state and abstact control
    def __init__(self, ui, handler):
        self.conf = {}
        self.context = self
        self.conf_read()
        handler.context = self
        self.ui = ui
        self.ui.context = self
        self.killring = []
        self.log = logging.getLogger('Snipe')
        self.backends = messages.AggregatorBackend(
            self,
            backends = [
                messages.StartupBackend(self),
                roost.Roost(self),
                irccloud.IRCCloud(self),
                ],)
        self.ui.initial(messager.Messager(self.ui))
        self.backends.backfill(None, time.time() - 86400)

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


class SnipeLogHandler(logging.Handler):
    size = util.Configurable(
        'log.size',
        1024*1024,
        'number of log entries to keep in memory',
        coerce=int)
    filename = util.Configurable(
        'log.file',
        '/tmp/snipe.%d.log' % (os.getuid()),
        'file to log to when we log',
        )
    writing = util.Configurable(
        'log.write',
        False,
        'automatically write out logs',
        coerce = util.coerce_bool,
        )
    interval = util.Configurable(
        'log.write_interval',
        1.0,
        'if log.write, how often',
        coerce = float,
        )

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.context = None
        self.buffer = collections.deque(maxlen=self.size)
        self.task = None

    @contextlib.contextmanager
    def the_lock(self):
        self.acquire()
        yield
        self.release()

    def emit(self, record):
        s = self.format(record)
        with self.the_lock():
            if self.buffer.maxlen != self.size:
                self.buffer = collections.deque(
                    self.buffer[-self.size:], maxlen=self.size)
            self.buffer.append(s)
            if self.writing and self.task is None:
                self.task = asyncio.async(self.writer())

    @staticmethod
    def opener(file, flags):
        return os.open(file, flags, mode=0o600)

    def dump(self, *args):
        with self.the_lock(), open(self.filename, 'a', opener=self.opener) as fp:
            fp.writelines(s + '\n' for s in self.buffer)
            self.buffer.clear()

    @asyncio.coroutine
    def writer(self):
        yield from asyncio.sleep(self.interval)
        self.dump()
        self.task = None

    def shutdown(self):
        if self.task is not None:
            self.task.cancel()
        with contextlib.suppress(Exception):
            self.task.result()

        self.dump()
