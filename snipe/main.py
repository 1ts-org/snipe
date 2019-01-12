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
'''
snipe.main
----------
'''

import curses
import logging
import signal
import sys
import warnings

from . import context
from . import imbroglio
from . import ttyfe


def main():
    '''Main function, does high-level setup and kicks off the main loop.'''
    try:
        handler = context.SnipeLogHandler(logging.DEBUG)
        logging.getLogger().addHandler(handler)
        signal.signal(signal.SIGUSR1, handler.signal_dump)
        log = logging.getLogger('Snipe')
        log.warning('snipe starting')

        logging.captureWarnings(True)
        warnings.simplefilter('always')
        warnings.simplefilter('ignore', category=DeprecationWarning)

        options = parse_options(sys.argv)

        context_ = context.Context()
        handler.context = context_
        context_.load(options)

        imbroglio.run(main_task(context_, handler, log))
    except imbroglio.Cancelled:
        pass
    finally:
        try:
            curses.putp(curses.tigetstr('clear'))
        except curses.error:
            pass
        log.warning('snipe ends')
        print()
        print('shutting down...', end='', flush=True)
        if handler.writing:
            handler.dump()
        logging.shutdown()
        print('.', end='', flush=True)
    print('.', flush=True)


async def main_task(context_, handler, log):
    handler.supervisor = await imbroglio.get_supervisor()
    log.warning('handler supervisor set')
    async with ttyfe.TTYFrontend() as ui:
        await context_.start(ui)
        ui.redisplay()
        await ui.read_loop()
        await context_.shutdown()


def parse_options(argv):
    # XXX terriblest option parsing
    options = [x[2:].split('=', 1) for x in argv if x.startswith('-O')]
    options = [x if len(x) > 1 else x + ['true'] for x in options]
    return dict(options)


if __name__ == '__main__':
    main()  # pragma: nocover
