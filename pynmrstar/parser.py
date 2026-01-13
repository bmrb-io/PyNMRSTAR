import logging

import pynmrstar_parser

from pynmrstar import entry as entry_mod, schema as schema_mod
from pynmrstar.exceptions import ParsingError

logger = logging.getLogger('pynmrstar')


class Parser(object):
    """Parses an entry. You should not ever use this class directly."""

    def __init__(self, entry_to_parse_into: 'entry_mod.Entry' = None) -> None:

        # Just make an entry to parse into if called with no entry passed
        if entry_to_parse_into is None:
            entry_to_parse_into = entry_mod.Entry.from_scratch("")

        self.ent: entry_mod.Entry = entry_to_parse_into
        self.full_data: str = ""
        self.token: str = ""
        self.source: str = "unknown"
        self.delimiter: str = " "
        self.line_number: int = 0

    def parse(self,
              data: str,
              source: str = "unknown",
              raise_parse_warnings: bool = False,
              convert_data_types: bool = False,
              schema: 'schema_mod.Schema' = None) -> 'entry_mod.Entry':
        try:
            pynmrstar_parser.parse(data, self.ent, source, raise_parse_warnings, convert_data_types, schema)
        except ValueError as e:
            raise ParsingError(str(e))
        return self.ent
