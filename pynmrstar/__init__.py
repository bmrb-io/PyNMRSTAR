#!/usr/bin/env python3

"""This module provides Entry, Saveframe, and Loop objects. Use python's
built in help function for documentation."""

import decimal

from . import definitions
from . import utils
from ._internal import __version__, _ensure_cnmrstar
from .entry import Entry
from .loop import Loop
from .parser import Parser as _Parser
from .saveframe import Saveframe
from .schema import Schema

# This makes sure that when decimals are printed a lower case "e" is used
decimal.getcontext().capitals = 0
# Make sure the cnmstar module is compiled
_ensure_cnmrstar()
del loop
del entry
del saveframe
del schema
del parser
del decimal

__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', 'definitions', 'utils', '__version__']
