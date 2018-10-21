#!/usr/bin/python3
import asyncio
import pprint
import logging

import snipe._rooster


def main():
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    r = snipe._rooster.Rooster(
        # 'http://localhost:1080/', 'HTTP@http0.1ts.org')
        'https://roost-api.1ts.org/', 'HTTP')
    loop.run_until_complete(
        r.newmessages(
            asyncio.coroutine(lambda m: pprint.pprint(m))))


if __name__ == '__main__':
    main()
