# -*- encoding: utf-8 -*-
# This code is substantially from https://github.com/KeepSafe/aiohttp
# which is Copyright © 2014 Keepsafe and "offered under the BSD license."
# I (Karl Ramm) claim no ownership of it.
# Hopefully it will be contributed back in some form soon.

import os
import asyncio
import base64
import hashlib
import struct

import aiohttp
import aiohttp.websocket

from . import util

@asyncio.coroutine
def websocket(url, headers={}):
    sec_key = base64.b64encode(os.urandom(16))

    send_headers = {
        'UPGRADE': 'WebSocket',
        'CONNECTION': 'Upgrade',
        'SEC-WEBSOCKET-VERSION': '13',
        'SEC-WEBSOCKET-KEY': sec_key.decode(),
        'USER-AGENT': util.USER_AGENT,
    }

    send_headers.update(headers)

    response = yield from aiohttp.request(
        'GET', url, headers=send_headers, read_until_eof=False)
    try:
        # websocket handshake
        if response.status != 101:
            raise ValueError("Handshake error: Invalid response status")
        if response.headers.get('upgrade', '').lower() != 'websocket':
            raise ValueError("Handshake error - Invalid upgrade header")
        if response.headers.get('connection', '').lower() != 'upgrade':
            raise ValueError("Handshake error - Invalid connection header")

        key = response.headers.get('sec-websocket-accept', '').encode()
        match = base64.b64encode(
            hashlib.sha1(
                sec_key + aiohttp.websocket.WS_KEY
                ).digest())
        if key != match:
            raise ValueError("Handshake error - Invalid challenge response")

        reader = response.connection.reader.set_parser(aiohttp.websocket.WebSocketParser)
        writer = WebSocketClientWriter(response.connection.writer)
    except:
        response.close()
        raise
    return reader, writer, response


class WebSocketClientWriter(aiohttp.websocket.WebSocketWriter):
    def _send_frame(self, message, opcode):
        """Send a frame over the websocket with message as its payload."""
        header = bytes([0x80 | opcode])
        msg_length = len(message)

        if msg_length < 126:
            header += bytes([msg_length | 128])
        elif msg_length < (1 << 16):
            header += bytes([126 | 128]) + struct.pack('!H', msg_length)
        else:
            header += bytes([127 | 128]) + struct.pack('!Q', msg_length)

        mask = os.urandom(4)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(message))

        self.writer.write(header + mask + payload)
