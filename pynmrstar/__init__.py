try:
    from loop import Loop
    from saveframe import Saveframe
    from entry import Entry
    from schema import Schema
    from parser import Parser as _Parser
    from pynmrstar import interpret_file, get_schema
    from pynmrstar import *
except ImportError:
    from .loop import Loop
    from .saveframe import Saveframe
    from .entry import Entry
    from .schema import Schema
    from .parser import Parser as _Parser
    from .pynmrstar import *
del loop
del entry
del saveframe
del schema
del parser
