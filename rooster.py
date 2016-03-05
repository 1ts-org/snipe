#!/usr/bin/python3
import asyncio
import pprint
import logging

import snipe._rooster

def main():
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    r = snipe._rooster.Rooster(
        'https://ordinator.1ts.org', 'daemon@ordinator.1ts.org')
    loop.run_until_complete(
        r.newmessages(
            asyncio.coroutine(lambda m: pprint.pprint(m))))

if __name__ == '__main__':
    main()
