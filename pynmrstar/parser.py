import logging

import pynmrstar_parser

from pynmrstar import _internal
from pynmrstar import entry as entry_mod, schema as schema_mod
from pynmrstar.exceptions import ParsingError

logger = logging.getLogger('pynmrstar')

def parse(data: str,
          parse_into: 'entry_mod.Entry',
          source: str = "unknown",
          raise_parse_warnings: bool = False,
          convert_data_types: bool = False,
          schema: 'schema_mod.Schema' = None) -> None:
    try:
        with _internal.parsing(raise_parse_warnings):
            pynmrstar_parser.parse(data, parse_into, source, raise_parse_warnings, convert_data_types, schema)
    except ParsingError:
        # Already a parse error, and it knows which line it happened on. Letting
        # it through unchanged is the whole point - re-wrapping it with str()
        # would fold the line number back into the message and lose it.
        raise
    except ValueError as e:
        # Anything else raised while building the object model: still a bad
        # file, but without a line number to report.
        raise ParsingError(str(e))
