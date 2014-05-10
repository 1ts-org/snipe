# -*- encoding: utf-8 -*-
# Copyright © 2014 Karl Ramm
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

import ply.lex


class Filter(object):
    name = None

    def __call__(self, m):
        raise NotImplemented

    def __str__(self):
        return self.gname()

    def __repr__(self):
        return self.__class__.__name__+'()'

    def parenthesize(self, p):
        if isinstance(p, conjunction):
            return '(' + str(p) + ')'
        else:
            return str(p)

    def gname(self):
        return self.name or self.__class__.__name__


class yes(Filter):
    def __call__(self, m):
        return True


class no(Filter):
    def __call__(self, m):
        return False

class not_(Filter):
    name = 'not'

    def __init__(self, p):
        self.p = p

    def __call__(self, m):
        return not self.f(m)

    def __str__(self):
        return self.gname() + ' ' + self.parenthesize(self.p)

    def __repr__(self):
        return self.__class.__name__ + '(' + repr(self.p) + ')'


class conjunction(Filter):
    def __init__(self, *args):
        self.operands = args

    def __str__(self):
        return (' ' + self.gname() + ' ').join(
            self.parenthesize(p) for p in self.operands
            )

    def __repr__(self):
        return ' ' + self.gname() + '(' + ', '.join(
            repr(p) for p in self.operands
            ) + ')'

class and_(conjunction):
    name = 'and'

    def __call__(self, m):
        for p in self.operands:
            if not p(m):
                return False
        return True

class or_(conjunction):
    name = 'or'

    def __call__(self, m):
        for p in self.operands:
            if p(m):
                return True
        return False

class xor_(conjunction):
    name = 'xor'

    def __call__(self, m):
        return len([True for p in self.operands if p(m)]) == 1

class lexer(object):
    tokens = (
        'NUMBER',
        'STRING',
        'REGEXP',
        'AND',
        'OR',
        'XOR',
        'NOT',
        'FIELD',
        'EQ',
        'EQEQ',
        'NE',
        'LT',
        'LTE',
        'GT',
        'GTE',
        'LPAREN',
        'RPAREN',
        'PYTHON',
        )

    def t_NUMBER(self, t):
        r'\d+'
        t.value = int(t.value)
        return t

    def t_STRING(self, t):
        r'"(?P<content>([^\\\n"]|(\\.))*)"'
        #r'(?P<quote>[' "'" r'"])(?P<content>.*)(?P=quote)'
        t.value = self.lexer.lexmatch.group('content')
        return t

    def t_REGEXP(self, t):
        r'/(?P<content>(\\/|[^/])*)/'
        t.value = self.lexer.lexmatch.group('content').replace(r'\/','/')
        return t

    def t_FIELD(self, t):
        r'[a-zA-Z_][a-zA-Z_0-9]*'
        word = {
            'and': 'AND',
            'or': 'OR',
            'xor': 'XOR',
            'not': 'NOT',
            }

        t.type = word.get(t.value, 'FIELD')
        return t

    t_EQ = '='
    t_EQEQ = '=='
    t_NE = '!='
    t_LT = '<'
    t_LTE = '<='
    t_GT = '>'
    t_GTE = '>='
    t_LPAREN = r'\('
    t_RPAREN = r'\)'

    def t_PYTHON(self, t):
        r'\$(?P<quote>[' "'" r'"])(?P<content>.*)(?P=quote)'
        t.value = self.lexer.lexmatch.group('content')
        return t

    t_ignore = '\n\t '

    def t_error(self, t):
        print '?', t.value[0]
        t.lexer.skip(1)

    def build(self):
        self.lexer = ply.lex.lex(module=self)

    def test(self, data):
        self.lexer.input(data)
        while True:
            tok = self.lexer.token()
            if not tok:
                break
            print tok

