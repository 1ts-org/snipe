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
#
#
# This was written while looking at
# https://github.com/roost-im/roost-python/blob/master/lib/roost.py
# which is by David Benjamin and Copyright © 2013 MIT.  I don't think
# there's enough of it in this for this to count as a derivative work,
# but credit where credit is due.
'''
snipe._rooster
--------------

A layer of glue between the roost backend and the upstream code.
'''

import urllib.parse
import base64
import logging
import socket


from . import imbroglio
from . import util
from ._roost_python import krb5
from ._roost_python import gss


class RoosterException(util.SnipeException):
    pass


class RoosterReconnectException(RoosterException):
    def __init__(self, string, wait=0):
        self.string = string
        self.wait = wait

    def __str__(self):
        return self.string


class Rooster(util.HTTP_JSONmixin):
    def __init__(self, url, service):
        self.token = None
        self.url = url
        if self.url[-1] == '/':
            # strip _1_ trailing /
            self.url = self.url[:-1]
        self.inservice = service
        self.service = None
        self.principal = None
        self.ctx = None
        self.ccache = None
        self.tailid = 0
        self.log = logging.getLogger('Rooster.%x' % (id(self),))
        self.setup_client_session()

    async def credentials(self):
        return await imbroglio.run_in_thread(get_zephyr_creds)

    async def auth(self, create_user=False):
        hostname = urllib.parse.urlparse(self.url).hostname
        if hostname.lower() == 'localhost':
            hostname = await imbroglio.run_in_thread(socket.getfqdn)
        self.service = (
            self.inservice
            + ('@' + hostname if '@' not in self.inservice else ''))

        self.principal, token = await imbroglio.run_in_thread(
            get_auth_token, self.service)

        result = await self._post_json(
            '/v1/auth',
            principal=self.principal,
            token=token,
            createUser=create_user,
            )

        self.token = result['authToken']
        await self.reset_client_session_headers({
            'Authorization': 'Bearer ' + self.token,
            })

    async def ensure_auth(self):
        if self.token is None:
            await self.auth()

    async def get_info(self):
        await self.ensure_auth()
        return (await self._get('/v1/info'))

    async def send(self, message):
        await self.ensure_auth()
        return (await self._post_json(
            '/v1/zwrite',
            message=message,
            credentials=(await self.credentials()),
            ))

    async def ping(self):
        await self.ensure_auth()
        return (await self._get('/v1/ping'))

    async def subscriptions(self):
        await self.ensure_auth()
        return (await self._get('/v1/subscriptions'))

    @staticmethod
    def triplet_to_dict(triplet):
        class_, instance, recipient = triplet
        return {
            'class': class_,
            'instance': instance,
            'recipient': recipient if recipient != '*' else '',
            }

    async def subscribe(self, subs):
        await self.ensure_auth()

        return (await self._post_json(
            '/v1/subscribe',
            subscriptions=[self.triplet_to_dict(triplet) for triplet in subs],
            credentials=(await self.credentials()),
            ))

    async def unsubscribe(self, subs):
        await self.ensure_auth()
        result = None
        self.log.error('unsubscribe(%s)', subs)

        # Why does /v1/subscribe take a list while /v1/unsubscribe
        # take a single triplet?  Who can say?  According to the
        # dictionary, "literally" means "figuratively", which means
        # nothing means anything anything means nothing.  Fix it in
        # the client library.
        for triplet in subs:
            triplet_dict = self.triplet_to_dict(triplet)
            result = (await self._post_json(
                '/v1/unsubscribe',
                subscription=triplet_dict,
                credentials=(await self.credentials()),
                ))
            self.log.error('unsubscribe: %s -> %s', triplet_dict, result)
        return result

    async def check_zephyrcreds(self):
        await self.ensure_auth()
        return (await self._get('/v1/zephyrcreds'))

    async def renew_zephyrcreds(self):
        await self.ensure_auth()
        return (await self._post_json(
            '/v1/zephyrcreds', credentials=self.zephyr_creds()))

    async def bytime(self, t):
        await self.ensure_auth()
        return (await self._post_json('/v1/bytime', t=t))

    async def messages(self, offset, limit, reverse=True, inclusive=False):
        await self.ensure_auth()

        if not offset:
            offset = ''

        return (await self._get(
            '/v1/messages',
            reverse=1 if reverse else 0,
            inclusive=1 if inclusive else 0,
            offset=offset,
            count=limit,
            ))

    async def newmessages(
            self, coro, startid=None, pingfrequency=5, connected_coro=None):
        # will coincidentally ensure_auth
        if startid is None:
            ms = await self.messages(None, 1, reverse=1, inclusive=0)
            if ms['messages']:
                startid = ms['messages'][0]['id']
            else:
                startid = None

        self.log.debug('startid=%s', startid)

        ws = util.JSONWebSocket(self.log)

        try:
            try:
                await ws.connect(self.url + '/v1/socket/websocket')
            except OSError as e:
                self.log.debug('error connecting')
                raise RoosterReconnectException(str(e), wait=5) from e
            await ws.write({
                'type': 'auth',
                'token': self.token,
                })
            if connected_coro is not None:
                await connected_coro()

            state = 'start'
            msgcount = 1
            tailid = self.tailid
            self.tailid += 1

            self.log.debug('starting new message loop')
            while True:
                timedout = True
                try:
                    async with imbroglio.Timeout(pingfrequency):
                        m = await ws.read()
                        timedout = False
                    if timedout:
                        self.log.debug('read timeout state %s', state)
                        if state == 'pong':
                            self.log.debug('ping')
                            await ws.write({
                                'type': 'ping',
                                })
                            state = 'ping'
                            continue
                        else:
                            raise RoosterReconnectException('ping timeout')
                except OSError as e:
                    raise RoosterReconnectException(
                        f'{e}: disconnected') from e
                except Exception:
                    raise

                self.log.debug('midloop state = %s, m = %s', state, m)

                if state == 'start':
                    assert m['type'] == 'ready'
                    self.log.debug('authed, starting tail %d', tailid)
                    await ws.write({
                        'type': 'new-tail',
                        'id': tailid,
                        'start': startid,
                        'inclusive': False,
                        })
                    await ws.write({
                        'type': 'extend-tail',
                        'id': tailid,
                        'count': msgcount,
                        })
                    state = 'pong'
                elif state in ('ping', 'pong'):
                    if m['type'] == 'pong':
                        self.log.debug('pong')
                        state = 'pong'
                    elif m['type'] == 'messages':
                        msgcount += 1
                        await ws.write({
                            'type': 'extend-tail',
                            'id': tailid,
                            'count': msgcount,
                            })
                        for msg in m['messages']:
                            await coro(msg)
                    else:
                        self.log.debug('unknown message type: %s', repr(m))
        finally:
            await ws.close()


def get_auth_token(service):
    context = krb5.Context()
    ccache = context.cc_default()
    principal = ccache.get_principal()
    princ_str = principal.unparse_name()

    client_name = gss.import_name(princ_str, gss.KRB5_NT_PRINCIPAL_NAME)
    target_name = gss.import_name(service, gss.C_NT_HOSTBASED_SERVICE)
    cred = gss.acquire_cred(client_name, initiate=True)

    gss_ctx = gss.create_initiator(
        target_name, credential=cred, mechanism=gss.KRB5_MECHANISM)
    token = gss_ctx.init_sec_context()
    if not gss_ctx.is_established():
        raise Exception('Should be single-token')

    return princ_str.decode('utf-8'), base64.b64encode(token).decode('ascii')


def get_zephyr_creds():
    # XXX hardcoded ATHENA.MIT.EDU
    context = krb5.Context()
    ccache = context.cc_default()
    principal = ccache.get_principal()
    zephyr = context.build_principal('ATHENA.MIT.EDU', ['zephyr', 'zephyr'])
    creds = ccache.get_credentials(principal, zephyr)
    return creds.to_dict()
