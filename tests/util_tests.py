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
Unit tests for stuff in utils.py
'''


import asyncio
import logging
import os
import random
import sys
import tempfile
import unittest

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.util  # noqa: E402


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


class TestAsCoroutine(unittest.TestCase):
    def test(self):
        val = ''

        def normal():
            nonlocal val
            val = 'normal'

        async def coroutine():
            nonlocal val
            await asyncio.sleep(0)
            val = 'coroutine'

        async def yielder(f):
            await f()

        self.assertTrue(
            asyncio.iscoroutinefunction(snipe.util.as_coroutine(normal)))
        self.assertTrue(
            asyncio.iscoroutinefunction(snipe.util.as_coroutine(coroutine)))

        self.assertTrue(asyncio.iscoroutinefunction(coroutine))

        loop = asyncio.get_event_loop()

        self.assertEqual(val, '')

        loop.run_until_complete(yielder(snipe.util.as_coroutine(normal)))
        self.assertEqual(val, 'normal')

        loop.run_until_complete(yielder(snipe.util.as_coroutine(coroutine)))
        self.assertEqual(val, 'coroutine')


class TConfigurable(snipe.util.Configurable):
    # Override the registry so this doesn't mess with anything else's behavior
    registry = {}


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
    registry = {}


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
            raise asyncio.CancelledError

        wrapped = snipe.util.coro_cleanup(self_cancel)

        self.assertTrue(asyncio.iscoroutinefunction(wrapped))

        loop = asyncio.get_event_loop()
        with self.assertRaises(asyncio.CancelledError):
            loop.run_until_complete(wrapped())

        async def key_error(*args):
            return {}[0]

        with self.assertLogs('coro_cleanup'):
            loop.run_until_complete(snipe.util.coro_cleanup(key_error)())

        class X:
            log = logging.getLogger('test_coro_cleanup')

        with self.assertLogs('test_coro_cleanup'):
            loop.run_until_complete(snipe.util.coro_cleanup(key_error)(X))


class TestStopwatch(unittest.TestCase):
    def test(self):
        with self.assertLogs('stopwatch', logging.DEBUG):
            with snipe.util.stopwatch('test'):
                pass


class MockClientSession:
    def __init__(self, *args, **kw):
        self.args = args
        self.kw = kw
        self.result = None
        self.method = None
        self.closed = False

    async def post(self, *args, **kw):
        return (await self.request('post', *args, **kw))

    async def patch(self, *args, **kw):
        return (await self.request('patch', *args, **kw))

    async def get(self, *args, **kw):
        return (await self.request('get', *args, **kw))

    async def ws_connect(self, *args, **kw):
        return (await self.request('ws_connect', *args, **kw))

    async def request(self, method, *args, **kw):
        self.method = method
        return self.result

    def close(self):
        self.closed = True


class MockResult:
    def __init__(self, data, exception):
        self.data = data
        self.exception = exception
        self.url = ''
        self.closed = False
        self.wrote = None

    async def json(self):
        if self.exception is not None:
            raise self.exception

        return self.data

    async def read(self):
        return self.data

    receive_json = read

    async def send_json(self, data):
        self.wrote = data

    def release(self):
        pass

    async def close(self):
        self.closed = True


class JSONMixinTesterSuper:
    async def shutdown(self):
        pass


class JSONMixinTester(snipe.util.HTTP_JSONmixin, JSONMixinTesterSuper):
    pass


class TestHTTP_JSONmixin(unittest.TestCase):
    def test(self):
        hjm = JSONMixinTester()
        hjm.log = logging.getLogger('test_http_json_mixin')
        hjm.url = 'http://example.com'

        hjm.setup_client_session()
        self.assertIn('User-Agent', dict(hjm._JSONmixin_headers))

        run = asyncio.get_event_loop().run_until_complete
        run(hjm.reset_client_session_headers())

        hjm._clientsession.result = MockResult('foo', None)

        self.assertEqual('foo', run(hjm._post('/foo')))

        run(hjm.reset_client_session_headers({'foo': 'bar'}))
        self.assertIsNone(hjm._clientsession.result)
        self.assertEqual(hjm._JSONmixin_headers['foo'], 'bar')

        hjm._clientsession.result = MockResult(b'foo', UnicodeError)

        with self.assertRaises(snipe.util.JSONDecodeError) as ar:
            run(hjm._post_json('/bar', baz='quux'))

        self.assertIn('foo', str(ar.exception))

        self.assertEqual(hjm._clientsession.method, 'post')

        hjm._clientsession.result = MockResult('foo', None)

        self.assertEqual('foo', run(hjm._get('/foo')))
        self.assertEqual(hjm._clientsession.method, 'get')

        self.assertEqual('foo', run(hjm._patch('/foo')))
        self.assertEqual(hjm._clientsession.method, 'patch')

        self.assertEqual('foo', run(hjm._request('zog', '/foo')))
        self.assertEqual(hjm._clientsession.method, 'zog')

        self.assertFalse(hjm._clientsession.closed)
        run(hjm.shutdown())
        self.assertTrue(hjm._clientsession.closed)


class TestJSONWebSocket(unittest.TestCase):
    def test(self):
        jws = snipe.util.JSONWebSocket(
            logging.getLogger('test'))
        jws.session.result = MockResult('foo', None)
        print(jws.session)

        run = asyncio.get_event_loop().run_until_complete
        r = run(jws.connect('/bar'))
        self.assertEqual(jws.session.method, 'ws_connect')
        self.assertIs(r, jws.session.result)

        self.assertEqual(run(jws.read()), 'foo')

        run(jws.write('bar'))
        self.assertEqual(r.wrote, 'bar')

        run(jws.close())
        self.assertTrue(r.closed)
        self.assertTrue(jws.session.closed)


if __name__ == '__main__':
    unittest.main()
