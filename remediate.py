#!/usr/bin/env python2

from __future__ import print_function

import sys
import pynmrstar
from monkeypatch import patch_parser
patch_parser(pynmrstar)

for file_name in sys.argv[1:]:
    try:
        comments = []
        pynmrstar.cnmrstar.load(sys.argv[1])

        # Get rid of the data line
        token = pynmrstar.cnmrstar.get_token_full()[0]
        while token:
            token, line_number, delimiter = pynmrstar.cnmrstar.get_token_full()
            if delimiter == '#':
                comments.append(token)
        comment_str = "\n".join(comments)

        pynmrstar.cnmrstar = None

        entry = pynmrstar.Entry.from_file(sys.argv[1])
        del entry['constraint_statistics']
        entry.rename_saveframe('global_Org_file_characteristics', 'constraint_statistics')

        sf_strings = []
        seen_saveframes = {}
        for saveframe in entry:
            if saveframe.category in seen_saveframes:
                sf_strings.append(saveframe.__str__(first_in_category=False))
            else:
                sf_strings.append(saveframe.__str__(first_in_category=True))
                seen_saveframes[saveframe.category] = True

        clean_string = "data_%s\n%s\n\n%s" % (entry.entry_id, comment_str, "\n".join(sf_strings))
    except Exception as err:
        print("Warning! Something went wrong for file %s: %s" % (sys.argv[1], err))
        continue

    with open(sys.argv[1], 'w') as fixed:
        fixed.write(clean_string)

