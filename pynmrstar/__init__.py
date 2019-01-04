try:
    from loop import Loop
    from saveframe import Saveframe
    from entry import Entry
    from schema import Schema
    from parser import Parser as _Parser
except ImportError:
    from .loop import Loop
    from .saveframe import Saveframe
    from .entry import Entry
    from .schema import Schema
    from .parser import Parser as _Parser
del loop
del entry
del saveframe
del schema
del parser
