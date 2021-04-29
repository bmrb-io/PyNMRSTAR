#!/usr/bin/env python3

"""This module provides :py:class:`pynmrstar.Entry`, :py:class:`pynmrstar.Saveframe`,
   :py:class:`pynmrstar.Loop`, and :py:class:`pynmrstar.Schema` objects.

It also provides some utility functions in :py:obj:`pynmrstar.utils`

Use python's built in help function for documentation."""

import decimal as _decimal
import logging

import cnmrstar

from pynmrstar import utils
from pynmrstar._internal import __version__
from pynmrstar.entry import Entry
from pynmrstar.loop import Loop
from pynmrstar.parser import Parser as _Parser
from pynmrstar.saveframe import Saveframe
from pynmrstar.schema import Schema

if "version" not in dir(cnmrstar) or cnmrstar.version() < "3.2.0":
    raise ImportError("The version of the cnmrstar module installed does "
                      "not meet the requirements. As this should be handled "
                      "automatically, there may be an issue with your installation.")


# Set up logging
logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')
logging.getLogger().setLevel(logging.INFO)

# This makes sure that when decimals are printed a lower case "e" is used
_decimal.getcontext().capitals = 0

del loop
del entry
del saveframe
del schema
del parser

__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', 'definitions', 'utils', '__version__', 'exceptions', 'cnmrstar']
