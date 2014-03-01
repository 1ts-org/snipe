# -*- encoding: utf-8 -*-


import select


class Mux(object):
    def __init__(self):
        self.muxables = {}
    def add(self, muxable):
        self.muxables[muxable.handle] = muxable
    def remove(self, muxable):
        del self.muxables[muxable.handle]
    def wait(self, timeout=None):
        readers = [x for x in self.muxables if self.muxables[x].reader]
        writers = [x for x in self.muxables if self.muxables[x].writer]
        if not (readers or writers):
            raise ValueError('No one is listening')
        readable, writable, errant = select.select(
            readers, writers, set(readers + writers), timeout)
        for x in errant:
            self.muxables[x].error()
        for x in writable:
            self.muxables[x].writable()
        for x in readable:
            self.muxables[x].readable()
    def wait_forever(self):
        while True:
            self.wait()


class Muxable(object):
    '''Abstract parent of things you can had to the Mux'''
    reader = False
    writer = False
    handle = None

    def readable(self):
        '''Callback for when the fileno is readable'''
        raise NotImplementedError

    def writable(self):
        '''Callback for when the fileno is writable'''
        raise NotImplementedError

    def error(self):
        '''Callback for when the fileno is errant'''
        raise NotImplementedError
