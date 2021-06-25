#!/usr/bin/env python3

import os
import sys

# Load the pynmrstar.py library
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

    shift_frames = full_entry.get_saveframes_by_category("assigned_chemical_shifts")

    if len(shift_frames) > 1:
        raise ValueError("The entry you specified has more than one assigned "
                         "chemical shift loop. Please remove the extra one.")
    elif len(shift_frames) == 0:
        raise ValueError("There don't appear to be any assigned chemical shift "
                         "saveframes in the file you specified.")
    else:
        saveframe = shift_frames[0]

try:
    print(saveframe.get_loop_by_category("_Atom_chem_shift").get_data_as_csv())
except KeyError:
    raise ValueError("The assigned chemical shifts saveframe didn't have an assigned"
                     " chemical shift loop. (Expecting loop: '_Atom_chem_shift')")
