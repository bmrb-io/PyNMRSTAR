#!/usr/bin/env python

from __future__ import print_function

import os
import sys

# Load the bmrb.py library
if not os.path.isfile("bmrb.py"):
    if not os.path.isfile("../bmrb.py"):
        raise ImportError("Could not locate bmrb.py library. Please copy to this directory.")
    sys.path.append("..")
import bmrb

if len(sys.argv) < 2:
    raise ValueError("You must provide the file to read from as the first argument.")

the_file = sys.argv[1]

if not os.path.isfile(the_file):
    raise IOError("The file you asked to read from does not exist.")
    sys.exit(1)

entry = bmrb.Entry.from_file(the_file)

# Go through the saveframes and loops and print off the tags
print("Entry %s" % entry.entry_id)
for saveframe in entry:
    print("  Saveframe %s:%s" % (saveframe.name, saveframe.category))
    for tag in saveframe.tags:
        print("    %s.%s" % (saveframe.tag_prefix, tag[0]))
    for loop in saveframe:
        print("    Loop %s" % loop.category)
        for col in loop.columns:
            print("      %s.%s" % (loop.category, col))

