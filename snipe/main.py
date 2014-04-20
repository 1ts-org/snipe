# -*- encoding: utf-8 -*-

import logging

import twisted.internet.reactor

from . import ttyfe
from . import context


def main():
    logging.basicConfig(filename='/tmp/snipe.log', level=logging.DEBUG)
    with ttyfe.TTYFrontend() as ui:
        context_ = context.Context(ui)
        twisted.internet.reactor.addReader(ui)
        ui.redisplay()
        twisted.internet.reactor.run()
    logging.shutdown()


if __name__ == '__main__':
    main()
