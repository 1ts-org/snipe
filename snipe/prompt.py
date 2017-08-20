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
snipe.prompt
------------

Editor subclasses for interacting withe user.
'''


import asyncio

from . import chunks
from . import editor
from . import keymap
from . import interactive


class LongPrompt(editor.Editor):
    histories = {}

    cheatsheet = [
        '*M-p*revious history',
        '*M-n*ext history',
        '*^G* aborts',
        '*^C^C* finishes',
        ]

    def __init__(
            self,
            *args,
            prompt='> ',
            callback=lambda x: None,
            history=None,
            **kw):
        self.divider = 0
        super().__init__(*args, **kw)
        self.prompt = prompt
        self.callback = callback
        proto = kw.get('prototype', None)
        if proto is not None:
            self.prompt = proto.prompt
            self.callback = proto.callback
            self.divider = proto.divider
        else:
            self.cursor.point = 0
            self.insert(prompt)
            self.divider = int(self.cursor)
        self.end_of_buffer()
        self.histptr = 0
        self.history = self.histories.setdefault(history, [])
        self.keymap['Control-G'] = self.delete_window
        self.inverse_input = False

    def destroy(self):
        self.history.append(self.buf[self.divider:])
        self.buf.unregister()
        super().destroy()

    @keymap.bind('Meta-p', 'Meta-Control-p')
    def previous_history(self):
        """Move back by one in the current history list."""

        self.move_history(-1)

    @keymap.bind('Meta-n', 'Meta-Control-n')
    def next_history(self):
        """Move forward by one in the current history list."""

        self.move_history(1)

    def move_history(self, offset):
        new_ptr = self.histptr - offset
        if new_ptr < 0 or new_ptr > len(self.history):
            return

        old = self.buf[self.divider:]
        if self.histptr == 0:
            self.stash = old
        else:
            self.history[-self.histptr] = old

        if new_ptr == 0:
            new = self.stash
        else:
            new = self.history[-new_ptr]

        self.cursor.point = self.divider
        self.delete(len(old))
        self.insert(new)
        self.histptr = new_ptr
        self.inverse_input = False

    def writable(self):
        return super().writable() and self.cursor >= self.divider

    def movable(self, point, interactive):
        if interactive and point < self.divider:
            return self.divider
        return super().movable(point, interactive)

    def maybe_inverse(self, tags):
        if self.inverse_input and 'reverse' not in tags:
            return tags + ('reverse',)
        else:
            return tags

    def view(self, *args, **kw):
        for mark, chunk in super().view(*args, **kw):
            if mark.point > self.divider:
                yield mark, chunk
            else:
                newchunk = chunks.Chunk()
                off = mark.point
                for tags, string in chunk:
                    if off < self.divider:
                        if off + len(string) > self.divider:
                            newchunk.append(
                                (set(tags) | {'bold'},
                                    string[:self.divider - off]))
                            newchunk.append(
                                (self.maybe_inverse(tags),
                                    string[self.divider - off:]))
                        else:  # string is all before the divider
                            newchunk.append(
                                (set(tags) | {'bold'}, string))
                    else:
                        newchunk.append((self.maybe_inverse(tags), string))
                    off += len(string)
                yield mark, newchunk

    def input(self):
        return self.buf[self.divider:]

    @keymap.bind('Control-C Control-C')
    def runcallback(self):
        """Complete whatever action this prompt is for."""

        self.callback(self.input())


class KeySeqPrompt(LongPrompt):
    cheatsheet = ['Type a key sequence.']

    def __init__(self, *args, keymap=None, **kw):
        super().__init__(*args, **kw)
        self.keymap = keymap
        self.active_keymap = keymap
        self.intermediate_action = self.echo_keystroke
        self.keymap_action = self.runcallback
        self.keyerror_action = lambda k: self.runcallback()
        self.keystrokes = []
        self.activated_keymap = None

    def keyecho(self, keystroke):
        pass

    def echo_keystroke(self, keystroke):
        self.keystrokes.append(keystroke)
        self.insert(self.keymap.unkey(keystroke) + ' ')
        self.fe.redisplay(self.redisplay_hint())

    def runcallback(self, func=None, *args, **kw):
        self.callback((self.keystrokes, func))


class ReplyMode:
    def __init__(self, msg):
        self.msg = msg

    cheatsheet = [
        '*^C^Y* yank quote',
        ]

    @keymap.bind('Control-C Control-Y')
    def yank_original(self, window: interactive.window):
        """Yank the contents of the message being replied to, with a > line
        prefix."""

        m = window.buf.mark(window.cursor)
        prefix = '> '
        with window.save_excursion(m):
            window.insert(
                prefix + ('\n' + prefix).join(self.msg.body.splitlines()))
        window.set_mark(m)


class Leaper(LongPrompt):
    def __init__(self, *args, completer=interactive.UnCompleter(), **kw):
        super().__init__(*args, **kw)
        self.completer = completer
        if self.completer.live:
            self.set_cheatsheet(self.cheatsheet + [
                '*^S* circulate forward',
                '*^R* circulate back',
                '*[tab]* completes',
                ])
        self.log.debug('candidates: %s', self.completer.candidates)
        self.state_complete()

    def state_complete(self):
        self.state = 'complete'
        self.saved_fill_column = self.fill_column
        self.fill_column = 0

    def state_normal(self):
        self.fill_column = self.saved_fill_column
        self.state = 'normal'

    def before_command(self):
        self.log.debug('before_command: %s %s', self.state, self.this_command)
        if self.state == 'preload':
            if self.this_command != 'complete_and_finish':
                if ('insert' in self.this_command
                        or self.this_command in (
                            'roll_forward', 'roll_backward')):
                    self.clear_input()

    def clear_input(self):
        self.cursor.point = self.divider
        self.delete_forward(self.complete_end() - self.divider)

    @keymap.bind('Control-H', 'Control-?', '[backspace]')
    def delete_backward(self, count: interactive.integer_argument=1):
        """Delete characters before the point, one by default, n if specified.
        If there is unmodified default input, delete all of it."""

        self.log.debug('custom delete_backward: %s', self.state)
        if self.state == 'preload':
            self.clear_input()
        else:
            super().delete_backward(count)

    def view(self, *args, **kw):
        self.log.debug('view: %s', self.state)
        end = self.complete_end()
        for mark, chunk in super().view(*args, **kw):
            if mark.point > end or self.state == 'normal':
                yield mark, chunk
            else:
                self.log.debug('yy: %s', chunk)
                chunklen = sum(len(string) for (tags, string) in chunk)
                if mark.point + chunklen < end:
                    yield mark, chunk
                else:
                    if chunk and chunk[-1][1][-1:] == '\n':
                        chunk[-1] = (chunk[-1][0], chunk[-1][1][:-1])
                    yield mark, chunk + self.match_chunks()

    @keymap.bind('Control-S')
    def roll_forward(self):
        """Circulate the current matches fowards."""
        m = self.matches()
        if len(m) < 2:
            return
        p = m[1][0]
        self.completer.roll(p)

    @keymap.bind('Control-R')
    def roll_backward(self):
        """Circulate the current matches backwards."""
        m = self.matches()
        if len(m) < 2:
            return
        p = m[-1][0]
        self.completer.roll(p)

    def match_chunks(self):
        if not self.completer.live:
            return chunks.Chunk([((), '')])
        m = [x[1] for x in self.matches()]
        self.log.debug('match_chunks: matches: %s', m)
        if not m:
            return chunks.Chunk([((), ' {}\n')])
        return chunks.Chunk([
            ((), ' {'),
            (('bold',), m[0]),
            ((), (
                ('|' if len(m) > 1 else '') +
                '|'.join(m[1:]) +
                '}\n'))])

    def complete_end(self):
        return len(self.buf)

    def completed_text(self):
        return self.buf[self.divider:self.complete_end()]

    def matches(self):
        if self.state == 'preload':
            return self.completer.matches()
        return self.completer.matches(self.completed_text())

    @keymap.bind('[tab]')
    def complete_command(self, key: interactive.keystroke):
        """Complete according to the current set completer.  Or self_insert if
        we're not completing right now."""

        result = None
        if (self.completer.live
                and (self.divider < self.cursor.point <= self.complete_end())):
            result = self.completer.expand(self.completed_text())

        if result is None:
            return self.self_insert(key=key)

        self.cursor.point = self.divider
        self.replace(self.complete_end() - self.divider, result)
        self.move(len(result))


class ShortPrompt(Leaper):
    cheatsheet = [
        '*M-p*revious history',
        '*M-n*ext history',
        '*^G* aborts',
        '*Enter* finishes',
        ]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        if kw.get('content'):
            if self.completer.live:
                self.completer.roll_to(kw['content'])
            self.state = 'preload'
            self.inverse_input = True
        self.keymap['[carriage return]'] = self.complete_and_finish
        self.keymap['Control-J'] = self.runcallback

    def after_command(self):
        self.state_complete()
        self.inverse_input = False

    def complete_and_finish(self):
        """Append the tail of the first candidate and complete whatever action
        this prompt is for"""
        self.log.debug('complete_and_finish()')
        matches = self.matches()
        if matches:
            self.callback(matches[0][2])
        else:
            self.runcallback()


class Composer(Leaper):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.set_fill_column_for = None
        histprefix = kw.get('history', '')
        self.histx = [
            self.histories.setdefault(histprefix + '-dest', []),
            self.histories.setdefault(histprefix + '-body', []),
            ]
        self.histptrs = [0, 0]
        self.stashes = ['', '']

        self.state = 'complete'
        if kw.get('content'):
            self.state_normal()
        self.log.debug('candidates %s', self.completer.candidates)
        self.keymap['[carriage return]'] = self.insert_newline

        # wrong, bad, but expedient
        self.completer.candidates.sort(key=lambda x: (len(x), x))

    def complete_end(self):
        with self.save_excursion():
            self.cursor.point = self.divider
            self.end_of_line()
            return int(self.cursor)

    def state_complete(self):
        super().state_complete()
        self.set_fill_column_for = None

    def state_normal(self):
        super().state_normal()
        dest = self.completed_text()
        params = [s.strip() for s in dest.split(';', 1)]
        backend = None
        backends = [
            b
            for b in self.context.backends
            if b.name.startswith(params[0])]
        if len(backends) == 1:
            backend = backends[0].name

        if backend and self.set_fill_column_for != backend:
            if backend == 'irccloud':
                self.fill_column = 0
            else:
                self.fill_column = self.default_fill_column
            self.set_fill_column_for = backend
            self.saved_fill_column = self.fill_column

    def after_command(self):
        self.log.debug('after command: %s', self.state)
        if self.state != 'normal':
            if self.cursor.point > self.complete_end():
                self.state_normal()
        else:  # normal
            if self.cursor.point <= self.complete_end():
                self.state_complete()

    @keymap.bind('[carriage return]', 'Control-J')
    def insert_newline(self, count: interactive.positive_integer_argument=1):
        """Insert a newline, or n newlines, ending completion."""
        if self.state == 'complete':
            self.complete_command('')

        self.state_normal()

        super().insert_newline(count)

    def setup_history(self):
        eodest = self.buf.mark(self.divider)
        with self.save_excursion(eodest):
            self.end_of_line()

        ind = int(self.cursor > eodest)  # 0 or 1
        history = self.histx[ind]
        divisions = [
            (self.divider, int(eodest)),
            (int(eodest) + 1, len(self.buf)),
            ]
        return ind, history, divisions

    def move_history(self, offset):
        if self.divider == len(self.buf):
            with self.save_excursion():
                self.cursor.point = self.divider
                self.insert('\n')

        ind, history, divisions = self.setup_history()
        self.log.debug(
            'move_history %d, ind=%d divisions=%s\nhistory=%s\nstashes=%s',
            offset, ind, divisions, history, self.stashes)
        start, end = divisions[ind]

        new_ptr = self.histptrs[ind] - offset
        self.log.debug('move_history %d, new_ptr=%d', offset, new_ptr)
        if new_ptr < 0 or new_ptr > len(history):
            self.log.debug(
                'move_history %d, new_ptr = %d, punting', offset, new_ptr)
            return

        old = self.buf[start:end]
        self.log.debug(
            'move_history %d, self.buf[%d:%d] = %s',
            offset, start, end, repr(old))
        if self.histptrs[ind] == 0:
            self.stashes[ind] = old
        else:
            history[-self.histptrs[ind]] = old

        if new_ptr == 0:
            new = self.stashes[ind]
        else:
            new = history[-new_ptr]

        self.cursor.point = start
        self.cursor += self.replace(end - start, new)
        self.histptrs[ind] = new_ptr

    @keymap.bind('Meta-Control-p')
    def previous_history_full(self):
        """Move back by one in the current whole-message history list."""
        super().move_history(-1)
        self.histptrs = [self.histptr, self.histptr]

    @keymap.bind('Meta-Control-n')
    def next_history_full(self):
        """Move forward by one in the current whole-message history list."""
        super().move_history(1)
        self.histptrs = [self.histptr, self.histptr]

    def destroy(self):
        ind, history, divisions = self.setup_history()
        for (history, (start, end)) in zip(self.histx, divisions):
            history.append(self.buf[start:end])
        super().destroy()

    @keymap.bind('Control-S')
    def roll_or_search_forward(self, word=None):
        if self.cursor.point <= self.complete_end():
            super().roll_forward()
        else:
            yield from self.search_forward(word)

    @keymap.bind('Control-R')
    def roll_or_search_backward(self, word=None):
        if self.cursor.point <= self.complete_end():
            super().roll_backward()
        else:
            yield from self.search_backward(word)


class Search(LongPrompt):
    cheatsheet = [
        'type your search query',
        '*Enter* or any normal command finishes',
        '*C-s*earch again forward',
        'search again *C-r*eversed',
        ]

    def __init__(
            self,
            *args,
            forward=True,
            target=None,
            suffix=': ',
            start=None,
            **kw):
        self.target = None
        super().__init__(*args, **kw)
        self.target = target
        self.forward = forward
        self.suffix = ': '
        self.start = start

        self.fail = False

        self.setprompt()

        self.keymap.clear()

        self.keymap['Control-G'] = self.abort
        self.keymap['Control-S'] = self.search_forward
        self.keymap['Control-R'] = self.search_backward
        self.keymap['Control-J'] = self.runcallback
        self.keymap['Control-M'] = self.runcallback
        self.keymap['Control-H'] = self.delete_backward
        self.keymap['Control-?'] = self.delete_backward
        self.keymap['[backspace]'] = self.delete_backward
        self.keymap['Control-Y'] = self.yank
        # eventually:
        # something about case insensitivity
        # C-w   pull in next word/character
        # C-M-w pull in next char
        # M-s C-e pull in to end o fline
        # with infrasrtucture for ungetching multikey sequences
        # self.keymap['Meta-y'] = self.yank_pop
        # self.keymap['Meta-p'] = self.previous_history
        # self.keymap['Meta-n'] = self.next_history
        # when implented elsewhere
        # Control-Q   # with control character view
        # Control-X 8
        # C-j for insert-newline with linebreakless view

        self.keyerror_action = self.callout

    def callout(self, k):
        self.runcallback()
        self.fe.ungetch(k)

    def runcallback(self):
        if self.start != self.target.cursor:
            self.target.set_mark(self.start)
            self.context.message('mark saved where search started')
        super().runcallback()

    def setprompt(self):
        direction = 'forward' if self.forward else 'backward'
        failing = '' if not self.fail else 'failing '
        with self.save_excursion():
            save, self.divider = self.divider, 0
            self.cursor.point = 0
            self.divider = super().replace(
                save,
                failing + self.prompt + direction + self.suffix,
                False
                )

    def replace(self, count, string, collapsible=False):
        self.log.debug(
            'replace %d/[%d], cursor=%d',
            count, len(string), self.cursor.point)
        result = super().replace(count, string, collapsible)
        if self.target is not None:
            term = self.input()
            self.target.search_term = term
            if not self.target.match(term, self.forward):
                self.log.debug('no match, finding')
                self.do_find()
            else:  # match
                self.fail = False
            self.setprompt()
            self.target.redisplay()
            self.redisplay()
        return result

    @asyncio.coroutine
    def search(self, string=None, forward=True):
        assert string is None
        if self.forward != forward:
            self.forward = forward
            self.setprompt()

        if not self.input():
            self.previous_history()
            if not self.input():
                self.whine()
                return

        self.do_find()
        self.setprompt()

    def do_find(self, wrap=False):
        self.fe.set_active_output(self.target)
        if self.target.find(self.input(), self.forward):
            self.fail = False
        else:
            if not self.fail:
                self.fail = True
                self.whine()
            elif not wrap:
                mark = self.target.make_mark(self.target.cursor)
                if self.forward:
                    self.target.beginning()
                else:
                    self.target.end()
                self.do_find(True)
                if self.fail:
                    self.target.go_mark(mark)
        self.target.redisplay()

    def abort(self):
        self.target.go_mark(self.start)
        self.delete_window()

    def delete_window(self):
        """Delelete current window."""
        self.fe.set_active_input()
        super().delete_window()

    def destroy(self):
        super().destroy()
        self.target.search_term = None
