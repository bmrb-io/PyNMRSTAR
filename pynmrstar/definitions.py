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
DICTIONARY_FILES: tuple = ('xlschem_ann.csv', 'adit_enum_hdr.csv', 'adit_enum_dtl.csv',
                           'adit_cat_grp_o.csv', 'adit_tag_validation.csv')

# The dictionary carries one set of validation flags per "view" -- the six
# ``Validate`` columns of xlschem_ann.csv, in this order. A flag string (in
# xlschem_ann, adit_cat_grp_o and adit_tag_validation alike) is indexed by the
# position of the profile in this tuple. BMRB's annotators' validator uses
# ``internal`` (DICTMODE = 1 in nmr-star-dictionary-scripts); a depositor
# checking a file against the public archive's requirements wants ``public``.
#
# Only ``public`` and ``internal`` are populated as of dictionary 3.2.14.0; the
# remaining columns exist but are blank.
VALIDATION_PROFILES: tuple = ('public', 'internal', 'small_molecule',
                              'small_molecule_struct', 'metabolomics', 'entry_completeness')
DEFAULT_VALIDATION_PROFILE: str = 'public'
# Kept for backwards compatibility (the schema tag table alone).
SCHEMA_URL: str = f'{DICTIONARY_URL}/xlschem_ann.csv'
FTP_URL: str = "https://bmrb.io/ftp/pub/bmrb"
