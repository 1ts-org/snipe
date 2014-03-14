# -*- encoding: utf-8 -*-

import logging

from . import ttyfe
from . import mux
from . import context


def main():
    logging.basicConfig(filename='/tmp/snipe.log', level=logging.DEBUG)
    with ttyfe.TTYFrontend() as ui:
        muxer = mux.Mux()
        context_ = context.Context(muxer, ui)
        muxer.add(ui)
        ui.redisplay()
        muxer.wait_forever()
    logging.shutdown()


if __name__ == '__main__':
    main()
