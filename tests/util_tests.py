# -*- encoding: utf-8 -*-
# Copyright © 2015 the Snipe contributors
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
Unit tests for stuff in util.py
'''


import email.parser
import inspect
import json
import logging
import os
import random
import socket
import ssl
import tempfile
import unittest
import zlib

from typing import (Dict)
from unittest import (mock)

import wsproto

from wsproto import (events)

import mocks

import snipe.imbroglio as imbroglio
import snipe.util


class TestSafeWrite(unittest.TestCase):
    def testSimple(self):

        with tempfile.TemporaryDirectory() as directory:
            pathname = os.path.join(directory, 'file')

            for rounds in range(2):
                string = hex(random.randrange(2**64)) + '\n'

                with snipe.util.safe_write(pathname) as fp:
                    fp.write(string)

                with open(pathname) as fp:
                    self.assertEqual(fp.read(), string)


class TestGlyphwidth(unittest.TestCase):
    def test_glyphwidth(self):
        self.assertEqual(snipe.util.glyphwidth('fred'), 4)
        self.assertEqual(snipe.util.glyphwidth(' '), 1)
        self.assertEqual(snipe.util.glyphwidth('\N{COMBINING DIAERESIS}'), 0)
        self.assertEqual(snipe.util.glyphwidth('a\N{COMBINING DIAERESIS}'), 1)
        self.assertEqual(
            snipe.util.glyphwidth('\N{CJK UNIFIED IDEOGRAPH-54C1}'), 2)
        self.assertEqual(
            snipe.util.glyphwidth(
                'x\N{COMBINING DIAERESIS}\N{COMBINING CEDILLA}'),
            1)
        self.assertEqual(snipe.util.glyphwidth('\x96'), 0)

    def test_fallback_wcwidth(self):
        self.assertEqual(snipe.util._fallback_wcwidth('a'), 1)
        self.assertEqual(
            snipe.util._fallback_wcwidth('\N{COMBINING DIAERESIS}'), 0)
        self.assertEqual(
            snipe.util._fallback_wcwidth('\N{CJK UNIFIED IDEOGRAPH-54C1}'), 2)
        self.assertEqual(
            snipe.util._fallback_wcwidth('\x96'), 0)


class TestUnirepr(unittest.TestCase):
    def test_escapify(self):
        self.assertEqual(
            snipe.util.escapify('a'), r'\N{LATIN SMALL LETTER A}')
        self.assertEqual(
            snipe.util.escapify('\b'), r'\010')
        self.assertEqual(
            snipe.util.escapify(chr(0xffff)), r'\uFFFF')
        self.assertEqual(
            snipe.util.escapify(chr(0xeffff)), r'\U000EFFFF')

    def test_unirepr(self):
        self.assertEqual(
            snipe.util.unirepr('foo'),
            '"foo"')
        self.assertEqual(
            snipe.util.unirepr('foo\nbar'),
            '"""foo\nbar"""')
        self.assertEqual(
            snipe.util.unirepr('""'),
            r'"\"\""')


class TestOneof(unittest.TestCase):
    def test_val_oneof(self):
        f = snipe.util.val_oneof({1, 2, 3})
        self.assertTrue(callable(f))
        self.assertTrue(f(2))
        self.assertFalse(f(4))


class TestTimestr(unittest.TestCase):
    def test_timestr(self):
        self.assertEqual(snipe.util.timestr(None), '[not]')
        self.assertEqual(snipe.util.timestr('frog'), "[?'frog']")
        os.environ['TZ'] = 'GMT'
        self.assertEqual(snipe.util.timestr(0), '[1970-01-01 00:00:00]')
        self.assertEqual(snipe.util.timestr(-999999999999999), '[undefined]')
        self.assertEqual(snipe.util.timestr(float('-inf')), '[immemorial]')
        self.assertEqual(snipe.util.timestr(float('inf')), '[omega]')
        self.assertEqual(snipe.util.timestr(float('nan')), '[unknown]')


class TestListify(unittest.TestCase):
    def test_listify(self):
        self.assertNotEqual(range(10), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        lrange = snipe.util.listify(range)
        self.assertEqual(lrange(10), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])


class TestEvalOutput(unittest.TestCase):
    def test_eval_output(self):
        self.assertEqual(snipe.util.eval_output('2 + 2'), '4\n')
        self.assertEqual(snipe.util.eval_output(''), '')
        self.assertEqual(snipe.util.eval_output('if True:'), None)
        self.assertTrue(snipe.util.eval_output('2 + ').startswith('Traceback'))
        self.assertTrue(snipe.util.eval_output('2 + ', mode='exec').startswith(
            'Traceback'))
        self.assertTrue(snipe.util.eval_output('{}[0]').startswith(
            'Traceback'))
        self.assertEqual(
            snipe.util.eval_output('print(2+2)\n', mode='exec'), '4\n')


class TestGetobj(unittest.TestCase):
    def test(self):
        self.assertIs(snipe.util.getobj('util_tests.TestGetobj'), TestGetobj)


class TConfigurable(snipe.util.Configurable):
    # Override the registry so this doesn't mess with anything else's behavior
    registry: Dict[str, snipe.util.Configurable] = {}


class HasContext:
    def __init__(self):
        self.context = None


class TestConfigurable(unittest.TestCase):
    def test_set_get0(self):
        val = ''

        def setter(c, v):
            nonlocal val
            val = v

        c = TConfigurable(
            'foo', default='foo', oneof={'foo', 'bar'}, action=setter)

        o = HasContext()

        self.assertIs(c.__get__(None, None), c)

        self.assertEqual(c.__get__(o, None), 'foo')

        o.context = mocks.Context()

        c.__set__(o, 'bar')

        self.assertEqual(c.__get__(o, None), 'bar')

        self.assertEqual(val, 'bar')

        self.assertRaises(ValueError, lambda: c.__set__(o, 'baz'))

        o.context.conf['set'] = {'foo': 'foo'}
        self.assertEqual(c.__get__(o, None), 'foo')
        TConfigurable.immanentize(o.context)
        self.assertEqual(val, 'foo')

    def test_set_get1(self):
        c = TConfigurable('foo', default=0, coerce=int)
        o = HasContext()
        o.context = mocks.Context()

        c.__set__(o, '5')

        self.assertEqual(c.__get__(o, None), 5)

    def test_set_get2(self):
        c = TConfigurable('foo')  # noqa: F841

        o = HasContext()
        o.context = mocks.Context()

        TConfigurable.set(o, 'foo', 'bar')
        self.assertEqual(TConfigurable.get(o, 'foo'), 'bar')

    def test_string(self):
        c = TConfigurable('foo')

        self.assertEqual(c.string(5), '5')

        c = TConfigurable('foo', string=lambda x: '%02d' % x)

        self.assertEqual(c.string(5), '05')

    def test_overrides(self):
        c = TConfigurable('foo', validate=lambda x: isinstance(x, str))

        TConfigurable.set_overrides({'foo': 'bar'})

        self.assertEqual(c.__get__(HasContext(), None), 'bar')

        with self.assertRaises(ValueError):
            TConfigurable.set_overrides({'foo': 5})


class TestCoerceBool(unittest.TestCase):
    def test(self):
        self.assertEqual(snipe.util.coerce_bool(1), True)
        self.assertEqual(snipe.util.coerce_bool(0), False)
        self.assertEqual(snipe.util.coerce_bool('zog'), False)
        self.assertEqual(snipe.util.coerce_bool('TRUE'), True)
        self.assertEqual(snipe.util.coerce_bool('oN'), True)
        self.assertEqual(snipe.util.coerce_bool('yes'), True)


class TLevel(snipe.util.Level):
    registry: Dict[str, snipe.util.Configurable] = {}


class TestLevel(unittest.TestCase):
    def test(self):
        c = TLevel('foo', logger='foo', default=logging.ERROR)  # noqa: F841
        o = HasContext()
        o.context = mocks.Context()

        TLevel.immanentize(o.context)

        self.assertEqual(logging.getLogger('foo').level, logging.ERROR)

        TLevel.set(o, 'foo', '10')
        self.assertEqual(logging.getLogger('foo').level, 10)

        TLevel.set(o, 'foo', 'warning')
        self.assertEqual(logging.getLogger('foo').level, logging.WARNING)

        self.assertRaises(ValueError, lambda: TLevel.set(o, 'foo', object()))
        self.assertRaises(ValueError, lambda: TLevel.set(o, 'foo', 'zog'))


class TestCoroCleanup(unittest.TestCase):
    def test(self):
        async def self_cancel():
            raise imbroglio.Cancelled

        wrapped = snipe.util.coro_cleanup(self_cancel)

        self.assertTrue(inspect.iscoroutinefunction(wrapped))

        with self.assertRaises(imbroglio.Cancelled):
            imbroglio.run(wrapped())

        async def key_error(*args):
            return {}[0]

        with self.assertLogs('coro_cleanup'):
            imbroglio.run(snipe.util.coro_cleanup(key_error)())

        class X:
            log = logging.getLogger('test_coro_cleanup')

        with self.assertLogs('test_coro_cleanup'):
            imbroglio.run(snipe.util.coro_cleanup(key_error)(X))


class TestStopwatch(unittest.TestCase):
    def test(self):
        with self.assertLogs('stopwatch', logging.DEBUG):
            with snipe.util.stopwatch('test'):
                pass


class JSONMixinTesterSuper:
    async def shutdown(self):
        self._is_shutdown = True


class MockHTTP:
    blobs = [b'']

    async def request(
            self,
            url,
            method='GET',
            *,
            json=None,
            data={},
            headers=(),
            log=None):
        self.url = url
        self._method = method
        self._json = json
        self._data = data
        self._headers = headers

        self.blobindex = 0

        return self

    async def readsome(self):
        if self.blobindex >= len(self.blobs):
            return None
        result = self.blobs[self.blobindex]
        self.blobindex += 1
        return result

    async def close(self):
        self.blobindex = 0


class JSONMixinTester(snipe.util.HTTP_JSONmixin, JSONMixinTesterSuper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TestHTTP_JSONmixin(unittest.TestCase):
    def test(self):
        with unittest.mock.patch('snipe.util.HTTP', MockHTTP()) as _HTTP:
            hjm = JSONMixinTester()

            hjm.log = logging.getLogger('test_http_json_mixin')
            hjm.url = 'http://example.com'

            hjm.setup_client_session()
            self.assertIn('User-Agent', dict(hjm._JSONmixin_headers))

            imbroglio.run(hjm.reset_client_session_headers())

            _HTTP.blobs = [json.dumps('foo').encode()]
            self.assertEqual('foo', imbroglio.run(hjm._post('/foo')))

            imbroglio.run(hjm.reset_client_session_headers({'foo': 'bar'}))
            self.assertEqual(dict(hjm._JSONmixin_headers)['foo'], 'bar')

            _HTTP.blobs = [b'zog']

            with self.assertRaises(snipe.util.JSONDecodeError) as ar:
                imbroglio.run(hjm._post_json('/bar', baz='quux'))

            self.assertIn('zog', str(ar.exception))
            self.assertEqual(_HTTP._method, 'POST')

            _HTTP.blobs = [json.dumps('foo').encode()]
            self.assertEqual('foo', imbroglio.run(hjm._get('/foo')))
            self.assertEqual(_HTTP._method, 'GET')

            self.assertEqual('foo', imbroglio.run(hjm._patch('/foo')))
            self.assertEqual(_HTTP._method, 'PATCH')

            imbroglio.run(hjm.shutdown())
            self.assertTrue(hjm._is_shutdown)


class MockHTTP_WS:
    def __init__(self):
        self._open = False

    async def request(self, url, headers={}, log=None):
        self._url = url
        self._headers = headers
        self._open = True
        self._wrote = None
        self._toread = None

        return self

    async def close(self):
        self._open = False

    async def write(self, data):
        self._wrote = data

    async def read(self):
        return self._toread


class TestJSONWebSocket(unittest.TestCase):
    def test(self):
        with unittest.mock.patch(
                'snipe.util.HTTP_WS', MockHTTP_WS()) as _HTTP_WS:
            jws = snipe.util.JSONWebSocket(
                logging.getLogger('test'))

            self.assertFalse(_HTTP_WS._open)
            imbroglio.run(jws.connect('/bar'))
            self.assertIs(jws.conn, _HTTP_WS)
            self.assertTrue(_HTTP_WS._open)

            _HTTP_WS._toread = json.dumps('foo')
            self.assertEqual(imbroglio.run(jws.read()), 'foo')

            imbroglio.run(jws.write('bar'))
            self.assertEqual(json.loads(_HTTP_WS._wrote), 'bar')

            _HTTP_WS._toread = 'bleah'
            with self.assertRaisesRegex(
                    snipe.util.JSONDecodeError, '.*bleah.*'):
                imbroglio.run(jws.read())

            imbroglio.run(jws.close())
            self.assertFalse(_HTTP_WS._open)


class MockCreateConnection:
    def __init__(self):
        self.left, self.right = socket.socketpair()

    def __call__(self, *args, **kw):
        self.args = args
        self.kw = kw
        return self.right


class TestNetworkStream(unittest.TestCase):
    def test(self):
        imbroglio.run(self._test())

    async def _test(self):
        with unittest.mock.patch(
                'socket.create_connection', MockCreateConnection()) as mc:
            mc.left.setblocking(False)
            self.assertIsInstance(
                socket.create_connection, MockCreateConnection)
            ns = await snipe.util.NetworkStream.connect('foo', 80)
            await ns.write(b'foo')
            self.assertEquals(b'foo', mc.left.recv(4096))

            mc.left.send(b'bar')
            self.assertTrue(await ns.readable())
            self.assertEquals(b'bar', (await ns.readsome()))

            mc.left.shutdown(socket.SHUT_RDWR)
            mc.left.close()
            self.assertEquals(None, (await ns.readsome()))
            self.assertFalse(await ns.readable())
            self.assertEquals(None, (await ns.readsome()))

            await ns.close()
            with self.assertRaises(OSError):
                ns.socket.send(b'foo')

        log = logging.getLogger('test')
        s = socket.socket()
        ns = snipe.util.NetworkStream(s, log=log)
        self.assertIs(log, ns.log)
        self.assertRegex(repr(ns), '^<NetworkStream')
        s.close()


class MockStream:
    def __init__(self, pending_eof=True):
        self.readdata = [b'stuff']
        self.wrote = []
        self.closed = False
        self.remaindata = len(self.readdata)
        self.reof = False
        self.pending_eof = pending_eof

    @classmethod
    async def connect(klass, host, port, log=None):
        self = klass(pending_eof=False)
        self.host = host
        self.port = port
        return self

    def __repr__(self):
        return '<MockStream>'

    def set_eof(self):
        self.reof = True
        self.readdata = []

    async def readsome(self):
        if self.reof:
            return None
        if not self.readdata:
            if self.pending_eof:
                self.reof = True
                return None
            return b''
        return self.readdata.pop(0)

    async def readable(self):
        return bool(self.readdata)

    async def write(self, data):
        self.wrote.append(data)

    async def close(self):
        self.closed = True

    def pushdata(self, *args):
        self.readdata.extend(args)

    async def maybewrite(self):
        pass


class MockContext:
    def __init__(self):
        self.read_exceptions = []

    def wrap_bio(self, incoming, outgoing, *, server_side, server_hostname):
        self.incoming = incoming
        self.outgoing = outgoing
        self.server_side = server_side
        self.server_hostname = server_hostname

        self.do_handshake_called = 0
        self.write_called = 0
        self.readex_iter = iter(self.read_exceptions)
        return self

    def do_handshake(self):
        self.do_handshake_called += 1
        if self.do_handshake_called == 1:
            self.outgoing.write(b'foo')
            raise ssl.SSLWantReadError
        elif self.do_handshake_called == 2:
            raise ssl.SSLWantReadError
        elif self.do_handshake_called == 3:
            self.outgoing.write(b'bar')
            raise ssl.SSLWantWriteError
        elif self.do_handshake_called == 4:
            self.outgoing.write(b'baz')

    def write(self, data):
        self.write_called += 1
        if self.write_called == 2:
            raise ssl.SSLWantReadError
        self.outgoing.write(data)

    def push_exceptions(self, *args):
        self.read_exceptions.extend(args)

    def read(self):
        if self.read_exceptions:
            raise self.read_exceptions.pop(0)
        return self.incoming.read()

    def pending(self):
        return bool(self.incoming.pending)


class TestSSLStream(unittest.TestCase):
    def test(self):
        imbroglio.run(self._test())

    async def _test(self):
        with unittest.mock.patch('ssl.create_default_context', MockContext):
            ss = snipe.util.SSLStream(MockStream(), 'foo')
            self.assertEqual('<SSLStream <MockStream>>', repr(ss))
            log = logging.getLogger('test')
            ss = snipe.util.SSLStream(MockStream(), 'foo', log=log)
            self.assertIs(log, ss.log)

            self.assertEqual(0, ss.obj.do_handshake_called)
            await ss.do_handshake()
            self.assertTrue(ss.handshake_done)

            self.assertEqual(4, ss.obj.do_handshake_called)
            await ss.do_handshake()
            self.assertEqual(4, ss.obj.do_handshake_called)

            self.assertEqual([b'foo', b'bar', b'baz'], ss.netstream.wrote)

            await ss.close()
            self.assertTrue(ss.netstream.closed)

            ss = snipe.util.SSLStream(MockStream(), 'foo')
            ss.handshake_done = True
            await ss.write(b'foo')
            self.assertEqual([b'foo'], ss.netstream.wrote)
            await ss.write(b'bar')
            self.assertEqual([b'foo', b'bar'], ss.netstream.wrote)
            self.assertEqual(3, ss.obj.write_called)

            ss.obj.write_called = 1  # roll back the number of writes
            await ss.write(b'baz')
            self.assertEqual([b'foo', b'bar', b'baz'], ss.netstream.wrote)

            self.assertEqual(b'stuff', ss.incoming.read())

            self.assertFalse(await ss.readable())
            self.assertTrue(ss.incoming.eof)

            ss = snipe.util.SSLStream(MockStream(), 'foo')
            ss.handshake_done = True

            ss.obj.outgoing.write(b'foo')
            await ss.maybewrite()

            self.assertEqual([b'foo'], ss.netstream.wrote)

            ss = snipe.util.SSLStream(MockStream(), 'foo')
            ss.handshake_done = True
            ss.netstream.reof = True
            # not 100% sure this can happend with NetworkStream
            # as current written, but it doesn exercise some code
            self.assertTrue(await ss.netstream.readable())
            self.assertFalse(await ss.readable())

            ss = snipe.util.SSLStream(MockStream(pending_eof=False), 'foo')
            ss.handshake_done = True

            self.assertTrue(await ss.readable())
            self.assertTrue(await ss.readable())
            self.assertEqual(b'stuff', (await ss.readsome()))
            self.assertFalse(await ss.readable())
            ss.obj.push_exceptions(ssl.SSLWantReadError)
            ss.netstream.set_eof()
            self.assertEqual(None, (await ss.readsome()))
            self.assertFalse(await ss.readable())

            ss = snipe.util.SSLStream(MockStream(pending_eof=False), 'foo')
            ss.handshake_done = True

            self.assertTrue(await ss.readable())
            self.assertTrue(await ss.readable())
            self.assertEqual(b'stuff', (await ss.readsome()))
            self.assertFalse(await ss.readable())
            ss.netstream.pushdata(b'things')
            self.assertTrue(await ss.readable())
            ss.obj.push_exceptions(ssl.SSLWantReadError)
            self.assertEqual(b'things', (await ss.readsome()))
            ss.netstream.set_eof()
            self.assertEqual(None, (await ss.readsome()))
            self.assertFalse(await ss.readable())
            self.assertEqual(None, (await ss.readsome()))

            ss = snipe.util.SSLStream(MockStream(), 'foo')
            ss.handshake_done = True
            ss.obj.push_exceptions(ssl.SSLEOFError)
            self.assertEqual(None, (await ss.readsome()))


class TestHTTP(unittest.TestCase):
    @snipe.imbroglio.test
    async def test0(self):
        with unittest.mock.patch('ssl.create_default_context', MockContext), \
                unittest.mock.patch('snipe.util.NetworkStream', MockStream):
            HTTP = await snipe.util.HTTP.request('https://foo/foo')
            self.assertIsInstance(HTTP.stream.obj, MockContext)
            self.assertIsInstance(HTTP.stream.netstream, MockStream)

            await HTTP.close()
            self.assertTrue(HTTP.stream.netstream.closed)

            log = logging.getLogger('test')
            HTTP = await snipe.util.HTTP.request('http://foo/foo', log=log)
            self.assertIsInstance(HTTP.stream, MockStream)

            self.assertEqual('<HTTP http://foo/foo <MockStream>>', repr(HTTP))

            self.assertEqual(
                b'GET /foo HTTP/1.1\r\nhost: foo\r\nconnection: close\r\n'
                b'accept-encoding: gzip\r\n\r\n',
                b''.join(HTTP.stream.wrote))

            HTTP = await snipe.util.HTTP.request(
                'http://foo/foo', method='POST', log=log, json='foo')
            self.assertEqual(
                b'POST /foo HTTP/1.1\r\nhost: foo\r\nconnection: close\r\n'
                b'accept-encoding: gzip\r\n'
                b'content-type: application/json\r\ncontent-length: 5\r\n\r\n'
                b'"foo"',
                b''.join(HTTP.stream.wrote))

            HTTP = await snipe.util.HTTP.request(
                'http://foo/foo', method='POST', log=log, data={'bar': 'foo'})
            self.assertEqual(
                b'POST /foo HTTP/1.1\r\nhost: foo\r\nconnection: close\r\n'
                b'accept-encoding: gzip\r\n'
                b'content-type: application/x-www-form-urlencoded\r\n'
                b'content-length: 7\r\n'
                b'\r\nbar=foo',
                b''.join(HTTP.stream.wrote))

    @snipe.imbroglio.test
    async def test1(self):
        with unittest.mock.patch('snipe.util.NetworkStream', MockStream):
            HTTP = await snipe.util.HTTP.request('http://foo/foo')
            self.assertIsInstance(HTTP.stream, MockStream)

            self.assertEqual('<HTTP http://foo/foo <MockStream>>', repr(HTTP))

            self.assertEqual(
                b'GET /foo HTTP/1.1\r\nhost: foo\r\nconnection: close\r\n'
                b'accept-encoding: gzip\r\n\r\n',
                b''.join(HTTP.stream.wrote))

            HTTP.stream.readdata = [
                b'',
                b'HTTP/1.1 200 Ok\r\nContent-Length: 5\r\n\r\nfoo\r\n'
                ]

            self.assertEqual(b'foo\r\n', (await HTTP.readsome()))

            HTTP = await snipe.util.HTTP.request('http://foo/foo')
            HTTP.stream.set_eof()

            with self.assertRaises(snipe.util.h11.RemoteProtocolError):
                await HTTP.readsome()

            HTTP = await snipe.util.HTTP.request('http://foo/foo')
            HTTP.stream.pending_eof = True
            HTTP.stream.readdata = [
                b'HTTP/1.1 200 Ok\r\n\r\n',
                b'foo\r\n',
                b'bar\r\n',
                ]

            self.assertEqual(b'foo\r\n', (await HTTP.readsome()))
            self.assertEqual(b'bar\r\n', (await HTTP.readsome()))
            self.assertIs(None, (await HTTP.readsome()))

    @snipe.imbroglio.test
    async def test_decompress(self):
        with unittest.mock.patch('snipe.util.NetworkStream', MockStream):
            HTTP = await snipe.util.HTTP.request('http://foo/foo')
            self.assertIsInstance(HTTP.stream, MockStream)

            self.assertEqual(
                b'GET /foo HTTP/1.1\r\nhost: foo\r\nconnection: close\r\n'
                b'accept-encoding: gzip\r\n\r\n',
                b''.join(HTTP.stream.wrote))

            k = zlib.compressobj(wbits=16 + zlib.MAX_WBITS)
            HTTP.stream.pending_eof = True
            HTTP.stream.readdata = [
                b'HTTP/1.1 200 Ok\r\nContent-Encoding: gzip\r\n\r\n',
                k.compress(b'foo\r\n') + k.flush(),
                ]

            self.assertEqual(b'foo\r\n', (await HTTP.readsome()))
            self.assertIs(None, (await HTTP.readsome()))


class WebSocketServerStream:
    def __init__(self):
        self.ws = wsproto.WSConnection(wsproto.ConnectionType.SERVER)
        self.out = []
        self.closed = False
        self.srream = None

    def __repr__(self):
        return f'{self.__class__.__name__}()'

    async def maybewrite(self):
        await imbroglio.sleep()

    async def readsome(self):
        out, self.out = self.out, []
        print(f'out: {out}')
        return b''.join(out)

    def _send(self, event):
        data = self.ws.send(event)
        print(f'_send: {data}')
        self.out.append(data)

    async def write(self, data):
        print(f'write: {data}')
        self.ws.receive_data(data)
        for event in self.ws.events():
            if isinstance(event, events.Request):
                self._send(events.AcceptConnection())
            elif isinstance(event, events.CloseConnection):
                self.closed = True
            elif isinstance(event, events.BytesMessage):
                self._send(events.Message(data=event.data))
            elif isinstance(event, events.TextMessage):
                self._send(events.Message(data=event.data))
            elif isinstance(event, events.Ping):
                self._send(event.response())

    def ping(self):
        self._send(events.Ping())

    def doclose(self):
        self._send(events.CloseConnection(code=0))

    async def close(self):
        pass


class TestHTTP_WS(unittest.TestCase):
    @imbroglio.test
    async def test_wsproto_headers(self):
        stream = MockStream()
        stream.readdata = [
            b'HTTP/1.1 200 Ok\r\n\r\n',
            ]
        HTTP_WS = snipe.util.HTTP_WS(
            'ws://foo/', stream=stream)
        with self.assertRaises(snipe.util.SnipeException):
            await HTTP_WS.connect([(b'Foo', b'bar')])
        data = (b''.join(stream.wrote)[16:])
        msg = email.parser.BytesParser().parsebytes(data)
        self.assertEqual('bar', msg['Foo'])

    @snipe.imbroglio.test
    async def test(self):
        stream = WebSocketServerStream()
        ws = await snipe.util.HTTP_WS.request(
            'http://foo/bar', stream=stream)
        self.assertEqual(
            repr(ws),
            r'<HTTP_WS http://foo/bar WebSocketServerStream()>')
        await ws.write('A' * 512)
        self.assertEqual('A' * 512, (await ws.read()))
        stream.ping()
        await ws.write(b'B' * 512)
        self.assertEqual(b'B' * 512, (await ws.read()))
        await ws.close()
        self.assertTrue(stream.closed)
        self.assertIsNone(await ws.read())
        self.assertIsNone(await ws.write(''))

    @snipe.imbroglio.test
    async def test_remoteclose(self):
        stream = WebSocketServerStream()
        ws = await snipe.util.HTTP_WS.request(
            'http://foo/bar', stream=stream)
        await ws.write('A' * 512)
        self.assertEqual('A' * 512, (await ws.read()))
        stream.doclose()
        self.assertIsNone(await ws.read())
        self.assertTrue(ws.closed)

    @snipe.imbroglio.test
    async def test_connect(self):
        ns_connect_called = False

        async def connect(*args, **kwargs):
            nonlocal ns_connect_called
            ns_connect_called = True

        async def _send(*args, **kwargs):
            raise Exception

        with mock.patch('snipe.util.NetworkStream.connect', connect), \
                mock.patch('snipe.util.SSLStream') as ssl, \
                mock.patch('snipe.util.HTTP_WS._send', _send):
            with self.assertRaises(Exception):
                await snipe.util.HTTP_WS.request('wss://foo')
            self.assertTrue(ns_connect_called)
            self.assertTrue(ssl.called)


if __name__ == '__main__':
    unittest.main()
