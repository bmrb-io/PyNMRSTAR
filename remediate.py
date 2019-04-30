#!/usr/bin/env python2

from __future__ import print_function

import sys
import pynmrstar
import gzip
from monkeypatch import patch_parser
patch_parser(pynmrstar)


for file_name in sys.argv[1:]:

    try:

        # Get the file contents
        if file_name.endswith('.gz'):
            file_data = gzip.GzipFile(file_name, 'r').read()
        else:
            file_data = open(file_name, 'r').read()
        pynmrstar.cnmrstar.load_string(file_data)

        # Get the comment at the beginning
        comment_lines = []
        token = pynmrstar.cnmrstar.get_token_full()[0]
        while token:
            token, line_number, delimiter = pynmrstar.cnmrstar.get_token_full()
            if delimiter == '#':
                comment_lines.append(token)
        comment_str = "\n".join(comment_lines)
        pynmrstar.cnmrstar.reset()

        # Get the entry
        entry = pynmrstar.Entry.from_string(file_data)
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

        clean_string = "data_%s\n\n%s\n\n%s" % (entry.entry_id, comment_str, "\n".join(sf_strings))
    except Exception as err:
        print("Warning! Something went wrong for file %s: %s" % (file_name, err))
        continue

    if file_name.endswith('.gz'):
        with gzip.GzipFile(file_name, 'w') as fixed:
            fixed.write(clean_string)
    else:
        with open(file_name, 'w') as fixed:
            fixed.write(clean_string)

