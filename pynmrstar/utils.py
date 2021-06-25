#!/usr/bin/env python3

""" This file contains various helper functions."""
import functools
import json
import os
from typing import Iterable, Any, Dict
from urllib.error import HTTPError, URLError

from pynmrstar import definitions, cnmrstar, entry as entry_mod
from pynmrstar._internal import _interpret_file
from pynmrstar.schema import Schema

# Set this to allow import * from pynmrstar to work sensibly
__all__ = ['diff', 'format_category', 'format_tag', 'get_schema', 'iter_entries', 'quote_value', 'validate']


def diff(entry1: 'entry_mod.Entry', entry2: 'entry_mod.Entry') -> None:
    """Prints the differences between two entries. Non-equal entries
    will always be detected, but specific differences detected depends
    on the order of entries."""

    diffs = entry1.compare(entry2)
    if len(diffs) == 0:
        print("Identical entries.")
    for difference in diffs:
        print(difference)


def format_category(tag: str) -> str:
    """Adds a '_' to the front of a tag (if not present) and strips out
    anything after a '.'"""

    if tag:
        if not tag.startswith("_"):
            tag = "_" + tag
        if "." in tag:
            tag = tag[:tag.index(".")]
    return tag


def format_tag(tag: str) -> str:
    """Strips anything before the '.'"""

    if '.' in tag:
        return tag[tag.index('.') + 1:]
    return tag


# noinspection PyDefaultArgument
def get_schema(passed_schema: 'Schema' = None, _cached_schema: Dict[str, Schema] = {}) -> 'Schema':
    """If passed a schema (not None) it returns it. If passed none,
    it checks if the default schema has been initialized. If not
    initialized, it initializes it. Then it returns the default schema."""

    if passed_schema:
        return passed_schema

    if not _cached_schema:

        # Try to load the local file first
        try:
            schema_file = os.path.join(os.path.dirname(os.path.realpath(__file__)))
            schema_file = os.path.join(schema_file, "reference_files/schema.csv")
            _cached_schema['schema'] = Schema(schema_file=schema_file)
        except IOError:
            # Try to load from the internet
            try:
                _cached_schema['schema'] = Schema()
            except (HTTPError, URLError):
                raise ValueError("Could not load a BMRB schema from the internet or from the local repository.")

    return _cached_schema['schema']


def iter_entries(metabolomics: bool = False) -> Iterable['entry_mod.Entry']:
    """ Returns a generator that will yield an Entry object for every
        macromolecule entry in the current BMRB database. Perfect for performing
        an operation across the entire BMRB database. Set `metabolomics=True`
        in order to get all the entries in the metabolomics database."""

    api_url = f"{definitions.API_URL}/list_entries?database=macromolecules"
    if metabolomics:
        api_url = f"{definitions.API_URL}/list_entries?database=metabolomics"

    for entry in json.loads(_interpret_file(api_url).read()):
        yield entry_mod.Entry.from_database(entry)


@functools.lru_cache(maxsize=65536, typed=True)
def quote_value(value: Any) -> str:
    """Automatically quotes the value in the appropriate way. Don't
    quote values you send to this method or they will show up in
    another set of quotes as part of the actual data. E.g.:

    quote_value('"e. coli"') returns '\'"e. coli"\''

    while

    quote_value("e. coli") returns "'e. coli'"

    This will automatically be called on all values when you use a str()
    method (so don't call it before inserting values into tags or loops).

    Be mindful of the value of STR_CONVERSION_DICT as it will effect the
    way the value is converted to a string.

    """

    # Allow manual specification of conversions for booleans, Nones, etc.
    if value in definitions.STR_CONVERSION_DICT:
        if any(isinstance(value, type(x)) for x in definitions.STR_CONVERSION_DICT):
            value = definitions.STR_CONVERSION_DICT[value]

    return cnmrstar.quote_value(value)


def validate(entry_to_validate: 'entry_mod.Entry', schema: 'Schema' = None) -> None:
    """Prints a validation report of an object."""

    validation = entry_to_validate.validate(schema=schema)
    if len(validation) == 0:
        print("No problems found during validation.")
    for pos, err in enumerate(validation):
        print(f"{pos + 1}: {err}")
