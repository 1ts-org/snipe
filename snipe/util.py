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


import contextlib
import ctypes
import datetime
import importlib
import json
import functools
import logging
import math
import os
import socket
import ssl
import sys
import time
import unicodedata
import unittest.mock as mock
import urllib.parse
import zlib

from typing import (Dict, List, Tuple)

import h11
import wsproto
import wsproto.connection
import wsproto.events
import wsproto.extensions

from . import imbroglio


class SnipeException(Exception):
    pass


class Configurable:
    registry: Dict[str, 'Configurable'] = {}

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
            raise ValueError('%s invalid for %s' % (repr(v), self.key))
        instance.context.conf.setdefault('set', {})[self.key] = value
        self.override = None
        self.action(instance.context, value)

    def set_override(self, v):
        value = self.coerce(v)
        if not self.validate(value):
            raise ValueError('%s invalid for %s' % (repr(v), self.key))
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
        ('log.gapbuffer', 'GapBuffer'),
        ('log.backend.terminus', 'TerminusBackend'),
        ('log.backend.startup', 'StartupBackend'),
        ('log.filter', 'filter'),
        ('log.websocket', 'WebSocket'),
        ('log.imbroglio', 'imbroglio'),
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

USER_AGENT = 'snipe 0 (development) (python %s)' % (
    sys.version.split('\n')[0].strip(),)


def coro_cleanup(f):
    @functools.wraps(f)
    async def catch_and_log(*args, **kw):
        try:
            return (await f(*args, **kw))
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
    except Exception:  # because really, no matter what happened
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
        self._JSONmixin_headers = [
            ('User-Agent', (USER_AGENT + f' (h11 {h11.__version__})'))]
        self._JSONmixin_headers.extend(headers.items())

    async def reset_client_session_headers(self, headers=None):
        self.setup_client_session(headers)

    async def _request(self, *args, **kwargs):
        response = None
        try:
            response = await HTTP.request(*args, **kwargs)
            datas = []
            while True:
                b = await response.readsome()
                if b is None:
                    break
                datas.append(b)
            bs = b''.join(datas)
            try:
                u = bs.decode('UTF-8')
                result = json.loads(u)
            except (UnicodeError, ValueError) as e:
                data = bs.decode(errors='replace')
                self.log.error(
                    'json %s from %s on %s',
                    e.__class__.__name__, response.url, repr(data))
                raise JSONDecodeError(repr(data)) from e
        finally:
            if response is not None:
                await response.close()
        return result

    async def _post(self, path, _data=None, **kw):
        self.log.debug(
            '_post(%s%s, %s, **%s)', repr(self.url), repr(path),
            self._JSONmixin_headers, repr(kw))
        return await self._request(
            urllib.parse.urljoin(self.url, path),
            method='POST',
            data=kw if _data is None else _data,
            headers=self._JSONmixin_headers,
            )

    async def _post_json(self, path, **kw):
        self.log.debug(
            '_post_json(%s%s, %s, **%s)', repr(self.url), repr(path),
            self._JSONmixin_headers, repr(kw))
        return await self._request(
            urllib.parse.urljoin(self.url, path),
            'POST',
            json=kw,
            headers=self._JSONmixin_headers,
            )

    async def _patch(self, path, **kw):
        self.log.debug(
            '_patch(%s%s, %s, **%s)', repr(self.url), repr(path),
            self._JSONmixin_headers, repr(kw))
        return await self._request(
            urllib.parse.urljoin(self.url, path),
            'PATCH',
            data=kw,
            headers=self._JSONmixin_headers,
            )

    async def _get(self, path, **kw):
        self.log.debug(
            f'_get({path!r}, **{kw!r});'
            f' url={self.url!r}, headers={self._JSONmixin_headers!r}')

        us = urllib.parse.urlsplit(urllib.parse.urljoin(self.url, path))
        return await self._request(
            urllib.parse.urlunsplit(
                us[:3] + (urllib.parse.urlencode(kw), '')),
            headers=self._JSONmixin_headers,
            )

    async def shutdown(self):
        await super().shutdown()


class JSONWebSocket:
    def __init__(self, log):
        self.conn = None
        self.log = log

    async def close(self):
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def connect(self, url, headers=[]):
        self.log.debug('connecting to %s %s', url, headers)
        self.conn = await HTTP_WS.request(url, headers=headers, log=self.log)

    async def write(self, data):
        data = json.dumps(data)
        return await self.conn.write(data)

    async def read(self):
        data = await self.conn.read()
        try:
            return json.loads(data)
        except json.decoder.JSONDecodeError as e:
            raise JSONDecodeError(data) from e  # raise our own exception


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
    except BaseException:
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
    except (OSError, AttributeError):  # pragma: nocover
        pass
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


