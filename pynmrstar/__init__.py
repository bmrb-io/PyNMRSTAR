#!/usr/bin/env python3

"""This module provides :py:class:`pynmrstar.Entry`, :py:class:`pynmrstar.Saveframe`,
   :py:class:`pynmrstar.Loop`, and :py:class:`pynmrstar.Schema` objects.

It also provides some utility functions in :py:obj:`pynmrstar.utils`

Use python's built in help function for documentation."""

import platform as _platform
import sys as _sys

if _platform.python_implementation() == "PyPy" and _sys.version_info < (3, 11):
    raise ImportError("When using PyPy, pynmrstar requires a version >= 3.11")

import decimal as _decimal
import logging

import pynmrstar.definitions as definitions
from pynmrstar import utils
from pynmrstar._internal import __version__
from pynmrstar.entry import Entry
from pynmrstar.loop import Loop
from pynmrstar.saveframe import Saveframe
from pynmrstar.schema import Schema

# Set up logging
logger = logging.getLogger('pynmrstar')

# This makes sure that when decimals are printed a lower case "e" is used
_decimal.getcontext().capitals = 0

del loop
del entry
del saveframe
del schema

__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', 'definitions', 'utils', '__version__', 'exceptions']
