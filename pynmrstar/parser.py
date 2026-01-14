import logging

import pynmrstar_parser

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
        pynmrstar_parser.parse(data, parse_into, source, raise_parse_warnings, convert_data_types, schema)
    except ValueError as e:
        raise ParsingError(str(e))
