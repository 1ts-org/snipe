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
Unit tests for stuff in messages.py
'''

import asyncio
import collections
import datetime
import itertools
import os
import sys
import time
import unittest

import mocks

sys.path.append('..')
sys.path.append('../lib')

import snipe.chunks as chunks      # noqa: E402
import snipe.filters as filters    # noqa: E402
import snipe.messages as messages  # noqa: E402
import snipe.util as util          # noqa: E402


class TestSnipeAddress(unittest.TestCase):
    def test(self):
        a = messages.SnipeAddress(None)
        self.assertEqual(a.address, [None])

        context = mocks.Context()
        s = SyntheticBackend(context, 'synthetic')

        a = messages.SnipeAddress(s, ['foo'])
        self.assertEqual(str(a), 'synthetic;foo')
        self.assertEqual(a.short(), str(a))
        self.assertEqual(a.reply(), str(a))
        self.assertEqual(repr(a), '<SnipeAddress synthetic foo>')


class TestMessage(unittest.TestCase):
    def test(self):
        os.environ['TZ'] = 'GMT'
        context = mocks.Context()
        s = SyntheticBackend(context, 'synthetic')
        m = messages.SnipeMessage(s, 'foo', 0.0)
        self.assertEqual(str(m.sender), 'synthetic')
        self.assertEqual(str(m), '00:00 synthetic\nfoo')
        self.assertEqual(
            m.display({}), [
                ({'bold'}, 'synthetic'),
                ({'right'}, ' 00:00:00'),
                (set(), 'foo\n'),
                ])
        self.assertIsNone(m.canon('foo', None))
        self.assertEqual(m.field('foo'), '')
        m.data['bar'] = 5
        self.assertEqual(m.field('bar'), 5)
        m.data['baz'] = 'quux'
        self.assertEqual(m.field('baz'), 'quux')

        timeything = collections.namedtuple('TimeyThing', ['time'])(0.0)
        self.assertEqual(m._coerce(timeything), 0.0)

        class IntyThing:
            __int__ = lambda self: 0  # noqa: E731
        intything = IntyThing()
        self.assertEqual(m._coerce(intything), 0)

        class FloatyThing:
            __float__ = lambda self: 0.0  # noqa: E731
        floatything = FloatyThing()
        self.assertEqual(m._coerce(floatything), 0.0)
        self.assertEqual(m._coerce('foo'), 'foo')

        self.assertEqual(m.reply(), s.name)
        self.assertEqual(m.followup(), s.name)

        self.assertEqual(m.filter(), filters.Compare('==', 'backend', s.name))

        self.assertEqual(float(m), m.time)

        m.transform('foo', 'bar')
        self.assertEqual(m.transformed, 'foo')
        self.assertEqual(m.body, 'bar')

        self.assertIs(
            m.get_decor({'decor': 'messages_tests.TestMessage'}),
            TestMessage)

        self.assertIs(
            m.get_decor({'decor': 'nonexistent.object'}),
            messages.SnipeMessage.Decor)


class TestDecor(unittest.TestCase):
    def test_decotags(self):
        self.assertEqual(
            set(messages.SnipeMessage.Decor.decotags(
                {'foreground': 'green', 'background': 'red'})),
            {'fg:green', 'bg:red'})

    def test_prefix_chunk(self):
        prefix_chunk = messages.SnipeMessage.Decor.prefix_chunk

        self.assertEqual(prefix_chunk('foo ', []), [])
        self.assertEqual(prefix_chunk(
            'foo ', chunks.Chunk([((), 'bar')])), [(set(), 'foo bar\n')])
        self.assertEqual(
            prefix_chunk('foo ', chunks.Chunk([((), 'bar\nbaz\n')])),
            [(set(), 'foo bar\nfoo baz\n')])
        self.assertEqual(
            prefix_chunk('foo ', chunks.Chunk([((), 'bar\n\nbaz\n')])),
            [(set(), 'foo bar\nfoo \nfoo baz\n')])

        self.assertEqual(
            prefix_chunk('foo ', chunks.Chunk([({'bold'}, 'bar\nbaz\n')])),
            [({'bold'}, 'foo bar\nfoo baz\n')])
        self.assertEqual(
            prefix_chunk('foo ', chunks.Chunk([({'bold'}, 'bar\n\nbaz\n')])),
            [
                ({'bold'}, 'foo bar\nfoo \nfoo baz\n'),
                ])
        self.assertEqual(
            prefix_chunk('foo ', chunks.Chunk([(('bold',), '\nbar\nbaz\n')])),
            [
                ({'bold'}, 'foo \nfoo bar\nfoo baz\n')])

        self.assertEqual(
            prefix_chunk(
                'foo ', chunks.Chunk([(('underline',), 'bar\nbaz\n')])),
            [
                (set(), 'foo '),
                ({'underline'}, 'bar'),
                (set(), '\nfoo '),
                ({'underline'}, 'baz'),
                (set(), '\n'),
                ])
        self.assertEqual(
            prefix_chunk(
                'foo ', chunks.Chunk([(('underline',), 'bar\n\nbaz\n')])),
            [
                (set(), 'foo '),
                ({'underline'}, 'bar'),
                (set(), '\nfoo \nfoo '),
                ({'underline'}, 'baz'),
                (set(), '\n'),
                ])

    def test_body(self):
        context = mocks.Context()
        s = SyntheticBackend(context, 'synthetic')
        m = messages.SnipeMessage(s, 'foo', 0.0)
        self.assertEqual(str(m.sender), 'synthetic')

        self.assertEqual(m.OnelineDecor.body(m), [])
        self.assertEqual(m.Decor.body(m), [(set(), 'foo\n')])
        s.indent = 'X '
        self.assertEqual(m.Decor.body(m), [(set(), 'X foo\n')])


class TestSnipeErrorMessage(unittest.TestCase):
    def test(self):
        s = SyntheticBackend(mocks.Context(), 'synthetic')
        m = messages.SnipeErrorMessage(s, 'error', 'traceback')
        self.assertTrue(m.error)
        self.assertEqual(
            str(m.filter()), 'backend == "synthetic" and error')
        self.assertEqual(
            str(m.filter(1)),
            'backend == "synthetic" and error and body == "error"')


class TestStartup(unittest.TestCase):
    def test(self):
        context = mocks.Context()
        startup = messages.StartupBackend(context)
        self.assertEqual(len(list(startup.walk(None))), 1)
        self.assertEqual(len(list(startup.walk(None, False))), 1)


class TestBackend(unittest.TestCase):
    def test_Backend(self):
        context = mocks.Context()
        synth = SyntheticBackend(context)
        synth.start()
        self.assertEqual(str(synth), synth.name)
        self.assertEqual(len(list(synth.walk(None))), 1)
        self.assertEqual(len(list(synth.walk(None, False))), 1)

        synth = SyntheticBackend(context, conf={'count': 3})
        synth.start()
        self.assertEqual(len(list(synth.walk(None))), 3)
        self.assertEqual(len(list(synth.walk(None, False))), 3)

        self.assertEqual(len(list(synth.walk(None))), 3)
        self.assertEqual(len(list(synth.walk(None, False))), 3)
        self.assertEqual(
            list(synth.walk(synth.messages[1], True)),
            [synth.messages[1], synth.messages[2]])
        self.assertEqual(
            list(synth.walk(synth.messages[1], False)),
            [synth.messages[1], synth.messages[0]])
        self.assertEqual(
            list(synth.walk(synth.messages[0], False)),
            [synth.messages[0]])

        self.assertFalse(synth.senders())
        self.assertFalse(synth.destinations())

        self.assertRaises(
            NotImplementedError, lambda: synth.send(None, None).send(None))

    def test_tasks(self):
        s = SyntheticBackend(mocks.Context())

        loop = asyncio.get_event_loop()

        @asyncio.coroutine
        def f():
            yield from asyncio.sleep(0)
        t = asyncio.Task(f())
        s.tasks.append(t)
        loop.run_until_complete(t)

        self.assertTrue(s.tasks)
        s.reap_tasks()
        self.assertFalse(s.tasks)

        t = asyncio.Task(f())
        s.tasks.append(t)
        loop.run_until_complete(s.shutdown())
        self.assertFalse(s.tasks)
        self.assertTrue(t.done())

        @asyncio.coroutine
        def g():
            raise Exception('exception')

        t = asyncio.Task(g())
        s.tasks.append(g)
        with self.assertLogs(s.log.name, level='ERROR'):
            loop.run_until_complete(s.shutdown())
        self.assertFalse(s.tasks)
        self.assertTrue(t.done())

    def test_redisplay(self):
        s = SyntheticBackend(mocks.Context())
        s.context.ui = mocks.FE()
        self.assertNotIn('redisplay', s.context.ui.called)
        s.redisplay(None, None)
        self.assertIn('redisplay', s.context.ui.called)
        s.context.ui.redisplay = lambda: None
        with self.assertLogs(s.log.name, level='ERROR'):
            s.redisplay(None, None)


class TestInfoMessage(unittest.TestCase):
    def test(self):
        m = messages.InfoMessage(None, 'foo')
        self.assertEquals(str(m), 'foo')
        self.assertEquals(m.display({}), [({'bold'}, 'foo')])


class TestDateBackend(unittest.TestCase):
    def test(self):
        d = messages.DateBackend(mocks.Context())
        d.context.backends.eldest = lambda: None
        self.assertFalse(list(d.walk(None, True)))
        self.assertFalse(list(d.walk(None, False)))

        d.context.backends.eldest = lambda: (
            datetime.datetime.now() - datetime.timedelta(days=1)).timestamp()
        self.assertTrue(list(d.walk(None, True)))
        self.assertFalse(list(d.walk(None, True, search=True)))

        self.assertFalse(list(d.walk(float('Inf'), True)))
        self.assertTrue(list(d.walk(float('Inf'), False)))
        self.assertTrue(list(d.walk(-float('Inf'), True)))

        self.assertTrue(list(d.walk(d.starting_at.timestamp() + .1, True)))

        self.assertEqual(d.count(), 0)

        self.assertIsNone(d.eldest())


class TestMerge(unittest.TestCase):
    def test(self):
        self.assertEquals(
            list(messages.merge([
                [1, 3, 5],
                [2, 3, 4, 6, 8],
                []])),
            [1, 2, 3, 4, 5, 6, 8])


class TestAggregator(unittest.TestCase):
    def test(self):
        context = mocks.Context()
        synth = SyntheticBackend(context)
        startup = messages.StartupBackend(context)
        sink = messages.SinkBackend(context)
        a = messages.AggregatorBackend(context, [startup, synth, sink])
        a.start()
        self.assertEqual(startup.count(), 1)
        self.assertEqual(synth.count(), 1)
        self.assertEqual(a.count(), 3)
        self.assertEqual(len(list(a.walk(None, False))), 3)
        list(a.send('sink', 'a message'))
        self.assertEqual(a.count(), 4)
        self.assertEqual(len(list(a.walk(None, False))), 4)
        self.assertEqual(len(list(a.walk(None))), 4)
        self.assertEqual(len(list(a.walk(None, search=True))), 3)
        self.assertEqual(
            len(list(a.walk(None, filter=filters.makefilter('yes')))),
            4)
        self.assertEqual(
            len(list(a.walk(
                None,
                filter=filters.makefilter('backend == "sink"'),
                search=True))),
            1)
        self.assertEqual(len(list(a.walk(
            float('Inf'),
            forward=False,
            backfill_to=0.0,
            ))), 4)
        self.assertEqual(len(list(a.walk(float('-Inf')))), 4)

        for i in range(2):  # because caching?
            forward = list(a.walk(None, True))
            for (x, y) in list(zip([None] + forward, forward + [None]))[1:-1]:
                self.assertLess(x, y)

            backward = list(a.walk(None, False))
            for (x, y) in list(
                    zip([None] + backward, backward + [None]))[1:-1]:
                self.assertGreater(x, y)

        self.assertTrue(a.walk(forward[0], True))

        self.assertEqual(a.eldest(), synth.messages[0].time)

        self.assertRaises(
            util.SnipeException, lambda: a.send('nope', None).send(None))

        count = 0

        @asyncio.coroutine
        def mock_shutdown():
            nonlocal count
            count += 1

        for backend in a:
            backend.shutdown = mock_shutdown

        loop = asyncio.get_event_loop()
        loop.run_until_complete(a.shutdown())

        self.assertGreater(count, 0)

        count = 0

        def mock_backfill(filter, target):
            nonlocal count
            count += 1

        for backend in a:
            backend.backfill = mock_backfill

        a.backfill(None, None)

        self.assertGreater(count, 0)

        self.assertEqual(a.destinations(), set())
        self.assertEqual(a.senders(), set())

        self.assertEqual(a.count(), 4)
        synth2 = SyntheticBackend(context)
        a.add(synth2)
        self.assertEqual(a.count(), 5)


class SyntheticBackend(messages.SnipeBackend):
    name = 'synthetic'

    def __init__(self, context, name=None, conf={}):
        super().__init__(context, name, conf)
        self.conf = conf
        self.myname = name

    def start(self):
        super().start()
        count = self.conf.get('count', 1)
        string = self.conf.get('string', '0123456789')
        width = self.conf.get('width', 72)
        if self.myname is None:
            self.myname = '%s-%d-%s-%d' % (
                self.name, count, string, width)
        now = int(time.time())
        self.messages = [
            messages.SnipeMessage(
                self,
                ''.join(itertools.islice(
                    itertools.cycle(string),
                    i,
                    i + width)),
                now - count + i)
            for i in range(count)]


if __name__ == '__main__':
    unittest.main()
