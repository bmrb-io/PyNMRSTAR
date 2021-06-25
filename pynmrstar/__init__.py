#!/usr/bin/env python3

"""This module provides :py:class:`pynmrstar.Entry`, :py:class:`pynmrstar.Saveframe`,
   :py:class:`pynmrstar.Loop`, and :py:class:`pynmrstar.Schema` objects.

It also provides some utility functions in :py:obj:`pynmrstar.utils`

Use python's built in help function for documentation."""

import decimal as _decimal
import logging

try:
    import cnmrstar
except ImportError:
    try:
        import pynmrstar.cnmrstar as cnmrstar
    except ImportError:
        raise ImportError("Couldn't import cnmrstar module which should be available.")

from pynmrstar import utils
from pynmrstar._internal import __version__, min_cnmrstar_version
from pynmrstar.entry import Entry
from pynmrstar.loop import Loop
from pynmrstar.parser import Parser as _Parser
from pynmrstar.saveframe import Saveframe
from pynmrstar.schema import Schema

if "version" not in dir(cnmrstar):
    raise ImportError(f"Could not determine the version of cnmrstar installed, and version {min_cnmrstar_version} or "
                      "greater is required.")
if cnmrstar.version() < min_cnmrstar_version:
    raise ImportError("The version of the cnmrstar module installed does not meet the requirements. As this should be "
                      f"handled automatically, there may be an issue with your installation. Version installed: "
                      f"{cnmrstar.version()}. Version required: {min_cnmrstar_version}")

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
