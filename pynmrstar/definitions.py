#!/usr/bin/python3

""" NMR-STAR definitions and other module parameters live here. Technically
you can edit them, but you should really know what you're doing.

Adding key->value pairs to STR_CONVERSION_DICT will automatically convert tags
whose value matches "key" to the string "value" when printing. This allows you
to set the default conversion value for Booleans or other objects.

WARNING: STR_CONVERSION_DICT cannot contain both booleans and arithmetic types.
Attempting to use both will cause an issue since boolean True == 1 in python
and False == 0.
"""

NULL_VALUES = ['', ".", "?", None]
WHITESPACE: str = " \t\n\v"
RESERVED_KEYWORDS = ["data_", "save_", "loop_", "stop_", "global_"]
STR_CONVERSION_DICT: dict = {None: "."}

API_URL: str = "http://webapi.bmrb.wisc.edu/v2"
SCHEMA_URL: str = 'https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/master/xlschem_ann.csv'
COMMENT_URL: str = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v3/reference_files/comments.str"
