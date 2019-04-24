import decimal

from .loop import Loop
from .saveframe import Saveframe
from .entry import Entry
from .schema import Schema
del loop
del entry
del saveframe
del schema

__version__: str = "3.0"
__all__ = ['Loop', 'Saveframe', 'Entry', 'Schema', '__version__']

# This makes sure that when decimals are printed a lower case "e" is used
decimal.getcontext().capitals = 0
