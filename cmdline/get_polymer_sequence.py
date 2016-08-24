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

result = entry.get_tags(["_Entity.Polymer_seq_one_letter_code"])["_Entity.Polymer_seq_one_letter_code"]

if len(result) == 0:
    print("No polymer sequences found in file.")
    sys.exit(2)
elif len(result) > 1:
    sys.stderr.write("Warning: multiple chains in entry.\n")

for polymer_sequence in result:
    print(polymer_sequence.replace("\n", ""))
