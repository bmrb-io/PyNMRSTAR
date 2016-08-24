#!/usr/bin/env python

from __future__ import print_function

import os
import sys
sys.path.append("..")
import bmrb

if len(sys.argv) < 2:
    raise ValueError("You must provide the file to read from as the first argument.")

the_file = sys.argv[1]

if not os.path.isfile(the_file):
    raise IOError("The file you asked to read from does not exist.")
    sys.exit(1)

# First try to load the file as a saveframe, then try to load as an entry
#  and pull out the first saveframe
try:
    saveframe = bmrb.Saveframe.from_file(the_file)
except ValueError:
    try:
        full_entry = bmrb.Entry.from_file(the_file)
    except ValueError:
        raise ValueError("The file you specified does not appear to be a "
                         "NMR-STAR file or NMR-STAR saveframe.")

    if len(full_entry) > 1:
        raise ValueError("You specified an NMR-STAR file with more than one saveframe.")
    else:
        saveframe = full_entry[0]

# Print the tags and their values
for tag in saveframe.tags:
    print("%s.%s: %s" % (saveframe.tag_prefix, tag[0], tag[1].replace("\n", "\\n")))

