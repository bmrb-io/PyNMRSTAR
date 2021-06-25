import logging
import re
from typing import Optional

from pynmrstar import definitions, cnmrstar, entry as entry_mod, loop as loop_mod, saveframe as saveframe_mod
from pynmrstar.exceptions import ParsingError


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

    def get_token(self) -> str:
        """ Returns the next token in the parsing process."""

        try:
            self.token, self.line_number, self.delimiter = cnmrstar.get_token_full()
        except ValueError as err:
            raise ParsingError(str(err))

        return self.token

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

    def parse(self, data: str, source: str = "unknown", raise_parse_warnings: bool = False,
              convert_data_types: bool = False) -> 'entry_mod.Entry':
        """ Parses the string provided as data as an NMR-STAR entry
        and returns the parsed entry. Raises ParsingError on exceptions.

        Set raise_parse_warnings to raise an exception if the file has
        something technically incorrect, but still parsable.

        Following is a list of the types of errors that would trigger
        raise_parse_warnings:

        * A loop with no data was found.
        * A loop with no tags or values was found.
        * A tag with an improper multi-line value was found.
        Multi-line values should look like this:
        \n;\nThe multi-line\nvalue here.\n;\n
        but the tag looked like this:
        \n; The multi-line\nvalue here.\n;\n"""

        self.load_data(data)
        self.get_token()

        # Make sure this is actually a STAR file
        if not self.token.lower().startswith("data_"):
            raise ParsingError("Invalid file. NMR-STAR files must start with 'data_' followed by the data name. "
                               f"Did you accidentally select the wrong file? Your file started with '{self.token}'.",
                               self.line_number)

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ParsingError("'data_' must be followed by data name. Simply 'data_' is not allowed.",
                               self.line_number)

        if self.delimiter != " ":
            raise ParsingError("The data_ keyword may not be quoted or semicolon-delimited.",
                               self.line_number)

        # Set the entry_id
        self.ent._entry_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.get_token() is not None:

            if not self.token.lower().startswith("save_"):
                raise ParsingError(f"Only 'save_NAME' is valid in the body of a NMR-STAR file. Found '{self.token}'.",
                                   self.line_number)

            if len(self.token) < 6:
                raise ParsingError("'save_' must be followed by saveframe name. You have a 'save_' tag which is "
                                   "illegal without a specified saveframe name.", self.line_number)

            if self.delimiter != " ":
                raise ParsingError("The save_ keyword may not be quoted or semicolon-delimited.",
                                   self.line_number)

            # Add the saveframe
            cur_frame: Optional[saveframe_mod.Saveframe] = saveframe_mod.Saveframe.from_scratch(self.token[5:],
                                                                                                source=source)
            self.ent.add_saveframe(cur_frame)

            # We are in a saveframe
            while self.get_token() is not None:

                if self.token.lower() == "loop_":
                    if self.delimiter != " ":
                        raise ParsingError("The loop_ keyword may not be quoted or semicolon-delimited.",
                                           self.line_number)

                    cur_loop: Optional[loop_mod.Loop] = loop_mod.Loop.from_scratch(source=source)

                    # We are in a loop
                    cur_data = []
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() is not None:

                        # Add a tag if it isn't quoted - if quoted, it should be treated as a data value
                        if self.token.startswith("_") and self.delimiter == " ":
                            try:
                                cur_loop.add_tag(self.token)
                            except ValueError as err:
                                raise ParsingError(str(err), self.line_number)

                        # On to data
                        else:

                            # Now that we have the tags we can add the loop
                            #  to the current saveframe
                            try:
                                cur_frame.add_loop(cur_loop)
                            except ValueError as err:
                                raise ParsingError(str(err), self.line_number)

                            # We are in the data block of a loop
                            while self.token is not None:
                                if self.token.lower() == "stop_":
                                    if self.delimiter != " ":
                                        raise ParsingError(
                                            "The stop_ keyword may not be quoted or semicolon-delimited.",
                                            self.line_number)
                                    if len(cur_loop.tags) == 0:
                                        if raise_parse_warnings:
                                            raise ParsingError("Loop with no tags.", self.line_number)
                                        else:
                                            logging.warning('Loop with no tags in parsed file on line: %s',
                                                            self.line_number)
                                        cur_loop = None
                                    if not seen_data:
                                        if raise_parse_warnings:
                                            raise ParsingError("Loop with no data.", self.line_number)
                                        else:
                                            logging.warning("Loop with no data on line: %s", self.line_number)

                                    if len(cur_data) > 0:
                                        if len(cur_data) % len(cur_loop.tags) != 0:
                                            raise ParsingError(f"The loop being parsed, '{cur_loop.category}' does "
                                                               f"not have the expected number of data elements. This "
                                                               f"indicates that either one or more tag values are "
                                                               f"either missing from or duplicated in this loop.",
                                                               self.line_number)
                                        try:
                                            cur_loop.add_data(cur_data, rearrange=True,
                                                              convert_data_types=convert_data_types)
                                        # If there is an issue with the loops during parsing, raise a parse error
                                        #  rather than the ValueError that would be raised if they made the mistake
                                        #   directly
                                        except ValueError as e:
                                            raise ParsingError(str(e))
                                    cur_data = []

                                    cur_loop = None
                                    in_loop = False
                                    break
                                elif self.token.startswith("_") and self.delimiter == " ":
                                    raise ParsingError("Cannot have more loop tags after loop data. Or perhaps this "
                                                       f"was a data value which was not quoted (but must be, "
                                                       f"if it starts with '_')? Value: '{self.token}'.",
                                                       self.line_number)
                                else:
                                    if len(cur_loop.tags) == 0:
                                        raise ParsingError("Data value found in loop before any loop tags were "
                                                           "defined. Value: '{self.token}'",
                                                           self.line_number)

                                    if self.token in definitions.RESERVED_KEYWORDS and self.delimiter == " ":
                                        error = "Cannot use keywords as data values unless quoted or semi-colon " \
                                                "delimited. Perhaps this is a loop that wasn't properly terminated " \
                                                "with a 'stop_' keyword before the saveframe ended or another loop " \
                                                f"began? Value found where 'stop_' or another data value expected: " \
                                                f"'{self.token}'."
                                        if len(cur_data) > 0:
                                            error += f" Last loop data element parsed: '{cur_data[-1]}'."
                                        raise ParsingError(error, self.line_number)
                                    cur_data.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.get_token()

                    if not self.token:
                        raise ParsingError(f"Loop improperly terminated at end of file. Loops must end with the "
                                           f"'stop_' token, but the file ended without the stop token.",
                                           self.line_number)
                    if self.token.lower() != 'stop_':
                        raise ParsingError(f"Loop improperly terminated at end of file. Loops must end with the "
                                           f"'stop_' token, but the token '{self.token}' was found instead.",
                                           self.line_number)

                # Close saveframe
                elif self.token.lower() == "save_":
                    if self.delimiter not in " ;":
                        raise ParsingError("The save_ keyword may not be quoted or semicolon-delimited.",
                                           self.line_number)

                    if cur_frame.tag_prefix is None:
                        raise ParsingError("The tag prefix was never set! Either the saveframe had no tags, you "
                                           "tried to read a version 2.1 file, or there is something else wrong with "
                                           f"your file. Saveframe error occurred within: '{cur_frame.name}'",
                                           line_number=self.line_number)
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    if cur_frame.name == 'internaluseyoushouldntseethis_frame':
                        raise ParsingError(f"Invalid token found in loop contents. Expecting 'loop_' "
                                           f"but found: '{self.token}'", line_number=self.line_number)
                    else:
                        raise ParsingError(f"Invalid token found in saveframe '{cur_frame.name}'. Expecting a tag, "
                                           f"loop, or 'save_' token but found: '{self.token}'",
                                           line_number=self.line_number)

                # Add a tag
                else:
                    if self.delimiter != " ":
                        raise ParsingError(f"Saveframe tags may not be quoted or semicolon-delimited. Quoted tag: '"
                                           f"{self.token}'.",
                                           self.line_number)
                    cur_tag: Optional[str] = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.get_token()
                    if self.delimiter == " ":
                        if self.token in definitions.RESERVED_KEYWORDS:
                            raise ParsingError("Cannot use keywords as data values unless quoted or semi-colon "
                                               f"delimited. Illegal value: '{self.token}'", self.line_number)
                        if self.token.startswith("_"):
                            raise ParsingError(
                                "Cannot have a tag value start with an underscore unless the entire value "
                                "is quoted. You may be missing a data value on the previous line. "
                                f"Illegal value: '{self.token}'", self.line_number)
                    try:
                        cur_frame.add_tag(cur_tag, self.token, convert_data_types=convert_data_types)
                    except ValueError as err:
                        raise ParsingError(str(err), line_number=self.line_number)

            if not self.token or self.token.lower() != "save_":
                raise ParsingError("Saveframe improperly terminated at end of file. Saveframes must be terminated "
                                   "with the 'save_' token.",
                                   self.line_number)

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        # Reset the parser
        cnmrstar.reset()

        return self.ent
