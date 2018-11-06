#!/usr/bin/python3
import snipe.imbroglio
import pprint
import logging

import snipe._rooster


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(name)s %(module)s:%(lineno)d %(funcName)s %(message)s',
        )
    r = snipe._rooster.Rooster(
        # 'http://localhost:1080/', 'HTTP@http0.1ts.org')
        'https://roost-api.1ts.org/', 'HTTP')
    snipe.imbroglio.run(r.newmessages(printmsg))


async def printmsg(m):
    pprint.pprint(m)


if __name__ == '__main__':
    main()
