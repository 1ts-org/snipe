#!/usr/bin/python3
# -*- encoding: utf-8 -*-
# Copyright © 2016 the Snipe Contributors
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
Unit tests for zephyr scribelike markup parsing
'''

import random
import unittest
import sys

sys.path.append('..')

import snipe.zcode as zcode


class TestZcode(unittest.TestCase):
    def test_strip(self):
        self.assertEqual(
            zcode.strip('foo'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@bar{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip('@bar{foo@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip('@bar{foo@@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip('@{foo@}bar}baz'),
            'foo@bar}baz',
            )
        self.assertEqual(
            zcode.strip('foo@bar{baz@(bang})}'),
            'foobazbang}',
            )
        self.assertEqual(
            zcode.strip(''),
            '',
            )
        self.assertEqual(
            zcode.strip('foo@bar{baz}'),
            'foobaz',
            )
        self.assertEqual(
            zcode.strip('foo@{@font[fixed]@@bar}'),
            'foo@bar'
            )
        self.assertEqual(
            zcode.strip('foo@{@color(green)@@bar}'),
            'foo@bar'
            )

    def test_strip_simple(self):
        self.assertEqual(
            zcode.strip_simple('foo'),
            'foo',
            )
        self.assertEqual(
            zcode.strip_simple('@{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip_simple('@bar{foo}'),
            'foo',
            )
        self.assertEqual(
            zcode.strip_simple('@bar{foo@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip_simple('@bar{foo@@bar}'),
            'foo@bar',
            )
        self.assertEqual(
            zcode.strip_simple('@{foo@}bar}baz'),
            'foo@bar}baz',
            )
        self.assertEqual(
            zcode.strip_simple('foo@bar{baz@(bang})}'),
            'foobazbang}',
            )
        self.assertEqual(
            zcode.strip_simple(''),
            '',
            )
        self.assertEqual(
            zcode.strip_simple('foo@bar{baz}'),
            'foobaz',
            )

    def test_strip_pic(self):
        self.assertEqual(
            zcode.strip('@{@color{241}l}@{@color{65}l}@{@color{101}v}@{@color{241}v}@{@color{241}v}@{@color{101}n}@{@color{101}n}@{@color{143}2}@{@color{143}2}@{@color{144}S}@{@color{144}S}@{@color{144}S}@{@color{144}X}@{@color{186}X}@{@color{144}S}@{@color{143}n}@{@color{101}n}@{@color{101}n}@{@color{101}n}@{@color{101}n}@{@color{101}o}@{@color{107}o}@{@color{107}2}@{@color{143}S}@{@color{143}S}@{@color{107}o}@{@color{143}2}@{@color{107}n}@{@color{101}v}@{@color{101}v}@{@color{101}v}@{@color{101}n}@{@color{107}o}@{@color{107}o}@{@color{107}n}@{@color{101}o}@{@color{107}2}@{@color{107}o}@{@color{107}2}@{@color{144}S}@{@color{144}2}@{@color{143}2}@{@color{101}X}@{@color{144}S}@{@color{144}1}@{@color{101}n}@{@color{101}1}@{@color{101}I}@{@color{101}I}@{@color{65}i}@{@color{241}i}@{@color{59}|}@{@color{240}|}@{@color{59}l}@{@color{241}i}@{@color{241}i}@{@color{241}i}@{@color{241}l}@{@color{101}l}@{@color{65}I}@{@color{101}v}@{@color{101}I}@{@color{101}I}@{@color{241}i}@{@color{241}i}@{@color{239}|}@{@color{238}|}@{@color{238}=}@{@color{238}|}@{@color{238}+}\n@{@color{101}n}@{@color{101}o}@{@color{143}X}@{@color{144}S}@{@color{107}o}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}2}@{@color{144}2}@{@color{144}2}@{@color{144}2}@{@color{143}o}@{@color{107}o}@{@color{107}o}@{@color{107}n}@{@color{107}n}@{@color{107}n}@{@color{107}n}@{@color{143}o}@{@color{144}X}@{@color{186}#}@{@color{186}X}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{107}n}@{@color{101}v}@{@color{101}v}@{@color{101}n}@{@color{107}o}@{@color{101}o}@{@color{107}o}@{@color{107}2}@{@color{143}S}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{144}2}@{@color{144}S}@{@color{144}S}@{@color{186}S}@{@color{144}2}@{@color{107}o}@{@color{101}v}@{@color{65}v}@{@color{65}v}@{@color{241}v}@{@color{241}v}@{@color{65}v}@{@color{101}v}@{@color{101}n}@{@color{101}v}@{@color{101}I}@{@color{65}I}@{@color{65}v}@{@color{101}v}@{@color{101}v}@{@color{101}v}@{@color{101}I}@{@color{101}l}@{@color{101}l}@{@color{101}I}@{@color{101}I}@{@color{101}l}@{@color{65}i}@{@color{65}i}@{@color{241}i}@{@color{241}|}\n@{@color{144}m}@{@color{144}X}@{@color{186}Z}@{@color{186}Z}@{@color{187}#}@{@color{187}Z}@{@color{150}Z}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{144}X}@{@color{144}q}@{@color{144}m}@{@color{150}X}@{@color{150}X}@{@color{144}q}@{@color{144}X}@{@color{107}X}@{@color{144}2}@{@color{144}X}@{@color{150}X}@{@color{186}Z}@{@color{150}X}@{@color{144}X}@{@color{150}X}@{@color{144}2}@{@color{107}o}@{@color{107}w}@{@color{107}X}@{@color{144}2}@{@color{144}2}@{@color{144}2}@{@color{144}S}@{@color{144}2}@{@color{144}S}@{@color{144}S}@{@color{144}2}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}2}@{@color{144}S}@{@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{144}o}@{@color{144}o}@{@color{107}n}@{@color{101}n}@{@color{101}v}@{@color{101}I}@{@color{101}v}@{@color{101}v}@{@color{101}v}@{@color{101}I}@{@color{101}v}@{@color{65}l}@{@color{65}l}@{@color{65}l}@{@color{65}i}@{@color{65}i}@{@color{241}i}@{@color{241}i}@{@color{241}i}@{@color{59}|}@{@color{59}i}@{@color{59}|}\n@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{150}Z}@{@color{151}U}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@color{187}U}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{187}U}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{187}Z}@{@color{150}Z}@{@color{150}Z}@{@color{150}Z}@{@color{144}Z}@{@color{144}Z}@{@color{144}Z}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{144}X}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}o}@{@color{107}n}@{@color{101}n}@{@color{107}n}@{@color{101}v}@{@color{101}v}@{@color{65}I}@{@color{65}I}@{@color{65}l}@{@color{65}l}@{@color{65}i}@{@color{65}l}@{@color{65}i}@{@color{65}l}@{@color{65}i}@{@color{65}i}@{@color{65}i}@{@color{241}i}@{@color{241}i}@{@color{241}i}\n@{@color{187}W}@{@color{187}m}@{@color{254}B}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{151}#}@{@color{187}Z}@{@color{187}#}@{@color{187}Z}@{@color{187}U}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{151}Z}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}@{@color{150}Z}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{150}X}@{@color{150}Z}@{@color{150}X}@{@color{150}X}@{@color{144}X}@{@color{144}S}@{@color{144}2}@{@color{144}o}@{@color{144}o}@{@color{144}o}@{@color{108}o}@{@color{108}o}@{@color{108}o}@{@color{107}o}@{@color{108})}@{@color{101}n}@{@color{101}v}@{@color{65}v}@{@color{65}v}@{@color{65}I}@{@color{65}l}@{@color{65}l}@{@color{65}l}@{@color{65}l}@{@color{65}i}@{@color{65}l}@{@color{241}i}@{@color{241}i}@{@color{59}i}@{@color{240}i}@{@color{240}i}\n@{@color{253}m}@{@color{254}B}@{@color{253}m}@{@color{187}B}@{@color{187}m}@{@color{253}B}@{@color{187}m}@{@color{187}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color{187}Z}@{@color{151}#}@{@color{151}Z}@{@color{151}Z}@{@color{151}#}@{@color{151}Z}@{@color{151}Z}@{@color{151}#}@{@color{187}Z}@{@color{151}#}@{@color{151}Z}@{@color{187}U}@{@color{187}Z}@{@color{187}#}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}@{@color{150}Z}@{@color{144}Z}@{@color{144}q}@{@color{144}q}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}Z}@{@color{150}S}@{@color{144}*}@{@color{144}^}@{@color{145}!}@{@color{235}-}@{@color{236}<}@{@color{235};}@{@color{235})}@{@color{108}o}@{@color{102}o}@{@color{244}o}@{@color{244}o}@{@color{102}w}@{@color{108}o}@{@color{108}X}@{@color{144}2}@{@color{144}2}@{@color{144}X}@{@color{144}2}@{@color{150}X}@{@color{144}2}@{@color{144}S}\n@{@color{187}B}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{188}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{188}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}B}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{151}2}@{@color{187}1}@{@color{251}\\}@{@color{232}.}@{@color{242}~}@{@color{16}/}@{@color{232})}@{@color{187}4}@{@color{240}w}@{@color{187}#}@{@color{187}X}@{@color{187}#}@{@color{144}X}@{@color{108}o}@{@color{108}m}@{@color{108}o}@{@color{108}w}@{@color{108}w}@{@color{108}d}@{@color{150}X}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}\n@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color{151}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}@{@color{187}m}@{@color{188}m}@{@color{253}m}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{253}B}@{@color{254}C}@{@color{151}^}@{@color{234}-}@{@color{58}+}@{@color{187}?}@{@color{144}4}@{@color{238})}@{@color{234}+}@{@color{238};}@{@color{239}>}@{@color{59}=}@{@color{233}_}@{@color{233}=}@{@color{65}=}@{@color{249}m}@{@color{187}#}@{@color{188}m}@{@color{188}B}@{@color{187}m}@{@color{187}m}@{@color{253}B}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}\n@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}m}@{@color{188}m}@{@color{253}m}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{188}B}@{@color{188}m}@{@color{188}B}@{@color{188}B}@{@color{253}B}@{@color{253}B}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}m}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{194}[}@{@color{240}:}@{@color{233}.}@{@color{232}/}@{@color{235}:}@{@color{232}.}@{@color{235}:}@{@color{237}-}@{@color{234}:}@{@color{235}_}@{@color{233}=}@{@color{194}[}@{@color{16}/}@{@color{236}=}@{@color{143}(}@{@color{230}W}@{@color{254}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}\n@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}m}@{@color{253}B}@{@color{253}B}@{@color{254}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color{254}B}@{@color{254}B}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@color{254}B}@{@color{254}W}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{188}W}@{@color{188}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color{254}$}@{@color{187}6}@{@color{234}-}@{@color{101}|}@{@color{65}|}@{@color{232}_}@{@color{234}=}@{@color{232}_}@{@color{237}=}@{@color{235};}@{@color{237}=}@{@color{235}:}@{@color{237};}@{@color{236}:}@{@color{236}-}@{@color{233}-}@{@color{186}(}@{@color{254}$}@{@color{253}m}@{@color{254}W}@{@color{254}B}@{@color{254}W}@{@color{254}B}@{@color{253}W}@{@color{253}m}@{@color{254}W}@{@color{254}B}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color{253}B}@{@color{253}W}\n@{@color{151}#}@{@color{151}Z}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}W}@{@color{253}B}@{@color{254}W}@{@color{253}m}@{@color{254}m}@{@color{253}m}@{@color{188}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}m}@{@color{254}W}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}B}@{@color{254}W}@{@color{254}E}@{@color{101}`}@{@color{101}<}@{@color{238}:}@{@color{236}=}@{@color{234}.}@{@color{235}:}@{@color{65}=}@{@color{236}=}@{@color{236}-}@{@color{16}.}@{@color{234}:}@{@color{235}=}@{@color{233},}@{@color{233},}@{@color{101}+}@{@color{235};}@{@color{233}.}@{@color{101}4}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}B}\n@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{253}W}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}m}@{@color{253}W}@{@color{254}m}@{@color{254}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}W}@{@color{254}m}@{@color{254}B}@{@color{254}m}@{@color{254}m}@{@color{194}f}@{@color{234}:}@{@color{239}`}@{@color{233}.}@{@color{65}`}@{@color{233}=}@{@color{236};}@{@color{233}.}@{@color{236}:}@{@color{237};}@{@color{65}`}@{@color{234}=}@{@color{233}.}@{@color{236}=}@{@color{236}=}@{@color{232}_}@{@color{232}.}@{@color{232}.}@{@color{234})}@{@color{254}?}@{@color{254}4}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{254}m}@{@color{254}B}@{@color{253}B}@{@color{254}W}\n@{@color{144}X}@{@color{144}X}@{@color{150}X}@{@color{187}X}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{187}X}@{@color{187}#}@{@color{187}X}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{187}Z}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}@{@color{253}m}@{@color{240}c}@{@color{232}j}@{@color{144}"}@{@color{233}-}@{@color{233}_}@{@color{235}:}@{@color{235}:}@{@color{235}a}@{@color{237}/}@{@color{237}|}@{@color{236}:}@{@color{232},}@{@color{234}=}@{@color{16}a}@{@color{241}<}@{@color{237}u}@{@color{240}m}@{@color{253}6}@{@color{16}a}@{@color{16},}@{@color{59}`}@{@color{237}-}@{@color{253}4}@{@color{254}B}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}B}@{@color{253}m}@{@color{254}m}\n@{@color{144}o}@{@color{144}2}@{@color{144}o}@{@color{144}X}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{151}X}@{@color{151}Z}@{@color{187}X}@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{151}X}@{@color{151}Z}@{@color{187}Z}@{@color{151}Z}@{@color{187}#}@{@color{187}Z}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color{187}Z}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}C}@{@color{236}>}@{@color{234}a}@{@color{236}a}@{@color{144}#}@{@color{187}#}@{@color{238}a}@{@color{234}a}@{@color{239}a}@{@color{235}a}@{@color{59}w}@{@color{65}w}@{@color{253}m}@{@color{187}m}@{@color{187}m}@{@color{253}#}@{@color{187}#}@{@color{187}#}@{@color{253}m}@{@color{102}w}@{@color{232},}@{@color{234})}@{@color{253}9}@{@color{188}m}@{@color{253}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}B}@{@color{253}m}\n@{@color{102}"}@{@color{108}!}@{@color{108}"}@{@color{108}!}@{@color{108}"}@{@color{108}!}@{@color{108}"}@{@color{144}!}@{@color{144}"}@{@color{144}!}@{@color{144}!}@{@color{144}"}@{@color{144}?}@{@color{150}!}@{@color{150}!}@{@color{144}!}@{@color{150}!}@{@color{150}!}@{@color{150}!}@{@color{150}!}@{@color{150}!}@{@color{150}!}@{@color{151}!}@{@color{187}!}@{@color{187}!}@{@color{187}?}@{@color{187}!}@{@color{187}!}@{@color{151}!}@{@color{151}!}@{@color{151}?}@{@color{187}?}@{@color{187}?}@{@color{187}!}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}Y}@{@color{187}?}@{@color{187}!}@{@color{151}?}@{@color{187}?}@{@color{187}?}@{@color{187}Y}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}Y}@{@color{187}?}@{@color{187}Y}@{@color{187}Y}@{@color{187}?}@{@color{187}Y}@{@color{150}*}@{@color{101}i}@{@color{64}i}@{@color{233},}@{@color{234} }@{@color{150}Y}@{@color{186}!}@{@color{144}Y}@{@color{186}?}@{@color{187}Y}@{@color{187}?}@{@color{187}Y}@{@color{187}?}\n@{@color{233}:}@{@color{234}-}@{@color{234}:}@{@color{234}.}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{234};}@{@color{234}:}@{@color{234}.}@{@color{235}=}@{@color{235};}@{@color{234}:}@{@color{235}:}@{@color{235}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{235};}@{@color{236}:}@{@color{235};}@{@color{235};}@{@color{235};}@{@color{234}=}@{@color{235};}@{@color{58}=}@{@color{58}=}@{@color{235}=}@{@color{58};}@{@color{235}=}@{@color{235}=}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}|}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{235}|}@{@color{58}|}@{@color{236}=}@{@color{235}=}@{@color{234}=}@{@color{235};}@{@color{234};}@{@color{233}_}@{@color{233};}@{@color{234}=}@{@color{235}=}@{@color{234}=}@{@color{235}=}@{@color{234}_}@{@color{234}=}@{@color{58}=}@{@color{58}|}@{@color{58}=}@{@color{58}i}@{@color{58}+}@{@color{58}|}\n@{@color{234}:}@{@color{234}.}@{@color{234}:}@{@color{234}-}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234};}@{@color{235}:}@{@color{235}:}@{@color{235};}@{@color{234}:}@{@color{235}:}@{@color{235};}@{@color{235};}@{@color{58};}@{@color{236}:}@{@color{58}=}@{@color{236};}@{@color{236}=}@{@color{235};}@{@color{235}=}@{@color{235};}@{@color{58}=}@{@color{58}=}@{@color{235};}@{@color{58};}@{@color{235}=}@{@color{235}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@color{58}+}@{@color{58}+}@{@color{58}+}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}=}@{@color{58}|}@{@color{58}|}@{@color{58}=}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{64}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}>}@{@color{58}=}@{@color{58}|}@{@color{58}+}@{@color{58}|}\n@{@color{233}.}@{@color{233}-}@{@color{234}.}@{@color{233}-}@{@color{234}-}@{@color{234}-}@{@color{235}-}@{@color{234}:}@{@color{234}-}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@color{235};}@{@color{235}:}@{@color{235};}@{@color{235}:}@{@color{235};}@{@color{235};}@{@color{235}:}@{@color{58}:}@{@color{236}=}@{@color{58}:}@{@color{235};}@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{58};}@{@color{58}=}@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@color{58}+}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}+}@{@color{64}+}@{@color{64}+}@{@color{58}+}@{@color{58}=}@{@color{58}|}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}>}@{@color{58}+}@{@color{58}+}@{@color{58}|}@{@color{58}+}@{@color{58}+}@{@color{58}+}@{@color{58}|}@{@color{58}|}@{@color{58}=}@{@color{58}+}\n@{@color{233}.}@{@color{233}.}@{@color{233}-}@{@color{234}-}@{@color{233}.}@{@color{233}:}@{@color{233}.}@{@color{233}.}@{@color{234}-}@{@color{234}.}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{235}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{235};}@{@color{235};}@{@color{236}=}@{@color{234};}@{@color{236};}@{@color{236};}@{@color{235};}@{@color{234};}@{@color{235};}@{@color{236};}@{@color{236}=}@{@color{235};}@{@color{235};}@{@color{235}=}@{@color{236}=}@{@color{235}=}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{235}=}@{@color{58}=}@{@color{235}=}@{@color{58}+}@{@color{58}=}@{@color{58}|}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}=}@{@color{58}|}@{@color{58}|}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}|}\n'),
            'llvvvnn22SSSXXSnnnnnoo2SSo2nvvvnoono2o2S22XS1n1IIii||liiillIvIIii||=|+\nnoXSoXXXS2222ooonnnnoX#XXXXnvvnooo2SXSS2SSS2ovvvvvvvnvIIvvvvIllIIliii|\nmXZZ#ZZXXXSSXqmXXqXX2XXZXXX2owX222S2SS2XXX2SXXSSoonnvIvvvIvllliiiii|i|\n##m######ZZU##UU##ZUZZ#ZZZZZZZXXXXXXSSXXXXXXXXXXXSonnnvvIIllililiiiiii\nWmBmm###mmm#####Z###Z#Z#ZUZZ#ZZZZZXXXXXXZXXXS2ooooooo)nvvvIlllliliiiii\nmBmBmBmmmmmm#######U#U#Z#ZZ#ZZ#Z#ZUZ#ZZZZZqqXXXZS*^!-<;)oooowoX22X2X2S\nBmmmmmmmm############mmmmmm##mmmmBmmmmmmmm###mm21\\.~/)4w#X#XomowwdXZZZ\n#######U####mmmmmmmmmmmmmmmBBBBBBBBBWmWBC^-+?4)+;>=_==m#mBmmB##m#####m\nmmmmmmmmmmmWmWmBmBmBBBBmWmBmBmBmBmmmmmm[:./:.:-:_=[/=(WmBmBmBmBmBmmmmm\n####mmmmmBBmmmmWmWBBmmBmmBBWmWmWmWmWmW$6-||_=_=;=:;:--($mWBWBWmWBWmWBW\n#Z####mmmmmWBWmmmmmmmmmWmWmmBBBmWmWBWE`<:=.:==-.:=,,+;.4mWmWmWmWmWmWmB\nZZZZZ#U########mWmBmWmWmWmmWmBBBBWmBmmf:`.`=;.:;`=.==_..)?4WmWmWmWmBBW\nXXXXZZ#X#XZZ#Z###########mmmmmmmmmmmmmcj"-_::a/|:,=a<um6a,`-4BmmBmBBmm\no2oXXXXXXXXZXZZZXZZZ#Z######U#Z########C>aa##aaaawwmmm###mw,)9mmmmmmBm\n"!"!"!"!"!!"?!!!!!!!!!!!!?!!!!???!?????Y?!???Y?????Y?YY?Y*ii, Y!Y?Y?Y?\n:-:.::::;:.=;::::::;:;;;=;===;======+|+=+=|=+====||===;;_;====_==|=i+|\n:.:-::::::;::;::;;;:=;=;=;==;;====+|=+=+=++++|||||=||=|||||||||||>=|+|\n.-.----:-::::::::;:;:;;::=:;=====;=====+=++=====+++++=|=+|=>++|+++||=+\n..--.:..-.::::::::::::::;;=;;;;;;;=;;======+===+=|=+|===+==||==+|==+=|\n',
            )

    def test_fuzz(self, tries=1000, max_len=64):
        # basically we're trying to get it to throw
        CHARS = zcode.LEFT + zcode.RIGHT + '@abc '
        for i in range(tries):
            zcode.strip_simple(''.join(
                random.choice(CHARS) for l in range(random.randint(0, max_len - 1))))
