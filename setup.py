#!/usr/bin/python3
from setuptools import setup, find_packages

setup(
    name='snipe-im',
    description='curses client for persistent IM systems',
    url='https://github.com/kcr/snipe',
    license='BSD',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console :: Curses',
        'Framework :: AsyncIO',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3 :: Only',
        'Operating System :: POSIX',
        ],
    long_description="""
snipe is a text-oriented (currently curses-based) "instant" messaging
client intended for services with persistence, such as Zulip
(https://zulip.org/), also IRCCloud (https://www.irccloud.com) and
roost (https://github.com/roost-im).""",
    version='0.dev5',
    packages=find_packages(exclude=['tests']),
    python_requires='>=3.6',
    entry_points={'console_scripts': [
        'snipe = snipe.main:main',
        ]},
    test_suite='nose.collector',
    tests_require=['nose'],
    # keep this in sync with requirements.txt
    install_requires=[
        'docutils',
        'h11',
        'Markdown==2.6.7',
        'parsedatetime',
        'ply',
        'wsproto',
        ]
)
