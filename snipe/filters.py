#/usr/bin/python3
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
snipe.filters
-------------
'''

import logging
import operator
import re
import functools

import ply.lex
import ply.yacc

from . import util


HELP = """80
=================
Filter Language
=================

Syntax
-------
Tokens
+++++++
::

  != < <= > >= ( ) and or xor not

Operators and grouping that do what you expect.

::

  = ==

The ``=`` comparison runs context-appropriiate canonicalization
functions on its operands, the ``==`` is a literal comparison.

Integer literals, e.g. ``17``.

String literals between double quotes. e.g. ``"foo"``.

Regexp literals, between forward slashes, e.g. ``/^bar$/``.  For
the moment, always cases sensitive (but what you're comparing to
may have been put in a canoical case if you use ``=``.

Identifier are bare words that match ``/[a-zA-Z_][a-zA-Z_0-9]*/``.
These usually refer to message fields but can refer to named filtes.

The keyword ``filter`` (which introduces a reference to a named filter),
the keywords ``yes``, and ``no``, which represent unconditional success
or failure.

::

  $'python code'  $"python code"

What it says on the tin.  Called with a message object in the variable
``m``.

Grammar
++++++++

| filter     -> expression / [empty]
| expression -> ``yes`` / ``no`` / ``$"python code"`` / ``filter`` ID
|               / ``(`` expression ``)``
|               / ``not`` expression
|               / expression ``and`` expression
|               / expression ``or`` expression
|               / expression ``xor`` expression
|               / value operator value
|               / value operator ``/regexp/``
|               / ``/regexp/`` operator value
|               / identifier
| value      -> number / ``"string"`` / identifier
| operator   -> ``=`` / ``==`` / ``!=`` / ``<`` / ``<=`` / ``>`` / ``>=``

Standard Fields
----------------

Booleans
++++++++

Have a truth value themselves, and aren't for comparisons e.g. ``personal and not noise``.

``personal``
  True if the message was directed at you.

``outgoing``
  If you sent the message.

``noise``
  If the backend things the message is administrivia.

``omega``
  Is the * at bottom of the messages list.

``error``
  Is an error message.

Fields
+++++++

``sender``
  The sending entity.

``body``
  The message body.

"""


class SnipeFilterError(util.SnipeException):
    pass


class Filter(object):
    name = None

    def __init__(self):
        self.log = logging.getLogger(
            'filter.%s.%x' % (self.__class__.__name__, id(self),))

    def __call__(self, m, state=None):
        raise NotImplementedError

    def simplify(self, d):
        return self

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


class Certitude(Filter):
    def __eq__(self, other):
        return self.__class__ is other.__class__

    def __hash__(self):
        return hash(self.__class__)


class Yes(Certitude):
    def __call__(self, m, state=None):
        return True

    def simplify(self, d):
        return True


class No(Certitude):
    def __call__(self, m, state=None):
        return False

    def simplify(self, d):
        return False


class Not(Filter):
    name = 'not'

    def __init__(self, p):
        self.p = p

    def __call__(self, m, state=None):
        return not self.p(m, state)

    def __str__(self):
        return self.gname() + ' ' + self.parenthesize(self.p)

    def __repr__(self):
        return self.__class__.__name__ + '(' + repr(self.p) + ')'

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.p == other.p

    def __hash__(self):
        return hash((self.__class__, self.p))

    def simplify(self, d):
        result = self.p.simplify(d)
        if isinstance(result, bool):
            return not result
        return super().simplify(d)


class Truth(Filter):
    def __init__(self, field):
        self.field = field

    def __call__(self, m, state=None):
        return bool(m.field(self.field))

    def __str__(self):
        return self.field

    def __repr__(self):
        return self.__class__.__name__ + '(' + repr(self.field) + ')'

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.field == other.field

    def __hash__(self):
        return hash((self.__class__, self.field))


class Conjunction(Filter):
    def __init__(self, *args):
        super().__init__()
        self.operands = []
        for arg in args:
            if arg is None:
                pass
            elif not isinstance(arg, self.__class__):
                self.operands.append(arg)
            else:
                self.operands += arg.operands
        self.operands = tuple(self.operands)


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

    def push(self, other):
        self.operands.append(other)

    def pop(self):
        if len(self.operands) > 2:
            self.operands.pop()
            return self
        else:
            return self.operands[0]

    def __hash__(self):
        return hash((self.__class__, self.operands))


class And(Conjunction):
    name = 'and'

    def __call__(self, m, state=None):
        for p in self.operands:
            if not p(m, state):
                return False
        return True

    def simplify(self, d):
        operands = []
        for p in self.operands:
            result = p.simplify(d)
            if not isinstance(result, bool):
                operands.append(p)
            elif result is False:
                return False
            elif result is True:
                pass # we can ignore it
        if len(operands) == 0:
            return True
        elif len(operands) == 1:
            return operands[0]
        else:
            return And(*operands)


class Or(Conjunction):
    name = 'or'

    def __call__(self, m, state=None):
        for p in self.operands:
            if p(m, state):
                return True
        return False

    def simplify(self, d):
        operands = []
        for p in self.operands:
            result = p.simplify(d)
            if not isinstance(result, bool):
                operands.append(p)
            elif result is True:
                return True
            elif result is False:
                pass # can ignore
        if len(operands) == 0:
            return False
        elif len(operands) == 1:
            return operands[0]
        else:
            return Or(*operands)


class Xor(Conjunction):
    name = 'xor'

    def __call__(self, m, state=None):
        return len([True for p in self.operands if p(m, state)]) == 1


class Python(Filter):
    def __init__(self, string):
        super(Python, self).__init__()
        self.string = string

    def __str__(self):
        return '$' + repr(self.string)

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            repr(self.string),
            )

    def __call__(self, m, state=None):
        try:
            return eval(self.string, {}, {'m': m, 'state': state})
        except:
            self.log.exception(
                'executing python filter %s on %s',
                repr(self.string),
                repr(m))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.string == other.string

    def __hash__(self):
        return hash((self.__class__, self.string))


class FilterLookup(Filter):
    def __init__(self, name):
        super(FilterLookup, self).__init__()
        self.filtername = name

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            repr(self.filtername),
            )

    def __call__(self, m, state=None):
        if state is not None:
            if self.filtername in state.setdefault('filterlookup', set()):
                return False
        else:
            state = {'filterlookup': set()}

        state['filterlookup'].add(self.filtername)

        conf = m.backend.context.conf
        self.log.debug('looking up filter %s', self.filtername)
        text = conf.get('filter', {}).get(self.filtername)
        if not text:
            self.log.debug('empty (%s)', repr(text))
            return False

        try:
            self.log.debug('%s: %s', self.filtername, text)
            return makefilter(text)(m, state)
        except:
            self.log.exception('in filter %s', self.filtername)
            return False

    def simplify(self, d):
        if self.filtername in d.setdefault('filterlookup', set()):
            return False

        d['filterlookup'].add(self.filtername)

        conf = d['context'].conf
        self.log.debug('looking up filter %s', self.filtername)
        text = conf.get('filter', {}).get(self.filtername)
        if not text:
            self.log.debug('empty (%s)', repr(text))
            return False

        try:
            self.log.debug('%s: %s', self.filtername, text)
            return makefilter(text).simplify(d)
        except:
            self.log.exception('in filter %s', self.filtername)
            return False

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__
            and self.filtername == other.filtername)

    def __hash__(self):
        return hash((self.__class__, self.filtername))

    def __str__(self):
        return 'filter ' + self.filtername


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

    def __call__(self, m, state=None):
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

    def __hash__(self):
        return hash((self.__class__, self.op, self.field, self.value))

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

    def simplify(self, d):
        v = self.value
        if isinstance(v, Identifier) or self.field not in d:
            return self
        return self.do(self.op, d[self.field], v)


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
            self.re = re.compile(self.value, re.DOTALL)
        except:
            self.log.exception('compiling regexp: %s', self.value)
            self.re = None

    @staticmethod
    def do(op, regexp, value):
        if regexp is None:
            return False
        result = bool(regexp.match(str(value)))
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

    def __call__(self, m, state=None):
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
        p[0] = FilterLookup(p[2])

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

    def p_truth(self, p):
        '''
        exp : ID
        '''
        p[0] = Truth(p[1])

    def p_error(self, p):
        self._errors.append(p)


parser = Parser()
lexer = Lexer()


@functools.lru_cache(maxsize=None)
def makefilter(s):
    lexer.reset_errors()
    parser.reset_errors()
    result = parser.parser.parse(s, lexer=lexer.lexer)
    if lexer.errors or parser.errors:
        raise SnipeFilterError(lexer.errors, parser.errors)
    return result


def validatefilter(s):
    try:
        makefilter(s)
        return True
    except SnipeFilterError:
        return False
