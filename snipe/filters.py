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

import logging
import operator
import re

import ply.lex
import ply.yacc

from . import util


class SnipeFilterError(util.SnipeException):
    pass


class Filter(object):
    name = None

    def __init__(self):
        self.log = logging.getLogger(
            'filter.%s.%x' % (self.__class__.__name__, id(self),))

    def __call__(self, m):
        raise NotImplemented

    def __str__(self):
        return self.gname()

    def __repr__(self):
        return self.__class__.__name__+'()'

    def parenthesize(self, p):
        if isinstance(p, Conjunction):
            return '(' + str(p) + ')'
        else:
            return str(p)

    def gname(self):
        return self.name or self.__class__.__name__.lower()


class Truth(Filter):
    def __eq__(self, other):
        return self.__class__ is other.__class__


class Yes(Truth):
    def __call__(self, m):
        return True


class No(Truth):
    def __call__(self, m):
        return False


class Not(Filter):
    name = 'not'

    def __init__(self, p):
        self.p = p

    def __call__(self, m):
        return not self.f(m)

    def __str__(self):
        return self.gname() + ' ' + self.parenthesize(self.p)

    def __repr__(self):
        return self.__class__.__name__ + '(' + repr(self.p) + ')'

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.p == other.p


class Conjunction(Filter):
    def __init__(self, *args):
        super().__init__()
        self.operands = args

    def __str__(self):
        return (' ' + self.gname() + ' ').join(
            self.parenthesize(p) for p in self.operands
            )

    def __repr__(self):
        return self.__class__.__name__ + '(' + ', '.join(
            repr(p) for p in self.operands
            ) + ')'

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__
            and self.operands == other.operands
            )


class And(Conjunction):
    name = 'and'

    def __call__(self, m):
        for p in self.operands:
            if not p(m):
                return False
        return True


class Or(Conjunction):
    name = 'or'

    def __call__(self, m):
        for p in self.operands:
            if p(m):
                return True
        return False


class Xor(Conjunction):
    name = 'xor'

    def __call__(self, m):
        return len([True for p in self.operands if p(m)]) == 1


class Python(Filter):
    def __init__(self, string):
        super(Python, self).__init__()
        self.string = string

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            repr(self.string),
            )

    def __call__(self, m):
        try:
            return eval(self.string, {}, {'m': m})
        except:
            self.log.exception(
                'executing python filter %s on %s',
                repr(self.string),
                repr(m))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.string == other.string


class FilterLookup(Filter):
    def __init__(self, name):
        super(FilterLookup, self).__init__()
        self.name = name

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            repr(self.name),
            )

    def __call__(self, m):
        return findfilter(self.name)(m) #XXX

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.name == other.name


class Comparison(Filter):
    def __init__(self, op, field, value):
        super(Comparison, self).__init__()
        self.op, self.field, self.value = (
            op, field, value)
        self.canon = True if self.op != '==' else False

    def __repr__(self):
        return '%s(%s, %s, %s)' % (
            self.__class__.__name__,
            repr(self.op),
            repr(self.field),
            repr(self.value),
            )

    def __call__(self, m):
        v = self.value
        if isinstance(v, Identifier): #XXX grumpiness about abstraction leakage
            v = m.field(str(v), self.canon)
        return self.do(self.op, m.field(self.field, self.canon), v)

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__
            and self.op == other.op
            and self.field == other.field
            and self.value == other.value
            )

    def __str__(self):
        if isinstance(self.value, Identifier):
            right = str(self.value)
        elif isinstance(self.value, str):
            right = '"%s"' % (
                self.value.replace('\\', '\\\\').replace('"', '\\"'),
                )
        else:
            right = repr(self.value)
        return '%s %s %s' % (
            self.field,
            self.op,
            right,
            )


class Compare(Comparison):
    @staticmethod
    def do(op, left, right):
        f = {
            '=': operator.eq,
            '==': operator.eq,
            '!=': operator.ne,
            '<': operator.lt,
            '<=': operator.le,
            '>': operator.gt,
            '>=': operator.ge,
            }[op]
        try:
            return f(left, right)
        except:
            #XXX log a snarky comment where the user will see?
            self.log.exception('in filter')
            return False

    @staticmethod
    def static(op, left, right):
        result = Compare.do(op, left, right)
        return Yes() if result else No()


class RECompare(Comparison):
    def __init__(self, *args):
        super(RECompare, self).__init__(*args)
        try:
            self.re = re.compile(self.value)
        except:
            self.log.exception('compiling regexp: %s', self.value)
            self.re = None

    @staticmethod
    def do(op, regexp, value):
        if regexp is None:
            return False
        result = bool(regexp.match(value))
        if op[0] == '!':
            result = not result
        return result

    @staticmethod
    def static(op, regexp, value):
        try:
            regexp = re.compile(regexp)
        except:
            self.log.exception('compiling regexp: %s', self.value)
            return No()

        result = RECompare.do(op, regexp, value)
        return Yes() if result else No()

    def __call__(self, m):
        return self.do(self.op, self.re, str(m.field(self.field, self.canon)))

    def __str__(self):
        return '%s %s /%s/' % (
            self.field,
            self.op,
            self.value.replace('/', r'\/'),
            )


class Lexeme:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.__class__.__name__ + '(' + repr(self.value) + ')'

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.value == other.value


class Identifier(Lexeme):
    pass


class Regexp(Lexeme):
    pass


