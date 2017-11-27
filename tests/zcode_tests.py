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

import snipe.zcode as zcode  # noqa: E402


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
        self.assertEqual(
            zcode.strip_simple('@bloop'),
            '@bloop',
            )

    def test_strip_pic(self):
        self.assertEqual(
            zcode.strip(
                '@{@color{241}l}@{@color{65}l}@{@color{101}v}@{@color{241}v}@'
                '{@color{241}v}@{@color{101}n}@{@color{101}n}@{@color{143}2}@'
                '{@color{143}2}@{@color{144}S}@{@color{144}S}@{@color{144}S}@'
                '{@color{144}X}@{@color{186}X}@{@color{144}S}@{@color{143}n}@'
                '{@color{101}n}@{@color{101}n}@{@color{101}n}@{@color{101}n}@'
                '{@color{101}o}@{@color{107}o}@{@color{107}2}@{@color{143}S}@'
                '{@color{143}S}@{@color{107}o}@{@color{143}2}@{@color{107}n}@'
                '{@color{101}v}@{@color{101}v}@{@color{101}v}@{@color{101}n}@'
                '{@color{107}o}@{@color{107}o}@{@color{107}n}@{@color{101}o}@'
                '{@color{107}2}@{@color{107}o}@{@color{107}2}@{@color{144}S}@'
                '{@color{144}2}@{@color{143}2}@{@color{101}X}@{@color{144}S}@'
                '{@color{144}1}@{@color{101}n}@{@color{101}1}@{@color{101}I}@'
                '{@color{101}I}@{@color{65}i}@{@color{241}i}@{@color{59}|}@{@'
                'color{240}|}@{@color{59}l}@{@color{241}i}@{@color{241}i}@{@c'
                'olor{241}i}@{@color{241}l}@{@color{101}l}@{@color{65}I}@{@co'
                'lor{101}v}@{@color{101}I}@{@color{101}I}@{@color{241}i}@{@co'
                'lor{241}i}@{@color{239}|}@{@color{238}|}@{@color{238}=}@{@co'
                'lor{238}|}@{@color{238}+}\n@{@color{101}n}@{@color{101}o}@{@c'
                'olor{143}X}@{@color{144}S}@{@color{107}o}@{@color{144}X}@{@c'
                'olor{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}2}@{@c'
                'olor{144}2}@{@color{144}2}@{@color{144}2}@{@color{143}o}@{@c'
                'olor{107}o}@{@color{107}o}@{@color{107}n}@{@color{107}n}@{@c'
                'olor{107}n}@{@color{107}n}@{@color{143}o}@{@color{144}X}@{@c'
                'olor{186}#}@{@color{186}X}@{@color{150}X}@{@color{144}X}@{@c'
                'olor{144}X}@{@color{107}n}@{@color{101}v}@{@color{101}v}@{@c'
                'olor{101}n}@{@color{107}o}@{@color{101}o}@{@color{107}o}@{@c'
                'olor{107}2}@{@color{143}S}@{@color{144}X}@{@color{144}S}@{@c'
                'olor{144}S}@{@color{144}2}@{@color{144}S}@{@color{144}S}@{@c'
                'olor{186}S}@{@color{144}2}@{@color{107}o}@{@color{101}v}@{@c'
                'olor{65}v}@{@color{65}v}@{@color{241}v}@{@color{241}v}@{@col'
                'or{65}v}@{@color{101}v}@{@color{101}n}@{@color{101}v}@{@colo'
                'r{101}I}@{@color{65}I}@{@color{65}v}@{@color{101}v}@{@color{'
                '101}v}@{@color{101}v}@{@color{101}I}@{@color{101}l}@{@color{'
                '101}l}@{@color{101}I}@{@color{101}I}@{@color{101}l}@{@color{'
                '65}i}@{@color{65}i}@{@color{241}i}@{@color{241}|}\n@{@color{1'
                '44}m}@{@color{144}X}@{@color{186}Z}@{@color{186}Z}@{@color{1'
                '87}#}@{@color{187}Z}@{@color{150}Z}@{@color{150}X}@{@color{1'
                '44}X}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{1'
                '44}X}@{@color{144}q}@{@color{144}m}@{@color{150}X}@{@color{1'
                '50}X}@{@color{144}q}@{@color{144}X}@{@color{107}X}@{@color{1'
                '44}2}@{@color{144}X}@{@color{150}X}@{@color{186}Z}@{@color{1'
                '50}X}@{@color{144}X}@{@color{150}X}@{@color{144}2}@{@color{1'
                '07}o}@{@color{107}w}@{@color{107}X}@{@color{144}2}@{@color{1'
                '44}2}@{@color{144}2}@{@color{144}S}@{@color{144}2}@{@color{1'
                '44}S}@{@color{144}S}@{@color{144}2}@{@color{144}X}@{@color{1'
                '44}X}@{@color{144}X}@{@color{144}2}@{@color{144}S}@{@color{1'
                '44}X}@{@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{1'
                '44}o}@{@color{144}o}@{@color{107}n}@{@color{101}n}@{@color{1'
                '01}v}@{@color{101}I}@{@color{101}v}@{@color{101}v}@{@color{1'
                '01}v}@{@color{101}I}@{@color{101}v}@{@color{65}l}@{@color{65'
                '}l}@{@color{65}l}@{@color{65}i}@{@color{65}i}@{@color{241}i}'
                '@{@color{241}i}@{@color{241}i}@{@color{59}|}@{@color{59}i}@{'
                '@color{59}|}\n@{@color{187}#}@{@color{187}#}@{@color{187}m}@{'
                '@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{'
                '@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{150}Z}@{'
                '@color{151}U}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{'
                '@color{187}U}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{'
                '@color{187}U}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{'
                '@color{187}Z}@{@color{150}Z}@{@color{150}Z}@{@color{150}Z}@{'
                '@color{144}Z}@{@color{144}Z}@{@color{144}Z}@{@color{150}X}@{'
                '@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{'
                '@color{144}X}@{@color{144}S}@{@color{144}S}@{@color{150}X}@{'
                '@color{150}X}@{@color{150}X}@{@color{144}X}@{@color{150}X}@{'
                '@color{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}X}@{'
                '@color{144}X}@{@color{144}X}@{@color{144}S}@{@color{144}o}@{'
                '@color{107}n}@{@color{101}n}@{@color{107}n}@{@color{101}v}@{'
                '@color{101}v}@{@color{65}I}@{@color{65}I}@{@color{65}l}@{@co'
                'lor{65}l}@{@color{65}i}@{@color{65}l}@{@color{65}i}@{@color{'
                '65}l}@{@color{65}i}@{@color{65}i}@{@color{65}i}@{@color{241}'
                'i}@{@color{241}i}@{@color{241}i}\n@{@color{187}W}@{@color{187'
                '}m}@{@color{254}B}@{@color{187}m}@{@color{187}m}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{187'
                '}m}@{@color{187}m}@{@color{187}#}@{@color{187}#}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}Z}@{@color{151'
                '}#}@{@color{187}Z}@{@color{187}#}@{@color{187}Z}@{@color{187'
                '}U}@{@color{187}Z}@{@color{187}Z}@{@color{187}#}@{@color{151'
                '}Z}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}@{@color{150'
                '}Z}@{@color{150}X}@{@color{144}X}@{@color{144}X}@{@color{144'
                '}X}@{@color{144}X}@{@color{150}X}@{@color{150}Z}@{@color{150'
                '}X}@{@color{150}X}@{@color{144}X}@{@color{144}S}@{@color{144'
                '}2}@{@color{144}o}@{@color{144}o}@{@color{144}o}@{@color{108'
                '}o}@{@color{108}o}@{@color{108}o}@{@color{107}o}@{@color{108'
                '})}@{@color{101}n}@{@color{101}v}@{@color{65}v}@{@color{65}v'
                '}@{@color{65}I}@{@color{65}l}@{@color{65}l}@{@color{65}l}@{@'
                'color{65}l}@{@color{65}i}@{@color{65}l}@{@color{241}i}@{@col'
                'or{241}i}@{@color{59}i}@{@color{240}i}@{@color{240}i}\n@{@col'
                'or{253}m}@{@color{254}B}@{@color{253}m}@{@color{187}B}@{@col'
                'or{187}m}@{@color{253}B}@{@color{187}m}@{@color{187}m}@{@col'
                'or{253}m}@{@color{253}m}@{@color{187}m}@{@color{187}m}@{@col'
                'or{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@col'
                'or{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@col'
                'or{187}#}@{@color{187}U}@{@color{187}#}@{@color{187}Z}@{@col'
                'or{151}#}@{@color{151}Z}@{@color{151}Z}@{@color{151}#}@{@col'
                'or{151}Z}@{@color{151}Z}@{@color{151}#}@{@color{187}Z}@{@col'
                'or{151}#}@{@color{151}Z}@{@color{187}U}@{@color{187}Z}@{@col'
                'or{187}#}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}@{@col'
                'or{150}Z}@{@color{144}Z}@{@color{144}q}@{@color{144}q}@{@col'
                'or{144}X}@{@color{144}X}@{@color{144}X}@{@color{144}Z}@{@col'
                'or{150}S}@{@color{144}*}@{@color{144}^}@{@color{145}!}@{@col'
                'or{235}-}@{@color{236}<}@{@color{235};}@{@color{235})}@{@col'
                'or{108}o}@{@color{102}o}@{@color{244}o}@{@color{244}o}@{@col'
                'or{102}w}@{@color{108}o}@{@color{108}X}@{@color{144}2}@{@col'
                'or{144}2}@{@color{144}X}@{@color{144}2}@{@color{150}X}@{@col'
                'or{144}2}@{@color{144}S}\n@{@color{187}B}@{@color{253}m}@{@co'
                'lor{253}m}@{@color{253}m}@{@color{188}m}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}#}@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@co'
                'lor{188}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{187}m}@{@color{187}m}@{@color{253}B}@{@co'
                'lor{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{151}2}@{@color{187}1}@{@color{251}\\}@{@co'
                'lor{232}.}@{@color{242}~}@{@color{16}/}@{@color{232})}@{@col'
                'or{187}4}@{@color{240}w}@{@color{187}#}@{@color{187}X}@{@col'
                'or{187}#}@{@color{144}X}@{@color{108}o}@{@color{108}m}@{@col'
                'or{108}o}@{@color{108}w}@{@color{108}w}@{@color{108}d}@{@col'
                'or{150}X}@{@color{151}Z}@{@color{151}Z}@{@color{150}Z}\n@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@co'
                'lor{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}U}@{@co'
                'lor{187}#}@{@color{151}#}@{@color{187}#}@{@color{187}#}@{@co'
                'lor{187}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}@{@co'
                'lor{187}m}@{@color{188}m}@{@color{253}m}@{@color{188}m}@{@co'
                'lor{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@co'
                'lor{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}B}@{@co'
                'lor{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@co'
                'lor{253}B}@{@color{253}B}@{@color{253}B}@{@color{253}B}@{@co'
                'lor{254}W}@{@color{254}m}@{@color{254}W}@{@color{253}B}@{@co'
                'lor{254}C}@{@color{151}^}@{@color{234}-}@{@color{58}+}@{@col'
                'or{187}?}@{@color{144}4}@{@color{238})}@{@color{234}+}@{@col'
                'or{238};}@{@color{239}>}@{@color{59}=}@{@color{233}_}@{@colo'
                'r{233}=}@{@color{65}=}@{@color{249}m}@{@color{187}#}@{@color'
                '{188}m}@{@color{188}B}@{@color{187}m}@{@color{187}m}@{@color'
                '{253}B}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color'
                '{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color'
                '{187}#}@{@color{187}m}\n@{@color{187}m}@{@color{187}m}@{@colo'
                'r{187}m}@{@color{187}m}@{@color{253}m}@{@color{188}m}@{@colo'
                'r{253}m}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@colo'
                'r{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@colo'
                'r{253}m}@{@color{253}B}@{@color{253}m}@{@color{188}B}@{@colo'
                'r{188}m}@{@color{188}B}@{@color{188}B}@{@color{253}B}@{@colo'
                'r{253}B}@{@color{253}m}@{@color{253}W}@{@color{253}m}@{@colo'
                'r{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@colo'
                'r{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@colo'
                'r{253}m}@{@color{188}m}@{@color{253}m}@{@color{253}m}@{@colo'
                'r{253}m}@{@color{194}[}@{@color{240}:}@{@color{233}.}@{@colo'
                'r{232}/}@{@color{235}:}@{@color{232}.}@{@color{235}:}@{@colo'
                'r{237}-}@{@color{234}:}@{@color{235}_}@{@color{233}=}@{@colo'
                'r{194}[}@{@color{16}/}@{@color{236}=}@{@color{143}(}@{@color'
                '{230}W}@{@color{254}m}@{@color{253}B}@{@color{253}m}@{@color'
                '{253}B}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color'
                '{253}B}@{@color{253}m}@{@color{253}B}@{@color{188}m}@{@color'
                '{253}m}@{@color{253}m}@{@color{253}m}@{@color{187}m}\n@{@colo'
                'r{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@colo'
                'r{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@colo'
                'r{253}m}@{@color{253}B}@{@color{253}B}@{@color{254}m}@{@colo'
                'r{253}m}@{@color{253}m}@{@color{253}m}@{@color{253}W}@{@colo'
                'r{253}m}@{@color{253}W}@{@color{254}B}@{@color{254}B}@{@colo'
                'r{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@colo'
                'r{253}m}@{@color{253}B}@{@color{254}B}@{@color{254}W}@{@colo'
                'r{253}m}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@colo'
                'r{253}m}@{@color{188}W}@{@color{188}m}@{@color{253}W}@{@colo'
                'r{253}m}@{@color{253}W}@{@color{254}$}@{@color{187}6}@{@colo'
                'r{234}-}@{@color{101}|}@{@color{65}|}@{@color{232}_}@{@color'
                '{234}=}@{@color{232}_}@{@color{237}=}@{@color{235};}@{@color'
                '{237}=}@{@color{235}:}@{@color{237};}@{@color{236}:}@{@color'
                '{236}-}@{@color{233}-}@{@color{186}(}@{@color{254}$}@{@color'
                '{253}m}@{@color{254}W}@{@color{254}B}@{@color{254}W}@{@color'
                '{254}B}@{@color{253}W}@{@color{253}m}@{@color{254}W}@{@color'
                '{254}B}@{@color{253}W}@{@color{253}m}@{@color{253}W}@{@color'
                '{253}B}@{@color{253}W}\n@{@color{151}#}@{@color{151}Z}@{@colo'
                'r{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@colo'
                'r{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@colo'
                'r{187}m}@{@color{187}W}@{@color{253}B}@{@color{254}W}@{@colo'
                'r{253}m}@{@color{254}m}@{@color{253}m}@{@color{188}m}@{@colo'
                'r{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@colo'
                'r{253}m}@{@color{254}W}@{@color{253}m}@{@color{253}W}@{@colo'
                'r{253}m}@{@color{253}m}@{@color{253}B}@{@color{253}B}@{@colo'
                'r{253}B}@{@color{253}m}@{@color{254}W}@{@color{254}m}@{@colo'
                'r{254}W}@{@color{254}B}@{@color{254}W}@{@color{254}E}@{@colo'
                'r{101}`}@{@color{101}<}@{@color{238}:}@{@color{236}=}@{@colo'
                'r{234}.}@{@color{235}:}@{@color{65}=}@{@color{236}=}@{@color'
                '{236}-}@{@color{16}.}@{@color{234}:}@{@color{235}=}@{@color{'
                '233},}@{@color{233},}@{@color{101}+}@{@color{235};}@{@color{'
                '233}.}@{@color{101}4}@{@color{254}m}@{@color{254}W}@{@color{'
                '254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{'
                '254}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{'
                '254}m}@{@color{254}W}@{@color{254}m}@{@color{254}B}\n@{@color'
                '{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color'
                '{187}Z}@{@color{187}#}@{@color{187}U}@{@color{187}#}@{@color'
                '{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color'
                '{187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color'
                '{253}W}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color'
                '{253}W}@{@color{253}m}@{@color{254}W}@{@color{254}m}@{@color'
                '{254}W}@{@color{254}m}@{@color{254}m}@{@color{253}W}@{@color'
                '{254}m}@{@color{254}B}@{@color{253}B}@{@color{253}B}@{@color'
                '{253}B}@{@color{253}W}@{@color{254}m}@{@color{254}B}@{@color'
                '{254}m}@{@color{254}m}@{@color{194}f}@{@color{234}:}@{@color'
                '{239}`}@{@color{233}.}@{@color{65}`}@{@color{233}=}@{@color{'
                '236};}@{@color{233}.}@{@color{236}:}@{@color{237};}@{@color{'
                '65}`}@{@color{234}=}@{@color{233}.}@{@color{236}=}@{@color{2'
                '36}=}@{@color{232}_}@{@color{232}.}@{@color{232}.}@{@color{2'
                '34})}@{@color{254}?}@{@color{254}4}@{@color{254}W}@{@color{2'
                '54}m}@{@color{254}W}@{@color{254}m}@{@color{254}W}@{@color{2'
                '54}m}@{@color{254}W}@{@color{254}m}@{@color{254}B}@{@color{2'
                '53}B}@{@color{254}W}\n@{@color{144}X}@{@color{144}X}@{@color{'
                '150}X}@{@color{187}X}@{@color{187}Z}@{@color{187}Z}@{@color{'
                '187}#}@{@color{187}X}@{@color{187}#}@{@color{187}X}@{@color{'
                '187}Z}@{@color{187}Z}@{@color{187}#}@{@color{187}Z}@{@color{'
                '187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{'
                '187}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{'
                '187}#}@{@color{187}#}@{@color{187}#}@{@color{187}m}@{@color{'
                '187}m}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{'
                '187}m}@{@color{253}m}@{@color{253}m}@{@color{253}m}@{@color{'
                '253}m}@{@color{253}m}@{@color{187}m}@{@color{253}m}@{@color{'
                '240}c}@{@color{232}j}@{@color{144}"}@{@color{233}-}@{@color{'
                '233}_}@{@color{235}:}@{@color{235}:}@{@color{235}a}@{@color{'
                '237}/}@{@color{237}|}@{@color{236}:}@{@color{232},}@{@color{'
                '234}=}@{@color{16}a}@{@color{241}<}@{@color{237}u}@{@color{2'
                '40}m}@{@color{253}6}@{@color{16}a}@{@color{16},}@{@color{59}'
                '`}@{@color{237}-}@{@color{253}4}@{@color{254}B}@{@color{253}'
                'm}@{@color{253}m}@{@color{253}B}@{@color{253}m}@{@color{253}'
                'B}@{@color{253}B}@{@color{253}m}@{@color{254}m}\n@{@color{144'
                '}o}@{@color{144}2}@{@color{144}o}@{@color{144}X}@{@color{150'
                '}X}@{@color{150}X}@{@color{150}X}@{@color{150}X}@{@color{150'
                '}X}@{@color{150}X}@{@color{151}X}@{@color{151}Z}@{@color{187'
                '}X}@{@color{187}Z}@{@color{187}Z}@{@color{187}Z}@{@color{151'
                '}X}@{@color{151}Z}@{@color{187}Z}@{@color{151}Z}@{@color{187'
                '}#}@{@color{187}Z}@{@color{187}#}@{@color{187}#}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187'
                '}U}@{@color{187}#}@{@color{187}Z}@{@color{187}#}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}#}@{@color{187'
                '}#}@{@color{187}#}@{@color{187}#}@{@color{187}C}@{@color{236'
                '}>}@{@color{234}a}@{@color{236}a}@{@color{144}#}@{@color{187'
                '}#}@{@color{238}a}@{@color{234}a}@{@color{239}a}@{@color{235'
                '}a}@{@color{59}w}@{@color{65}w}@{@color{253}m}@{@color{187}m'
                '}@{@color{187}m}@{@color{253}#}@{@color{187}#}@{@color{187}#'
                '}@{@color{253}m}@{@color{102}w}@{@color{232},}@{@color{234})'
                '}@{@color{253}9}@{@color{188}m}@{@color{253}m}@{@color{187}m'
                '}@{@color{187}m}@{@color{187}m}@{@color{187}m}@{@color{187}B'
                '}@{@color{253}m}\n@{@color{102}"}@{@color{108}!}@{@color{108}'
                '"}@{@color{108}!}@{@color{108}"}@{@color{108}!}@{@color{108}'
                '"}@{@color{144}!}@{@color{144}"}@{@color{144}!}@{@color{144}'
                '!}@{@color{144}"}@{@color{144}?}@{@color{150}!}@{@color{150}'
                '!}@{@color{144}!}@{@color{150}!}@{@color{150}!}@{@color{150}'
                '!}@{@color{150}!}@{@color{150}!}@{@color{150}!}@{@color{151}'
                '!}@{@color{187}!}@{@color{187}!}@{@color{187}?}@{@color{187}'
                '!}@{@color{187}!}@{@color{151}!}@{@color{151}!}@{@color{151}'
                '?}@{@color{187}?}@{@color{187}?}@{@color{187}!}@{@color{187}'
                '?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}'
                '?}@{@color{187}Y}@{@color{187}?}@{@color{187}!}@{@color{151}'
                '?}@{@color{187}?}@{@color{187}?}@{@color{187}Y}@{@color{187}'
                '?}@{@color{187}?}@{@color{187}?}@{@color{187}?}@{@color{187}'
                '?}@{@color{187}Y}@{@color{187}?}@{@color{187}Y}@{@color{187}'
                'Y}@{@color{187}?}@{@color{187}Y}@{@color{150}*}@{@color{101}'
                'i}@{@color{64}i}@{@color{233},}@{@color{234} }@{@color{150}Y'
                '}@{@color{186}!}@{@color{144}Y}@{@color{186}?}@{@color{187}Y'
                '}@{@color{187}?}@{@color{187}Y}@{@color{187}?}\n@{@color{233}'
                ':}@{@color{234}-}@{@color{234}:}@{@color{234}.}@{@color{234}'
                ':}@{@color{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}'
                ';}@{@color{234}:}@{@color{234}.}@{@color{235}=}@{@color{235}'
                ';}@{@color{234}:}@{@color{235}:}@{@color{235}:}@{@color{234}'
                ':}@{@color{235}:}@{@color{234}:}@{@color{235};}@{@color{236}'
                ':}@{@color{235};}@{@color{235};}@{@color{235};}@{@color{234}'
                '=}@{@color{235};}@{@color{58}=}@{@color{58}=}@{@color{235}=}'
                '@{@color{58};}@{@color{235}=}@{@color{235}=}@{@color{58}=}@{'
                '@color{58}=}@{@color{58}=}@{@color{58}=}@{@color{58}+}@{@col'
                'or{58}|}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@color{5'
                '8}=}@{@color{58}|}@{@color{58}=}@{@color{58}+}@{@color{58}=}'
                '@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{235}|}@{'
                '@color{58}|}@{@color{236}=}@{@color{235}=}@{@color{234}=}@{@'
                'color{235};}@{@color{234};}@{@color{233}_}@{@color{233};}@{@'
                'color{234}=}@{@color{235}=}@{@color{234}=}@{@color{235}=}@{@'
                'color{234}_}@{@color{234}=}@{@color{58}=}@{@color{58}|}@{@co'
                'lor{58}=}@{@color{58}i}@{@color{58}+}@{@color{58}|}\n@{@color'
                '{234}:}@{@color{234}.}@{@color{234}:}@{@color{234}-}@{@color'
                '{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@color'
                '{234}:}@{@color{235}:}@{@color{234};}@{@color{235}:}@{@color'
                '{235}:}@{@color{235};}@{@color{234}:}@{@color{235}:}@{@color'
                '{235};}@{@color{235};}@{@color{58};}@{@color{236}:}@{@color{'
                '58}=}@{@color{236};}@{@color{236}=}@{@color{235};}@{@color{2'
                '35}=}@{@color{235};}@{@color{58}=}@{@color{58}=}@{@color{235'
                '};}@{@color{58};}@{@color{235}=}@{@color{235}=}@{@color{58}='
                '}@{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@'
                'color{58}+}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@colo'
                'r{58}+}@{@color{58}+}@{@color{58}+}@{@color{58}+}@{@color{58'
                '}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@'
                '{@color{58}=}@{@color{58}|}@{@color{58}|}@{@color{58}=}@{@co'
                'lor{58}|}@{@color{58}|}@{@color{58}|}@{@color{58}|}@{@color{'
                '58}|}@{@color{64}|}@{@color{58}|}@{@color{58}|}@{@color{58}|'
                '}@{@color{58}|}@{@color{58}|}@{@color{58}>}@{@color{58}=}@{@'
                'color{58}|}@{@color{58}+}@{@color{58}|}\n@{@color{233}.}@{@co'
                'lor{233}-}@{@color{234}.}@{@color{233}-}@{@color{234}-}@{@co'
                'lor{234}-}@{@color{235}-}@{@color{234}:}@{@color{234}-}@{@co'
                'lor{234}:}@{@color{234}:}@{@color{234}:}@{@color{234}:}@{@co'
                'lor{234}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}@{@co'
                'lor{235};}@{@color{235}:}@{@color{235};}@{@color{235}:}@{@co'
                'lor{235};}@{@color{235};}@{@color{235}:}@{@color{58}:}@{@col'
                'or{236}=}@{@color{58}:}@{@color{235};}@{@color{58}=}@{@color'
                '{235}=}@{@color{58}=}@{@color{235}=}@{@color{58}=}@{@color{5'
                '8};}@{@color{58}=}@{@color{58}=}@{@color{235}=}@{@color{58}='
                '}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}+}@{@'
                'color{58}+}@{@color{58}=}@{@color{58}=}@{@color{58}=}@{@colo'
                'r{58}=}@{@color{58}=}@{@color{58}+}@{@color{58}+}@{@color{64'
                '}+}@{@color{64}+}@{@color{58}+}@{@color{58}=}@{@color{58}|}@'
                '{@color{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@co'
                'lor{58}>}@{@color{58}+}@{@color{58}+}@{@color{58}|}@{@color{'
                '58}+}@{@color{58}+}@{@color{58}+}@{@color{58}|}@{@color{58}|'
                '}@{@color{58}=}@{@color{58}+}\n@{@color{233}.}@{@color{233}.}'
                '@{@color{233}-}@{@color{234}-}@{@color{233}.}@{@color{233}:}'
                '@{@color{233}.}@{@color{233}.}@{@color{234}-}@{@color{234}.}'
                '@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}'
                '@{@color{234}:}@{@color{234}:}@{@color{235}:}@{@color{234}:}'
                '@{@color{235}:}@{@color{235}:}@{@color{234}:}@{@color{234}:}'
                '@{@color{235}:}@{@color{234}:}@{@color{235};}@{@color{235};}'
                '@{@color{236}=}@{@color{234};}@{@color{236};}@{@color{236};}'
                '@{@color{235};}@{@color{234};}@{@color{235};}@{@color{236};}'
                '@{@color{236}=}@{@color{235};}@{@color{235};}@{@color{235}=}'
                '@{@color{236}=}@{@color{235}=}@{@color{58}=}@{@color{58}=}@{'
                '@color{58}=}@{@color{58}+}@{@color{235}=}@{@color{58}=}@{@co'
                'lor{235}=}@{@color{58}+}@{@color{58}=}@{@color{58}|}@{@color'
                '{58}=}@{@color{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}'
                '=}@{@color{58}=}@{@color{58}+}@{@color{58}=}@{@color{58}=}@{'
                '@color{58}|}@{@color{58}|}@{@color{58}=}@{@color{58}=}@{@col'
                'or{58}+}@{@color{58}|}@{@color{58}=}@{@color{58}=}@{@color{5'
                '8}+}@{@color{58}=}@{@color{58}|}\n'),
            'llvvvnn22SSSXXSnnnnnoo2SSo2nvvvnoono2o2S22XS1n1IIii||liiill'
            'IvIIii||=|+\nnoXSoXXXS2222ooonnnnoX#XXXXnvvnooo2SXSS2SSS2ovv'
            'vvvvvnvIIvvvvIllIIliii|\nmXZZ#ZZXXXSSXqmXXqXX2XXZXXX2owX222S'
            '2SS2XXX2SXXSSoonnvIvvvIvllliiiii|i|\n##m######ZZU##UU##ZUZZ#'
            'ZZZZZZZXXXXXXSSXXXXXXXXXXXSonnnvvIIllililiiiiii\nWmBmm###mmm'
            '#####Z###Z#Z#ZUZZ#ZZZZZXXXXXXZXXXS2ooooooo)nvvvIlllliliiiii'
            '\nmBmBmBmmmmmm#######U#U#Z#ZZ#ZZ#Z#ZUZ#ZZZZZqqXXXZS*^!-<;)oo'
            'oowoX22X2X2S\nBmmmmmmmm############mmmmmm##mmmmBmmmmmmmm###m'
            'm21\\.~/)4w#X#XomowwdXZZZ\n#######U####mmmmmmmmmmmmmmmBBBBBBB'
            'BBWmWBC^-+?4)+;>=_==m#mBmmB##m#####m\nmmmmmmmmmmmWmWmBmBmBBB'
            'BmWmBmBmBmBmmmmmm[:./:.:-:_=[/=(WmBmBmBmBmBmmmmm\n####mmmmmB'
            'BmmmmWmWBBmmBmmBBWmWmWmWmWmW$6-||_=_=;=:;:--($mWBWBWmWBWmWB'
            'W\n#Z####mmmmmWBWmmmmmmmmmWmWmmBBBmWmWBWE`<:=.:==-.:=,,+;.4m'
            'WmWmWmWmWmWmB\nZZZZZ#U########mWmBmWmWmWmmWmBBBBWmBmmf:`.`=;'
            '.:;`=.==_..)?4WmWmWmWmBBW\nXXXXZZ#X#XZZ#Z###########mmmmmmmm'
            'mmmmmcj"-_::a/|:,=a<um6a,`-4BmmBmBBmm\no2oXXXXXXXXZXZZZXZZZ#'
            'Z######U#Z########C>aa##aaaawwmmm###mw,)9mmmmmmBm\n"!"!"!"!"'
            '!!"?!!!!!!!!!!!!?!!!!???!?????Y?!???Y?????Y?YY?Y*ii, Y!Y?Y?'
            'Y?\n:-:.::::;:.=;::::::;:;;;=;===;======+|+=+=|=+====||===;;'
            '_;====_==|=i+|\n:.:-::::::;::;::;;;:=;=;=;==;;====+|=+=+=+++'
            '+|||||=||=|||||||||||>=|+|\n.-.----:-::::::::;:;:;;::=:;===='
            '=;=====+=++=====+++++=|=+|=>++|+++||=+\n..--.:..-.::::::::::'
            '::::;;=;;;;;;;=;;======+===+=|=+|===+==||==+|==+=|\n'
            )

    def test_fuzz(self, tries=1000, max_len=64):
        # basically we're trying to get it to throw
        CHARS = zcode.LEFT + zcode.RIGHT + '@abc '
        for i in range(tries):
            test_article = ''.join(
                random.choice(CHARS)
                for l in range(random.randint(0, max_len - 1)))
            print('trying', repr(test_article))
            zcode.strip_simple(test_article)

    def test_tree(self):
        self.assertEqual(
            zcode.tree(''),
            [''],
            )
        self.assertEqual(
            zcode.tree('foo'),
            ['', 'foo'],
            )
        self.assertEqual(
            zcode.tree('@{foo}'),
            ['', ['@', 'foo']],
            )
        self.assertEqual(
            zcode.tree('@bar{foo}'),
            ['', ['@bar', 'foo']],
            )
        self.assertEqual(
            zcode.tree('@bar{foo@bar}'),
            ['', ['@bar', 'foo@bar']],
            )
        self.assertEqual(
            zcode.tree('@bar{foo@@bar}'),
            ['', ['@bar', 'foo@bar']],
            )
        self.assertEqual(
            zcode.tree('@{foo@}bar}baz'),
            ['', ['@', 'foo@'], 'bar}baz'],
            )
        self.assertEqual(
            zcode.tree('foo@bar{baz@(bang})}'),
            ['', 'foo', ['@bar', 'baz', ['@', 'bang}']]],
            )
        self.assertEqual(
            zcode.tree('foo@bar{baz}'),
            ['', 'foo', ['@bar', 'baz']]
            )
        self.assertEqual(
            zcode.tree('@bloop'),
            ['', '@bloop'],
            )

    def test_tag(self):
        self.assertEqual(
            zcode.tag('', frozenset()),
            [],
            )
        self.assertEqual(
            zcode.tag('foo', frozenset()),
            [(set(), 'foo')],
            )
        self.assertEqual(
            zcode.tag('@color(green)foo', frozenset()),
            [({'fg:green'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('@i(foo)', frozenset()),
            [({'underline'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('@b(foo)', frozenset()),
            [({'bold'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('@b(@i(@roman(foo)))', frozenset()),
            [(set(), 'foo')],
            )
        self.assertEqual(
            zcode.tag('@font(fixed)foo', frozenset()),
            [(set(), 'foo')],
            )
        self.assertEqual(
            zcode.tag('@color(red)@{@color(green)foo}', frozenset()),
            [({'fg:green'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('@color(green)foo', frozenset({'fg:red'})),
            [({'fg:green'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('foo', frozenset({'bold'})),
            [({'bold'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('foo', frozenset({'fg:red'})),
            [({'fg:red'}, 'foo')],
            )
        self.assertEqual(
            zcode.tag('@i{foo\nbar}', frozenset()),
            [({'underline'}, 'foo'), (set(), '\n'), ({'underline'}, 'bar')],
            )
