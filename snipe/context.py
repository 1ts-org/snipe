# -*- encoding: utf-8 -*-

import unicodedata
import contextlib
import re

from . import messages
from . import ttyfe


class Window(object):
    def __init__(self, frontend):
        self.fe = frontend
        self.keymap = {}
        self.renderer = None

        self.keymap[chr(ord('Q') - ord('@'))] = self.quit
        self.keymap[chr(ord('Z') - ord('@'))] = self.stop

    def input_char(self, k):
        if k in self.keymap:
            self.keymap[k](k)
        else:
            self.whine(k)

    def quit(self, k):
        exit()

    def whine(self, k):
        self.fe.notify()

    def stop(self, k):
        self.fe.sigtstp(None, None)

    def view(self, origin=None, direction=None):
        yield 0, [('visible',), '']


class Messager(Window):
    def __init__(self, frontend):
        super(Messager, self).__init__(frontend)
        #SPACE
        #n, p, ^n ^p ↓ ↑ j k


class Context(object):
    # per-session state and abstact control
    def __init__(self, mux, ui):
        self.mux = mux
        self.ui = ui
        self.backends = messages.AggregatorBackend(
            backends = [
                messages.StartupBackend(),
                messages.SyntheticBackend(conf={'count': 100}),
                ],)
        from . import editor
        self.ui.initial(editor.Editor(self.ui))


@contextlib.contextmanager
def ignores(*exceptions):
    try:
        yield
    except exceptions:
        pass


class Keymap(dict):
    modifier_aliases = {
        'ctl': 'control',
        'alt': 'meta',
        }
    modifiers = ['control', 'shift', 'meta', 'hyper', 'super']
    all_modifiers = modifiers + modifier_aliases.keys()

    keyseq_re = re.compile(
        '^(?P<modifiers>((' + '|'.join(all_modifiers) + ')-)*)'
        + r'((?P<char>.)|\[(?P<name>[^]]+)\])'
        + r'(|(\s+(?P<rest>\S.*)))'
        + '$',
        re.IGNORECASE
        )

    other_keys = {
        'escape': '\x1b',
        'esc': '\x1b',
        'delete': '\x7f',
        'linefeed': '\x0a',
        'line feed': '\x0a',
        'carriage return': '\x0d',
        'return': '\x0d',
        }

    unother_keys = {v: k for (k, v) in other_keys.items()}

    @staticmethod
    def split(keyseqspec):
        if not hasattr(keyseqspec, 'lower'):
            return keyseqspec, None

        match = Keymap.keyseq_re.match(keyseqspec)

        if not match:
            raise KeyError('Invalid Key Sequence Specification')

        d = match.groupdict()

        modifiers = d.get('modifiers', '-')[:-1].split('-')
        modifiers = set(
            Keymap.modifier_aliases.get(modifier, modifier).lower()
            for modifier in modifiers if modifier)

        key = d['char']
        rest = d['rest']

        name = d['name']
        if key is None:
            with ignores(KeyError):
                key = unicodedata.lookup(name.upper())

        if key is None:
            with ignores(KeyError):
                key = Keymap.other_keys.get(name.lower())

        if key is None:
            with ignores(KeyError):
                key = ttyfe.key.get(name.upper())

        if key is None:
            raise KeyError('unknown name: %s' % name)

        if 'hyper' in modifiers or 'super' in modifiers:
            return None, None #valid but untypable

        if 'control' in modifiers:
            if not hasattr(key, 'upper'):
                # XXX ignoring control+function keys for now
                return None, None #valid but untypable
            if key == '?':
                key = '\x7f'
            elif ord('@') <= ord(key.upper()) <= ord('_'):
                key = chr(ord(key.upper()) - ord('@'))
            else:
                return None, None #valid but untypable
            modifiers.remove('control')

        if 'shift' in modifiers:
            # XXX ignoring SLEFT et al for now
            if not hasattr(key, 'upper'):
                # XXX ignoring control+function keys for now
                return None, None #valid but untypable
            # XXX ignore e.g. shift-1 (!, on a US keyboard, argh) for now
            key = key.upper()
            modifiers.remove('shift')

        if 'meta' in modifiers:
            if key in Keymap.unother_keys:
                name = '[' + Keymap.unother_keys[key].upper() + ']'
            elif ord(key) < ord(' '):
                name = (
                    'Control-['
                    + unicodedata.name(unicode(chr(ord(key) + ord('@'))))
                    + ']'
                    )
            else:
                name = '[' + unicodedata.name('key') + ']'
            if rest:
                name += ' ' + rest
            rest = name
            key = '\x1b' # ESC
            modifiers.remove('meta')

        assert bool(modifiers) == False

        return key, rest
