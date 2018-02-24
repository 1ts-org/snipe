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
snipe.util
----------

Assorted utility functions.
'''


import asyncio
import contextlib
import ctypes
import datetime
import importlib
import json
import functools
import logging
import math
import os
import sys
import time
import unicodedata
import unittest.mock as mock
import urllib.parse

import aiohttp


class SnipeException(Exception):
    pass


class Configurable:
    registry = {}

    def __init__(
            self, key,
            default=None, doc=None, action=None, coerce=None, validate=None,
            string=None, oneof=None,
            ):
        self.key = key
        self.default = default
        self._action = action
        self._validate = validate
        self._coerce = coerce
        self._string = string
        self.oneof = oneof
        if oneof and not validate:
            self._validate = val_oneof(oneof)
        self.override = None
        self.doc = doc
        self.registry[key] = self

    def __get__(self, instance, owner):
        if not instance:
            return self
        if self.override is not None:
            return self.override
        if not instance.context:
            return self.default
        return instance.context.conf.get('set', {}).get(self.key, self.default)

    def __set__(self, instance, v):
        value = self.coerce(v)
        if not self.validate(value):
            raise TypeError('%s invalid for %s' % (repr(v), self.key))
        instance.context.conf.setdefault('set', {})[self.key] = value
        self.override = None
        self.action(instance.context, value)

    def set_override(self, v):
        value = self.coerce(v)
        if not self.validate(value):
            raise TypeError('%s invalid for %s' % (repr(v), self.key))
        self.override = value

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

    @classmethod
    def get(self, instance, key):
        obj = self.registry[key]
        return obj.__get__(instance, None)

    @classmethod
    def set_overrides(self, overrides):
        for k, v in overrides.items():
            self.registry[k].set_override(v)


def coerce_bool(x):
    if hasattr(x, 'lower'):
        return x.lower().strip() in ('true', 'on', 'yes')
    else:
        return bool(x)


class Level(Configurable):
    def __init__(self, key, logger, default=logging.WARNING, doc=None):
        super().__init__(key, default, doc=doc)
        self.logger = logger

    def action(self, instance, value):
        logging.getLogger(self.logger).setLevel(value)

    names = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

    def coerce(self, value):
        if hasattr(value, 'upper'):  # stringish
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
        ('log.filter', 'filter'),
        ('log.websocket', 'WebSocket'),
        ]:
    Level(
        userspace_name,
        program_name,
        {'log.context': logging.INFO}.get(userspace_name, logging.WARNING),
        'logging for %s object' % (program_name,)
        )


LICENSE = '''
Copyright © 2014-2016 the Snipe contributors
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

  snipe is a messaging client originally written by Karl Ramm

  You can type ? for help at this screen, but on some screens you'll
  need to press the escape key first.   If you're new here, there should
  be a cheatsheet for commonly used keys at the top of the window.

  snipe is free/open source software.  Type ? L for relevant lawyerese.
