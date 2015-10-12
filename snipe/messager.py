#!/usr/bin/python3
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
snipe.messager
--------------
UI for looking at messages.
'''


import time
import datetime
import traceback
import pprint
import asyncio
import bisect

from . import filters
from . import roost
from . import keymap
from . import window
from . import help
from . import editor
from . import prompt
from . import util
from . import interactive


class Messager(window.Window, window.PagingMixIn):
    default_filter = util.Configurable(
        'default_filter', None,
        'Default filter for messager windows',
        validate=filters.validatefilter,
        )

    def __init__(self, *args, filter_new = None, prototype=None, **kw):
        super().__init__(*args, **kw)

        if prototype is None:
            self.cursor = next(self.fe.context.backends.walk(None, False))
            self.the_mark = None
            self.mark_ring = []
            self.filter_reset()
            self.starks = []
        else:
            self.filter = prototype.filter
            self.filter_stack = list(prototype.filter_stack)
            self.cursor = prototype.cursor
            self.the_mark = prototype.the_mark
            self.mark_ring = prototype.mark_ring
            self.starks = prototype.starks

        if filter_new is not None:
            self.filter_replace(filter_new)

        self.secondary = None
        self.keymap['[space]'] = self.pagedown
        self.keymap.interrogate(help)
        # the following will be interesting in the advent of non-singleton
        # backends; maybe this should just interrogate the modules instead
        for backend in self.context.backends:
            self.keymap.interrogate(backend)
            self.keymap.interrogate(backend.__class__.__module__)
        self.rules = []
        for (filt, decor) in self.context.conf.get('rule', []):
            try:
                self.rules.append((filters.makefilter(filt), decor))
            except:
                self.log.exception(
                    'error in filter %s for decor %s', filt, decor)
        self.real_keymap = self.keymap
        self.install_per_message_keymap()

    def focus(self):
        if self.secondary is not None:
            self.cursor = self.secondary
            self.secondary = None
        return True

    def walk(self, origin, direction, backfill_to=None, search=False):
        self.log.debug(
            'walk(%s, forward=%s, backfill_to=%s, search=%s)',
            repr(origin), repr(direction), util.timestr(backfill_to), repr(search))
        return self.fe.context.backends.walk(
            origin, direction, self.filter, backfill_to, search)

    def view(self, origin, direction='forward'):
        self.log.debug('view(%s, %s)', repr(origin), repr(direction))
        it = self.walk(origin, direction != 'forward')
        try:
            next(it)
            prev = next(it)
            backfill_to = prev.time
        except StopIteration:
            prev = None
            backfill_to = None

        for x in self.walk(
                origin, direction == 'forward', backfill_to=backfill_to):
            try:
                decoration = {}
                for filt, decor in self.rules:
                    if filt(x):
                        decoration.update(decor)
                chunk = x.display(decoration)
            except:
                chunk = [
                    (('bold',), repr(x) + '\n'),
                    ((), traceback.format_exc()),
                    ((), pprint.pformat(x.data) + '\n'),
                    ]

            if x == self.cursor or x == self.secondary:
                if not chunk:
                    # this is a bug so it will do the wrong thing sometimes
                    yield x, [(('visible', 'standout'), '\n')]
                    continue

                # carve off the first line
                first = []
                while True:
                    if not chunk:
                        # we ran out of chunks without hitting a \n
                        first[-1] = (first[-1][0], first[-1][1] + '\n')
                        break
                    tags, text = chunk[0]
                    if '\n' not in text and 'right' not in tags:
                        first.append((tags, text))
                        chunk = chunk[1:]
                    elif 'right' in tags:
                        first.append((tags, text))
                        chunk = chunk[1:]
                        break
                    else:
                        line, rest = text.split('\n', 1)
                        first.append((tags, line + '\n'))
                        chunk = [(tags, rest)] + chunk[1:]
                        break

                if x == self.cursor:
                    first = (
                        [(first[0][0] + ('visible',), first[0][1])] + first[1:])
                if x == self.secondary or self.secondary is None:
                    first = [
                        (tags + ('standout',), text) for (tags, text) in first]
                yield x, first + chunk
            else:
                yield x, chunk

            prev = x

    def check_redisplay_hint(self, hint):
        if super().check_redisplay_hint(hint):
            return True
        mrange = hint.get('messages')
        if mrange:
            head, sill = self.renderer.display_range()
            m1, m2 = mrange
            self.log.debug('head=%s, sill=%s', repr(head), repr(sill))
            self.log.debug('m1=%s, m2=%s', repr(m1), repr(m2))
            self.log.debug('max(head, m1)=%s', repr(max(head, m1)))
            self.log.debug('min(sill, m2)=%s', repr(min(sill, m2)))
            if max(head, m1) <= min(sill, m2):
                self.log.debug('True!')
                return True
        self.log.debug("Fals.e")
        return False

    def install_per_message_keymap(self):
        self.active_keymap = keymap.Keymap(self.active_keymap)
        if self.cursor is not None:
            self.active_keymap.interrogate(self.cursor)
        self.log.error('self.cursor is %s', repr(self.cursor))

    def after_command(self):
        super().after_command()
        if self.cursor.omega:
            m = self.replymsg()
            if m is not None and (
                    not self.starks or self.starks[-1] < m):
                self.starks.append(m)
        self.install_per_message_keymap()

    @keymap.bind('Control-n', 'n', 'j', '[down]')
    def next_message(self):
        """Move to the next message."""

        self.move(True)

    @keymap.bind('Control-p', 'p', 'k', '[up]')
    def prev_message(self):
        """Move to the previous message."""

        self.move(False)

    @keymap.bind('Meta-n') #XXX should be Meta-[down] as well but well, curses
    def next_messsage_cleverly(self, arg: interactive.argument=None):
        """Move to the next message that's sort of like the current one.
        Control-Us increase specificity if the backend supports it.  Repeated
        "clever" movement commands will retain the specificity."""

        self.move_cleverly(True, arg)

    @keymap.bind('Meta-p') #XXX should be Meta-[down] as well but well, curses
    def prev_messsage_cleverly(self, arg: interactive.argument=None):
        """Move to the last message that's sort of like the current one.
        Repeated "clever" movement commands will retain the specificity."""

        self.move_cleverly(False, arg)

    def move_cleverly(self, forward, arg):
        self.this_command = 'move_cleverly'
        if self.last_command != 'move_cleverly' or arg is not None:
            if arg == None:
                cleverness = 0
            elif isinstance(arg, int):
                cleverness = arg
            else:
                cleverness = len(arg)
            self.move_cleverly_state = cleverness
        self.move(forward, filters.And(
            self.filter,
            self.replymsg().filter(self.move_cleverly_state)))

    def move(self, forward, infilter=None):
        self.log.debug(
            'move %s: cursor: %s',
            'forward' if forward else 'backward',
            repr(self.cursor),
            )

        mfilter = infilter
        if mfilter is None:
            mfilter = self.filter

        target = None
        if not forward:
            target = float('-inf')

        it = iter(self.fe.context.backends.walk(
            self.cursor, forward, mfilter, target, infilter is not None))

        try:
            candidate = next(it)
            self.log.debug(
                'move %s: intermediate: %s',
                'forward' if forward else 'backward',
                repr(candidate),
                )
            if candidate == self.cursor:
                candidate = next(it)
            # you don't want to move-with-filter onto the omega message,
            # but the omega message has code to buypass filters.  meh.
            if infilter is None or not candidate.omega:
                self.cursor = candidate
            self.log.debug(
                'move %s: cursor: %s',
                'forward' if forward else 'backward',
                repr(self.cursor),
                )
        except StopIteration:
            self.whine('No more messages')

    def cursor_set_walk(self, origin, direction, backfill_to=None):
        """Set the cursor by getting the first result from a walk"""

        self.cursor = next(self.walk(origin, direction, backfill_to))

    def cursor_set_walk_mark(self, origin, direction, backfill_to=None):
        """Set the cursor by getting the first result from a walk, and set the
        mark if it changes."""

        old = self.cursor
        self.cursor_set_walk(origin, direction, backfill_to)
        if old != self.cursor:
            self.set_mark(old)

    @keymap.bind('s')
    def send(self, recipient='', msg=None):
        """Start composing a message."""

        sill = self.renderer.display_range()[1]
        if sill.omega: # We're at the bottom of the message list
            self.secondary = self.cursor
            self.cursor = sill

        kw = {}
        if msg is not None:
            kw['modes'] = [prompt.ReplyMode(msg)]

        message = yield from self.read_string(
            'compose (Control-J to send) --> ',
            height=10,
            content=recipient + '\n' if recipient else '',
            history='send',
            fill=True,
            **kw)
        if '\n' not in message:
            message += '\n'
        params, body = message.split('\n', 1)
        yield from self.fe.context.backends.send(params, body)

    def replymsg(self):
        replymsg = self.cursor
        if replymsg.omega:
            try:
                it = self.walk(self.cursor, False)
                next(it)
                replymsg = next(it)
            except StopIteration:
                replymsg = None
        return replymsg

    @keymap.bind('f')
    def followup(self):
        """Followup (wide-reply) to a message."""

        msg = self.replymsg()
        yield from self.send(msg.followup(), msg)

    @keymap.bind('r')
    def reply(self):
        """Replay (narrow-reply) to a message."""

        msg = self.replymsg()
        yield from self.send(msg.reply(), msg)

    @keymap.bind('[END]', 'Shift-[END]', '[SEND]', 'Meta->', '>')
    def last(self):
        """Move to the last message."""

        self.cursor_set_walk_mark(float('inf'), False)

    @keymap.bind('[HOME]', 'Shift-[HOME]', '[SHOME]', 'Meta-<', '<')
    def first(self):
        """Move to the first (currently loaded) message."""

        self.cursor_set_walk_mark(float('-inf'), True)

    def filter_replace(self, new_filter):
        self.filter = new_filter

        if self.filter is not None and not self.filter(self.cursor):
            # if filter is none, self.cursor is valid.
            with util.stopwatch('finding new cursor for filter'):
                self.cursor_set_walk(self.cursor, True)
            self.reframe()

    @keymap.bind('Meta-/ 0')
    def filter_reset(self):
        """Clear the filter stack and go back to the default filter."""

        self.filter_stack = []
        self.filter_replace(
            filters.makefilter(self.default_filter)
            if self.default_filter
            else None)

    @keymap.bind('Meta-/ =')
    def filter_edit(self, arg: interactive.argument=[]):
        """Edit the text representation of the current filter and push the
        result.

        With a prefix, ask for a named filter to edit."""

        if not arg:
            s = '' if self.filter is None else str(self.filter)

            s = yield from self.read_string(
                'Filter expression (Control-J when finished):\n', s, 5)

            self.filter_replace(filters.makefilter(s))
        else:
            conf = self.context.conf
            name = yield from self.read_string(
                'filter name: ',
                complete=interactive.completer(conf.get('filter', {}).keys()))
            name = name.strip()
            s = conf.get('filter', {}).get(name, '')
            s = yield from self.read_string(
                'Filter expression %s (Control-J when finished):\n' % (name,), s, 5)
            if not s.strip():
                if name in conf.get('filter', {}):
                    del conf['filter'][name]
            else:
                f = filters.makefilter(s)
                conf.setdefault('filter', {})[name] = str(f)
            self.context.conf_write()

    @keymap.bind('Meta-/ -')
    def filter_everything(self):
        """Filter everything."""

        self.filter_push_and_replace(filters.No())

    def filter_clear_decorate(self, decoration):
        self.rules = [
            (filt, decor) for (filt, decor) in self.rules if filt != self.filter]
        self.rules.append((self.filter, decoration))
        self.context.conf['rule'] = [
            (filts, decor)
            for (filts, decor) in self.context.conf.get('rule', [])
            if filts != str(self.filter)
            ]
        self.context.conf['rule'].append((str(self.filter), decoration))
        self.context.conf_write()
        self.filter_reset()

    @keymap.bind('Meta-/ g')
    def filter_foreground_background(self):
        """Take the current filter and set a foreground and background color for
        messages that match it."""
        fg = yield from self.read_string('Foreground: ')
        bg = yield from self.read_string('Background: ')
        self.filter_clear_decorate({'foreground': fg, 'background': bg})

    @keymap.bind('Meta-/ f')
    def filter_foreground(self):
        """Take the current filter and set a foreground color for messages that
        match it."""

        fg = yield from self.read_string('Foreground: ')
        self.filter_clear_decorate({'foreground': fg})

    @keymap.bind('Meta-/ b')
    def filter_background(self):
        """Take the current filter and set a background color for messages that
        match it."""

        bg = yield from self.read_string('Background: ')
        self.filter_clear_decorate({'background': bg})

    def filter_push_and_replace(self, new_filter):
        if self.filter is not None:
            self.filter_stack.append(self.filter)
        self.filter_replace(new_filter)

    def filter_push(self, new_filter):
        if self.filter is None:
            self.filter_push_and_replace(new_filter)
        else:
            self.filter_push_and_replace(filters.And(self.filter, new_filter))

    @keymap.bind('Meta-/ c')
    def filter_class(self):
        """Push a filter for a canonicalized zephyr class."""

        yield from self.do_filter_class('=')

    @keymap.bind('Meta-/ C')
    def filter_class_exactly(self):
        """Push a filter for an uncanonicalized zephyr class."""

        yield from self.do_filter_class('==')

    @asyncio.coroutine
    def do_filter_class(self, op):
        class_ = yield from self.read_string(
            'Class: ', self.replymsg().field('class', False))
        self.filter_push(filters.And(
            filters.Compare('==', 'backend', 'roost'),
            filters.Compare(op, 'class', class_)))

    @keymap.bind('Meta-/ p')
    def filter_personals(self):
        """Push a filter to only personal messages."""

        self.filter_push(filters.Truth('personal'))

    @keymap.bind('Meta-/ s')
    def filter_sender(self):
        """Push a filter to a sender."""

        sender = yield from self.read_string(
            'Sender: ', self.replymsg().field('sender'))
        self.filter_push(filters.Compare('=', 'sender', sender))

    @keymap.bind('Meta-/ /')
    def filter_cleverly(self, arg: interactive.argument=[]):
        """Push a filter based on the current message.  More Control-Us
        increase specificity, if the backend supports it."""

        self.filter_push(self.replymsg().filter(len(arg)))

    @keymap.bind('Meta-/ .')
    def filter_cleverly_negative(self, arg: interactive.argument=[]):
        """Push a negative filter based on the current message.  More
        Control-Us increase specificity, if the backend supports it."""

        self.filter_push(filters.Not(self.replymsg().filter(len(arg))))

    @keymap.bind("Meta-/ Meta-/")
    def filter_pop(self):
        """Pop the current filter, replacing it with the next one on the
        stack."""

        if not self.filter_stack:
            self.filter_reset()
        else:
            self.filter = self.filter_stack.pop()

    @keymap.bind('Meta-/ S')
    def filter_save(self, arg: interactive.argument=[]):
        """Save current the filter to a named filter.  With a prefix,
        save to the default filter."""

        if self.filter:

            if arg:
                self.default_filter = str(self.filter)
            else:
                conf = self.context.conf
                name = yield from self.read_string(
                    'target filter name: ',
                    complete=interactive.completer(
                            conf.get('filter', {}).keys()))
                name = name.strip()
                conf.setdefault('filter', {})[name] = str(self.filter)
            self.context.conf_write()
            self.filter_reset()

    @keymap.bind('Meta-i')
    def show_message_data(self):
        """Dump the current message data into a window."""

        from pprint import pformat

        self.show(
            repr(self.cursor)
            + '\n'
            + ', '.join(
                ('' if getattr(self.cursor, field) else 'not ') + field
                for field in ('personal', 'outgoing', 'noise', 'omega', 'error'))
            + '\n'
            + 'sender: ' + repr(str(self.cursor.sender)) + '\n'
            + 'body: ' + '\n '.join(pformat(self.cursor.body).split('\n'))
             + '\n'
            + pformat(getattr(self.cursor, 'data', None)))

    def goto_time(self, when):
        self.log.info('going to %s', datetime.datetime.fromtimestamp(when).isoformat(' '))
        self.cursor_set_walk_mark(when, True, when)

    @keymap.bind('Meta-g')
    def goto(self):
        """Go to a specified time, backfilling as appropriate.  Date-time
        parsing is unfortunately adhoc and idiosyncractic."""

        import parsedatetime
        p = parsedatetime.Calendar()

        s = yield from self.read_string('When: ')
        x, y = p.parse(s)
        self.log.debug('parsed date result %d: %s', y, repr(x))
        if y:
            t = time.mktime(x)
            self.goto_time(t)

    @keymap.bind('Control-X [')
    def prev_day(self, count: interactive.integer_argument=1):
        """Jump to the previous midnight, backfilling as appropriate.

        Integer argument specifies multiple days."""

        if count < 0:
            return self.next_day(-count)

        if count > 0:
            if self.cursor.omega:
                date = datetime.date.today()
            else:
                when = datetime.datetime.fromtimestamp(self.cursor.time)
                date = when.date()
                if when.time() == datetime.time(0): #midnight
                    #XXX should check if we're at the first message today
                    date -= datetime.timedelta(days=1)
            midnight = datetime.datetime.combine(date, datetime.time())
            delta = datetime.timedelta(days=count - 1)
            when = midnight - delta
            self.goto_time(when.timestamp())

    @keymap.bind('Control-X ]')
    def next_day(self, count: interactive.integer_argument=1):
        """Jump to the next midnight.

        Integer argument specifies multiple days."""

        if count < 0:
            return self.prev_day(-count)

        if count > 0:
            if self.cursor.omega:
                return

            date = datetime.date.fromtimestamp(self.cursor.time)
            midnight = datetime.datetime.combine(date, datetime.time())
            delta = datetime.timedelta(days=count)
            when = midnight + delta
            self.goto_time(when.timestamp())

    @keymap.bind('Control-[space]')
    def set_mark(self, where=None, prefix: interactive.argument=None):
        """Without a ^U before [#]_, set the mark (append it to the mark ring).

        With a ^U, stick the current point at the current beginning of the
        mark ring, and set the point to the current end of the mark ring.

        .. [#] repeating the command after a ^U will continue to jump around
            rather than setting the mark.
        """
        #XXX this documentation is weak and this could share a lot of code
        #with the same command over in the editor
        if prefix is not None or \
          (self.last_command == 'set_mark' and self.set_mark_state == 1):
            self.mark_ring.insert(
                0, (where if where is not None else self.cursor))
            where = self.the_mark
            self.the_mark = self.mark_ring.pop()
            self.cursor_set_walk(where, True)
            self.set_mark_state = 1
        else:
            self.mark_ring.append(self.the_mark)
            self.the_mark = where if where is not None else self.cursor
            self.set_mark_state = 0

    @keymap.bind('Control-X Control-X')
    def exchange_point_and_mark(self):
        """Move the point to where the mark is, and set the mark where the point
        used to be."""

        if self.the_mark is not None:
            where, self.the_mark = self.the_mark, self.cursor
            self.cursor_set_walk(where, True)

    @keymap.bind('[')
    def previous_stark(self):
        """Move to the previous Stark point."""
        if not self.starks:
            return
        i = bisect.bisect_left(self.starks, self.cursor.time) - 1
        if i >= 0:
            self.goto_time(self.starks[i].time)

    @keymap.bind(']')
    def next_stark(self):
        """Move to the next Stark point, or if there isn't one, the omega
        message."""
        i = bisect.bisect_left(self.starks, self.cursor.time)
        if not self.starks or self.starks[i] == self.cursor:
            i += 1
        if i >= len(self.starks):
            self.last()
        elif i >= 0:
            self.goto_time(self.starks[i].time)

    @keymap.bind('.')
    def set_stark(self):
        """Set a Stark point."""
        if self.cursor not in self.starks:
            #XXX I have doubts about the complexity of the following but I'm
            #betting that the array will never get particularly large
            #and it's after my bedtime.
            self.starks.append(self.cursor)
            self.starks.sort()
