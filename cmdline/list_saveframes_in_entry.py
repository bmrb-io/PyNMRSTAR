#!/usr/bin/env python3

import os
import sys

import pynmrstar

if len(sys.argv) < 2:
    raise ValueError("You must provide the file to read from as the first argument.")

the_file = sys.argv[1]

if not os.path.isfile(the_file):
    raise IOError("The file you asked to read from does not exist.")

# Load the NMR-STAR file and print the list of saveframes in the format:
# saveframe_name: saveframe_category
for saveframe in pynmrstar.Entry.from_file(the_file):
    print("%s: %s" % (saveframe.name, saveframe.category))

