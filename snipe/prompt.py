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
            complete=None,
            callback=lambda x: None,
            history=None,
            **kw):
        self.divider = 0
        super().__init__(*args, **kw)
        self.prompt = prompt
        self.callback = callback
        self.complete = complete
        proto = kw.get('prototype', None)
        if proto is not None:
            self.prompt = proto.prompt
            self.callback = proto.callback
            self.complete = proto.complete
            self.divider = proto.divider
        else:
            self.cursor.point = 0
            self.insert(prompt)
            self.divider = int(self.cursor)
        self.complete_state = None
        self.end_of_buffer()
        self.histptr = 0
        self.history = self.histories.setdefault(history, [])
        self.keymap['Control-G'] = self.delete_window
        if complete is not None:
            self.cheatsheet = list(self.cheatsheet)
            self.cheatsheet.append('*[tab]* completes')

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

    def writable(self):
        return super().writable() and self.cursor >= self.divider

    def movable(self, point, interactive):
        if interactive and point < self.divider:
            return self.divider
        return super().movable(point, interactive)

    def view(self, *args, **kw):
        for mark, chunk in super().view(*args, **kw):
            if mark.point > self.divider:
                yield mark, chunk
            else:
                newchunk = []
                off = mark.point
                for tags, string in chunk:
                    if off < self.divider:
                        if off + len(string) > self.divider:
                            newchunk.append(
                                (tags + ('bold',), string[:self.divider - off]))
                            newchunk.append(
                                (tags, string[self.divider - off:]))
                        else: # string is all before the divider
                            newchunk.append(
                                ((tags + ('bold',)), string))
                    else:
                        newchunk.append((tags, string))
                    off += len(string)
                yield mark, newchunk

    def input(self):
        return self.buf[self.divider:]

    @keymap.bind('Control-C Control-C')
    def runcallback(self):
        """Complete whatever action this prompt is for."""

        self.callback(self.input())

    @keymap.bind('[tab]')
    def complete(self, key: interactive.keystroke):
        """If there is a completer set for the buffer, complete at the point."""

        if self.complete is None:
            return self.self_insert(key=key)

        if self.cursor < self.divider:
            self.whine('No completing the prompt')
            return

        if self.last_command != 'complete' or self.complete_state is None:
            self.complete_state = self.complete(
                self.buf[self.divider:self.cursor], self.buf[self.cursor:])

        try:
            left, right = next(self.complete_state)
        except StopIteration:
            self.whine('No more completions')
            self.complete_state = None
            self.replace(len(self.buf) - self.cursor.point, '')
            return

        self.log.debug('complete: %s, %s', repr(left), repr(right))

        c = self.buf.mark(self.cursor)
        self.cursor.point = self.divider
        self.replace(len(self.buf) - self.divider, left + right)
        self.cursor.point += len(left)


class Composer(LongPrompt):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        histprefix = kw.get('history', '')
        self.histx = [
            self.histories.setdefault(histprefix + '-dest', []),
            self.histories.setdefault(histprefix + '-body', []),
            ]
        self.histptrs = [0, 0]
        self.stashes = [None, None]

    def setup_history(self):
        eodest = self.buf.mark(self.divider)
        with self.save_excursion(eodest):
            self.end_of_line()

        ind = int(self.cursor > eodest) # 0 or 1
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
        self.cursor.point += self.replace(end - start, new)
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


class ShortPrompt(LongPrompt):
    cheatsheet = [
        '*M-p*revious history',
        '*M-n*ext history',
        '*^G* aborts',
        '*Enter* finishes',
        ]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.keymap['[carriage return]'] = self.runcallback
        self.keymap['Control-J'] = self.runcallback


class KeySeqPrompt(LongPrompt):
    cheatsheet = ['Type a key sequence.']
    def __init__(self, *args, keymap=None, **kw):
        super().__init__(*args, **kw)
        self.keymap = keymap
        self.active_keymap = keymap
        self.intermediate_action = self.echo_keystroke
        self.keymap_action = self.runcallback
        self.keyerror_action = self.runcallback
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


class LeapPrompt(ShortPrompt):
    def __init__(self, *args, candidates=[], **kw):
        super().__init__(*args, **kw)
        self.candidates = list(candidates)
        self.keymap['[carriage return]'] = self.complete_and_finish

    def view(self, *args, **kw):
        v = list(super().view(*args, **kw))
        self.log.debug('v: %s, %d', repr(v), len(v))
        self.log.debug('before first yield')
        yield from v[:-1]
        self.log.debug('after first yield')
        mark, chunks = v[-1]
        m = [x[1] for x in self.matches()]
        if m:
            chunks = chunks + [
                ((), ' {'),
                (('bold',), m[0]),
                ((), (
                    ('|' if len(m) > 1 else '') +
                    '|'.join(m[1:]) +
                    '}'))]
        self.log.debug('now %s', repr(chunks))
        yield mark, chunks

    @keymap.bind('Control-S')
    def roll_forward(self):
        m = self.matches()
        if len(m) < 2:
            return
        p = m[1][0]
        self.candidates = self.candidates[p:] + self.candidates[:p]

    @keymap.bind('Control-R')
    def roll_backward(self):
        m = self.matches()
        if len(m) < 2:
            return
        p = m[-1][0]
        self.candidates = self.candidates[p:] + self.candidates[:p]

    def matches(self):
        sofar = self.input()
        return [
            (n, c)
            for n, c in enumerate(self.candidates)
            if not sofar or sofar in c]

    def complete_and_finish(self):
        """Append the tail of the first candidate and complete whatever action
        this prompt is for"""
        self.log.debug('complete_and_finish()')
        matches = self.matches()
        if matches:
            self.callback(matches[0][1])
        else:
            self.runcallback()
