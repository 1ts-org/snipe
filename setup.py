#!/usr/bin/python3
from setuptools import setup, find_packages
from pip.req import parse_requirements
setup(
    name='snipe',
    version='0',
    packages=find_packages(),
    entry_points={'console_scripts': [
        'snipe = snipe.main:main',
        ]},
    test_suite='nose.collector',
    tests_require=['nose'],
    install_requires=[
        str(ir.req)
        for ir in parse_requirements('requirements.txt', session='hack')]
)
