# -*- encoding: utf-8 -*-


from . import messages


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

    def view(self):
        return ViewStub([])

class ViewStub(object):
    def __init__(self, content):
        self.content = content

    @property
    def point(self):
        return self.content

    def forward(self):
        return iter([])

    def reverse(self):
        return iter([])


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
