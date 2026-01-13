import logging
import re

import pynmrstar_parser

from pynmrstar import cnmrstar, entry as entry_mod, schema as schema_mod

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


    @staticmethod
    def load_data(data: str) -> None:
        """ Loads data in preparation of parsing and cleans up newlines
        and massages the data to make parsing work properly when multi-line
        values aren't as expected. Useful for manually getting tokens from
        the parser."""

        # Fix DOS line endings
        data = data.replace("\r\n", "\n").replace("\r", "\n")
        # Change '\n; data ' started multi-lines to '\n;\ndata'
        data = re.sub(r'\n;([^\n]+?)\n', r'\n;\n\1\n', data)

        cnmrstar.load_string(data)


    def parse(self,
              data: str,
              source: str = "unknown",
              raise_parse_warnings: bool = False,
              convert_data_types: bool = False,
              schema: 'schema_mod.Schema' = None) -> 'entry_mod.Entry':
        pynmrstar_parser.parse(data, self.ent, source, raise_parse_warnings, convert_data_types, schema)
        return self.ent
