#!/usr/bin/python3

NULL_VALUES = ['', ".", "?", None]
WHITESPACE: str = " \t\n\v"
RESERVED_KEYWORDS = ["data_", "save_", "loop_", "stop_", "global_"]

API_URL: str = "http://webapi.bmrb.wisc.edu/v2"
SCHEMA_URL: str = 'https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/master/xlschem_ann.csv'
STR_CONVERSION_DICT: dict = {None: "."}