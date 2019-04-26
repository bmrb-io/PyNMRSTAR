#!/usr/bin/env python3

#############################################
#                 Imports                   #
#############################################

import json
import os
from gzip import GzipFile
from io import StringIO, BytesIO
from typing import IO
from typing import Union, Optional, Iterable, Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from . import definitions
from . import entry as entry_mod
from . import schema as schema_mod

try:
    from . import cnmrstar
except ImportError:
    cnmrstar = None

#############################################
#            Global Variables               #
#############################################

# Set this to allow import * from pynmrstar to work sensibly
__all__ = ['diff', 'validate', 'interpret_file', 'get_schema', 'format_category', 'format_tag']

_STANDARD_SCHEMA: Optional['schema_mod.Schema'] = None


def clean_value(value: Any) -> str:
    """Automatically quotes the value in the appropriate way. Don't
    quote values you send to this method or they will show up in
    another set of quotes as part of the actual data. E.g.:

    clean_value('"e. coli"') returns '\'"e. coli"\''

    while

    clean_value("e. coli") returns "'e. coli'"

    This will automatically be called on all values when you use a str()
    method (so don't call it before inserting values into tags or loops).

    Be mindful of the value of STR_CONVERSION_DICT as it will effect the
    way the value is converted to a string.

    """

    # Allow manual specification of conversions for booleans, Nones, etc.
    if value in definitions.STR_CONVERSION_DICT:
        if any(isinstance(value, type(x)) for x in definitions.STR_CONVERSION_DICT):
            value = definitions.STR_CONVERSION_DICT[value]

    # Use the fast code if it is available
    if cnmrstar is not None:
        # It's faster to assume we are working with a string and catch
        #  errors than to check the instance for every object and convert
        try:
            return cnmrstar.clean_value(value)
        except (ValueError, TypeError):
            return cnmrstar.clean_value(str(value))

    # Convert non-string types to string
    if not isinstance(value, str):
        value = str(value)

    # If it is a STAR-format multi-line comment already, we need to escape it
    if "\n;" in value:
        value = value.replace("\n", "\n   ")
        if value[-1] != "\n":
            value = value + "\n"
        if value[0] != "\n":
            value = "\n   " + value
        return value

    # If it's going on it's own line, don't touch it
    if "\n" in value:
        if value[-1] != "\n":
            return value + "\n"
        return value

    if value == "":
        raise ValueError("Empty strings are not allowed as values. Use a '.' or a '?' if needed.")

    # If it has single and double quotes it will need to go on its
    #  own line under certain conditions...
    if '"' in value and "'" in value:
        can_wrap_single = True
        can_wrap_double = True

        for pos, char in enumerate(value):
            next_char = value[pos + 1:pos + 2]

            if next_char != "" and next_char in definitions.WHITESPACE:
                if char == "'":
                    can_wrap_single = False
                if char == '"':
                    can_wrap_double = False

        if not can_wrap_single and not can_wrap_double:
            return '%s\n' % value
        elif can_wrap_single:
            return "'%s'" % value
        elif can_wrap_double:
            return '"%s"' % value

    # Check for special characters in a tag
    if any(x in value for x in definitions.WHITESPACE) or '#' in value or value in definitions.RESERVED_KEYWORDS or \
            value.startswith("_"):
        # If there is a single quote wrap in double quotes
        if "'" in value:
            return '"%s"' % value
        # Either there is a double quote or no quotes
        else:
            return "'%s'" % value

    # Quote if necessary
    if value[0] == "'":
        return '"' + value + '"'
    if value[0] == '"':
        return "'" + value + "'"

    # It's good to go
    return value


def diff(entry1: 'entry_mod.Entry', entry2: 'entry_mod.Entry') -> None:
    """Prints the differences between two entries. Non-equal entries
    will always be detected, but specific differences detected depends
    on order of entries."""

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


def get_schema(passed_schema: 'schema_mod.Schema' = None) -> 'schema_mod.Schema':
    """If passed a schema (not None) it returns it. If passed none,
    it checks if the default schema has been initialized. If not
    initialized, it initializes it. Then it returns the default schema."""

    if passed_schema:
        return passed_schema

    global _STANDARD_SCHEMA
    if _STANDARD_SCHEMA is None:

        # Try to load the local file first
        try:
            schema_file = os.path.join(os.path.dirname(os.path.realpath(__file__)))
            schema_file = os.path.join(schema_file, "../reference_files/schema.csv")
            _STANDARD_SCHEMA = schema_mod.Schema(schema_file=schema_file)
        except IOError:
            # Try to load from the internet
            try:
                _STANDARD_SCHEMA = schema_mod.Schema()
            except (HTTPError, URLError):
                raise ValueError("Could not load a BMRB schema from the "
                                 "internet or from the local repository.")

    return _STANDARD_SCHEMA


def interpret_file(the_file: Union[str, IO]) -> StringIO:
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read'):
        read_data: Union[bytes, str] = the_file.read()
        if type(read_data) == bytes:
            buffer: BytesIO = BytesIO(read_data)
        elif type(read_data, str):
            buffer = BytesIO(read_data.encode())
        else:
            raise IOError("What did your file object return when .read() was called on it?")
    elif isinstance(the_file, str):
        if the_file.startswith("http://") or the_file.startswith("https://") or the_file.startswith("ftp://"):
            with urlopen(the_file) as url_data:
                buffer = BytesIO(url_data.read())
        else:
            with open(the_file, 'rb') as read_file:
                buffer = BytesIO(read_file.read())
    else:
        raise ValueError("Cannot figure out how to interpret the file you passed.")

    # Decompress the buffer if we are looking at a gzipped file
    try:
        gzip_buffer = GzipFile(fileobj=buffer)
        gzip_buffer.readline()
        gzip_buffer.seek(0)
        buffer = BytesIO(gzip_buffer.read())
    # Apparently we are not looking at a gzipped file
    except (IOError, AttributeError, UnicodeDecodeError):
        pass

    buffer.seek(0)
    return StringIO(buffer.read().decode())


def iter_entries(metabolomics: bool = False) -> Iterable['entry_mod.Entry']:
    """ Returns a generator that will yield an Entry object for every
        macromolecule entry in the current BMRB database. Perfect for performing
        an operation across the entire BMRB database. Set `metabolomics=True`
        in order to get all the entries in the metabolomics database."""

    api_url = "%s/list_entries?database=macromolecules" % definitions.API_URL
    if metabolomics:
        api_url = "%s/list_entries?database=metabolomics" % definitions.API_URL

    for entry in json.loads(interpret_file(api_url).read()):
        yield entry.Entry.from_database(entry)


def validate(entry_to_validate: 'entry_mod.Entry', schema: 'schema_mod.Schema' = None) -> None:
    """Prints a validation report of an object."""

    validation = entry_to_validate.validate(schema=schema)
    if len(validation) == 0:
        print("No problems found during validation.")
    for pos, err in enumerate(validation):
        print("%d: %s" % (pos + 1, err))