class NetworkStream:
    def __init__(self, sock, hostname='', port=0, log=None):
        if log is None:
            self.log = logging.getLogger(
                'NetworkStream.%s.%d' % (hostname, port))
        else:
            self.log = log

        self.socket = sock
        self.socket.setblocking(False)
        self.reof = False

        self.log.debug('%s', f'connected to {self.socket!r}')

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.socket!r}>'

    @classmethod
    async def connect(klass, hostname, port, log=None):
        sock = await imbroglio.run_in_thread(
            socket.create_connection, (hostname, port), 5)
        return klass(sock, hostname, port, log)

    async def readsome(self):
        if self.reof:
            return None
        await imbroglio.readwait(self.socket.fileno())
        try:
            buf = self.socket.recv(4096)
        except BlockingIOError:  # pragma: nocover
            # shouldn't actually happen
            return ''
        if buf == b'':
            self.log.debug('readsome: got eof')
            self.reof = True
            return None
        self.log.debug('readsome: %d bytes, reof %s', len(buf), self.reof)
        return buf

    async def readable(self):
        if self.reof:
            self.log.debug('eof -> not readable')
            return False
        timedout, duration = await imbroglio.readwait(self.socket.fileno(), 0)
        self.log.debug(f'readable: {not timedout}')
        return not timedout

    async def write(self, data):
        self.log.debug('sending %d bytes', len(data))
        while data:
            await imbroglio.writewait(self.socket.fileno())
            sent = self.socket.send(data)
            data = data[sent:]

    async def close(self):
        self.log.debug('%s', f'NetworkStream {self} closing')
        with contextlib.suppress(OSError):
            self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()


class SSLStream:
    # XXX needs refactored

    def __init__(self, netstream, hostname, log=None):
        if log is None:
            self.log = logging.getLogger('SSLStream.%s' % (hostname,))
        else:
            self.log = log
        self.reof = False

        self.netstream = netstream
        self.incoming = ssl.MemoryBIO()
        self.outgoing = ssl.MemoryBIO()
        self.ctx = ssl.create_default_context()
        self.obj = self.ctx.wrap_bio(
            self.incoming, self.outgoing, server_side=False,
            server_hostname=hostname)
        self.handshake_done = False
        self.log.debug('%s', f'wrapped {self.netstream!r}')

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.netstream!r}>'

    async def do_handshake(self):
        if self.handshake_done:
            return

        self.log.debug('doing handshake')

        while True:
            try:
                self.obj.do_handshake()
            except ssl.SSLWantReadError:
                if self.outgoing.pending:
                    await self.netstream.write(self.outgoing.read())
                indata = await self.netstream.readsome()
                if indata is None:
                    self.incoming.write_eof()
                else:
                    self.incoming.write(indata)
                continue
            except ssl.SSLWantWriteError:
                await self.netstream.write(self.outgoing.read())
                continue
            break
        if self.outgoing.pending:
            await self.netstream.write(self.outgoing.read())
        self.handshake_done = True

    async def write(self, data):
        await self.do_handshake()

        self.log.debug('writing %d bytes', len(data))

        while True:
            try:
                self.obj.write(data)
            except ssl.SSLWantReadError:
                self.log.debug(
                    'nead read, %d output pending', self.outgoing.pending)
                # if self.outgoing.pending:
                #     await self.netstream.write(self.outgoing.read())
                await self.maybewrite()
                incoming = await self.netstream.readsome()
                if incoming is None:
                    self.incoming.write_eof()
                else:
                    self.incoming.write(incoming)
                continue
            break

        return await self.netstream.write(self.outgoing.read())

    async def maybewrite(self):
        self.log.debug(f'maybewrite {self.outgoing.pending}')
        if self.outgoing.pending:
            await self.netstream.write(self.outgoing.read())

    async def readsome(self):
        if self.reof:
            return None
        await self.readable()

        while True:
            try:
                data = self.obj.read()
                if data == b'':
                    self.reof = True
                    return None
            except ssl.SSLWantReadError:
                self.log.debug('want read')
                await self.maybewrite()
                data = await self.netstream.readsome()
                if data is None:
                    self.incoming.write_eof()
                    self.log.debug('wrote eof')
                    continue
                self.incoming.write(data)
                continue
            except ssl.SSLEOFError:
                self.log.debug('(got EOFError)', exc_info=True)
                self.reof = True
                return None
            break

        self.log.debug('got %d bytes from SSL', len(data))
        return data

    async def readable(self):
        if self.reof:
            self.log.debug('at eof')
            return False
        count = 0
        # can actually cause network io there's anything waiting
        await self.do_handshake()
        while True:
            if not await self.netstream.readable():
                if self.netstream.reof:
                    self.incoming.write_eof()
                    self.log.debug('wrote eof B')
                break
            else:
                self.log.debug('socket is readable?')
            # consume all the bytes on the wire
            d = await self.netstream.readsome()
            if d is None:
                self.incoming.write_eof()
                self.log.debug('wrote eof 0')
                break
            count += len(d)
            if d:
                self.incoming.write(d)
        self.log.debug(f'read {count} bytes from network stream')
        return bool(self.obj.pending())

    async def close(self):
        self.log.debug('%s', f'closing {self.netstream}')
        await self.netstream.close()


