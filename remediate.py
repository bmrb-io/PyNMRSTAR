#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
import pynmrstar
import gzip
from monkeypatch import patch_parser
patch_parser(pynmrstar)

if not pynmrstar.cnmrstar:
    raise ValueError('The cnmrstar tokenizer must be compiled and available.')


def get_comment(file_data_local):
    """ Returns the file comment. Fixes the unicode character. """

    # Get the comment at the beginning
    comment_lines = []
    pynmrstar.cnmrstar.load_string(file_data_local)
    pynmrstar.cnmrstar.get_token_full()
    token, line_number, delimiter = pynmrstar.cnmrstar.get_token_full()
    while token:
        if token.count('#') > 1:
            break
        if delimiter == '#':
            comment_lines.append(token)
        token, line_number, delimiter = pynmrstar.cnmrstar.get_token_full()

    pynmrstar.cnmrstar.reset()
    return "\n".join(comment_lines)


for file_name in sys.argv[1:]:

    try:

        # Get the file contents
        if file_name.endswith('.gz'):
            file_data = gzip.GzipFile(file_name, 'r').read()
        else:
            file_data = open(file_name, 'r').read()

        # Get the entry
        entry = pynmrstar.Entry.from_string(file_data)

        changes_made = False

        # Fix the duplicate loop issue if needed
        if 'global_Org_file_characteristics' in entry.frame_dict:
            del entry['constraint_statistics']

            # It's normally safer to us entry.rename_saveframe, but in this case we know there are no $references,
            #  so it's much faster to reassign the name directly and skip checking all the other saveframes
            rename_frame = entry.get_saveframe_by_name('global_Org_file_characteristics')
            rename_frame.name = 'constraint_statistics'
            rename_frame['sf_framecode'] = 'constraint_statistics'
            changes_made = True

        # Fix the unicode comment issue
        comment_str = get_comment(file_data)

        if "–" in comment_str:
            comment_str = comment_str.replace("–", '-')
            changes_made = True

        if not changes_made:
            continue

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

