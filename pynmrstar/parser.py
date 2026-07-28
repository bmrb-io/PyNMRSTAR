import logging

import pynmrstar_parser

from pynmrstar import _internal
from pynmrstar import entry as entry_mod, schema as schema_mod
from pynmrstar.exceptions import ParsingError

logger = logging.getLogger('pynmrstar')


def _locate_tag(data: str, tag: str, saveframe: str, occurrence: int) -> int:
    """The 1-based line of the ``occurrence``-th use of ``tag`` inside
    ``saveframe``, or 0 if it cannot be found.

    Only ever called after a parse has already failed, so a linear scan costs
    nothing. Semicolon-delimited blocks are skipped, so a tag name appearing
    inside a text value is never mistaken for the tag itself.
    """

    wanted = tag.lower()
    current = None
    in_semicolon_block = False
    seen = 0

    for number, line in enumerate(data.splitlines(), start=1):
        if line.startswith(';'):
            in_semicolon_block = not in_semicolon_block
            continue
        if in_semicolon_block:
            continue

        stripped = line.strip()
        if stripped.startswith('save_'):
            current = stripped[len('save_'):] or None
            continue
        if current != saveframe or not stripped.startswith('_'):
            continue

        if stripped.split(None, 1)[0].lower() == wanted:
            seen += 1
            if seen == occurrence:
                return number

    return 0


def parse(data: str,
          parse_into: 'entry_mod.Entry',
          source: str = "unknown",
          raise_parse_warnings: bool = False,
          convert_data_types: bool = False,
          schema: 'schema_mod.Schema' = None) -> None:
    try:
        with _internal.parsing(raise_parse_warnings):
            pynmrstar_parser.parse(data, parse_into, source, raise_parse_warnings, convert_data_types, schema)
    except ValueError as e:
        # Two structural problems -- a duplicated tag, and a tag whose category
        # does not match its saveframe -- are detected while building the object
        # model rather than while tokenizing, so the tokenizer's line number is
        # not attached to them. Recover it from the source text, which is right
        # here. A caller told only "this file will not parse", with no
        # indication of where, has nothing to act on.
        structural = _internal.take_structural_error()
        line_number = None
        if structural:
            # The offending use is the second one for a duplicated tag, and the
            # first for a tag that does not belong to its saveframe at all.
            occurrence = 2 if structural['kind'] == 'duplicate_tag' else 1
            line_number = _locate_tag(data, structural['tag'],
                                      structural['saveframe'], occurrence) or None
        raise ParsingError(str(e), line_number=line_number)