class HTTP:
    def __init__(self, url, method='GET', log=None):
        if log is not None:
            self.log = log
        else:
            self.log = logging.getLogger('HTTP')
        self.url = url
        self.method = method
        parsed = urllib.parse.urlsplit(url)
        self.scheme = parsed.scheme or 'http'
        assert self.scheme in ('http', 'https')
        self.hostname = parsed.hostname
        self.port = int(parsed.port or {'http': 80, 'https': 443}[self.scheme])
        self.qs = (parsed.path or '/') + (
            ('?' + parsed.query) if parsed.query else '')
        self.conn = h11.Connection(our_role=h11.CLIENT)
        self.connected = False
        self.response = None
        self.decompressor = None

    @classmethod
    async def request(
            klass, url, method='GET', data=None, json=None, headers=[],
            log=None):
        obj = klass(url, method, log)
        await obj.connect(data=data, _json=json, headers=headers)
        return obj

    async def connect(self, data=None, _json=None, headers=[]):
        self.stream = await NetworkStream.connect(self.hostname, self.port)
        if self.scheme == 'https':
            self.stream = SSLStream(self.stream, self.hostname)

        outheaders = [
            ('Host', self.hostname),
            ('Connection', 'close'),
            ('Accept-Encoding', 'gzip'),
            ]
        if _json is not None:
            # overrides data
            data = json.dumps(_json)
            outheaders.append(('Content-Type', 'application/json'))
        if data is not None:
            if hasattr(data, 'items'):
                data = urllib.parse.urlencode(data)
                outheaders.append(
                    ('Content-Type', 'application/x-www-form-urlencoded'))
            if hasattr(data, 'encode'):
                data = data.encode('UTF-8')
            outheaders.append(('Content-Length', str(len(data))))
        outheaders.extend(headers)
        await self.send(h11.Request(
            method=self.method,
            target=self.qs,
            headers=outheaders))
        if data is not None:
            await self.send(h11.Data(data=data))
        await self.send(h11.EndOfMessage())
        self.connected = True
        self.log.debug('%s', f'{self.url}: connected to {self.stream!r}')

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.url} {self.stream!r}>'

    async def send(self, event):
        data = self.conn.send(event)
        if not data:
            return
        await self.stream.write(data)

    async def next_event(self):
        while True:
            event = self.conn.next_event()
            self.log.debug('HTTP event: %s', repr(event))
            if event is h11.NEED_DATA:
                data = await self.stream.readsome()
                if data == b'':
                    continue
                if data is None:
                    data = b''
                self.conn.receive_data(data)
                continue
            return event

    async def readsome(self):
        assert self.connected

        while True:
            event = await self.next_event()
            if type(event) is h11.Response:
                self.response = event
                ce = dict(event.headers).get(b'content-encoding')
                if ce is not None:
                    ce = set(ce.replace(b' ', b'').split(b','))
                else:
                    ce = set()
                self.log.debug('%s', f'ce: {ce!r}')
                if b'gzip' in ce:
                    self.decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    self.log.debug(
                        '%s', f'decompressor is {self.decompressor!r}')

            elif type(event) is h11.Data:
                data = bytes(event.data)
                if self.decompressor is not None:
                    data = self.decompressor.decompress(data)
                return data
            elif type(event) in (h11.EndOfMessage, h11.ConnectionClosed):
                return None

    async def close(self):
        self.log.debug('%s', 'closing {self.stream}')
        await self.stream.close()