class PlyShim:
    def __init__(self):
        self.reset_errors()

    def reset_errors(self):
        self._errors = []

    errors = property(lambda self: self._errors)


class Lexer(PlyShim):
    def __init__(self):
        super().__init__()
        self.lexer = ply.lex.lex(module=self)

    tokens = (
        'EQ',
        'EQEQ',
        'NE',
        'LT',
        'LTE',
        'GT',
        'GTE',
        'NUMBER',
        'STRING',
        'REGEXP',
        'ID',
        'PYTHON',
        'FILTER',
        'YES',
        'NO',
        'LPAREN',
        'RPAREN',
        'AND',
        'OR',
        'XOR',
        'NOT',
        )

    def t_NUMBER(self, t):
        r'\d+'
        t.value = int(t.value)
        return t

    def t_STRING(self, t):
        r'"(?P<content>([^\\\n"]|(\\.))*)"'
        #r'(?P<quote>[' "'" r'"])(?P<content>.*)(?P=quote)'
        t.value = self.lexer.lexmatch.group('content')
        t.value = '\\'.join(x.replace(r'\"', '"') for x in t.value.split('\\\\'))
        return t

    def t_REGEXP(self, t):
        r'/(?P<content>(\\/|[^/])*)/'
        t.value = self.lexer.lexmatch.group('content').replace(r'\/','/')
        return t

    def t_ID(self, t):
        r'[a-zA-Z_][a-zA-Z_0-9]*'
        word = {
            'and': 'AND',
            'or': 'OR',
            'xor': 'XOR',
            'not': 'NOT',
            'filter': 'FILTER',
            'yes': 'YES',
            'no': 'NO',
            }

        t.type = word.get(t.value, 'ID')
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
        self._errors.append(t)
        t.lexer.skip(1)

    def test(self, data):
        self.lexer.input(data)
        while True:
            tok = self.lexer.token()
            if not tok:
                break
            yield tok
        if self._errors:
            raise SnipeFilterError(self._errors, [])


class Parser(PlyShim):
    def __init__(self, debug=False):
        super().__init__()
        self.parser = ply.yacc.yacc(module=self, write_tables=False, debug=debug)

    tokens = Lexer.tokens

    precedence = (
        ('left', 'XOR', 'OR', 'AND'),
        ('right', 'NOT'), #?
    )

    def p_fil_exp(self, p):
        'fil : exp'
        p[0] = p[1]

    def p_fil_empty(self, p):
        'fil :'
        p[0] = None

    def p_exp_yes(self, p):
        'exp : YES'
        p[0] = Yes()

    def p_exp_no(self, p):
        'exp : NO'
        p[0] = No()

    def p_exp_python(self, p):
        'exp : PYTHON'
        p[0] = Python(p[1])

    def p_exp_filter(self, p):
        'exp : FILTER ID'
        p[0] = FilterLookup(p[1])

    def p_exp_parens(self, p):
        'exp : LPAREN exp RPAREN'
        p[0] = p[2]

    def p_exp_not(self, p):
        'exp : NOT exp'
        p[0] = Not(p[2])

    def p_exp_and(self, p):
        'exp : exp AND exp'
        p[0] = And(p[1], p[3])

    def p_exp_or(self, p):
        'exp : exp OR exp'
        p[0] = Or(p[1], p[3])

    def p_exp_xor(self, p):
        'exp : exp XOR exp'
        p[0] = Xor(p[1], p[3])

    def p_val(self, p):
        '''
        val : NUMBER
            | STRING
            | id
        '''
        p[0] = p[1]

    def p_eqop(self, p):
        '''
        eop : EQ
            | EQEQ
            | NE
        '''
        p[0] = p[1]

    def p_relop(self, p):
        '''
        rop : LT
            | LTE
            | GT
            | GTE
        '''
        p[0] = p[1]

    def p_op(self, p):
        '''
        op  : eop
            | rop
        '''
        p[0] = p[1]

    def p_id(self, p):
        '''
        id  : ID
        '''
        p[0] = Identifier(p[1])

    def p_re(self, p):
        '''
        re  : REGEXP
        '''
        p[0] = Regexp(p[1])

    def p_exp_comparison(self, p):
        '''
        exp : val op val
        '''
        op = p[2]
        if isinstance(p[1], Identifier):
            left, right = str(p[1]), p[3]
        elif isinstance(p[3], Identifier):
            left, right = str(p[3]), p[1]
            op = {
                '=': '=', '==': '==', '!=': '!=',           #symmetric
                '<': '>=', '<=': '>', '>': '<=', '>=': '<', #not
                }[op]
        else:
            p[0] = Compare.static(op, p[1], p[3])
            return
        p[0] = Compare(op, left, right)

    def p_exp_recompare(self, p):
        '''
        exp : val eop re
            | re eop val
        '''
        if isinstance(p[1], Regexp):
            regexp, val = p[1], p[3]
        else:
            regexp, val = p[3], p[1]
        if not isinstance(val, Identifier):
            p[0] = RECompare.static(p[2], str(regexp), str(val))
        else:
            p[0] = RECompare(p[2], str(val), str(regexp))

    def p_error(self, p):
        self._errors.append(p)

parser = Parser()
lexer = Lexer()

def makefilter(s):
    lexer.reset_errors()
    parser.reset_errors()
    result = parser.parser.parse(s, lexer=lexer.lexer)
    if lexer.errors or parser.errors:
        raise SnipeFilterError(lexer.errors, parser.errors)
    return result
