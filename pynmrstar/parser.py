import logging
import re
from typing import Optional, Any

from pynmrstar import definitions, entry as entry_mod, loop as loop_mod, saveframe as saveframe_mod
from pynmrstar._internal import _get_cnmrstar
from pynmrstar.exceptions import ParsingError

cnmrstar = _get_cnmrstar()


class Parser(object):
    """Parses an entry. You should not ever use this class directly."""

    def __init__(self, entry_to_parse_into: 'entry_mod.Entry' = None) -> None:

        # Just make an entry to parse into if called with no entry passed
        if entry_to_parse_into is None:
            entry_to_parse_into = entry_mod.Entry.from_scratch("")

        self.ent: entry_mod.Entry = entry_to_parse_into
        self.to_process: str = ""
        self.full_data: str = ""
        self.index: int = 0
        self.token: str = ""
        self.source: str = "unknown"
        self.delimiter: str = " "
        self.line_number: int = 0

    def get_line_number(self) -> int:
        """ Returns the current line number that is in the process of
        being parsed."""

        if cnmrstar is not None:
            return self.line_number
        else:
            return self.full_data[0:self.index].count("\n") + 1

    def get_token(self, raise_parse_warnings: bool = False) -> str:
        """ Returns the next token in the parsing process."""

        if cnmrstar is not None:
            try:
                self.token, self.line_number, self.delimiter = cnmrstar.get_token_full()
            except ValueError as err:
                raise ParsingError(str(err))
        else:
            self.real_get_token(raise_parse_warnings)
            self.line_number = 0

            if self.delimiter == ";":
                try:
                    # Un-indent value which contain STAR multi-line values
                    # Only do this check if we are comma-delineated
                    if self.token.startswith("\n   "):
                        # Only remove the whitespaces if all lines have them
                        trim = True
                        for pos in range(1, len(self.token) - 4):
                            if self.token[pos] == "\n":
                                if self.token[pos + 1:pos + 4] != "   ":
                                    trim = False

                        if trim and "\n   ;" in self.token:
                            self.token = self.token[:-1].replace("\n   ", "\n")

                except AttributeError:
                    pass

        if self.token:
            logging.debug("'%s': '%s'" % (self.delimiter, self.token))
        else:
            logging.debug("No more tokens.")

        # Return the token
        return self.token

    @staticmethod
    def index_handle(haystack: Any, needle: Any, start_pos: Optional[int] = None) -> Optional[int]:
        """ Finds the index while catching ValueError and returning
        None instead."""

        try:
            return haystack.index(needle, start_pos)
        except ValueError:
            return None

    @staticmethod
    def next_whitespace(data) -> int:
        """ Returns the position of the next whitespace character in the
        provided string. If no whitespace it returns the length of the
        string."""

        for pos, char in enumerate(data):
            if char in definitions.WHITESPACE:
                return pos
        return len(data)

    def load_data(self, data: str) -> None:
        """ Loads data in preparation of parsing and cleans up newlines
        and massages the data to make parsing work properly when multi-line
        values aren't as expected. Useful for manually getting tokens from
        the parser."""

        # Fix DOS line endings
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        # Change '\n; data ' started multi-lines to '\n;\ndata'
        data = re.sub(r'\n;([^\n]+?)\n', r'\n;\n\1\n', data)

        if cnmrstar is not None:
            cnmrstar.load_string(data)
        else:
            self.full_data = data + "\n"

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

        # Prepare the data for parsing
        self.load_data(data)

        # Create the NMRSTAR object
        cur_data = []

        # Get the first token
        self.get_token()

        # Make sure this is actually a STAR file
        if not self.token.startswith("data_"):
            raise ParsingError("Invalid file. NMR-STAR files must start with 'data_'. Did you accidentally select the "
                               "wrong file?", self.get_line_number())

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ParsingError("'data_' must be followed by data name. Simply 'data_' is not allowed.",
                               self.get_line_number())

        if self.delimiter != " ":
            raise ParsingError("The data_ keyword may not be quoted or semicolon-delineated.")

        # Set the entry_id
        self.ent._entry_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.get_token() is not None:

            if not self.token.startswith("save_"):
                raise ParsingError("Only 'save_NAME' is valid in the body of a NMR-STAR file. Found '%s'." % self.token,
                                   self.get_line_number())

            if len(self.token) < 6:
                raise ParsingError("'save_' must be followed by saveframe name. You have a 'save_' tag which is "
                                   "illegal without a specified saveframe name.", self.get_line_number())

            if self.delimiter != " ":
                raise ParsingError("The save_ keyword may not be quoted or semicolon-delineated.",
                                   self.get_line_number())

            # Add the saveframe
            cur_frame: Optional[saveframe_mod.Saveframe] = saveframe_mod.Saveframe.from_scratch(self.token[5:],
                                                                                                source=source)
            self.ent.add_saveframe(cur_frame)

            # We are in a saveframe
            while self.get_token() is not None:

                if self.token == "loop_":
                    if self.delimiter != " ":
                        raise ParsingError("The loop_ keyword may not be quoted or semicolon-delineated.",
                                           self.get_line_number())

                    cur_loop: Optional[loop_mod.Loop] = loop_mod.Loop.from_scratch(source=source)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() is not None:

                        # Add a tag
                        if self.token.startswith("_"):
                            if self.delimiter != " ":
                                raise ParsingError("Loop tags may not be quoted or semicolon-delineated.",
                                                   self.get_line_number())
                            if seen_data:
                                raise ParsingError("Cannot have more loop tags after loop data.")
                            cur_loop.add_tag(self.token)

                        # On to data
                        else:

                            # Now that we have the tags we can add the loop
                            #  to the current saveframe
                            cur_frame.add_loop(cur_loop)

                            # We are in the data block of a loop
                            while self.token is not None:
                                if self.token == "stop_":
                                    if self.delimiter != " ":
                                        raise ParsingError(
                                            "The stop_ keyword may not be quoted or semicolon-delineated.",
                                            self.get_line_number())
                                    if len(cur_loop.tags) == 0:
                                        if raise_parse_warnings:
                                            raise ParsingError("Loop with no tags.", self.get_line_number())
                                        else:
                                            logging.warning('Loop with not tags in parsed file on line: %s' %
                                                            self.get_line_number())
                                        cur_loop = None
                                    if not seen_data:
                                        if raise_parse_warnings:
                                            raise ParsingError("Loop with no data.", self.get_line_number())
                                        else:
                                            logging.warning("Loop with no data on line: %s" % self.get_line_number())

                                    if len(cur_data) > 0:
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
                                else:
                                    if len(cur_loop.tags) == 0:
                                        raise ParsingError("Data found in loop before loop tags.",
                                                           self.get_line_number())

                                    if (self.token in definitions.RESERVED_KEYWORDS and
                                            self.delimiter == " "):
                                        raise ParsingError("Cannot use keywords as data values unless quoted or "
                                                           "semi-colon delineated. Perhaps this is a loop that wasn't "
                                                           "properly terminated? Illegal value: " + self.token,
                                                           self.get_line_number())
                                    cur_data.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.get_token()

                    if self.token != "stop_":
                        raise ParsingError("Loop improperly terminated at end of file.", self.get_line_number())

                # Close saveframe
                elif self.token == "save_":
                    if self.delimiter not in " ;":
                        raise ParsingError("The save_ keyword may not be quoted or semicolon-delineated.",
                                           self.get_line_number())

                    if cur_frame.tag_prefix is None:
                        raise ParsingError("The tag prefix was never set! Either the saveframe had no tags, you "
                                           "tried to read a version 2.1 file, or there is something else wrong with "
                                           "your file. Saveframe error occurred within: '%s'" % cur_frame.name)
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    raise ParsingError("Invalid token found in saveframe '%s': '%s'" % (cur_frame.name, self.token),
                                       self.get_line_number())

                # Add a tag
                else:
                    if self.delimiter != " ":
                        raise ParsingError("Saveframe tags may not be quoted or semicolon-delineated.",
                                           self.get_line_number())
                    cur_tag: Optional[str] = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.get_token()
                    if self.delimiter == " ":
                        if self.token in definitions.RESERVED_KEYWORDS:
                            raise ParsingError("Cannot use keywords as data values unless quoted or semi-colon "
                                               "delineated. Illegal value: " +
                                               self.token, self.get_line_number())
                        if self.token.startswith("_"):
                            raise ParsingError(
                                "Cannot have a tag value start with an underscore unless the entire value "
                                "is quoted. You may be missing a data value on the previous line. "
                                "Illegal value: " + self.token, self.get_line_number())
                    cur_frame.add_tag(cur_tag, self.token, self.get_line_number(),
                                      convert_data_types=convert_data_types)

            if self.token != "save_":
                raise ParsingError("Saveframe improperly terminated at end of file.", self.get_line_number())

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        # Reset the parser
        if cnmrstar is not None:
            cnmrstar.reset()

        return self.ent

    def real_get_token(self, raise_parse_warnings: bool = False) -> Optional[str]:
        """ Actually processes the input data to find a token. get_token
        is just a wrapper around this with some exception handling."""

        # Reset the delimiter
        self.delimiter = " "

        # Nothing left
        if self.token is None:
            return

        # We're at the end if the index is the length
        if self.index == len(self.full_data):
            self.token = None
            return

        # Get just a single line of the file
        raw_tmp = ""
        tmp = ""
        while len(tmp) == 0:
            self.index += len(raw_tmp)

            try:
                newline_index = self.full_data.index("\n", self.index + 1)
                raw_tmp = self.full_data[self.index:newline_index]
            except ValueError:
                # End of file
                self.token = self.full_data[self.index:].lstrip(definitions.WHITESPACE)
                if self.token == "":
                    self.token = None
                self.index = len(self.full_data)
                return

            newline_index = self.full_data.index("\n", self.index + 1)
            raw_tmp = self.full_data[self.index:newline_index + 1]
            tmp = raw_tmp.lstrip(definitions.WHITESPACE)

        # If it is a multi-line comment, recalculate our viewing window
        if tmp[0:2] == ";\n":
            try:
                q_start = self.full_data.index(";\n", self.index)
                q_end = self.full_data.index("\n;", q_start) + 3
            except ValueError:
                q_end = len(self.full_data)

            raw_tmp = self.full_data[self.index:q_end]
            tmp = raw_tmp.lstrip()

        self.index += len(raw_tmp) - len(tmp)

        # Skip comments
        if tmp.startswith("#"):
            self.index += len(tmp)
            return self.get_token()

        # Handle multi-line values
        if tmp.startswith(";\n"):
            tmp = tmp[2:]

            # Search for end of multi-line value
            if "\n;" in tmp:
                until = tmp.index("\n;")
                valid = self.index_handle(tmp, "\n;\n")

                # The line is terminated properly
                if valid == until:
                    self.token = tmp[0:until + 1]
                    self.index += until + 4
                    self.delimiter = ";"
                    return

                # The line was terminated improperly
                else:
                    if self.next_whitespace(tmp[until + 2:]) == 0:
                        if raise_parse_warnings:
                            raise ParsingError("Warning: Technically invalid line found in file. Multi-line values "
                                               "should terminate with \\n;\\n but in this file only \\n; with "
                                               "non-return whitespace following was found.", self.get_line_number())
                        else:
                            logging.warning("Technically invalid line found in file. Multi-line values "
                                            "should terminate with \\n;\\n but in this file only \\n; with non-return "
                                            "whitespace following was found. Line: %s" % self.get_line_number())
                        self.token = tmp[0:until + 1]
                        self.index += until + 4
                        self.delimiter = ";"
                        return
                    else:
                        raise ParsingError('Invalid file. A multi-line value ended with a "\\n;" and then a '
                                           'non-whitespace value. Multi-line values should end with "\\n;\\n".',
                                           self.get_line_number())
            else:
                raise ParsingError("Invalid file. Multi-line comment never ends. Multi-line comments must terminate "
                                   "with a line that consists ONLY of a ';' without characters before or after. (Other "
                                   "than the newline.)", self.get_line_number())

        # Handle values quoted with '
        if tmp.startswith("'"):
            until = self.index_handle(tmp, "'", 1)

            if until is None:
                raise ParsingError("Invalid file. Single quoted value was never terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed by whitespace
            try:
                while tmp[until + 1:until + 2] not in definitions.WHITESPACE:
                    until = self.index_handle(tmp, "'", until + 1)
            except TypeError:
                raise ParsingError("Invalid file. Single quoted value was never terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
            self.delimiter = "'"
            return

        # Handle values quoted with "
        if tmp.startswith('"'):
            until = self.index_handle(tmp, '"', 1)

            if until is None:
                raise ParsingError("Invalid file. Double quoted value was never terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed by whitespace
            try:
                while tmp[until + 1:until + 2] not in definitions.WHITESPACE:
                    until = self.index_handle(tmp, '"', until + 1)
            except TypeError:
                raise ParsingError("Invalid file. Double quoted value was never terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
            self.delimiter = '"'
            return

        # Figure out where this token ends
        white = self.next_whitespace(tmp)
        if white == len(tmp):
            self.token = tmp
            self.index += len(self.token) + 1
            if self.token[0] == "$" and len(self.token) > 1:
                self.delimiter = '$'
            return

        # The token isn't anything special, just return it
        self.index += white
        self.token = tmp[0:white]
        if self.token[0] == "$" and len(self.token) > 1:
            self.delimiter = '$'
        return
