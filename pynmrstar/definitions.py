#!/usr/bin/python3

""" NMR-STAR definitions and other module parameters live here. Technically
you can edit them, but you should really know what you're doing.

Adding key->value pairs to STR_CONVERSION_DICT will automatically convert tags
whose value matches "key" to the string "value" when printing. This allows you
to set the default conversion value for Booleans or other objects.

WARNINGS:
 * STR_CONVERSION_DICT cannot contain both booleans and arithmetic types.
   Attempting to use both will cause an issue since boolean True == 1 in python
   and False == 0.

 * You must call utils.quote_value.clear_cache() after changing the
   STR_CONVERSION_DICT or else your changes won't take effect due to caching!

   The only exception is if you set STR_CONVERSION_DICT before performing any
   actions which would call quote_value() - which include calling __str__ or
   format() on Entry, Saveframe, and Loop objects.
"""

NULL_VALUES = ['', ".", "?", None]
WHITESPACE: str = " \t\n\v"
RESERVED_KEYWORDS = ["data_", "save_", "loop_", "stop_", "global_"]
STR_CONVERSION_DICT: dict = {None: "."}

API_URL: str = "https://api.bmrb.io/v2"
SCHEMA_URL: str = 'https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/master/xlschem_ann.csv'
COMMENT_URL: str = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v3/reference_files/comments.str"
TYPES_URL: str = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v3/pynmrstar/reference_files/data_types.csv"
FTP_URL: str = "https://bmrb.io/ftp/pub/bmrb"
