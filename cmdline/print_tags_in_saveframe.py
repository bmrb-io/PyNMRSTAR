#!/usr/bin/env python3

import os
import sys

import pynmrstar
from pynmrstar.exceptions import ParsingError

if len(sys.argv) < 2:
    raise ValueError("You must provide the file to read from as the first argument.")

the_file = sys.argv[1]

if not os.path.isfile(the_file):
    raise IOError("The file you asked to read from does not exist.")

# First try to load the file as a saveframe, then try to load as an entry
#  and pull out the first saveframe
try:
    saveframe = pynmrstar.Saveframe.from_file(the_file)
except ParsingError:
    try:
        full_entry = pynmrstar.Entry.from_file(the_file)
    except ParsingError:
        raise ParsingError("The file you specified does not appear to be a "
                           "NMR-STAR file or NMR-STAR saveframe.")
    saveframe = full_entry[0]

# Print the tags and their values
for tag in saveframe.tags:
    print("%s.%s: %s" % (saveframe.tag_prefix, tag[0], tag[1].replace("\n", "\\n")))

