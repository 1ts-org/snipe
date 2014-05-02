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
#
#
# This was written while looking at
# https://github.com/roost-im/roost-python/blob/master/lib/roost.py
# which is by David Benjamin and Copyright © 2013 MIT.  I don't think
# there's enough of it to count as a derivative work, but credit where
# credit is due.

import asyncio
import json
import urllib.parse

from ._roost_python import krb5
from ._roost_python import gss

class Rooster:
    def __init__(self, url):
        self.token = None
        self.expires = None
        self.url = url
        self.principal = None
        self.ctx = None
        self.ccache = None

    @asyncio.coroutine
    def auth(self, create_user=False):
        self.ctx = krb5.Context()
        self.ccache = self.ctx.cc_default()
        self.principal = self.ccache.get_principal()
        princ_str = self.principal.unparse_name()

        client_name = gss.import_name(princ_str, gss.KRB5_NT_PRINCIPAL_NAME)
        target_name = gss.import_name(ROOST_SERVICE, gss.C_NT_HOSTBASED_SERVICE)
        cred = gss.acquire_cred(client_name, initiate=True)

        gss_ctx = gss.create_initiator(
            target_name, credential=cred, mechanism=gss.KRB5_MECHANISM)
        token = gss_ctx.init_sec_context()
        if not gss_ctx.is_established():
            raise Exception('Should be single-token')

        result = yield from self.http(
            '/v1/auth',
            {
                'principal': princ_str.decode('utf-8'),
                'token': base64.b64encode(token).decode('ascii'),
                'createUser': create_user,
                },
            )

        self.token = result['authToken']
        self.expires = result['expires']

    def ensure_auth(self):
        if self.token is None:
            yield from self.auth()

    @asyncio.coroutine
    def get_info(self):
        yield from self.ensure_auth()
        return (yield from self.http('/v1/info'))

    def zephyr_creds(self):
        #XXX hardcoded ATHENA.MIT.EDU
        zephyr = self.ctx.build_principal('ATHENA.MIT.EDU', ['zephyr', 'zephyr'])
        creds = self.ccache.get_credentials(self.principal, zephyr)
        return creds.to_dict()

    @asyncio.coroutine
    def send(self, message):
        yield from self.ensure_auth()
        return (yield from self.http(
            '/v1/zwrite', {
                'message': message,
                'credentials': self.zephyr_creds(),
                },
            ))

    @asyncio.coroutine
    def ping(self):
        yield from self.ensure_auth()
        return (yield from self.http('/v1/ping'))

    @asyncio.coroutine
    def subscriptions(self):
        yield from self.ensure_auth()
        return (yield from self.http('/v1/subscriptions'))

    @asyncio.coroutine
    def subscribe(self, subs):
        yield from self.ensure_auth()

        return (yield from self.http(
            '/v1/subscribe', {
                'subscriptions': [
                    {
                        'class': class_,
                        'instance': instance,
                        'recipient': recipient if recipient != '*' else '',
                        } for (class_, instance, recipient) in subs],
                'credentials': self.zephyr_creds(),
                },
            ))

    @asyncio.coroutine
    def check_zephyrcreds(self):
        yield from self.ensure_auth()
        return (yield from self.http('/v1/zephyrcreds'))

    @asyncio.coroutine
    def renew_zephyrcreds(self):
        yield from self.ensure_auth()
        return (yield from self.http(
            '/v1/zephyrcreds', {
                'credentials': self.zephyr_creds(),
                }
            ))

    @asyncio.coroutine
    def bytime(self, t):
        yield from self.ensure_auth()
        return (yield from self.http(
            '/v1/bytime',
            {
                't': t,
                },
            ))

    @asyncio.coroutine
    def messages(self, offset, limit, reverse=True, inclusive=True):
        yield from self.ensure_auth()

        if not offset:
            offset = ''

        return (yield from self.http(
            '/v1/messages',
            params = {
                'reverse': reverse,
                'inclusive': inclusive,
                'offset': offset,
                'count': limit,
                },
            ))

    @asyncio.coroutine
    def http(self, url, data=None, params=None):
        method = 'GET' if data is None else 'POST'

        if data is not None:
            data = json.dumps(data)

        headers = {}
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
        if self.token is not None:
            headers['Authorization'] = 'Bearer ' + self.token

        if params:
            print(urllib.parse.urlencode(params))

        response = yield from aiohttp.request(
            method,
            self.url + url,
            data = data,
            params = params,
            headers = headers,
            )

        result = []
        while True:
            try:
                result.append((yield from response.content.read()))
            except aiohttp.EofStream:
                break

        response.close()

        result = b''.join(result)
        result = result.decode('utf-8')
        try:
            result = json.loads(result)
        except:
            print (result)
            raise

        return result
