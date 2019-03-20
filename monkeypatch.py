#!/usr/bin/python


def patch_parser(pynmstar_instance):

    def parse(self, data, source="unknown"):
        """ Parses the string provided as data as an NMR-STAR entry
        and returns the parsed entry. Raises ValueError on exceptions."""

        # Prepare the data for parsing
        self.load_data(data)

        # Create the NMRSTAR object
        curframe = None
        curloop = None
        curtag = None
        curdata = []

        # Get the first token
        self.get_token()

        # Make sure this is actually a STAR file
        if not self.token.startswith("data_"):
            raise ValueError("Invalid file. NMR-STAR files must start with"
                             " 'data_'. Did you accidentally select the wrong"
                             " file?", self.get_line_number())

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ValueError("'data_' must be followed by data name. Simply "
                             "'data_' is not allowed.", self.get_line_number())

        if self.delimiter != " ":
            raise ValueError("The data_ keyword may not be quoted or "
                             "semicolon-delineated.")

        # Set the entry_id
        self.ent.entry_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.get_token() is not None:

            if not self.token.startswith("save_"):
                raise ValueError("Only 'save_NAME' is valid in the body of a "
                                 "NMR-STAR file. Found '" + self.token + "'.",
                                 self.get_line_number())

            if len(self.token) < 6:
                raise ValueError("'save_' must be followed by saveframe name. "
                                 "You have a 'save_' tag which is illegal "
                                 "without a specified saveframe name.",
                                 self.get_line_number())

            if self.delimiter != " ":
                raise ValueError("The save_ keyword may not be quoted or "
                                 "semicolon-delineated.",
                                 self.get_line_number())

            # Add the saveframe
            curframe = pynmstar_instance.Saveframe.from_scratch(self.token[5:], source=source)
            self.ent.add_saveframe(curframe)

            # We are in a saveframe
            while self.get_token() is not None:

                if self.token == "loop_":
                    if self.delimiter != " ":
                        raise ValueError("The loop_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())

                    curloop = pynmstar_instance.Loop.from_scratch(source=source)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() is not None:

                        # Add a tag
                        if self.token.startswith("_"):
                            if self.delimiter != " ":
                                raise ValueError("Loop tags may not be quoted "
                                                 "or semicolon-delineated.",
                                                 self.get_line_number())
                            if seen_data:
                                raise ValueError("Cannot have more loop tags "
                                                 "after loop data.")
                            curloop.add_tag(self.token)

                        # On to data
                        else:

                            # Now that we have the tags we can add the loop
                            #  to the current saveframe
                            try:
                                curframe.add_loop(curloop)
                            except ValueError:
                                existing_loop = curframe[curloop.category]
                                if existing_loop.tags != curloop.tags:
                                    raise ValueError('Cannot parse file. Two loops of the same category with different'
                                                     'tags are present.')
                                else:
                                    existing_loop.renumber_rows('ID', start_value=999, maintain_ordering=True)
                                    curloop = existing_loop

                            # We are in the data block of a loop
                            while self.token is not None:
                                if self.token == "stop_":
                                    if self.delimiter != " ":
                                        raise ValueError("The stop_ keyword may"
                                                         " not be quoted or "
                                                         "semicolon-delineated.",
                                                         self.get_line_number())
                                    if len(curloop.tags) == 0:
                                        if (pynmstar_instance.RAISE_PARSE_WARNINGS and
                                                "tag-only-loop" not in pynmstar_instance.WARNINGS_TO_IGNORE):
                                            raise ValueError("Loop with no "
                                                             "tags.", self.get_line_number())
                                        curloop = None
                                    if (not seen_data and
                                            pynmstar_instance.RAISE_PARSE_WARNINGS and
                                            "empty-loop" not in pynmstar_instance.WARNINGS_TO_IGNORE):
                                        raise ValueError("Loop with no data.",
                                                         self.get_line_number())
                                    else:
                                        if len(curdata) > 0:
                                            curloop.add_data(curdata,
                                                             rearrange=True)
                                        curloop = None
                                        curdata = []

                                    curloop = None
                                    in_loop = False
                                    break
                                else:
                                    if len(curloop.tags) == 0:
                                        raise ValueError("Data found in loop "
                                                         "before loop tags.",
                                                         self.get_line_number())

                                    if (self.token in self.reserved and
                                            self.delimiter == " "):
                                        raise ValueError("Cannot use keywords "
                                                         "as data values unless"
                                                         " quoted or semi-colon"
                                                         " delineated. Perhaps "
                                                         "this is a loop that "
                                                         "wasn't properly "
                                                         "terminated? Illegal "
                                                         "value: " + self.token,
                                                         self.get_line_number())
                                    curdata.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.get_token()

                    if self.token != "stop_":
                        raise ValueError("Loop improperly terminated at end of"
                                         " file.", self.get_line_number())

                # Close saveframe
                elif self.token == "save_":
                    if self.delimiter not in " ;":
                        raise ValueError("The save_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())
                    if not pynmstar_instance.ALLOW_V2_ENTRIES:
                        if curframe.tag_prefix is None:
                            raise ValueError("The tag prefix was never set! "
                                             "Either the saveframe had no tags,"
                                             " you tried to read a version 2.1 "
                                             "file without setting "
                                             "ALLOW_V2_ENTRIES to True, or "
                                             "there is something else wrong "
                                             "with your file. Saveframe error "
                                             "occured: '%s'" % curframe.name)
                    curframe = None
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    raise ValueError("Invalid token found in saveframe '" +
                                     curframe.name + "': '" + self.token +
                                     "'", self.get_line_number())

                # Add a tag
                else:
                    if self.delimiter != " ":
                        raise ValueError("Saveframe tags may not be quoted or "
                                         "semicolon-delineated.",
                                         self.get_line_number())
                    curtag = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.get_token()
                    if self.delimiter == " ":
                        if self.token in self.reserved:
                            raise ValueError("Cannot use keywords as data values"
                                             " unless quoted or semi-colon "
                                             "delineated. Illegal value: " +
                                             self.token, self.get_line_number())
                        if self.token.startswith("_"):
                            raise ValueError("Cannot have a tag value start "
                                             "with an underscore unless the "
                                             "entire value is quoted. You may "
                                             "be missing a data value on the "
                                             "previous line. Illegal value: " +
                                             self.token, self.get_line_number())
                    curframe.add_tag(curtag, self.token, self.get_line_number())

            if self.token != "save_":
                raise ValueError("Saveframe improperly terminated at end of "
                                 "file.", self.get_line_number())

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        # Reset the parser
        if pynmstar_instance.cnmrstar is not None:
            pynmstar_instance.cnmrstar.reset()

        for loop in self.ent.get_loops_by_category('_Constraint_file'):
            loop.sort_rows('ID')
            max_row = 0
            for row in loop.get_tag('ID'):
                if max_row > int(row) < 999:
                    max_row = int(row)
            id_col = loop._tag_index('ID')

            renumber_row = max_row + 2
            for row in loop.data:
                if int(row[id_col]) >= 999:
                    row[id_col] = int(row[id_col]) - 999 + renumber_row

        return self.ent

    # Do the actual patching
    pynmstar_instance._Parser.original_parse = pynmstar_instance._Parser.parse
    pynmstar_instance._Parser.parse = parse


def unpatch_parser(pynmstar_instance):
    pynmstar_instance._Parser.parse = pynmstar_instance._Parser.original_parse