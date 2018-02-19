#!/usr/bin/env python

from __future__ import print_function

import os
import sys

# Load the pynmrstar.py library
if not os.path.isfile("pynmrstar.py"):
    if not os.path.isfile("../pynmrstar.py"):
        raise ImportError("Could not locate pynmrstar.py library. Please copy to this directory.")
    sys.path.append("..")
import bmrb

if len(sys.argv) < 2:
    raise ValueError("You must provide the file to read from as the first argument.")

the_file = sys.argv[1]

if not os.path.isfile(the_file):
    raise IOError("The file you asked to read from does not exist.")
    sys.exit(1)

# Load the NMR-STAR file and print the list of saveframes in the format:
# saveframe_name: saveframe_category
for saveframe in bmrb.Entry.from_file(the_file):
    print("%s: %s" % (saveframe.name, saveframe.category))