'''

USER_AGENT = 'snipe 0 (development) (python %s) (aiohttp %s)' % (
    sys.version.split('\n')[0].strip(), aiohttp.__version__)


def coro_cleanup(f):
    @asyncio.coroutine
    @functools.wraps(f)
    def catch_and_log(*args, **kw):
        try:
            return (yield from asyncio.coroutine(f)(*args, **kw))
        except asyncio.CancelledError:
            pass  # yay
        except Exception:
            if args and hasattr(args[0], 'log'):
                log = args[0].log
            else:
                log = logging.getLogger('coro_cleanup')
            log.exception('coroutine cleanup')
    return catch_and_log


@contextlib.contextmanager
def stopwatch(tag, log=None):
    if log is None:
        log = logging.getLogger('stopwatch')
    t0 = time.time()
    yield
    log.debug('%s took %fs', tag, time.time() - t0)


def listify(f):
    '''Decorator that turns a function that returns an iterator into a function
    that returns a list; because generators are a convenient idiom but
    sometimes you really want lists.
    '''
    @functools.wraps(f)
    def listifier(*args, **kw):
        return list(f(*args, **kw))
    return listifier


def timestr(t):
    if t is None:
        return '[not]'

    try:
        t = float(t)
    except:
        return '[?' + repr(t) + ']'

    try:
        return '[' + datetime.datetime.fromtimestamp(t).isoformat(' ') + ']'
    except (OverflowError, ValueError, OSError):
        pass

    if t < 0:
        if math.isinf(t):
            return '[immemorial]'
        else:
            return '[undefined]'
    else:
        if math.isinf(t):
            return '[omega]'
        else:
            return '[unknown]'

    return '[impossible]'  # pragma: nocover


class JSONDecodeError(SnipeException):
    def __init__(self, data):
        self.data = data

    def __str__(self):
        return str(self.data)


class HTTP_JSONmixin:
    # object must have a .log attribute
    def setup_client_session(self, headers=None, **kw):
        if headers is None:
            headers = {}
        headers['User-Agent'] = USER_AGENT
        self._JSONmixin_headers = headers
        self._JSONmixin_kw = kw
        self._clientsession = None

    @asyncio.coroutine
    def _ensure_client_session(self):
        if self._clientsession is None:
            self._clientsession = aiohttp.ClientSession(
                headers=self._JSONmixin_headers, **self._JSONmixin_kw)

    @asyncio.coroutine
    def reset_client_session_headers(self, headers):
        if getattr(self, '_clientsession', None) is not None:
            yield from asyncio.coroutine(self._clientsession.close)()
            self._clientsession = None
        self._JSONmixin_headers = headers
        yield from self._ensure_client_session()

    @asyncio.coroutine
    def _result(self, response):
        yield from self._ensure_client_session()
        try:
            result = yield from response.json()
        except (UnicodeError, ValueError) as e:
            data = yield from response.read()
            self.log.error(
                'json %s from %s on %s',
                e.__class__.__name__, response.url, repr(data))
            raise JSONDecodeError(repr(data)) from e
        finally:
            response.release()
        return result

    @asyncio.coroutine
    def _post(self, path, **kw):
        yield from self._ensure_client_session()
        self.log.debug(
            '_post(%s%s, **%s)', repr(self.url), repr(path), repr(kw))
        response = yield from self._clientsession.post(
            urllib.parse.urljoin(self.url, path), data=kw)
        return (yield from self._result(response))

    @asyncio.coroutine
    def _post_json(self, path, **kw):
        yield from self._ensure_client_session()
        self.log.debug(
            '_post_json(%s%s, **%s)', repr(self.url), repr(path), repr(kw))
        response = yield from self._clientsession.post(
            urllib.parse.urljoin(self.url, path),
            data=json.dumps(kw),
            headers={'Content-Type': 'application/json'},
            )
        return (yield from self._result(response))

    @asyncio.coroutine
    def _patch(self, path, **kw):
        yield from self._ensure_client_session()
        self.log.debug(
            '_patch(%s%s, **%s)', repr(self.url), repr(path), repr(kw))
        response = yield from self._clientsession.patch(
            urllib.parse.urljoin(self.url, path), data=kw)
        return (yield from self._result(response))

    @asyncio.coroutine
    def _get(self, path, **kw):
        yield from self._ensure_client_session()
        self.log.debug(
            '_get(%s%s, **%s)', repr(self.url), repr(path), repr(kw))
        response = yield from self._clientsession.get(
            urllib.parse.urljoin(self.url, path), params=kw)
        return (yield from self._result(response))

    @asyncio.coroutine
    def _request(self, method, url, **kw):
        yield from self._ensure_client_session()
        self.log.debug(
            '_request(%s, %s, **%s)', repr(method), repr(url), repr(kw))
        response = yield from self._clientsession.request(method, url, **kw)
        return (yield from self._result(response))

    @asyncio.coroutine
    def shutdown(self):
        yield from super().shutdown()
        if self._clientsession is not None:
            yield from asyncio.coroutine(self._clientsession.close)()


class JSONWebSocket:
    def __init__(self, log):
        self.resp = None
        self.log = log
        self.session = aiohttp.ClientSession()

    @asyncio.coroutine
    def close(self):
        if self.resp is not None:
            yield from asyncio.coroutine(self.resp.close)()
            self.resp = None
        yield from asyncio.coroutine(self.session.close)()

    @asyncio.coroutine
    def connect(self, url, headers=None):
        if headers is None:
            headers = {}
        headers['User-Agent'] = USER_AGENT
        self.log.debug('connecting to %s', url)
        self.resp = yield from self.session.ws_connect(url, headers=headers)

        return self.resp

    @asyncio.coroutine
    def write(self, data):
        return (yield from asyncio.coroutine(self.resp.send_json)(data))

    @asyncio.coroutine
    def read(self):
        return (yield from self.resp.receive_json())


@contextlib.contextmanager
def safe_write(path, mode=0o600):
    """Open a file for writing without letting go with both hands."""
    directory, name = os.path.split(path)
    tmp = os.path.join(directory, ',' + name)
    backup = os.path.join(directory, name + '~')

    fp = open(
        tmp, 'w', opener=lambda file, flags: os.open(file, flags, mode=mode))

    yield fp

    fp.close()
    # TODO consider checking that the size of the file matches what was written

    if os.path.exists(path):
        with contextlib.suppress(OSError):
            os.unlink(backup)
        os.link(path, backup)
    os.rename(tmp, path)


def eval_output(string, environment=None, mode='single'):
    import code
    import io
    import traceback

    try:
        if mode == 'exec':
            c = compile(string, '<input>', mode)
        else:
            c = code.compile_command(string, symbol=mode)
        if c is None:
            return None
        else:
            in_ = io.StringIO()
            out = io.StringIO()
            with mock.patch('sys.stdout', out), \
                    mock.patch('sys.stderr', out), \
                    mock.patch('sys.stdin', in_):
                eval(c, environment)
            out = out.getvalue()
    except:
        out = traceback.format_exc()

    return out


def val_oneof(vals):
    return lambda x: x in vals


def _fallback_wcwidth(c):
    # from http://bugs.python.org/msg155361
    # http://bugs.python.org/issue12568
    if (
            (c < ' ') or
            (u'\u1160' <= c <= u'\u11ff') or  # hangul jamo
            (unicodedata.category(c) in ('Mn', 'Me', 'Cf', 'Cc')
                and c != u'\u00ad')  # 00ad = soft hyphen
            ):
        return 0
    if unicodedata.east_asian_width(c) in ('F', 'W'):
        return 2
    return 1


def _setup_wcwidth():
    LIBC = 'libc.so.6'  # XXX current versions of linux
    wcwidth = _fallback_wcwidth
    try:
        ctypes.cdll.LoadLibrary(LIBC)
        libc = ctypes.CDLL(LIBC)
        os_wcwidth = libc.wcwidth

        def wcwidth(c):
            return max(os_wcwidth(ord(c)), 0)
    except (OSError, AttributeError):
        pass  # pragma: nocover
    return wcwidth


_wcwidth = _setup_wcwidth()


@functools.lru_cache(None)
def glyphwidth(s):
    return sum(_wcwidth(c) for c in s)


def escapify(c):
    try:
        return r'\N{%s}' % (unicodedata.name(c),)
    except ValueError:
        i = ord(c)
        if i < 0xff:
            return r'\%03o' % i
        elif i <= 0xffff:
            return r'\u%04X' % i
        else:
            return r'\U%08X' % i


def unirepr(x):
    s = ''.join(
        c if (c == '\n' or ord(' ') <= ord(c) < 0xff) else escapify(c)
        for c in x)
    s = s.replace('"', r'\"')
    if '\n' in s:
        return '"""' + s + '"""'
    else:
        return '"' + s + '"'


def getobj(qualname):
    modname, name = qualname.rsplit('.', 1)
    module = importlib.import_module(modname, __package__)
    return getattr(module, name)
