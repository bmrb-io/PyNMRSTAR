#!/usr/bin/python3

""" NMR-STAR definitions and other module parameters live here.

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
STR_CONVERSION_DICT: dict = {None: "."}

API_URL: str = "https://api.bmrb.io/v2"
# Base location of the NMR-STAR dictionary distribution (the built files, not the
# source spreadsheet). GitHub for now; will point at BMRB.io in future. Only
# dictionary versions 3.2.14.0 and above are supported. Override the source for
# development with the PYNMRSTAR_DICTIONARY_SOURCE environment variable (a URL
# base or a local directory holding the distribution files).
DICTIONARY_URL: str = 'https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/' \
                      'nmr-star-development/NMR-STAR/internal_106_distribution'
# The distribution files a Schema is built from.
DICTIONARY_FILES: tuple = ('xlschem_ann.csv', 'adit_enum_hdr.csv', 'adit_enum_dtl.csv')
# Kept for backwards compatibility (the schema tag table alone).
SCHEMA_URL: str = f'{DICTIONARY_URL}/xlschem_ann.csv'
FTP_URL: str = "https://bmrb.io/ftp/pub/bmrb"
