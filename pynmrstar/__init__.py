#!/usr/bin/env python3

"""This module provides :py:class:`pynmrstar.Entry`, :py:class:`pynmrstar.Saveframe`,
   :py:class:`pynmrstar.Loop`, and :py:class:`pynmrstar.Schema` objects.

It also provides some utility functions in :py:obj:`pynmrstar.utils`

Use python's built in help function for documentation."""

import decimal as _decimal
import logging

from pynmrstar import utils
from pynmrstar._internal import __version__, _get_cnmrstar
from pynmrstar.entry import Entry
from pynmrstar.loop import Loop
from pynmrstar.parser import Parser as _Parser
from pynmrstar.saveframe import Saveframe
from pynmrstar.schema import Schema

# Set up logging
logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')
logging.getLogger().setLevel(logging.INFO)

# This makes sure that when decimals are printed a lower case "e" is used
_decimal.getcontext().capitals = 0
# Make sure the cnmstar module is compiled
cnmrstar = _get_cnmrstar()
del loop
del entry
del saveframe
del schema
del parser

__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', 'definitions', 'utils', '__version__', 'exceptions', 'cnmrstar']

