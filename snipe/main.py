# -*- encoding: utf-8 -*-

import asyncio
import logging

from . import ttyfe
from . import context


def main():
    logging.basicConfig(filename='/tmp/snipe.log', level=logging.DEBUG)
    with ttyfe.TTYFrontend() as ui:
        context_ = context.Context(ui)
        loop = asyncio.get_event_loop()
        loop.add_reader(0, ui.readable)
        ui.redisplay()
        loop.run_forever()
    logging.shutdown()


if __name__ == '__main__':
    main()
