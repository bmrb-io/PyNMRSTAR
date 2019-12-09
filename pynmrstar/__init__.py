#!/usr/bin/env python3

"""This module provides Entry, Saveframe, Loop, and Schema objects.

It also provides some utility functions in pynmrstar.utils

Use python's built in help function for documentation."""

import decimal as _decimal
import logging
import warnings

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


def clean_value(value):
    """Deprecated. Please use utils.quote_value() instead."""
    warnings.warn('This function has moved to utils.quote_value().', DeprecationWarning)
    return utils.quote_value(value)


def iter_entries(metabolomics=False):
    """Deprecated. Please use utils.iter_entries() instead."""

    warnings.warn('This function has moved to utils.iter_entries().', DeprecationWarning)
    return utils.iter_entries(metabolomics=metabolomics)



__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', 'definitions', 'utils', '__version__', 'exceptions', 'cnmrstar']

