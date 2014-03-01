# -*- encoding: utf-8 -*-

from . import ttyfe
from . import mux
from . import context


def main():
    with ttyfe.TTYFrontend() as ui:
        muxer = mux.Mux()
        context_ = context.Context(muxer, ui)
        muxer.add(ui)
        muxer.wait_forever()


if __name__ == '__main__':
    main()
