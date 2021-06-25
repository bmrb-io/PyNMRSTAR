#!/usr/bin/env python3
import sys

from pynmrstar.unit_tests import start_tests

# Run unit tests if we are called directly
if __name__ == '__main__':
    print('Running tests...')
    print(f'Python version: {sys.version}')
    print(f'System platform: {sys.platform}')
    # Options, parse 'em
    start_tests()
