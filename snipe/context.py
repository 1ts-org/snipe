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
snipe.context
-------------
'''


import os
import subprocess
import contextlib
import logging
import json
import time
import collections
import asyncio
import importlib

from . import messages
from . import ttyfe
from . import util
from . import window
from . import messager
from . import roost
from . import irccloud
from . import slack


class Context:
    '''
    Wherein we keep our global state.
    '''
    # per-session state and abstact control

    DEFAULT_BACKENDS = '.roost; .irccloud'

    backend_spec = util.Configurable('backends', DEFAULT_BACKENDS)

    stark_file = util.Configurable('starkfile', 'starks')

    def __init__(self, ui, handler, cli_conf={}):
        self.conf = {
            'filter': {
                'personal': 'personal',
                'auto':
                    'backend == "startup"'
                    ' or (backend == "roost" and opcode = "auto")'
                    ' or noise',
                'error': 'error',
                'default': 'yes',
                },
            'rule': [
                ['filter personal', {
                    'background': 'blue',
                    'foreground': 'white'}],
                ['filter error', {
                    'background': 'red',
                    'foreground': 'white'}],
                ['filter auto', {
                    'background': 'grey24',
                    }],
                ],
            }
        self.ui = ui
        self.ui.context = self
        self.killring = []
        self.log = logging.getLogger('Snipe')
        self.context = self
        self.directory = os.path.join(os.path.expanduser('~'), '.snipe')
        self.conf_read()
        util.Configurable.set_overrides(cli_conf)

        if 'rules' in self.conf:
            self.conf['rule'] = self.conf['rules']
            del self.conf['rules']
            self.conf_write()

        handler.context = self
        self.backends = messages.AggregatorBackend(
            self,
            backends = [
                messages.StartupBackend(self),
                messages.DateBackend(self),
                ] + self.startbackends(),)

        # This is called by conf_read, except we need to do it again because
        # we may have just newly imported a backend
        util.Configurable.immanentize(self)

        self.status = window.StatusLine(self.ui)
        self.ui.initial(
            lambda: messager.Messager(self.ui), statusline=self.status)
        self.messagelog = []

        self.starks = []
        try:
            with open(self.stark_path()) as fp:
                self.starks = [float(f) for f in fp.read().splitlines()]
                self.log.debug('loaded starks: %s', repr(self.starks))
        except:
            self.log.exception('reading starks')

    def startbackends(self):
        started = []
        backends = self.backend_spec.split(';')
        backends = [backend.strip() for backend in backends]
        for string in backends:
            try:
                line = string.split()
                if not line:
                    continue #XXX should complain
                kwargs = {}
                if len(line) > 1:
                    for arg in line[1:]:
                        kv = arg.split('=')
                        if len(kv) != 2:
                            self.log.error('invalid argument %s', kv)
                            continue
                        kwargs[kv[0]] = kv[1]
                self.log.debug('starting backend %s', string)
                module = importlib.import_module(line[0], __package__)
                backend = getattr(module, module._backend)(self, **kwargs)
                started.append(backend)
            except:
                self.log.exception('starting backend %s', string)
        return started

    def conf_read(self):
        path = os.path.join(self.directory, 'config')
        try:
            if os.path.exists(path):
                self.conf = json.load(open(path))
        finally:
            util.Configurable.immanentize(self)

    def conf_write(self):
        self.ensure_directory()
        with util.safe_write(os.path.join(self.directory, 'config')) as fp:
            json.dump(self.conf, fp)
            fp.write('\n')

    def ensure_directory(self):
        if os.path.isdir(self.directory):
            return

        os.mkdir(self.directory)
        os.chmod(self.directory, 0o700)
        if os.path.realpath(self.directory).startswith('/afs/'): #XXX
            cmd = [
                'fs', 'sa', self.directory,
                'system:anyuser', 'none', 'system:authuser', 'none',
                ]
            p = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = p.communicate()[0]
            if p.returncode:
                self.log.error(
                    '%s (=%d): %s', ' '.join(cmd), p.returncode, out)
                #XXX should complain more
            else:
                self.log.debug('%s: %s', ' '.join(cmd), out)

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
        if self.killring:
            return self.killring[-(1 + (off - 1) % len(self.killring))]
        else:
            return ''

    def shutdown(self):
        self.backends.shutdown()

    def message(self, s):
        self.messagelog.append(s)
        self.status.message(s)

    def keyecho(self, s):
        self.status.message(s, ())

    def clear(self):
        self.status.clear()

    def stark_path(self):
        return os.path.join(self.directory, self.stark_file)

    def write_starks(self):
        self.ensure_directory()
        with util.safe_write(self.stark_path()) as fp:
            fp.write(''.join('%f\n' % (f,) for f in self.starks[-16:]))


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

        if self.writing:
            self.dump()
