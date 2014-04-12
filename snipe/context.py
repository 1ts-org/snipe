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
        self.keymap = Keymap({
            'Control-Q': self.quit,
            'Control-Z': self.stop,
            })

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
    def __init__(self, d={}):
        super(Keymap, self).__init__()
        self.update(d)

    def update(self, d):
        for k, v in d.items():
            if hasattr(v, 'items'):
                self[k] = Keymap(v)
            else:
                self[k] = v

    def __repr__(self):
        return (
            self.__class__.__name__
            + '('
            + super(Keymap, self).__repr__()
            + ')'
            )

    def __getitem__(self, key):
        if not hasattr(key, 'lower'):
            return super(Keymap, self).__getitem__(key)
        else:
            key, rest = self.split(key)
            v = super(Keymap, self).__getitem__(key)
            if key is None:
                return None # default?
            if rest:
                return v[rest]
            return v

    def __setitem__(self, key, value):
        if not hasattr(key, 'lower'):
            return super(Keymap, self).__setitem__(key, value)
        else:
            key, rest = self.split(key)
            if key is None:
                return
            if rest is None:
                super(Keymap, self).__setitem__(key, value)
            else:
                try:
                    v = super(Keymap, self).__getitem__(key)
                except KeyError:
                    v = None
                if v is None:
                    v = Keymap()
                    super(Keymap, self).__setitem__(key, v)
                if not hasattr(v, '__getitem__'):
                    raise KeyError(repr(key) + 'is not a keymap')
                v[rest] = value

    def __delitem__(self, key):
        if not hasattr(key, 'lower'):
            return super(Keymap, self).__delitem__(key)
        else:
            key, rest = self.split(key)
            if rest is None:
                super(Keymap, self).__delitem__(key)
            else:
                v = super(Keymap, self).__getitem__(key)
                if not hasattr(v, '__getitem__'):
                    raise KeyError(repr(key) + 'is not a keymap')
                del v[rest]

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
        'tab': '\x09',
        }

    unother_keys = {v: k for (k, v) in other_keys.items()}

    @staticmethod
    def split(keyseqspec):
        if not hasattr(keyseqspec, 'lower'):
            return keyseqspec, None

        if len(keyseqspec) == 1:
            return keyseqspec, None

        match = Keymap.keyseq_re.match(keyseqspec)

        if not match:
            raise TypeError('Invalid Key Sequence Specification')

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
            raise TypeError('unknown name: %s' % name)

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