class HTTP_WS:
    def __init__(self, url, log=None, stream=None):
        if log is None:
            log = logging.getLogger('HTTP_WS')
        self.log = log

        self.stream = stream
        self.url = url
        parsed = urllib.parse.urlsplit(url)
        self.scheme = parsed.scheme or 'ws'
        if self.scheme.startswith('http'):
            self.scheme = 'ws' + self.scheme[4:]
        assert self.scheme in ('ws', 'wss')
        self.hostname = parsed.hostname
        self.port = int(parsed.port or {'ws': 80, 'wss': 443}[self.scheme])
        self.resource = (parsed.path or '/') + (
            ('?' + parsed.query) if parsed.query else '')

        self.ws = wsproto.WSConnection(wsproto.ConnectionType.CLIENT)

        self.connected = False
        self.closed = False
        self.response = None
        self.inbuf = []
        self.reading = False

    async def connect(self, headers=[]):
        self.log.debug('opening connection to %s %s', self.hostname, self.port)
        if self.stream is None:
            self.stream = await NetworkStream.connect(
                self.hostname, self.port, log=self.log)
            if self.scheme == 'wss':
                self.log.debug('starting SSL layer')
                self.stream = SSLStream(
                    self.stream, self.hostname, log=self.log)

        await self._send(wsproto.events.Request(
            host=self.hostname,
            target=self.resource,
            extra_headers=headers,
            extensions=[wsproto.extensions.PerMessageDeflate()]))

        # pull up to one event off the events() iterator
        event = None
        while event is None:
            await self._communicate()
            with contextlib.suppress(StopIteration):
                event = next(self.ws.events())

        if not isinstance(event, wsproto.events.AcceptConnection):
            raise SnipeException(
                f'expected connection established event, got {event}')

        self.log.debug('%s', f'{self.url}: connected to {self.stream!r}')
        self.log.debug('%s', f'connected: {event}')

        self.connected = True

    @classmethod
    async def request(
            klass,
            url,
            headers: List[Tuple[str, str]]=[],
            log=None,
            stream=None):
        obj = klass(url, log=log, stream=stream)
        await obj.connect(headers)
        return obj

    async def read(self):
        if self.closed or not self.connected:
            return None
        ident = f'{id(self):x}: '

        self.log.debug(f'{ident}outside readsome loop')
        while True:
            self.log.debug(f'{ident}top of readsome loop')
            for event in self.ws.events():
                self.log.debug('%s', f'{ident}readsome {event}')
                if isinstance(event, wsproto.events.CloseConnection):
                    await self._send(event.response())
                    if self.inbuf:  # pragma: nocover
                        self.log.error(
                            '%s',
                            f'{ident}Connection Closed with {self.inbuf!r}'
                            f'code={event.code} reason={event.reason}')
                    self.connected = False
                    self.closed = True
                    return None
                elif isinstance(event, wsproto.events.TextMessage):
                    self.inbuf.append(event.data)
                    self.log.debug(
                        '%s',
                        f'{ident}{event.__class__.__name__}'
                        ' {event.message_finished}')
                    if event.message_finished:
                        retval = ''.join(self.inbuf)
                        self.inbuf = []
                        return retval
                    else:  # pragma: nocover
                        # this seems to be a difficult situation to generate
                        self.log.debug(
                            f'{ident}supposedly not releasing message')
                elif isinstance(event, wsproto.events.Ping):
                    await self._send(event.response())
                elif isinstance(event, wsproto.events.BytesMessage):
                    self.log.debug(
                        '%s', f'{ident}binary message {event.data!r}?')
                    return event.data
            self.log.debug(f'{ident}about to communicate')
            await self._communicate()
            self.log.debug(f'{ident}bottom of readsome loop')

    async def write(self, buf):
        if not self.connected or self.closed:
            return
        self.log.debug('writing %d bytes', len(buf))
        d = self.ws.send(wsproto.events.Message(data=buf))
        if d:
            self.log.debug('just writing... %d bytes', len(d))
            await self.stream.write(d)
            self.log.debug('just sent %d bytes', len(d))

    async def close(self):
        self.log.debug('HTTP_WS closing')
        self.closed = True
        self.connected = False
        try:
            await self._send(wsproto.events.CloseConnection(code=0))
        except wsproto.utilities.LocalProtocolError:  # pragma: nocover
            self.log.debug(
                '%s',
                f'ignored while closing websocket connection for {self.url}',
                exc_info=True,
                )
        except Exception:  # pragma: nocover
            self.log.exception(
                '%s', f'while closing websocket connection for {self.url}')
        finally:
            self.log.debug('%s', f'closing {self.stream} for {self.url}')
            await self.stream.close()

    async def _communicate(self):
        self.log.debug(
            '%s',
            f'communicate: connected={self.connected} closed={self.closed}')
        await self.stream.maybewrite()

        self.log.debug('reading...')
        d = await self.stream.readsome()
        # XXX if not d: EOF
        if d is not None:
            self.log.debug('received %d bytes', len(d))
        self.ws.receive_data(d)  # turns out wsproto signals EOF with None too

    async def _send(self, event):
        bytes_to_send = self.ws.send(event)
        if bytes_to_send:
            await self.stream.write(bytes_to_send)

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.url} {self.stream!r}>'
