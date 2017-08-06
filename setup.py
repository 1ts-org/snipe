#!/usr/bin/python3
from setuptools import setup, find_packages
from pip.req import parse_requirements
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
        ],
    long_description="""
snipe is a text-oriented (currently curses-based) "instant" messaging
client intended for services with persistence, such as Zulip
(https://zulip.org/), also IRCCloud (https://www.irccloud.com) and
roost (https://github.com/roost-im).""",
    version='0.dev0',
    packages=find_packages(exclude=['tests']),
    python_requires='>=3.3',
    entry_points={'console_scripts': [
        'snipe = snipe.main:main',
        ]},
    test_suite='nose.collector',
    tests_require=['nose'],
    install_requires=[
        str(ir.req)
        for ir in parse_requirements('requirements.txt', session='hack')]
)
