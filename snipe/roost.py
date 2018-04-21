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
snipe.roost
-----------
Backend for talking to `roost <https://github.com/roost-im>`_
'''


import asyncio
import itertools
import time
import shlex
import os
import contextlib
import re
import pwd
import getopt
import traceback
import codecs
import subprocess
import inspect
import unicodedata

from . import chunks
from . import messages
from . import _rooster
from . import util
from . import filters
from . import keymap
from . import interactive
from . import zcode


_backend = 'Roost'


class Roost(messages.SnipeBackend):
    name = 'roost'

    backfill_count = util.Configurable(
        'roost.backfill_count', 8,
        'Keep backfilling until you have this many messages'
        ' unless you hit the time limit',
        coerce=int)
    backfill_length = util.Configurable(
        'roost.backfill_length', 24 * 3600,
        'only backfill this far looking for roost.backfill_count messages',
        coerce=int)
    url = util.Configurable(
        'roost.url', 'https://roost-api.mit.edu')
    service_name = util.Configurable(
        'roost.servicename', 'HTTP',
        "Kerberos servicename, you probably don't need to change this")
    realm = util.Configurable(
        'roost.realm', 'ATHENA.MIT.EDU',
        'Zephyr realm that roost is fronting for')
    signature = util.Configurable(
        'roost.signature', pwd.getpwuid(os.getuid()).pw_gecos.split(',')[0],
        'Name-ish field on messages')
    subunify = util.Configurable(
        'roost.subunify', False, 'un-ify subscriptions')
    FORMAT_TYPES = {'strip', 'raw', 'format'}
    FORMAT_DOC = (
        '\n\nstrip - Remove markup\n'
        'raw - leave markup unmolested\nformat - obey the markup')
    format_zsig = util.Configurable(
        'roost.format.signature', 'strip',
        'How to display the signature' + FORMAT_DOC,
        oneof=FORMAT_TYPES)
    format_body = util.Configurable(
        'roost.format.message', 'format',
        'How to display the message body' + FORMAT_DOC,
        oneof=FORMAT_TYPES)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messages = []
        self.r = _rooster.Rooster(self.url, self.service_name)
        self.chunksize = 128
        self.loaded = False
        self.backfilling = False
        self.connected = False
        self._destinations = set()
        self._zephyr_subs = os.path.join(
            self.context.home_directory, '.zephyr.subs')

    def start(self):
        self.new_task = asyncio.Task(self.new_messages())
        self.tasks.append(self.new_task)

    @asyncio.coroutine
    def new_messages(self):
        while True:
            for m in reversed(self.messages):
                start = m.data.get('id')
                if start is not None:
                    break
            else:
                start = None

            errmsg = None
            activity = 'getting new messages from %s' % self.url
            try:
                self.connected = True  # XXX kinda racy?
                self.log.debug(activity)
                yield from self.r.newmessages(self.new_message, start)
            except _rooster.RoosterReconnectException as e:
                msg = '%s: %s' % (self.name, str(e))
                self.log.exception(msg)
                self.context.message(msg)
                if e.wait:
                    self.log.debug('waiting: %d', e.wait)
                    yield from asyncio.sleep(e.wait)
                continue
            except asyncio.CancelledError:
                return
            except Exception as exc:
                errmsg = str(exc)
                snipe_exception = isinstance(exc, util.SnipeException)
                self.log.exception(activity)
                tb = traceback.format_exc()
            finally:
                self.connected = False

            if errmsg is None:
                pass
            elif 'User does not exist' in errmsg:
                yield from self.new_registration()
            else:
                body = '%s: %s' % (activity, errmsg)
                if not snipe_exception:
                    body += '\n' + tb
                self.add_message(messages.SnipeErrorMessage(self, body, tb))
                return

    @asyncio.coroutine
    def new_registration(self):
        msg = inspect.cleandoc("""
        You don't seem to be registered with the roost server.  Select
        this message and hit Y to begin the registration process.
        You'll be asked to confirm again with a message somewhat more
        alarmist than necessary because I couldn't resist the
        reference to the Matrix.
        """)
        f = asyncio.Future()
        self.add_message(RoostRegistrationMessage(self, msg, f))
        yield from f

        f = asyncio.Future()
        msg = inspect.cleandoc("""
        This is your last chance.  After this, there is no turning
        back.  The roost server will be receiving your messages and
        storing them forever.  Press Y here if you're okay that the
        people who run the server might accidentally see some of your
        messages.
        """)
        self.add_message(RoostRegistrationMessage(self, msg, f))
        yield from f
        try:
            yield from self.r.auth(create_user=True)
            self.add_message(messages.SnipeMessage(self, 'Registered.'))
            self.load_subs(self._zephyr_subs)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.exception('registering')
            self.add_message(messages.SnipeErrorMessage(
                self, str(e), traceback.format_exc()))

    @asyncio.coroutine
    def error_message(self, activity, func, *args):
        """run a coroutine, creating a message with a traceback if it raises"""
        try:
            return (yield from func(*args))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.exception(activity)
            body = '%s: %s' % (activity, str(e))
            tb = traceback.format_exc()
            if not isinstance(e, util.SnipeException):
                body += '\n' + tb
            self.add_message(messages.SnipeErrorMessage(self, body, tb))

    @property
    def principal(self):
        return self.r.principal

    @asyncio.coroutine
    def send(self, paramstr, body):
        self.log.debug('send paramstr=%s', paramstr)

        flags, recipients = getopt.getopt(shlex.split(paramstr), 'xRCc:i:O:')

        flags = dict(flags)
        self.log.debug('send flags=%s', repr(flags))

        if not recipients:
            recipients = ['']

        if '-C' in flags and len(recipients) > 1:
            body = 'CC: ' + ' '.join(recipients) + '\n' + body

        if '-R' in flags:
            body = codecs.encode(body, 'rot13')

        for recipient in recipients:
            if '-x' in flags:
                flags['-O'] = 'crypt'
                cmd = ['zcrypt', '-E', '-c', flags.get('-c', 'MESSAGE')]
                proc = yield from asyncio.create_subprocess_exec(
                    *cmd,
                    **dict(
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        )
                    )
                stdout, stderr = yield from proc.communicate(body.encode())
                stdout = stdout.decode(errors='replace')
                stderr = stderr.decode(errors='replace')
                if proc.returncode:
                    self.log.error(
                        'roost: %s returned %d',
                        ' '.join(cmd), proc.returncode)
                if stderr:
                    self.log.error(
                        'roost: %s send %s to stderr',
                        ' '.join(cmd), repr(stderr))
                    raise Exception('zcrypt: ' + stderr)
                if proc.returncode:
                    raise Exception('zcrypt returned %d' % (proc.returncode))
                body = stdout

            message = {
                'class': flags.get('-c', 'MESSAGE'),
                'instance': flags.get('-i', 'PERSONAL'),
                'recipient': recipient,
                'opcode': flags.get('-O', ''),
                'signature': flags.get('-s', self.signature),
                'message': body,
                }

            self.log.debug('sending %s', repr(message))

            result = yield from self.r.send(message)
            self.log.info('sent to %s: %s', recipient, repr(result))

    @asyncio.coroutine
    def new_message(self, m):
        msg = yield from self.construct_and_maybe_decrypt(m)
        self.add_message(msg)

    def add_message(self, msg):
        if self.messages and msg.time <= self.messages[-1].time:
            msg.time = self.messages[-1].time + .00001
        self.messages.append(msg)
        self.drop_cache()
        self.redisplay(msg, msg)

    @asyncio.coroutine
    def construct_and_maybe_decrypt(self, m):
        msg = RoostMessage(self, m)
        try:
            if msg.data.get('opcode') == 'crypt':
                cmd = ['zcrypt', '-D', '-c', msg.data['class']]
                proc = yield from asyncio.create_subprocess_exec(
                    *cmd,
                    **dict(
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        )
                    )
                stdout, stderr = yield from proc.communicate(msg.body.encode())
                stdout = stdout.decode(errors='replace')
                stderr = stderr.decode(errors='replace')
                if proc.returncode:
                    self.log.error(
                        'roost: %s returned %d',
                        ' '.join(cmd),
                        proc.returncode)
                if stderr:
                    self.log.error(
                        'roost: %s send %s to stderr',
                        ' '.join(cmd), repr(stderr))
                if not (proc.returncode or stderr):
                    sigil = '**END**\n'
                    if stdout.endswith(sigil):
                        stdout = stdout[:-len(sigil)]
                    msg.transform('zcrypt', stdout)
        except:
            self.log.exception('zcrypt, decrypting')

        self._destinations.add(msg.followup())
        self._destinations.add(msg.reply())
        self._senders.add(msg.reply())
        return msg

    def backfill(self, mfilter, target=None, count=0, origin=None):
        self.log.debug(
            'backfill([filter], target=%s, count=%s, origin=%s)',
            util.timestr(target), count, util.timestr(origin))

        # if we're not gettting new messages, don't try to get old ones
        if not self.connected or self.loaded or target is None:
            return

        filledpoint = self.messages[0].time if self.messages else time.time()

        if filledpoint < target:
            self.log.debug(
                '%s < %s', util.timestr(filledpoint), util.timestr(target))
            return

        target = max(target, filledpoint - self.backfill_length)

        self.log.debug('triggering backfill, target=%s', util.timestr(target))

        msgid = None
        if self.messages:
            msgid = self.messages[0].data.get('id')
            if origin is None:
                origin = filledpoint

        self.reap_tasks()
        self.tasks.append(
            asyncio.Task(self.error_message(
                'backfilling',
                self.do_backfill, msgid, mfilter, target, count, origin)))

    @asyncio.coroutine
    def do_backfill(self, start, mfilter, target, count, origin):
        # yield from asyncio.sleep(.0001)
        self.log.debug(
            'do_backfill(start=%s, [filter], %s, %s, origin=%s)',
            repr(start),
            util.timestr(target),
            repr(count),
            util.timestr(origin))

        @contextlib.contextmanager
        def backfillguard():
            if self.backfilling:
                yield True
            else:
                self.log.debug('entering guard')
                self.backfilling = True
                yield False
                self.backfilling = False
                self.log.debug('leaving guard')

        with backfillguard() as already:
            if already:
                self.log.debug('already backfiling')
                return

            if mfilter is None:
                def mfilter(m):
                    return True

            if self.loaded:
                self.log.debug('no more messages to backfill')
                return
            self.log.debug('backfilling')
            chunk = yield from self.r.messages(start, self.chunksize)

            if chunk['isDone']:
                self.log.info('IT IS DONE.')
                self.loaded = True
            ms = []
            for m in chunk['messages']:
                cm = yield from self.construct_and_maybe_decrypt(m)
                ms.append(cm)
            count += len([m for m in ms if mfilter(m)])
            # Make sure ordering is stable
            # XXX really assuming messages are millisecond unique si dumb
            anchor = []
            if self.messages and ms:
                anchor = [(self.messages[0], ms[0])]
            for (nextmsg, prevmsg) in itertools.chain(anchor, zip(ms, ms[1:])):
                # walking backwards through time
                if nextmsg.time == prevmsg.time:
                    prevmsg.time = nextmsg.time - .00001
            ms.reverse()
            self.messages = ms + self.messages
            self.drop_cache()
            self.log.warning(
                '%d messages, total %d, earliest %s',
                count,
                len(self.messages),
                util.timestr(self.messages[0].time) if self.messages else '-')

            # and (maybe) circle around
            yield from asyncio.sleep(.1)
            self.backfill(mfilter, target, count=count, origin=origin)

            if ms:
                self.redisplay(ms[0], ms[-1])
            else:
                self.redisplay(None, None)
            self.log.debug('done backfilling')

    @keymap.bind('R S')
    def dump_subscriptions(self, window: interactive.window):
        subs = yield from self.r.subscriptions()
        subs = [
            (x['class'], x['instance'], x['recipient'] or '*') for x in subs]
        subs.sort()
        subs = [' '.join(x) for x in subs]
        window.show('\n'.join(subs))

    @staticmethod
    def spec_to_triplets(params):
        flags, rest = getopt.getopt(shlex.split(params.strip()), 'c:i:r:')
        flags = dict(flags)

        instance = flags.get('-i', '*')
        realm = flags.get('-r', '')
        if realm and not realm.startswith('@'):
            realm = '@' + realm

        if '-c' in flags or not rest:
            class_ = flags.get('-c', 'MESSAGE')
            recipients = rest

            return [(class_, instance, rec + realm) for rec in recipients]
        else:
            return [(class_, instance, realm) for class_ in rest]

    @asyncio.coroutine
    def load_subs(self, filename):
        if not os.path.exists(filename):
            return
        with open(filename) as fp:
            lines = fp.read().split()
        triplets = [line.split(',', 2) for line in lines]

        for triplet in triplets:
            if triplet[2].endswith('@' + self.realm) and triplet[2][0] in '@*':
                triplet[2] = '*'

        yield from self.r.subscribe(triplets)

    @staticmethod
    @util.listify
    def do_subunify(subs):
        for (class_, instance, recipient) in subs:
            for (i, j) in itertools.product(range(4), range(4)):
                yield ('un' * i + class_ + '.d' * j, instance, recipient)

    @keymap.bind('R s')
    def subscribe(self, window: interactive.window):
        spec = yield from window.read_string(
            'subscribe to: ',
            name='zephyr class',
            )
        if spec.strip():
            subs = self.spec_to_triplets(spec)
            if self.subunify:
                subs = self.do_subunify(subs)
            self.log.debug('subbing to %s', repr(subs))
            yield from self.r.subscribe(subs)

    @keymap.bind('R l')
    def subscribe_file(self, window: interactive.window):
        default = self._zephyr_subs
        if not os.path.exists(default):
            default = None
        filename = yield from window.read_filename(
            'Load subscriptions from file: ', content=default)
        yield from self.load_subs(filename)

    @keymap.bind('R u')
    def unsubscribe(self, window: interactive.window):
        spec = yield from window.read_string(
            'unsubscribe from: ',
            name='zephyr class',
            )
        if spec.strip():
            subs = self.spec_to_triplets(spec)
            if self.subunify:
                subs = self.do_subunify(subs)
            self.log.debug('unsubbing from %s', repr(subs))
            yield from self.r.unsubscribe(subs)

    @keymap.bind('R R')
    def reconnect(self):
        if self.new_task is not None and not self.new_task.done():
            self.disconnect()
        self.start()

    @keymap.bind('R D')
    def disconnect(self):
        self.new_task.cancel()
        try:
            yield from self.new_task
        except:
            self.log.exception('cancelling new_task')
        with contextlib.suppress(ValueError):
            self.tasks.remove(self.new_task)
        self.new_task = None


class RoostMessage(messages.SnipeMessage):
    def __init__(self, backend, m):
        super().__init__(backend, m['message'], m['receiveTime'] / 1000)
        self.data = m
        self._sender = RoostPrincipal(backend, m['sender'])

        self.personal = (
            self.data['recipient'] and self.data['recipient'][0] != '@')
        self.outgoing = self.data['sender'] == self.backend.r.principal

    def __str__(self):
        return (
            'Class: {class_} Instance: {instance} Recipient: {recipient}'
            '{opcode}\n'
            'From: {signature} <{sender}> at {date}\n'
            '{body}\n').format(
            class_=self.data['class'],
            instance=self.data['instance'],
            recipient=self.data['recipient'],
            opcode=(
                ''
                if not self.data['opcode']
                else ' [{}]'.format(self.data['opcode'])),
            signature=self.data['signature'],
            sender=self.sender,
            date=time.ctime(self.data['time'] / 1000),
            body=self.body
                + ('' if self.body and self.body[-1] == '\n' else '\n'),
            )

    class_un = re.compile(r'^(un)*')
    class_dotd = re.compile(r'(\.d)*$')

    @staticmethod
    def _normalize(value):
        return unicodedata.normalize('NFKC', value).lower()

    def canon(self, field, value):
        if field == 'sender' or field == 'recipient':
            value = str(value)
            atrealmlen = len(self.backend.realm) + 1
            if value[-atrealmlen:] == '@' + self.backend.realm:
                return value[:-atrealmlen]
        elif field == 'class':
            value = self._normalize(value)
            x1, x2 = self.class_un.search(value).span()
            value = value[x2:]
            x1, x2 = self.class_dotd.search(value).span()
            value = value[:x1]
        elif field == 'instance':
            value = self._normalize(value)
            x1, x2 = self.class_dotd.search(value).span()
            value = value[:x1]
        elif field == 'opcode':
            value = value.lower().strip()
        return value

    def reply(self):
        l = []
        if self.transformed == 'rot13':
            l += ['-R']
        if self.data['recipient'] and self.data['recipient'][0] != '@':
            if self.data['class'].upper() != 'MESSAGE':
                l += ['-c', self.data['class']]
            if self.data['instance'].upper() != 'PERSONAL':
                l += ['-i', self.data['instance']]
        if self.outgoing and self.data['recipient']:
            l.append(self.data['recipient'])
        else:
            l.append(self.sender.short())

        return self.backend.name + '; ' + ' '.join(shlex.quote(s) for s in l)

    def followup(self):
        l = []
        if self.transformed == 'rot13':
            l += ['-R']
        if self.transformed == 'zcrypt':
            l += ['-x']
        if self.data['class'].upper() != 'MESSAGE':
            l += ['-c', self.data['class']]
        if self.data['instance'].upper() != 'PERSONAL':
            l += ['-i', self.data['instance']]
        if self.data['recipient'] and self.data['recipient'][0] != '@':
            if not self.body.startswith('CC: '):
                return self.reply()
            else:
                cc = self.body.splitlines()[0].split()[1:]
                cc.append(self.sender.short())
                cc = [self.canon('sender', x) for x in cc]  # canonicalize
                me = self.canon('sender', self.backend.r.principal)
                cc = list(sorted(set(cc) - {me}))  # uniquify, filter self
                l += ['-C'] + cc
        if self.data['recipient'] and self.data['recipient'][0] == '@':
            l += [self.data['recipient']]  # presumably a there should be a -r?
        return self.backend.name + '; ' + ' '.join(shlex.quote(s) for s in l)

    def filter(self, specificity=0):
        nfilter = filters.Compare('==', 'backend', self.backend.name)
        if self.personal:
            if str(self._sender) == self.backend.principal:
                sender = self.backend.name + '; ' + self.field('recipient')
                recipient = self.field('recipient')
            else:
                sender = self.field('sender')
                recipient = self.canon('sender', self.data['sender'])
            return filters.And(
                nfilter,
                filters.Truth('personal'),
                filters.Or(
                    filters.Compare('=', 'sender', sender),
                    filters.Compare('=', 'recipient', recipient)))
        elif self.field('class'):
            nfilter = filters.And(
                nfilter,
                filters.Compare('=', 'class', self.field('class')))
            if specificity > 0:
                nfilter = filters.And(
                    nfilter,
                    filters.Compare('=', 'instance', self.field('instance')))
            if specificity > 1:
                nfilter = filters.And(
                    nfilter,
                    filters.Compare('=', 'sender', self.field('sender')))
            return nfilter

        return super().filter(specificity)  # pragma: nocover

    class Decor(messages.SnipeMessage.Decor):
        @classmethod
        def headline(self, msg, tags=set()):
            instance = msg.data['instance']
            instance = instance or "''"
            chunk = chunks.Chunk()

            if msg.personal:
                if msg.outgoing:
                    chunk += [(
                        tags | {'bold'},
                        '(personal> <' + msg.field('recipient') + '>')]
                else:
                    chunk += [(tags | {'bold'}, '<personal)')]

            if not msg.personal or msg.data['class'].lower() != 'message':
                chunk += [
                    (tags, '-c '),
                    (tags | {'bold'}, msg.data['class']),
                    ]
            if instance.lower() != 'personal':
                chunk += [
                    (tags, ' -i ' + instance),
                    ]

            if msg.data['recipient'] and msg.data['recipient'][0] == '@':
                chunk += [(tags | {'bold'}, ' ' + msg.data['recipient'])]

            if msg.data['opcode']:
                chunk += [(tags, ' [' + msg.data['opcode'] + ']')]

            chunk += [
                (tags, ' <'),
                (tags | {'bold'}, msg.sender.short()),
                (tags, '>'),
                ]

            sig = msg.data.get('signature', '').strip()
            if sig:
                sigl = sig.split('\n')
                sig = '\n'.join(sigl[:1] + ['    ' + s for s in sigl[1:]])
                if msg.backend.format_zsig == 'format':
                    chunk += [(tags, ' ')] + zcode.tag(sig, frozenset(tags))
                else:
                    if msg.backend.format_zsig == 'strip':
                        sig = zcode.strip(sig)
                    chunk += [
                        (tags, ' ' + sig),
                        ]

            chunk.append(
                (tags | {'right'},
                 time.strftime(
                    ' %H:%M:%S', time.localtime(msg.data['time'] / 1000))))

            return chunk

        @classmethod
        def format(self, msg, tags=set()):
            body = msg.body
            if body:
                if not body.endswith('\n'):
                    body += '\n'
                if msg.backend.format_body == 'format':
                    chunk = zcode.tag(body, frozenset(tags))
                else:
                    if msg.backend.format_body == 'strip':
                        body = zcode.strip(body)
                    chunk = chunks.Chunk([(tags, body)])
            else:
                chunk = chunks.Chunk()

            return chunk.show_control()


class RoostPrincipal(messages.SnipeAddress):
    def __init__(self, backend, principal):
        self.principal = principal
        super().__init__(backend, [principal])

    def __str__(self):
        return self.backend.name + '; ' + self.short()

    def short(self):
        atrealmlen = len(self.backend.realm) + 1
        if self.principal[-atrealmlen:] == '@' + self.backend.realm:
            return self.principal[:-atrealmlen]
        return self.principal


class RoostRegistrationMessage(messages.SnipeMessage):
    def __init__(self, backend, text, future):
        super().__init__(backend, text)
        self.future = future

    @keymap.bind('Y')
    def forward_the_future(self):
        if not self.future.done():
            self.future.set_result(None)
