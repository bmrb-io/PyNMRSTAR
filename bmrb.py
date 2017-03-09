#!/usr/bin/env python

"""This module provides Entry, Saveframe, and Loop objects. Use python's
built in help function for documentation.

There are eight module variables you can set to control our behavior.

* Setting bmrb.VERBOSE to True will print some of what is going on to
the terminal.

* Setting bmrb.RAISE_PARSE_WARNINGS to True will raise an exception if
the parser encounters something problematic. Normally warnings are
suppressed.

* In addition, if you want to ignore some parse warnings but allow the
rest, you can specify warnings to ignore by adding the warning to ignore
to the "WARNINGS_TO_IGNORE" list.

Here are descriptions of the parse warnings that can be suppressed:

* "tag-only-loop": A loop with no data was found.
* "empty-loop": A loop with no tags or values was found.
* "tag-not-in-schema": A tag was found in the entry that was not present
in the schema.
* "invalid-null-value": A tag for which the schema disallows null values
had a null value.
* "bad-multiline": A tag with an improper multi-line value was found.
Multiline values should look like this:
\n;\nThe multi-line\nvalue here.\n;\n
but the tag looked like this:
\n; The multi-line\nvalue here.\n;\n

* Setting SKIP_EMPTY_LOOPS to True will suppress the printing of empty
loops when calling __str__ methods.

* Adding key->value pairs to STR_CONVERSION_DICT will automatically
convert tags whose value matches "key" to the string "value" when
printing. This allows you to set the default conversion value for
Booleans or other objects.

* Setting bmrb.ALLOW_V2_ENTRIES will allow parsing of NMR-STAR version
2.1 entries. Most other methods will not operate correctly on parsed
2.1 entries. This is only to allow you parse and access the data in
these entries - nothing else. Only set this if you have a really good
reason to. Attempting to print a 2.1 entry will 'work' but tags that
were after loops will be moved to before loops.

* Setting bmrb.DONT_SHOW_COMMENTS to True will supress the printing of
comments before saveframes.

* Setting bmrb.CONVERT_DATATYPES to True will automatically convert
the data loaded from the file into the corresponding python type as
determined by loading the standard BMRB schema. This would mean that
all floats will be represented as decimal.Decimal objects, all integers
will be python int objects, strings and vars will remain strings, and
dates will become datetime.date objects. When printing str() is called
on all objects. Other that converting uppercase "E"s in scientific
notation floats to lowercase "e"s this should not cause any change in
the way re-printed NMR-STAR objects are displayed.

Some errors will be detected and exceptions raised, but this does not
implement a full validator (at least at present).

Call directly (rather than importing) to run a self-test.
"""

#############################################
#                 Imports                   #
#############################################

# Make sure print functions work in python2 and python3
from __future__ import print_function

# Standard library imports
import os
import re
import sys
import json
import decimal
import optparse

from optparse import SUPPRESS_HELP
from copy import deepcopy
from csv import reader as csv_reader, writer as csv_writer
from datetime import date
from gzip import GzipFile

# Determine if we are running in python3
PY3 = (sys.version_info[0] == 3)

#pylint: disable=wrong-import-position,no-name-in-module
#pylint: disable=import-error,wrong-import-order
# Python version dependent loads
if PY3:
    from urllib.request import urlopen
    from urllib.error import HTTPError, URLError
    from io import StringIO, BytesIO
else:
    from urllib2 import urlopen, HTTPError, URLError
    from cStringIO import StringIO
    BytesIO = StringIO

# This is an odd place for this, but it can't really be avoided if
#  we want to keep the import at the top.
def _build_extension():
    """ Try to compile the c extension. """
    import subprocess

    curdir = os.getcwd()
    try:
        pdir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        os.chdir(os.path.join(pdir, "c"))

        # Use the appropriate build command
        build_cmd = ['make']
        if PY3:
            build_cmd.append("python3")

        process = subprocess.Popen(build_cmd, stderr=subprocess.STDOUT,
                                   stdout=subprocess.PIPE)
        process.communicate()
        retcode = process.poll()
        # The make commmand exited with a non-zero status
        if retcode:
            return False

        # We were able to build the extension?
        return True
    except OSError:
        # There was an error going into the c dir
        return False
    finally:
        # Go back to the directory we were in before exiting
        os.chdir(curdir)

    # We should never make it here, but if we do the null return
    #  prevents the attempted importing of the c module.

# See if we can use the fast tokenizer
try:
    import cnmrstar
    if "version" not in dir(cnmrstar) or cnmrstar.version() < "2.2.7":
        print("Recompiling cnmrstar module due to API changes. You may "
              "experience a segmentation fault immediately following this "
              "message but should have no issues the next time you run your "
              "script or this program.")
        _build_extension()
        sys.exit(0)

except ImportError as e:
    cnmrstar = None

    # Check for nobuild file before continuing
    if not os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                       ".nocompile")):

        if _build_extension():
            try:
                import cnmrstar
            except ImportError:
                pass

# See if we can import from_iterable
try:
    from itertools import chain as _chain
    _from_iterable = _chain.from_iterable
except ImportError:
    def _from_iterable(iterables):
        """ A simple implementation of chain.from_iterable.
        As such: _from_iterable(['ABC', 'DEF']) --> A B C D E F """

        for item in iterables:
            for element in item:
                yield element

#############################################
#            Global Variables               #
#############################################

# Set this to allow import * from bmrb to work sensibly
__all__ = ['Entry', 'Saveframe', 'Loop', 'Schema', 'diff', 'validate',
           'enable_nef_defaults', 'enable_nmrstar_defaults',
           'delete_empty_saveframes', 'PY3']

# May be set by calling code
VERBOSE = False

ALLOW_V2_ENTRIES = False
RAISE_PARSE_WARNINGS = False
WARNINGS_TO_IGNORE = []
SKIP_EMPTY_LOOPS = False
DONT_SHOW_COMMENTS = False
CONVERT_DATATYPES = False

# WARNING: STR_CONVERSION_DICT cannot contain both booleans and
# arithmetic types. Attempting to use both will cause an issue since
# boolean True == 1 in python and False == 0.
STR_CONVERSION_DICT = {None:"."}

# Used internally
_STANDARD_SCHEMA = None
_COMMENT_DICTIONARY = {}
_API_URL = "http://webapi.bmrb.wisc.edu/v1"
_SCHEMA_URL = 'http://svn.bmrb.wisc.edu/svn/nmr-star-dictionary/bmrb_only_files/adit_input/xlschem_ann.csv'
_WHITESPACE = " \t\n\v"
_VERSION = "2.3.2"

#############################################
#             Module methods                #
#############################################

# Public use methods
def enable_nef_defaults():
    """ Sets the module variables such that our behavior matches the NEF
    standard. Specifically, suppress printing empty loops by default and
    convert True -> "true" and False -> "false" when printing."""

    global STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS, DONT_SHOW_COMMENTS
    STR_CONVERSION_DICT = {None:".", True:"true", False:"false"}
    SKIP_EMPTY_LOOPS = True
    DONT_SHOW_COMMENTS = True

def enable_nmrstar_defaults():
    """ Sets the module variables such that our behavior matches the
    BMRB standard (NMR-STAR). This is the default behavior of this module.
    This method only exists to revert after calling enable_nef_defaults()."""

    global STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS, DONT_SHOW_COMMENTS
    STR_CONVERSION_DICT = {None:"."}
    SKIP_EMPTY_LOOPS = False
    DONT_SHOW_COMMENTS = False

def delete_empty_saveframes(entry_object,
                            tags_to_ignore=["sf_category","sf_framecode"],
                            allowed_null_values=[".","?",None]):
    """ This method will delete all empty saveframes in an entry
    (the loops in the saveframe must also have be empty for the saveframe
    to be deleted). "Empty" means no values in tags, not no tags present."""

    to_delete_list = []

    # Go through the saveframes
    for pos, frame in enumerate(entry_object):
        to_delete = True

        # Go through the tags
        for tag in frame.tag_iterator():

            # Check if the tag is one to ignore
            if tag[0].lower() not in tags_to_ignore:
                # Check if the value is not null
                if tag[1] not in allowed_null_values:
                    to_delete = False
                    break

        # Now check the loops
        for loop in frame:
            if loop.data != []:
                to_delete = False
                break

        # Now we know if we can delete
        if to_delete:
            to_delete_list.append(pos)

    # Delete the frames
    for pos in reversed(to_delete_list):
        del entry_object[pos]

def diff(entry1, entry2):
    """Prints the differences between two entries. Non-equal entries
    will always be detected, but specific differences detected depends
    on order of entries."""

    diffs = entry1.compare(entry2)
    if len(diffs) == 0:
        print("Identical entries.")
    for difference in diffs:
        print(difference)

def validate(entry_to_validate, schema=None):
    """Prints a validation report of an object."""

    validation = entry_to_validate.validate(schema=schema)
    if len(validation) == 0:
        print("No problems found during validation.")
    for pos, err in enumerate(validation):
        print("%d: %s" % (pos + 1, err))

class _ErrorHandler(object):
    def fatalError(self, line, msg):
        print("Critical parse error in line %s: %s\n" % (line, msg))
    def error(self, line, msg):
        print("Parse error in line %s: %s\n" % (line, msg))
    def warning(self, line, msg):
        print("Parser warning in line %s: %s\n" % (line, msg))

def clean_value(value):
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
    if value in STR_CONVERSION_DICT:
        if any(isinstance(value, type(x)) for x in STR_CONVERSION_DICT):
            value = STR_CONVERSION_DICT[value]

    # Use the fast code if it is available
    if cnmrstar != None:
        # It's faster to assume we are working with a string and catch
        #  errors than to check the instance for every object and convert
        try:
            return cnmrstar.clean_value(value)
        except (ValueError, TypeError):
            return cnmrstar.clean_value(str(value))

    # Convert non-string types to string
    if not isinstance(value, str):
        value = str(value)

    # If it is a STAR-format multiline comment already, we need to escape it
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
        raise ValueError("Empty strings are not allowed as values. "
                         "Use a '.' or a '?' if needed.")

    # If it has single and double quotes it will need to go on its
    #  own line under certain conditions...
    if '"' in value and "'" in value:
        can_wrap_single = True
        can_wrap_double = True

        for pos, char in enumerate(value):
            next_char = value[pos+1:pos+2]

            if next_char != "" and next_char in _WHITESPACE:
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
    if (any(x in value for x in " \t\v#") or
            any(value.startswith(x) for x in
                ["data_", "save_", "loop_", "stop_", "_"])):
        # If there is a single quote wrap in double quotes
        if "'" in value:
            return  '"%s"' % value
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

# Internal use only methods

def _json_serialize(obj):
    """JSON serializer for objects not serializable by default json code"""

    # Serialize datetime.date objects by calling str() on them
    if isinstance(obj, (date, decimal.Decimal)):
        return str(obj)
    raise TypeError("Type not serializable: %s" % type(obj))

def _format_category(value):
    """Adds a '_' to the front of a tag (if not present) and strips out
    anything after a '.'"""

    if value:
        if not value.startswith("_"):
            value = "_" + value
        if "." in value:
            value = value[:value.index(".")]
    return value

def _format_tag(value):
    """Strips anything before the '.'"""

    if '.' in value:
        value = value[value.index('.')+1:]
    return value

def _get_schema(passed_schema=None):
    """If passed a schema (not None) it returns it. If passed none,
    it checks if the default schema has been initialized. If not
    initialzed, it initializes it. Then it returns the default schema."""

    global _STANDARD_SCHEMA
    if passed_schema is None:
        passed_schema = _STANDARD_SCHEMA
    if passed_schema is None:

        # Try to load the local file first
        try:
            sfile = os.path.join(os.path.dirname(os.path.realpath(__file__)))
            sfile = os.path.join(sfile, "reference_files/schema.csv")

            _STANDARD_SCHEMA = Schema(schema_file=sfile)
        except:
            # Try to load from the internet
            try:
                _STANDARD_SCHEMA = Schema()
            except (HTTPError, URLError):
                raise ValueError("Could not load a BMRB schema from the "
                                 "internet or from the local repository.")
        passed_schema = _STANDARD_SCHEMA

    return passed_schema

def _interpret_file(the_file):
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read') and hasattr(the_file, 'readline'):
        star_buffer = the_file
    elif isinstance(the_file, str) or isinstance(the_file, unicode):
        if (the_file.startswith("http://") or the_file.startswith("https://") or
                the_file.startswith("ftp://")):
            url_data = urlopen(the_file)
            star_buffer = BytesIO(url_data.read())
            url_data.close()
        else:
            with open(the_file, 'rb') as read_file:
                star_buffer = BytesIO(read_file.read())
    else:
        raise ValueError("Cannot figure out how to interpret the file"
                         " you passed.")

    # Decompress the buffer if we are looking at a gzipped file
    try:
        gzip_buffer = GzipFile(fileobj=star_buffer)
        gzip_buffer.readline()
        gzip_buffer.seek(0)
        star_buffer = gzip_buffer
    # Apparently we are not looking at a gzipped file
    except (IOError, AttributeError, UnicodeDecodeError):
        star_buffer.seek(0)

    # If the type is still bytes, convert it to string for python3
    full_star = star_buffer.read()
    star_buffer.seek(0)
    if PY3 and isinstance(full_star, bytes):
        star_buffer = StringIO(full_star.decode())

    return star_buffer

def _load_comments(file_to_load=None):
    """ Loads the comments that should be placed in written files. """

    # Figure out where to load the file from
    if file_to_load is None:
        file_to_load = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        file_to_load = os.path.join(file_to_load, "reference_files/comments.str")

    try:
        comment_entry = Entry.from_file(file_to_load)
    except IOError:
        return

    # Load the comments
    categories = comment_entry.get_tag("_comment.category")
    comments = comment_entry.get_tag("_comment.comment")

    for pos, val in enumerate(categories):
        comment = comments[pos]
        if comment != ".":
            _COMMENT_DICTIONARY[val] = comments[pos].rstrip() + "\n\n"

def _tag_key(x, schema=None):
    """ Helper function to figure out how to sort the tags."""
    try:
        return _get_schema(schema).schema_order.index(x)
    except ValueError:
        # Generate an arbitrary sort order for tags that aren't in the
        #  schema but make sure that they always come after tags in the
        #   schema
        return len(_get_schema(schema).schema_order) + hash(x)

#############################################
#                Classes                    #
#############################################

# Internal use class
class _Parser(object):
    """Parses an entry. You should not ever use this class directly."""

    reserved = ["stop_", "loop_", "save_", "data_", "global_"]

    def __init__(self, entry_to_parse_into=None):

        # Just make an entry to parse into if called with no entry passed
        if entry_to_parse_into is None:
            entry_to_parse_into = Entry.from_scratch("")

        self.ent = entry_to_parse_into
        self.to_process = ""
        self.full_data = ""
        self.index = 0
        self.token = ""
        self.source = "unknown"
        self.delimiter = " "
        self.line_number = 0

    def get_line_number(self):
        """ Returns the current line number that is in the process of
        being parsed."""

        if cnmrstar != None:
            return self.line_number
        else:
            return self.full_data[0:self.index].count("\n")+1

    def get_token(self):
        """ Returns the next token in the parsing process."""

        if cnmrstar is not None:
            self.token, self.line_number, self.delimiter = cnmrstar.get_token_full()
        else:
            self.real_get_token()
            self.line_number = 0

            if self.delimiter == ";":
                try:
                    # Unindent value which contain STAR multi-line values
                    # Only do this check if we are comma-delineated
                    if self.token.startswith("\n   "):
                        # Only remove the whitespaces if all lines have them
                        trim = True
                        for pos in range(1, len(self.token) - 4):
                            if self.token[pos] == "\n":
                                if self.token[pos+1:pos+4] != "   ":
                                    trim = False

                        if trim and "\n   ;" in self.token:
                            self.token = self.token[:-1].replace("\n   ", "\n")

                except AttributeError:
                    pass

        # This is just too VERBOSE
        if VERBOSE == "very":
            if self.token:
                print("'%s': '%s'" % (self.delimiter, self.token))
            else:
                print("No more tokens.")

        # Return the token
        return self.token

    @staticmethod
    def index_handle(haystack, needle, startpos=None):
        """ Finds the index while catching ValueError and returning
        None instead."""

        try:
            return haystack.index(needle, startpos)
        except ValueError:
            return None

    @staticmethod
    def next_whitespace(data):
        """ Returns the position of the next whitespace character in the
        provided string. If no whitespace it returns the length of the
        string."""

        for pos, char in enumerate(data):
            if char in _WHITESPACE:
                return pos
        return len(data)

    def load_data(self, data):
        """ Loads data in preparation of parsing and cleans up newlines
        and massages the data to make parsing work properly when multiline
        values aren't as expected. Useful for manually getting tokens from
        the parser."""

        # Fix DOS line endings
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        # Change '\n; data ' started multilines to '\n;\ndata'
        data = re.sub(r'\n;([^\n]+?)\n', r'\n;\n\1\n', data)

        if cnmrstar != None:
            cnmrstar.load_string(data)
        else:
            self.full_data = data + "\n"

    def parse(self, data, source="unknown"):
        """ Parses the string provided as data as an NMR-STAR entry
        and returns the parsed entry. Raises ValueError on exceptions."""

        # Prepare the data for parsing
        self.load_data(data)

        # Create the NMRSTAR object
        curframe = None
        curloop = None
        curtag = None
        curdata = []

        # Get the first token
        self.get_token()

        # Make sure this is actually a STAR file
        if not self.token.startswith("data_"):
            raise ValueError("Invalid file. NMR-STAR files must start with"
                             " 'data_'. Did you accidentally select the wrong"
                             " file?", self.get_line_number())

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ValueError("'data_' must be followed by data name. Simply "
                             "'data_' is not allowed.", self.get_line_number())

        if self.delimiter != " ":
            raise ValueError("The data_ keyword may not be quoted or "
                             "semicolon-delineated.")

        # Set the entry_id
        self.ent.entry_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.get_token() != None:

            if not self.token.startswith("save_"):
                raise ValueError("Only 'save_NAME' is valid in the body of a "
                                 "NMR-STAR file. Found '" + self.token + "'.",
                                 self.get_line_number())

            if len(self.token) < 6:
                raise ValueError("'save_' must be followed by saveframe name. "
                                 "You have a 'save_' tag which is illegal "
                                 "without a specified saveframe name.",
                                 self.get_line_number())

            if self.delimiter != " ":
                raise ValueError("The save_ keyword may not be quoted or "
                                 "semicolon-delineated.",
                                 self.get_line_number())

            # Add the saveframe
            curframe = Saveframe.from_scratch(self.token[5:], source=source)
            self.ent.add_saveframe(curframe)

            # We are in a saveframe
            while self.get_token() != None:

                if self.token == "loop_":
                    if self.delimiter != " ":
                        raise ValueError("The loop_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())

                    curloop = Loop.from_scratch(source=source)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() != None:

                        # Add a column
                        if self.token.startswith("_"):
                            if self.delimiter != " ":
                                raise ValueError("Loop tags may not be quoted "
                                                 "or semicolon-delineated.",
                                                 self.get_line_number())
                            if seen_data:
                                raise ValueError("Cannot have more loop tags "
                                                 "after loop data.")
                            curloop.add_column(self.token)

                        # On to data
                        else:

                            # Now that we have the columns we can add the loop
                            #  to the current saveframe
                            curframe.add_loop(curloop)

                            # We are in the data block of a loop
                            while self.token != None:
                                if self.token == "stop_":
                                    if self.delimiter != " ":
                                        raise ValueError("The stop_ keyword may"
                                                         " not be quoted or "
                                                         "semicolon-delineated.",
                                                         self.get_line_number())
                                    if len(curloop.columns) == 0:
                                        if (RAISE_PARSE_WARNINGS and
                                                "tag-only-loop" not in WARNINGS_TO_IGNORE):
                                            raise ValueError("Loop with no "
                                                             "tags.", self.get_line_number())
                                        curloop = None
                                    if (not seen_data and
                                            RAISE_PARSE_WARNINGS and
                                            "empty-loop" not in WARNINGS_TO_IGNORE):
                                        raise ValueError("Loop with no data.",
                                                         self.get_line_number())
                                    else:
                                        if len(curdata) > 0:
                                            curloop.add_data(curdata,
                                                             rearrange=True)
                                        curloop = None
                                        curdata = []

                                    curloop = None
                                    in_loop = False
                                    break
                                else:
                                    if len(curloop.columns) == 0:
                                        raise ValueError("Data found in loop "
                                                         "before loop tags.",
                                                         self.get_line_number())

                                    if (self.token in self.reserved and
                                            self.delimiter == " "):
                                        raise ValueError("Cannot use keywords "
                                                         "as data values unless"
                                                         " quoted or semi-colon"
                                                         " delineated. Perhaps "
                                                         "this is a loop that "
                                                         "wasn't properly "
                                                         "terminated? Illegal "
                                                         "value: " + self.token,
                                                         self.get_line_number())
                                    curdata.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.get_token()

                    if self.token != "stop_":
                        raise ValueError("Loop improperly terminated at end of"
                                         " file.", self.get_line_number())

                # Close saveframe
                elif self.token == "save_":
                    if self.delimiter not in " ;":
                        raise ValueError("The save_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())
                    if not ALLOW_V2_ENTRIES:
                        if curframe.tag_prefix is None:
                            raise ValueError("The tag prefix was never set! "
                                             "Either the saveframe had no tags,"
                                             " you tried to read a version 2.1 "
                                             "file without setting "
                                             "ALLOW_V2_ENTRIES to True, or "
                                             "there is something else wrong "
                                             "with your file. Saveframe error "
                                             "occured: '%s'" % curframe.name)
                    curframe = None
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    raise ValueError("Invalid token found in saveframe '" +
                                     curframe.name +  "': '" + self.token +
                                     "'", self.get_line_number())

                # Add a tag
                else:
                    if self.delimiter != " ":
                        raise ValueError("Saveframe tags may not be quoted or "
                                         "semicolon-delineated.",
                                         self.get_line_number())
                    curtag = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.get_token()
                    if self.delimiter == " ":
                        if self.token in self.reserved:
                            raise ValueError("Cannot use keywords as data values"
                                             " unless quoted or semi-colon "
                                             "delineated. Illegal value: " +
                                             self.token, self.get_line_number())
                        if self.token.startswith("_"):
                            raise ValueError("Cannot have a tag value start "
                                             "with an underscore unless the "
                                             "entire value is quoted. You may "
                                             "be missing a data value on the "
                                             "previous line. Illegal value: " +
                                             self.token, self.get_line_number())
                    curframe.add_tag(curtag, self.token, self.get_line_number())

            if self.token != "save_":
                raise ValueError("Saveframe improperly terminated at end of "
                                 "file.", self.get_line_number())

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        # Reset the parser
        if cnmrstar != None:
            cnmrstar.reset()

        return self.ent

    def real_get_token(self):
        """ Actually processes the input data to find a token. get_token
        is just a wrapper around this with some exception handling."""

        # Reset the delimiter
        self.delimiter = " "

        # Nothing left
        if self.token is None:
            return

        # We're at the end if the index is the length
        if self.index == len(self.full_data):
            self.token = None
            return

        # Get just a single line of the file
        raw_tmp = ""
        tmp = ""
        while len(tmp) == 0:
            self.index += len(raw_tmp)

            try:
                newline_index = self.full_data.index("\n", self.index+1)
                raw_tmp = self.full_data[self.index:newline_index]
            except ValueError:
                # End of file
                self.token = self.full_data[self.index:].lstrip(_WHITESPACE)
                if self.token == "":
                    self.token = None
                self.index = len(self.full_data)
                return

            newline_index = self.full_data.index("\n", self.index+1)
            raw_tmp = self.full_data[self.index:newline_index+1]
            tmp = raw_tmp.lstrip(_WHITESPACE)

        # If it is a multiline comment, recalculate our viewing window
        if tmp[0:2] == ";\n":
            try:
                qstart = self.full_data.index(";\n", self.index)
                qend = self.full_data.index("\n;", qstart) + 3
            except ValueError:
                qstart = self.index
                qend = len(self.full_data)

            raw_tmp = self.full_data[self.index:qend]
            tmp = raw_tmp.lstrip()

        self.index += len(raw_tmp) - len(tmp)

        # Skip comments
        if tmp.startswith("#"):
            self.index += len(tmp)
            return self.get_token()

        # Handle multi-line values
        if tmp.startswith(";\n"):
            tmp = tmp[2:]

            # Search for end of multi-line value
            if "\n;" in tmp:
                until = tmp.index("\n;")
                valid = self.index_handle(tmp, "\n;\n")

                # The line is terminated properly
                if valid == until:
                    self.token = tmp[0:until+1]
                    self.index += until+4
                    self.delimiter = ";"
                    return

                # The line was terminated improperly
                else:
                    if self.next_whitespace(tmp[until+2:]) == 0:
                        if (RAISE_PARSE_WARNINGS and
                                "bad-multiline" not in WARNINGS_TO_IGNORE):
                            raise ValueError("Warning: Technically invalid line"
                                             " found in file. Multiline values "
                                             "should terminate with \\n;\\n but"
                                             " in this file only \\n; with "
                                             "non-return whitespace following "
                                             "was found.",
                                             self.get_line_number())
                        self.token = tmp[0:until+1]
                        self.index += until + 4
                        self.delimiter = ";"
                        return
                    else:
                        raise ValueError('Invalid file. A multi-line value '
                                         'ended with a "\\n;" and then a '
                                         'non-whitespace value. Multi-line '
                                         'values should end with "\\n;\\n".',
                                         self.get_line_number())
            else:
                raise ValueError("Invalid file. Multi-line comment never ends."
                                 " Multi-line comments must terminate with a "
                                 "line that consists ONLY of a ';' without "
                                 "characters before or after. (Other than the "
                                 "newline.)", self.get_line_number())

        # Handle values quoted with '
        if tmp.startswith("'"):
            until = self.index_handle(tmp, "'", 1)

            if until is None:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until+1:until+2] not in _WHITESPACE:
                    until = self.index_handle(tmp, "'", until+1)
            except TypeError:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until+1
            self.delimiter = "'"
            return

        # Handle values quoted with "
        if tmp.startswith('"'):
            until = self.index_handle(tmp, '"', 1)

            if until is None:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.get_line_number())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until+1:until+2] not in _WHITESPACE:
                    until = self.index_handle(tmp, '"', until+1)
            except TypeError:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until+1
            self.delimiter = '"'
            return

        # Figure out where this token ends
        white = self.next_whitespace(tmp)
        if white == len(tmp):
            self.token = tmp
            self.index += len(self.token) + 1
            if self.token[0] == "$" and len(self.token) > 1:
                self.delimiter = '$'
            return

        # The token isn't anything special, just return it
        self.index += white
        self.token = tmp[0:white]
        if self.token[0] == "$" and len(self.token) > 1:
            self.delimiter = '$'
        return

class Schema(object):
    """A BMRB schema. Used to validate STAR files."""

    def __init__(self, schema_file=None):
        """Initialize a BMRB schema. With no arguments the most
        up-to-date schema will be fetched from the BMRB FTP site.
        Otherwise pass a URL or a file to load a schema from using the
        schema_file keyword argument."""

        self.headers = []
        self.schema = {}
        self.schema_order = []
        self.category_order = []
        self.version = "unknown"
        self.data_types = {}

        # Try loading from the internet first
        if schema_file is None:
            schema_file = _SCHEMA_URL
        self.schema_file = schema_file

        # Get the schema from the internet, wrap in StringIO and pass that
        #  to the csv reader
        schem_stream = _interpret_file(schema_file)
        fix_newlines = StringIO('\n'.join(schem_stream.read().splitlines()))

        csv_reader_instance = csv_reader(fix_newlines)
        self.headers = next(csv_reader_instance)

        # Skip the header descriptions and header index values and anything
        #  else before the real data starts
        tmp_line = next(csv_reader_instance)
        try:
            while tmp_line[0] != "TBL_BEGIN":
                tmp_line = next(csv_reader_instance)
        except IndexError:
            raise ValueError("Could not parse a schema from the specified "
                             "URL: %s" % schema_file)
        self.version = tmp_line[3]

        # Determine the primary key field
        tag_field = self.headers.index("Tag")
        nullable = self.headers.index("Nullable")

        for line in csv_reader_instance:

            if line[0] == "TBL_END":
                break

            # Convert nulls
            if line[nullable] == "NOT NULL":
                line[nullable] = False
            else:
                line[nullable] = True

            self.schema[line[tag_field].lower()] = dict(zip(self.headers, line))

            self.schema_order.append(line[tag_field])
            formatted = _format_category(line[tag_field])
            if formatted not in self.category_order:
                self.category_order.append(formatted)

        # Read in the data types
        types_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                  "reference_files/data_types.csv")

        with open(types_file, "rt") as types_file:
            csv_reader_instance = csv_reader(types_file)

            for item in csv_reader_instance:
                self.data_types[item[0]] = item[1]

    def __repr__(self):
        """Return how we can be initialized."""

        return "bmrb.Schema(schema_file='%s') version %s" % (self.schema_file,
                                                             self.version)

    def __str__(self):
        """Print the schema that we are adhering to."""

        return self.string_representation()

    def string_representation(self, search=None):
        """ Prints all the tags in the schema if search is not specified
        and prints the tags that contain the search string if it is."""

        # Get the longest lengths
        lengths = [max([len(_format_tag(x)) for x in self.schema_order])]

        values = []
        for key in self.schema.keys():
            sc = self.schema[key]
            values.append((sc["Data Type"], sc["Nullable"], sc["SFCategory"],
                           sc["Tag"]))

        for y in range(0, len(values[0])):
            lengths.append(max([len(str(x[y])) for x in values]))

        text = """BMRB schema from: '%s' version '%s'
%s
  %-*s %-*s %-*s %-*s
""" % (self.schema_file, self.version, "Tag_Prefix", lengths[0], "Tag",
       lengths[1]-6, "Type", lengths[2], "Null_Allowed", lengths[3],
       "SF_Category")

        last_tag = ""

        for tag in self.schema_order:
            # Skip to the next tag if there is a search and it fails
            if search and search not in tag:
                continue
            st = self.schema.get(tag.lower(), None)
            tag_cat = _format_category(tag)
            if st:
                if tag_cat != last_tag:
                    last_tag = tag_cat
                    text += "\n%-30s\n" % tag_cat

                text += "  %-*s %-*s %-*s  %-*s\n" % (lengths[0], _format_tag(tag),
                                                      lengths[1], st["Data Type"],
                                                      lengths[2], st["Nullable"],
                                                      lengths[3], st["SFCategory"])

        return text

    def add_tag(self, tag, tag_type, null_allowed, sf_category, loop_flag,
                after=None):
        """ Adds the specified tag to the tag dictionary. You must provide:

        1) The full tag as such:
            "_Entry_interview.Sf_category"
        2) The tag type which is one of the following:
            "INTEGER"
            "FLOAT"
            "CHAR(len)"
            "VARCHAR(len)"
            "TEXT"
            "DATETIME year to day"
        3) A python True/False that indicates whether null values are allowed.
        4) The sf_category of the parent saveframe.
        5) A True/False value which indicates if this tag is a loop tag.
        6) Optional: The tag to order this tag behind when normalizing
           saveframes."""

        # Add the underscore preceeding the tag
        if tag[0] != "_":
            tag = "_" + tag

        # See if the tag is already in the schema
        if tag.lower() in self.schema:
            raise ValueError("Cannot add a tag to the schema that is already in"
                             " the schema: %s" % tag)

        # Check the tag type
        tag_type = tag_type.upper()
        if tag_type not in ["INTEGER", "FLOAT", "TEXT", "DATETIME year to day"]:
            if tag_type.startswith("CHAR(") or tag_type.startswith("VARCHAR("):
                # This will allow things through that have extra junk on the
                #  end, but in general it is okay to be forgiving as long as we
                #   can guess what they mean.
                length = tag_type[tag_type.index("(")+1:tag_type.index(")")]
                # Check the length for non-numbers and 0
                try:
                    1/int(length)
                except (ValueError, ZeroDivisionError):
                    raise ValueError("Illegal length specified in tag type: "
                                     "%s " % length)

                # Cut off anything that might be at the end
                tag_type = tag_type[0:tag_type.index(")")+1]
            else:
                raise ValueError("The tag type you provided is not valid. "
                                 "Please use a type as specified in the help "
                                 "for this method.")

        # Check the null allowed
        if str(null_allowed).lower() == "false":
            null_allowed = False
        if str(null_allowed).lower() == "true":
            null_allowed = True
        if not (null_allowed is True or null_allowed is False):
            raise ValueError("Please specify whether null is allowed with True/"
                             "False")

        # Check the category
        if not sf_category:
            raise ValueError("Please provide the sf_category of the parent "
                             "saveframe.")

        # Check the loop flag
        if loop_flag != True and loop_flag != False:
            raise ValueError("Invalid loop_flag. Please specify True or False.")

        # Conditionally check the tag to insert after
        new_tag_pos = len(self.schema_order)
        if after != None:
            try:
                # See if the tag with caps exists in the order
                new_tag_pos = self.schema_order.index(after) + 1
            except ValueError:
                try:
                    # See if the tag in lowercase exists in the order
                    new_tag_pos = [x.lower() for x in
                                   self.schema_order].index(after.lower()) + 1
                except ValueError:
                    raise ValueError("The tag you specified to insert this tag "
                                     "after does not exist in the schema.")
        else:
            # Determine a sensible place to put the new tag
            search = _format_category(tag.lower())
            for pos, stag in enumerate([x.lower() for x in self.schema_order]):
                if stag.startswith(search):
                    new_tag_pos = pos + 1

        # Add the new tag to the tag order and tag list
        self.schema_order.insert(new_tag_pos, tag)
        self.category_order.insert(new_tag_pos, "_" + _format_tag(tag))

        # Calculate up the 'Dictionary Sequence' based on the tag position
        new_tag_pos = (new_tag_pos - 1) * 10

        def _test_pos(position, schema):
            for item in schema.schema.values():
                if float(item["Dictionary sequence"]) == position:
                    return _test_pos(position + 1, schema)
            return position

        new_tag_pos = _test_pos(new_tag_pos, self)

        self.schema[tag.lower()] = {"Data Type":tag_type, "Loopflag": loop_flag,
                                    "Nullable":null_allowed, "public": "Y",
                                    "SFCategory":sf_category, "Tag":tag,
                                    "Dictionary sequence": new_tag_pos}

    def convert_tag(self, tag, value, linenum=None):
        """ Converts the provided tag from string to the appropriate
        type as specified in this schema."""

        # If we don't know what the tag is, just return it
        if tag.lower() not in self.schema:
            if (RAISE_PARSE_WARNINGS and
                    "tag-not-in-schema" not in WARNINGS_TO_IGNORE):
                raise ValueError("There is a tag in the file that isn't in the"
                                 " schema: '%s' on line '%s'" % (tag, linenum))
            else:
                if VERBOSE:
                    print("Couldn't convert tag because it is not in the "
                          "dictionary: " + tag)
                return value

        full_tag = self.schema[tag.lower()]

        # Get the type
        valtype, null_allowed = full_tag["Data Type"], full_tag["Nullable"]

        # Check for null
        if value == "." or value == "?":
            if (not null_allowed and RAISE_PARSE_WARNINGS and
                    "invalid-null-value" not in WARNINGS_TO_IGNORE):
                raise ValueError("There is a null in the file that isn't "
                                 "allowed according to the schema: '%s' on "
                                 "line '%s'" % (tag, linenum))
            else:
                return None

        # Keep strings strings
        if "CHAR" in valtype or "VARCHAR" in valtype or "TEXT" in valtype:
            return value

        # Convert ints
        if "INTEGER" in valtype:
            try:
                return int(value)
            except:
                raise ValueError("Could not parse the file because a value "
                                 "that should be an INTEGER is not. Please "
                                 "turn off CONVERT_DATATYPES or fix the file. "
                                 "Tag: '%s' on line '%s'" % (tag, linenum))

        # Convert floats
        if "FLOAT" in valtype:
            try:
                # If we used int() we would lose the precision
                return decimal.Decimal(value)
            except:
                raise ValueError("Could not parse the file because a value "
                                 "that should be a FLOAT is not. Please turn "
                                 "off CONVERT_DATATYPES or fix the file. Tag: "
                                 "'%s' on line '%s'" % (tag, linenum))

        if "DATETIME year to day" in valtype:
            try:
                year, month, day = [int(x) for x in value.split("-")]
                return date(year, month, day)
            except:
                raise ValueError("Could not parse the file because a value "
                                 "that should be a DATETIME is not. Please "
                                 "turn off CONVERT_DATATYPES or fix the file. "
                                 "Tag: '%s' on line '%s'" % (tag, linenum))

        # We don't know the data type, so just keep it a string
        return value

    def val_type(self, tag, value, category=None, linenum=None):
        """ Validates that a tag matches the type it should have
        according to this schema."""

        if tag.lower() not in self.schema:
            return ["Tag '%s' not found in schema. Line '%s'." %
                    (tag, linenum)]

        # We will skip type checks for None's
        was_none = value is None

        # Allow manual specification of conversions for booleans, Nones, etc.
        if value in STR_CONVERSION_DICT:
            if any(isinstance(value, type(x)) for x in STR_CONVERSION_DICT):
                value = STR_CONVERSION_DICT[value]

        # Value should always be string
        if not isinstance(value, str):
            value = str(value)

        # Make local copies of the fields we care about
        full_tag = self.schema[tag.lower()]
        bmrb_type = full_tag["BMRB data type"]
        valtype = full_tag["Data Type"]
        null_allowed = full_tag["Nullable"]
        allowed_category = full_tag["SFCategory"]
        capitalized_tag = full_tag["Tag"]

        if category != None:
            if category != allowed_category:
                return ["The tag '%s' in category '%s' should be in category "
                        "'%s'." % (capitalized_tag, category, allowed_category)]

        if value == ".":
            if not null_allowed:
                return ["Value cannot be NULL but is: '%s':'%s' on line '%s'."
                        % (capitalized_tag, value, linenum)]
            return []

        if "CHAR" in valtype:
            length = int(valtype[valtype.index("(")+1:valtype.index(")")])
            if len(str(value)) > length:
                return ["Length of '%d' is too long for %s: "
                        "'%s':'%s' on line '%s'." %
                        (len(value), valtype, capitalized_tag, value, linenum)]

        # Check that the value matches the regular expression for the type
        if not was_none and not re.match(self.data_types[bmrb_type], str(value)):
            return ["Value does not match specification: '%s':'%s' on line '%s'"
                    ".\n     Type specified: %s\n     Regular expression for "
                    "type: '%s'" % (capitalized_tag, value, linenum, bmrb_type,
                              self.data_types[bmrb_type])]

        # Check the tag capitalization
        if tag != capitalized_tag:
            return ["The tag '%s' is improperly capitalized but otherwise "
                    "valid. Should be '%s'." % (tag, capitalized_tag)]
        return []

class Entry(object):
    """An OO representation of a BMRB entry. You can initialize this
    object several ways; (e.g. from a file, from the official database,
    from scratch) see the classmethods."""

    def __delitem__(self, item):
        """Remove the indicated saveframe."""

        if isinstance(item, Saveframe):
            del self.frame_list[self.frame_list.index(item)]
            return
        else:
            self.__delitem__(self.__getitem__(item))

    def __eq__(self, other):
        """Returns True if this entry is equal to another entry, false
        if it is not equal."""

        return len(self.compare(other)) == 0

    def __ne__(self, other):
        """It isn't enough to define __eq__ in python2.x."""

        return not self.__eq__(other)

    def __getitem__(self, item):
        """Get the indicated saveframe."""

        try:
            return self.frame_list[item]
        except TypeError:
            return self.get_saveframe_by_name(item)

    def __init__(self, **kargs):
        """Don't use this directly, use from_file, from_scratch,
        from_string, or from_database to construct."""

        # Default initializations
        self.entry_id = 0
        self.frame_list = []
        self.source = None

        # They initialized us wrong
        if len(kargs) == 0:
            raise ValueError("You must provide either a Entry ID, a file name, "
                             "an entry number, or a string to initialize. Use "
                             "the class methods.")
        elif len(kargs) > 1:
            raise ValueError("You cannot provide multiple optional arguments. "
                             "Use the class methods instead of initializing "
                             "directly.")

        # Initialize our local variables
        self.frame_list = []

        if 'the_string' in kargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kargs:
            star_buffer = _interpret_file(kargs['file_name'])
            self.source = "from_file('%s')" % kargs['file_name']
        elif 'entry_num' in kargs:
            self.source = "from_database(%s)" % kargs['entry_num']

            # The location to fetch entries from
            entry_number = kargs['entry_num']
            url = 'http://rest.bmrb.wisc.edu/bmrb/NMR-STAR3/%s' % entry_number

            # Parse from the official BMRB library
            try:
                if PY3:
                    star_buffer = StringIO(urlopen(url).read().decode())
                else:
                    star_buffer = urlopen(url)
            except HTTPError:
                raise IOError("Entry '%s' does not exist in the public "
                              "database." % entry_number)
            except URLError:
                raise IOError("You don't appear to have an active internet "
                              "connection. Cannot fetch entry.")
        else:
            # Initialize a blank entry
            self.entry_id = kargs['entry_id']
            self.source = "from_scratch()"
            return

        # Load the BMRB entry from the file
        parser = _Parser(entry_to_parse_into=self)
        parser.parse(star_buffer.read(), source=self.source)

    def __len__(self):
        """ Returns the number of saveframes in the entry."""

        return len(self.frame_list)

    def __lt__(self, other):
        """Returns true if this entry is less than another entry."""

        return self.entry_id > other.entry_id

    def __repr__(self):
        """Returns a description of the entry."""

        return "<bmrb.Entry '%s' %s>" % (self.entry_id, self.source)

    def __setitem__(self, key, item):
        """Set the indicated saveframe."""

        # It is a saveframe
        if isinstance(item, Saveframe):
            # Add by ordinal
            try:
                self.frame_list[key] = item
            except TypeError:
                # Add by key
                if key in self.frame_dict():
                    dict((frame.name, frame) for frame in self.frame_list)
                    for pos, frame in enumerate(self.frame_list):
                        if frame.name == key:
                            self.frame_list[pos] = item
                else:
                    raise KeyError("Saveframe with name '%s' does not exist "
                                   "and therefore cannot be written to. Use "
                                   "the add_saveframe method to add new "
                                   "saveframes." % key)
        else:
            raise ValueError("You can only assign an entry to a saveframe"
                             " splice.")

    def __str__(self):
        """Returns the entire entry in STAR format as a string."""

        ret_string = ("data_%s\n\n" % self.entry_id +
                      "\n".join([str(frame) for frame in self.frame_list]))
        return ret_string

    @classmethod
    def from_database(cls, entry_num):
        """Create an entry corresponding to the most up to date entry on
        the public BMRB server. (Requires ability to initiate outbound
        HTTP connections.)"""

        # Try to load the entry using JSON
        try:
            entry_url = _API_URL + "/rest/entry/%s/"
            entry_url = entry_url % entry_num

            # Convert bytes to string if python3
            serialized_ent = urlopen(entry_url).read()
            if PY3:
                serialized_ent = serialized_ent.decode()

            # Parse JSON string to dictionary
            json_data = json.loads(serialized_ent)
            if "error" in json_data:
                if "does not exist" in json_data["error"]:
                    raise IOError("Entry '%s' does not exist in the public "
                                  "database." % entry_num)
                else:
                    raise ValueError("An error occured while fetching the entry"
                                     ": %s" % json_data["error"])
            entry_dictionary = json_data[str(entry_num)]
            ent = Entry.from_json(entry_dictionary)

            # Update the entry source
            ent_source = "from_database(%s)" % entry_num
            ent.source = ent_source
            for each_saveframe in ent:
                each_saveframe.source = ent_source
                for each_loop in each_saveframe:
                    each_loop.source = ent_source

            # TODO: Delete this once the database is remediated
            # Convert datatypes
            if CONVERT_DATATYPES:
                schem = _get_schema()
                for each_saveframe in ent:
                    for tag in each_saveframe.tags:
                        cur_tag = each_saveframe.tag_prefix + "." + tag[0]
                        tag[1] = schem.convert_tag(cur_tag, tag[1],
                                                   linenum="SF %s" %
                                                   each_saveframe.name)
                    for loop in each_saveframe:
                        for row in loop.data:
                            for pos in range(0, len(row)):
                                catgry = loop.category + "." + loop.columns[pos]
                                linenum = "Loop %s" % loop.category
                                row[pos] = schem.convert_tag(catgry, row[pos],
                                                             linenum=linenum)

            return ent
        # The entry doesn't exist
        except KeyError:
            raise IOError("Entry '%s' does not exist in the public database." %
                          entry_num)
        except (HTTPError, URLError):
            if VERBOSE:
                print("BMRB API server appears to be down. Attempting to load "
                      "from FTP site.")
            return cls(entry_num=entry_num)

    @classmethod
    def from_file(cls, the_file):
        """Create an entry by loading in a file. If the_file starts with
        http://, https://, or ftp:// then we will use those protocols to
        attempt to open the file."""

        return cls(file_name=the_file)

    @classmethod
    def from_json(cls, json_dict):
        """Create an entry from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python "
                                 "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        if "saveframes" not in json_dict:
            raise ValueError("The JSON you provide must be a hash and must"
                             " contain the key 'saveframes' - even if the key "
                             "points to 'None'.")

        if "entry_id" not in json_dict and "bmrb_id" not in json_dict:
            raise ValueError("The JSON you provide must be a hash and must"
                             " contain the key 'entry_id' - even if the key "
                             "points to 'None'.")


        # Until the migration is complete, 'bmrb_id' is a synonym for
        #  'entry_id'
        if 'entry_id' not in json_dict:
            json_dict['entry_id'] = json_dict['bmrb_id']

        # Create an entry from scratch and populate it
        ret = Entry.from_scratch(json_dict['entry_id'])
        ret.frame_list = [Saveframe.from_json(x) for x in
                          json_dict['saveframes']]
        ret.source = "from_json()"

        # Return the new loop
        return ret

    @classmethod
    def from_string(cls, the_string):
        """Create an entry by parsing a string."""

        return cls(the_string=the_string)

    @classmethod
    def from_scratch(cls, entry_id):
        """Create an empty entry that you can programatically add to.
        You must pass a value corresponding to the Entry ID.
        (The unique identifier "xxx" from "data_xxx".)"""

        return cls(entry_id=entry_id)

    def add_saveframe(self, frame):
        """Add a saveframe to the entry."""

        if not isinstance(frame, Saveframe):
            raise ValueError("You can only add instances of saveframes "
                             "using this method.")

        # Do not allow the addition of saveframes with the same name
        #  as a saveframe which already exists in the entry
        if frame.name in self.frame_dict():
            raise ValueError("Cannot add a saveframe with name '%s' since a "
                             "saveframe with that name already exists in the "
                             "entry." % frame.name)

        self.frame_list.append(frame)

    def compare(self, other):
        """Returns the differences between two entries as a list.
        Otherwise returns 1 if different and 0 if equal. Non-equal
        entries will always be detected, but specific differences
        detected depends on order of entries."""

        diffs = []
        if self is other:
            return []
        if isinstance(other, str):
            if str(self) == other:
                return []
            else:
                return ['String was not exactly equal to entry.']
        try:
            if str(self.entry_id) != str(other.entry_id):
                diffs.append("Entry ID does not match between entries: "
                             "'%s' vs '%s'." % (self.entry_id, other.entry_id))
            if len(self.frame_list) != len(other.frame_list):
                diffs.append("The number of saveframes in the entries are not"
                             " equal: '%d' vs '%d'." %
                             (len(self.frame_list), len(other.frame_list)))
            for frame in self.frame_dict():
                if other.frame_dict().get(frame, None) is None:
                    diffs.append("No saveframe with name '%s' in other entry." %
                                 self.frame_dict()[frame].name)
                else:
                    comp = self.frame_dict()[frame].compare(
                        other.frame_dict()[frame])
                    if len(comp) > 0:
                        diffs.append("Saveframes do not match: '%s'." %
                                     self.frame_dict()[frame].name)
                        diffs.extend(comp)

        except AttributeError as err:
            diffs.append("An exception occured while comparing: '%s'." % err)

        return diffs

    def frame_dict(self):
        """Returns a dictionary of saveframe name -> saveframe object"""

        fast_dict = dict((frame.name, frame) for frame in self.frame_list)

        # If there are no duplicates then continue
        if len(fast_dict) == len(self.frame_list):
            return fast_dict

        # Figure out where the duplicate is
        frame_dict = {}

        for frame in self.frame_list:
            if frame.name in frame_dict:
                raise ValueError("The entry has multiple saveframes with the "
                                 "same name. That is illegal. Please remove or "
                                 "rename one. Duplicate name: %s" % frame.name)
            frame_dict[frame.name] = True

    def get_json(self, serialize=True):
        """ Returns the entry in JSON format. If serialize is set to
        False a dictionary representation of the entry that is
        serializeable is returned."""

        frames = [x.get_json(serialize=False) for x in self.frame_list]

        # Store the "bmrb_id" as well to prevent old code from breaking
        entry_dict = {
            "entry_id": self.entry_id,
            "bmrb_id": self.entry_id,
            "saveframes": frames
        }

        if serialize:
            return json.dumps(entry_dict, default=_json_serialize)
        else:
            return entry_dict

    def get_loops_by_category(self, value):
        """Allows fetching loops by category."""

        value = _format_category(value).lower()

        results = []
        for frame in self.frame_list:
            for one_loop in frame.loops:
                if one_loop.category.lower() == value:
                    results.append(one_loop)
        return results

    def get_saveframe_by_name(self, frame):
        """Allows fetching a saveframe by name."""

        frames = self.frame_dict()
        if frame in frames:
            return frames[frame]
        else:
            raise KeyError("No saveframe with name '%s'" % frame)

    def get_saveframes_by_category(self, value):
        """Allows fetching saveframes by category."""

        return self.get_saveframes_by_tag_and_value("sf_category", value)

    def get_saveframes_by_tag_and_value(self, tag_name, value):
        """Allows fetching saveframe(s) by tag and tag value."""

        ret_frames = []

        for frame in self.frame_list:
            results = frame.get_tag(tag_name)
            if results != [] and results[0] == value:
                ret_frames.append(frame)

        return ret_frames

    def get_tag(self, tag, whole_tag=False):
        """ Given a tag (E.g. _Assigned_chem_shift_list.Data_file_name)
        return a list of all values for that tag. Specify whole_tag=True
        and the [tag_name, tag_value (,tag_linenumber)] pair will be
        returned."""

        if "." not in str(tag) and not ALLOW_V2_ENTRIES:
            raise ValueError("You must provide the tag category to call this"
                             " method at the entry level.")

        results = []
        for frame in self.frame_list:
            results.extend(frame.get_tag(tag, whole_tag=whole_tag))

        return results

    def get_tags(self, tags):
        """ Given a list of tags, get all of the tags and return the
        results in a dictionary."""

        # All tags
        if tags is None or not isinstance(tags, list):
            raise ValueError("Please provide a list of tags.")

        results = {}
        for tag in tags:
            results[tag] = self.get_tag(tag)

        return results

    def normalize(self, schema=None):
        """ Sorts saveframes, loops, and tags according to the schema
        provided (or BMRB default if none provided) and according
        to the assigned ID."""

        # The saveframe/loop order
        ordering = _get_schema(schema).category_order
        # Use these to sort saveframes and loops
        def sf_key(x):
            """ Helper function to sort the saveframes."""

            try:
                return (ordering.index(x.tag_prefix), x.get_tag("ID"))
            except ValueError:
                # Generate an arbitrary sort order for saveframes that aren't
                #  in the schema but make sure that they always come after
                #   saveframes in the schema
                return (len(ordering) + hash(x), x.get_tag("ID"))

        def loop_key(x):
            """ Helper function to sort the loops."""

            try:
                return ordering.index(x.category)
            except ValueError:
                # Generate an arbitrary sort order for loops that aren't in the
                #  schema but make sure that they always come after loops in the
                #   schema
                return len(ordering) + hash(x)

        # Go through all the saveframes
        for each_frame in self:
            each_frame.sort_tags()
            # Iterate through the loops
            for each_loop in each_frame:
                each_loop.sort_tags()

                # See if we can sort the rows (in addition to columns)
                try:
                    each_loop.sort_rows("Ordinal")
                except ValueError:
                    pass
            each_frame.loops.sort(key=loop_key)
        self.frame_list.sort(key=sf_key)

    def nef_string(self):
        """ Returns a string representation of the entry in NEF. """

        # Store the current values of these module variables
        global STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS, DONT_SHOW_COMMENTS
        tmp_dict, tmp_loops_state = STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS
        tmp_dont_show_comments = DONT_SHOW_COMMENTS

        # Change to NEF defaults and get the string representation
        enable_nef_defaults()
        result = str(self)

        # Revert module variables
        STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS = tmp_dict, tmp_loops_state
        DONT_SHOW_COMMENTS = tmp_dont_show_comments
        return result

    def rename_saveframe(self, original_name, new_name):
        """ Renames a saveframe and updates all pointers to that
        saveframe in the entry with the new name."""

        # Strip off the starting $ in the names
        if original_name.startswith("$"):
            original_name = original_name[1:]
        if new_name.startswith("$"):
            new_name = new_name[1:]

        # Make sure there is no saveframe called what
        #  the new name is
        if [x.name for x in self.frame_list].count(new_name) > 0:
            raise ValueError("Cannot rename a saveframe as '%s' because a "
                             "saveframe with that name already exists." %
                             new_name)

        # This can raise a ValueError, but no point catching it
        #  since it really is a ValueError if they provide a name
        #   of a saveframe that doesn't exist in the entry.
        change_frame = self.get_saveframe_by_name(original_name)

        # Make sure the new saveframe name is valid
        for char in new_name:
            if char in _WHITESPACE:
                raise ValueError("You cannot have whitespace characters in a "
                                 "saveframe name. Illegal character: '%s'" %
                                 char)

        # Update the saveframe
        change_frame['Sf_framecode'] = new_name
        change_frame.name = new_name

        # What the new references should look like
        old_reference = "$" + original_name
        new_reference = "$" + new_name

        # Go through all the saveframes
        for each_frame in self:
            # Iterate through the tags
            for each_tag in each_frame.tags:
                if each_tag[1] == old_reference:
                    each_tag[1] = new_reference
            # Iterate through the loops
            for each_loop in each_frame:
                for each_row in each_loop:
                    for pos, val in enumerate(each_row):
                        if val == old_reference:
                            each_row[pos] = new_reference

    def print_tree(self):
        """Prints a summary, tree style, of the frames and loops in
        the entry."""

        print(repr(self))
        for pos, frame in enumerate(self):
            print("\t[%d] %s" % (pos, repr(frame)))
            for pos2, one_loop in enumerate(frame):
                print("\t\t[%d] %s" % (pos2, repr(one_loop)))

    def validate(self, validate_schema=True, schema=None,
                 validate_star=True):
        """Validate an entry in a variety of ways. Returns a list of
        errors found. 0-length list indicates no errors found. By
        default all validation modes are enabled.

        validate_schema - Determines if the entry is validated against
        the NMR-STAR schema. You can pass your own custom schema if desired,
        otherwise the schema will be fetched from the BMRB servers.

        validate_star - Determines if the STAR syntax checks are ran."""

        errors = []

        # They should validate for something...
        if not validate_star and not validate_schema:
            errors.append("Validate() should be called with at least one "
                          "validation method enabled.")

        if validate_star:

            # Check for saveframes with same name
            saveframe_names = sorted(x.name for x in self)
            for ordinal in range(0, len(saveframe_names)-2):
                if saveframe_names[ordinal] == saveframe_names[ordinal+1]:
                    errors.append("Multiple saveframes with same name: '%s'" %
                                  saveframe_names[ordinal])

            # Check for dangling references
            fdict = self.frame_dict()

            for each_frame in self:
                # Iterate through the tags
                for each_tag in each_frame.tags:
                    tag_copy = str(each_tag[1])
                    if (tag_copy.startswith("$")
                            and tag_copy[1:] not in fdict):
                        errors.append("Dangling saveframe reference '%s' in "
                                      "tag '%s.%s'" % (each_tag[1],
                                                       each_frame.tag_prefix,
                                                       each_tag[0]))

                # Iterate through the loops
                for each_loop in each_frame:
                    for each_row in each_loop:
                        for pos, val in enumerate(each_row):
                            val = str(val)
                            if val.startswith("$") and val[1:] not in fdict:
                                errors.append("Dangling saveframe reference "
                                              "'%s' in tag '%s.%s'" %
                                              (val,
                                               each_loop.category,
                                               each_loop.columns[pos]))

        # Ask the saveframes to check themselves for errors
        for frame in self:
            errors.extend(frame.validate(validate_schema=validate_schema,
                                         schema=schema,
                                         validate_star=validate_star))

        return errors

class Saveframe(object):
    """A saveframe. Use the classmethod from_scratch to create one."""

    def __delitem__(self, item):
        """Remove the indicated tag or loop."""

        # If they specify the specific loop to delete, go ahead and delete it
        if isinstance(item, Loop):
            del self.loops[self.loops.index(item)]
            return

        # See if the result of get(item) is a loop. If so, delete it
        # (calls this method recursively)
        to_delete = self.__getitem__(item)
        if isinstance(to_delete, Loop):
            self.__delitem__(to_delete)
            return

        # It must be a tag. Try to delete the tag
        else:
            self.delete_tag(item)

    def __eq__(self, other):
        """Returns True if this saveframe is equal to another saveframe,
        False if it is equal."""

        return len(self.compare(other)) == 0

    def __ne__(self, other):
        """It isn't enough to define __eq__ in python2.x."""

        return not self.__eq__(other)

    def __getitem__(self, item):
        """Get the indicated loop or tag."""

        try:
            return self.loops[item]
        except TypeError:
            results = self.get_tag(item)
            if results != []:
                return results
            else:
                try:
                    return self.loop_dict()[item.lower()]
                except KeyError:
                    raise KeyError("No tag or loop matching '%s'" % item)

    def __len__(self):
        """Return the number of loops in this saveframe."""

        return len(self.loops)

    def __lt__(self, other):
        """Returns True if this saveframe sorts lower than the compared
        saveframe, false otherwise. The alphabetical ordering of the
        saveframe category is used to perform the comparison."""

        return self.tag_prefix < other.tag_prefix

    def __init__(self, **kargs):
        """Don't use this directly. Use the class methods to construct."""

        # They initialized us wrong
        if len(kargs) == 0:
            raise ValueError("Use the class methods to initialize.")

        # Initialize our local variables
        self.tags = []
        self.loops = []
        self.name = ""
        self.source = "unknown"
        self.category = "unset"
        self.tag_prefix = None

        # Update our source if it provided
        if 'source' in kargs:
            self.source = kargs['source']

        if 'the_string' in kargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kargs:
            star_buffer = _interpret_file(kargs['file_name'])
            self.source = "from_file('%s')" % kargs['file_name']
        elif 'saveframe_name' in kargs:
            # If they are creating from scratch, just get the saveframe name
            self.name = kargs['saveframe_name']
            if 'tag_prefix' in kargs:
                self.tag_prefix = _format_category(kargs['tag_prefix'])
            return
                # Creating from template (schema)
        elif 'all_tags' in kargs:
            schema_obj = _get_schema(kargs['schema'])
            schema = schema_obj.schema
            self.category = kargs['category']
            self.name = self.category

            # Make sure it is a valid category
            if self.category not in [x["SFCategory"] for x in schema.values()]:
                raise ValueError("The saveframe category '%s' was not found "
                                 "in the dictionary." % self.category)

            s = sorted(schema.values(),
                       key=lambda x: float(x["Dictionary sequence"]))

            loops_added = []

            for item in s:
                if item["SFCategory"] == self.category:

                    # It is a tag in this saveframe
                    if item["Loopflag"] == "N":

                        ft = _format_tag(item["Tag"])
                        # Set the value for sf_category and sf_framecode
                        if ft == "Sf_category" or ft == "Sf_framecode":
                            self.add_tag(item["Tag"], self.category)
                        else:
                            # Unconditional add
                            if kargs['all_tags']:
                                self.add_tag(item["Tag"], None)
                            # Conditional add
                            else:
                                if item["public"] != "I":
                                    self.add_tag(item["Tag"], None)

                    # It is a contained loop tag
                    else:
                        cat_formatted = _format_category(item["Tag"])
                        if cat_formatted not in loops_added:
                            loops_added.append(cat_formatted)
                            nl = Loop.from_template(cat_formatted,
                                                    all_tags=kargs['all_tags'],
                                                    schema=schema_obj)
                            self.add_loop(nl)

            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kargs and kargs['csv']:
            csvreader = csv_reader(star_buffer)
            tags = next(csvreader)
            values = next(csvreader)
            if len(tags) != len(values):
                raise ValueError("Your CSV data is invalid. The header length"
                                 " does not match the data length.")
            for ordinal in range(0, len(tags)):
                self.add_tag(tags[ordinal], values[ordinal])
            return


        tmp_entry = Entry.from_scratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_1 " + star_buffer.read())
        parser = _Parser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source)

        # Copy the first parsed saveframe into ourself
        if len(tmp_entry.frame_list) > 1:
            raise ValueError("You attempted to parse one saveframe but the "
                             "source you provided had more than one saveframe."
                             " Please either parse all saveframes as an entry "
                             "or only parse one saveframe. Saveframes "
                             "detected: " + str(tmp_entry.frame_list))
        self.tags = tmp_entry[0].tags
        self.loops = tmp_entry[0].loops
        self.name = tmp_entry[0].name
        self.tag_prefix = tmp_entry[0].tag_prefix

    @classmethod
    def from_scratch(cls, sf_name, tag_prefix=None, source="from_scratch()"):
        """Create an empty saveframe that you can programatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""

        return cls(saveframe_name=sf_name, tag_prefix=tag_prefix,
                   source=source)

    @classmethod
    def from_file(cls, the_file, csv=False):
        """Create a saveframe by loading in a file. Specify csv=True is
        the file is a CSV file. If the_file starts with http://,
        https://, or ftp:// then we will use those protocols to attempt
        to open the file."""

        return cls(file_name=the_file, csv=csv)

    @classmethod
    def from_json(cls, json_dict):
        """Create a saveframe from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python "
                                 "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ["name", "tag_prefix", "tags", "loops"]:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a hash and must"
                                 " contain the key '%s' - even if the key "
                                 "points to None." % check)

        # Create a saveframe from scratch and populate it
        ret = Saveframe.from_scratch(json_dict['name'])
        ret.tag_prefix = json_dict['tag_prefix']
        ret.category = json_dict.get('category', 'unset')
        ret.tags = json_dict['tags']
        ret.loops = [Loop.from_json(x) for x in json_dict['loops']]
        ret.source = "from_json()"

        # Return the new loop
        return ret

    @classmethod
    def from_string(cls, the_string, csv=False):
        """Create a saveframe by parsing a string. Specify csv=True is
        the string is in CSV format and not NMR-STAR format."""

        return cls(the_string=the_string, csv=csv)

    @classmethod
    def from_template(cls, category, all_tags=False, schema=None):
        """ Create a saveframe that has all of the tags and loops from the
        schema present. No values will be assigned. Specify the category
        when calling this method.

        The optional argument all_tags forces all tags to be included
        rather than just the mandatory tags."""

        return cls(category=category, all_tags=all_tags,
                   schema=schema, source="from_template()")

    def __repr__(self):
        """Returns a description of the saveframe."""

        return "<bmrb.Saveframe '%s'>" % self.name

    def __setitem__(self, key, item):
        """Set the indicated loop or tag."""

        # It's a loop
        if isinstance(item, Loop):
            try:
                integer = int(str(key))
                self.loops[integer] = item
            except ValueError:
                if key.lower() in self.loop_dict():
                    for pos, tmp_loop in enumerate(self.loops):
                        if tmp_loop.category.lower() == key.lower():
                            self.loops[pos] = item
                else:
                    raise KeyError("Loop with category '%s' does not exist and"
                                   " therefore cannot be written to. Use "
                                   "add_loop instead." % key)
        else:
            # If the tag already exists, set its value
            self.add_tag(key, item, update=True)

    def __str__(self):
        """Returns the saveframe in STAR format as a string."""

        if ALLOW_V2_ENTRIES:
            if self.tag_prefix is None:
                width = max([len(x[0]) for x in self.tags])
            else:
                width = max([len(self.tag_prefix+"."+x[0]) for x in self.tags])
        else:
            if self.tag_prefix is None:
                raise ValueError("The tag prefix was never set!")

            # Make sure this isn't a dummy saveframe before proceeding
            try:
                width = max([len(self.tag_prefix+"."+x[0]) for x in self.tags])
            except ValueError:
                return "\nsave_%s\n\nsave_\n" % self.name

        ret_string = ""

        # Insert the comment if not disabled
        if not DONT_SHOW_COMMENTS:
            if self.category in _COMMENT_DICTIONARY:
                ret_string = _COMMENT_DICTIONARY[self.category]

        # Print the saveframe
        ret_string += "save_%s\n" % self.name
        pstring = "   %%-%ds  %%s\n" % width
        mstring = "   %%-%ds\n;\n%%s;\n" % width

        # Print the tags
        for each_tag in self.tags:
            clean_tag = clean_value(each_tag[1])

            if ALLOW_V2_ENTRIES and self.tag_prefix is None:
                if "\n" in clean_tag:
                    ret_string += mstring % (each_tag[0], clean_tag)
                else:
                    ret_string += pstring % (each_tag[0], clean_tag)
            else:
                formatted_tag = self.tag_prefix + "." + each_tag[0]
                if "\n" in clean_tag:
                    ret_string += mstring % (formatted_tag, clean_tag)
                else:
                    ret_string += pstring % (formatted_tag, clean_tag)

        # Print any loops
        for each_loop in self.loops:
            ret_string += str(each_loop)

        # Close the saveframe
        ret_string += "save_\n"
        return ret_string

    def add_loop(self, loop_to_add):
        """Add a loop to the saveframe loops."""

        if (loop_to_add.category in self.loop_dict() or
                str(loop_to_add.category).lower() in self.loop_dict()):
            if loop_to_add.category is None:
                raise ValueError("You cannot have two loops with the same "
                                 "category in one saveframe. You are getting "
                                 "this error because you haven't yet set your "
                                 "loop categories.")
            else:
                raise ValueError("You cannot have two loops with the same "
                                 "category in one saveframe. Category: '%s'." %
                                 loop_to_add.category)

        self.loops.append(loop_to_add)

    def add_tag(self, name, value, linenum=None, update=False):
        """Add a tag to the tag list. Does a bit of validation and
        parsing. Set update to true to update a tag if it exists rather
        than raise an exception."""

        if "." in name:
            if name[0] != ".":
                prefix = _format_category(name)
                if self.tag_prefix is None:
                    self.tag_prefix = prefix
                elif self.tag_prefix != prefix:
                    raise ValueError("One saveframe cannot have tags with "
                                     "different categories (or tags that don't "
                                     "match the set category)! '%s' vs '%s'." %
                                     (self.tag_prefix, prefix))
                name = name[name.index(".")+1:]
            else:
                name = name[1:]

        # No duplicate tags
        if self.get_tag(name) != []:
            if not update:
                raise ValueError("There is already a tag with the name '%s'." %
                                 name)
            else:
                self.get_tag(name, whole_tag=True)[0][1] = value
                return

        if "." in name:
            raise ValueError("There cannot be more than one '.' in a tag name.")
        if " " in name:
            raise ValueError("Tag names can not contain spaces.")

        # See if we need to convert the datatype
        if CONVERT_DATATYPES:
            new_tag = [name, _get_schema().convert_tag(
                self.tag_prefix + "." + name, value, linenum=linenum)]
        else:
            new_tag = [name, value]

        # Set the category if the tag we are loading is the category
        tagname_lower = name.lower()
        if tagname_lower == "sf_category" or tagname_lower == "_saveframe_category":
            if self.category == "unset":
                self.category = value

        if linenum:
            new_tag.append(linenum)

        if VERBOSE:
            print("Adding tag: '%s' with value '%s'" % (name, value))

        self.tags.append(new_tag)

    def add_tags(self, tag_list, update=False):
        """Adds multiple tags to the list. Input should be a list of
        tuples that are either [key, value] or [key]. In the latter case
        the value will be set to ".".  Set update to true to update a
        tag if it exists rather than raise an exception."""

        for tag_pair in tag_list:
            if len(tag_pair) == 2:
                self.add_tag(tag_pair[0], tag_pair[1], update=update)
            elif len(tag_pair) == 1:
                self.add_tag(tag_pair[0], ".", update=update)
            else:
                raise ValueError("You provided an invalid tag/value to add:"
                                 " '%s'." % tag_pair)

    def compare(self, other):
        """Returns the differences between two saveframes as a list.
        Non-equal saveframes will always be detected, but specific
        differences detected depends on order of saveframes."""

        diffs = []

        # Check if this is literally the same object
        if self is other:
            return []
        # Check if the other object is our string representation
        if isinstance(other, str):
            if str(self) == other:
                return []
            else:
                return ['String was not exactly equal to saveframe.']

        # We need to do this in case of an extra "\n" on the end of one tag
        if str(other) == str(self):
            return []

        # Do STAR comparison
        try:
            if str(self.name) != str(other.name):
                # No point comparing apples to oranges. If the tags are
                #  this different just return
                diffs.append("\tSaveframe names do not match: '%s' vs '%s'." %
                             (self.name, other.name))
                return diffs

            if str(self.tag_prefix) != str(other.tag_prefix):
                # No point comparing apples to oranges. If the tags are
                #  this different just return
                diffs.append("\tTag prefix does not match: '%s' vs '%s'." %
                             (self.tag_prefix, other.tag_prefix))
                return diffs

            if len(self.tags) < len(other.tags):
                diffs.append("\tNumber of tags does not match: '%d' vs '%d'. "
                             "The compared entry has at least one tag this "
                             "entry does not."  %
                             (len(self.tags), len(other.tags)))

            for tag in self.tags:
                other_tag = other.get_tag(tag[0])

                if other_tag == []:
                    diffs.append("\tNo tag with name '%s.%s' in compared "
                                 "entry." % (self.tag_prefix, tag[0]))
                    continue

                # Compare the string version of the tags in case there are
                #  non-string types. Use the conversion dict to get to str
                if (str(STR_CONVERSION_DICT.get(tag[1], tag[1])) !=
                        str(STR_CONVERSION_DICT.get(other_tag[0],
                                                    other_tag[0]))):
                    diffs.append("\tMismatched tag values for tag '%s.%s':"
                                 " '%s' vs '%s'." %
                                 (self.tag_prefix, tag[0],
                                  str(tag[1]).replace("\n", "\\n"),
                                  str(other_tag[0]).replace("\n", "\\n")))

            if len(self.loops) != len(other.loops):
                diffs.append("\tNumber of children loops does not match: "
                             "'%d' vs '%d'." %
                             (len(self.loops), len(other.loops)))

            compare_loop_dict = other.loop_dict()
            for each_loop in self.loops:
                if each_loop.category.lower() in compare_loop_dict:
                    compare = each_loop.compare(
                        compare_loop_dict[each_loop.category.lower()])
                    if len(compare) > 0:
                        diffs.append("\tLoops do not match: '%s'." %
                                     each_loop.category)
                        diffs.extend(compare)
                else:
                    diffs.append("\tNo loop with category '%s' in other"
                                 " entry." % (each_loop.category))

        except AttributeError as err:
            diffs.append("\tAn exception occured while comparing: '%s'." % err)

        return diffs

    def delete_tag(self, tag):
        """Deletes a tag from the saveframe based on tag name."""

        tag = _format_tag(tag).lower()

        for position, each_tag in enumerate(self.tags):
            # If the tag is a match, remove it
            if each_tag[0].lower() == tag:
                return self.tags.pop(position)

        raise KeyError("There is no tag with name '%s' to remove." % tag)

    def get_data_as_csv(self, header=True, show_category=True):
        """Return the data contained in the loops, properly CSVd, as a
        string. Set header to False omit the header. Set show_category
        to False to omit the loop category from the headers."""

        csv_buffer = StringIO()
        cwriter = csv_writer(csv_buffer)

        if header:
            if show_category:
                cwriter.writerow(
                    [str(self.tag_prefix)+"."+str(x[0]) for x in self.tags])
            else:
                cwriter.writerow([str(x[0]) for x in self.tags])

        data = []
        for each_tag in self.tags:
            data.append(each_tag[1])

        cwriter.writerow(data)

        csv_buffer.seek(0)
        return csv_buffer.read().replace('\r\n', '\n')

    def get_json(self, serialize=True):
        """ Returns the saveframe in JSON format. If serialize is set to
        False a dictionary representation of the saveframe that is
        serializeable is returned."""

        saveframe_data = {
            "name": self.name,
            "category": self.category,
            "tag_prefix": self.tag_prefix,
            "tags": [[x[0], x[1]] for x in self.tags],
            "loops": [x.get_json(serialize=False) for x in self.loops]
        }

        if serialize:
            return json.dumps(saveframe_data, default=_json_serialize)
        else:
            return saveframe_data

    def get_loop_by_category(self, name):
        """Return a loop based on the loop name (category)."""

        name = _format_category(name).lower()
        for each_loop in self.loops:
            if str(each_loop.category).lower() == name:
                return each_loop
        raise KeyError("No loop with category '%s'." % name)

    def get_tag(self, query, whole_tag=False):
        """Allows fetching the value of a tag by tag name. Specify
        whole_tag=True and the [tag_name, tag_value] pair will be
        returned."""

        results = []

        # Make sure this is the correct saveframe if they specify a tag
        #  prefix
        if "." in query:
            tag_prefix = _format_category(query)
        else:
            tag_prefix = self.tag_prefix

        # Check the loops
        for each_loop in self.loops:
            if ((each_loop.category is not None and tag_prefix is not None and
                 each_loop.category.lower() == tag_prefix.lower()) or
                    ALLOW_V2_ENTRIES):
                results.extend(each_loop.get_tag(query, whole_tag=whole_tag))

        # Check our tags
        query = _format_tag(query).lower()
        if (ALLOW_V2_ENTRIES or
                (tag_prefix is not None and
                 tag_prefix.lower() == self.tag_prefix.lower())):
            for tag in self.tags:
                if query == tag[0].lower():
                    if whole_tag:
                        results.append(tag)
                    else:
                        results.append(tag[1])

        return results

    def loop_dict(self):
        """Returns a hash of loop category -> loop."""

        res = {}
        for each_loop in self.loops:
            if each_loop.category is not None:
                res[each_loop.category.lower()] = each_loop
        return res

    def loop_iterator(self):
        """Returns an iterator for saveframe loops."""

        return iter(self.loops)

    def set_tag_prefix(self, tag_prefix):
        """Set the tag prefix for this saveframe."""

        self.tag_prefix = _format_category(tag_prefix)

    def sort_tags(self, schema=None):
        """ Sort the tags so they are in the same order as a BMRB
        schema. Will automatically use the standard schema if none
        is provided."""

        mod_key = lambda x: _tag_key(self.tag_prefix + "." + x[0],
                                     schema=schema)
        self.tags.sort(key=mod_key)

    def tag_iterator(self):
        """Returns an iterator for saveframe tags."""

        return iter(self.tags)

    def print_tree(self):
        """Prints a summary, tree style, of the loops in the saveframe."""

        print(repr(self))
        for pos, each_loop in enumerate(self):
            print("\t[%d] %s" % (pos, repr(each_loop)))

    def validate(self, validate_schema=True, schema=None,
                 validate_star=True):
        """Validate a saveframe in a variety of ways. Returns a list of
        errors found. 0-length list indicates no errors found. By
        default all validation modes are enabled.

        validate_schema - Determines if the entry is validated against
        the NMR-STAR schema. You can pass your own custom schema if desired,
        otherwise the schema will be fetched from the BMRB servers.

        validate_star - Determines if the STAR syntax checks are ran."""

        errors = []

        my_category = self.category
        if my_category == "unset":
            errors.append("Cannot properly validate saveframe: '" + self.name +
                          "'. No saveframe category defined.")
            my_category = None

        if validate_schema:
            # Get the default schema if we are not passed a schema
            my_schema = _get_schema(schema)

            for tag in self.tags:
                lineno = str(tag[2]) + " of original file" if len(tag) > 2 else None
                formatted_tag = self.tag_prefix + "." + tag[0]
                cur_errors = my_schema.val_type(formatted_tag, tag[1],
                                                category=my_category,
                                                linenum=lineno)
                errors.extend(cur_errors)

        # Check the loops for errors
        for each_loop in self.loops:
            errors.extend(
                each_loop.validate(validate_schema=validate_schema,
                                   schema=schema,
                                   validate_star=validate_star,
                                   category=my_category))

        return errors

class Loop(object):
    """A BMRB loop object."""

    def __eq__(self, other):
        """Returns True if this loop is equal to another loop, False if
        it is different."""

        return len(self.compare(other)) == 0

    def __ne__(self, other):
        """It isn't enough to define __eq__ in python2.x."""

        return not self.__eq__(other)

    def __getitem__(self, item):
        """Get the indicated row from the data array."""

        try:
            return self.data[item]
        except TypeError:
            if isinstance(item, tuple):
                item = list(item)
            return self.get_tag(tags=item)

    def __init__(self, **kargs):
        """Use the classmethods to initialize."""

        # Initialize our local variables
        self.columns = []
        self.data = []
        self.category = None
        self.source = "unknown"

        # Update our source if it provided
        if 'source' in kargs:
            self.source = kargs['source']

        # Update our category if provided
        if 'category' in kargs:
            self.category = _format_category(kargs['category'])
            return

        # They initialized us wrong
        if len(kargs) == 0:
            raise ValueError("Use the class methods to initialize.")

        # Parsing from a string
        if 'the_string' in kargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kargs['the_string'])
            self.source = "from_string()"
        # Parsing from a file
        elif 'file_name' in kargs:
            star_buffer = _interpret_file(kargs['file_name'])
            self.source = "from_file('%s')" % kargs['file_name']
        # Creating from template (schema)
        elif 'tag_prefix' in kargs:
            schema = _get_schema(kargs['schema'])
            clean_tp = kargs['tag_prefix']

            # Put the _ on the front for them if necessary
            if not clean_tp.startswith("_"):
                clean_tp = "_" + clean_tp
            if not clean_tp.endswith("."):
                clean_tp = clean_tp + "."

            for item in schema.schema_order:
                # The tag is in the loop
                if item.lower().startswith(clean_tp.lower()):

                    # Unconditional add
                    if kargs['all_tags']:
                        self.add_column(item)
                    # Conditional add
                    else:
                        if schema.schema[item.lower()]["public"] != "I":
                            self.add_column(item)
            if len(self.columns) == 0:
                raise ValueError("The tag prefix '%s' has no corresponding tags"
                                 " in the dictionary." % clean_tp)
            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kargs and kargs['csv']:
            csvreader = csv_reader(star_buffer)
            self.add_column(next(csvreader))
            for row in csvreader:
                self.add_data(row)
            self.source = "from_csv('%s')" % kargs['csv']
            return

        tmp_entry = Entry.from_scratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_0 save_internaluseyoushouldntseethis_frame"
                               " _internal.use internal " + star_buffer.read() +
                               " save_")
        parser = _Parser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source)

        # Check that there was only one loop here
        if len(tmp_entry[0].loops) > 1:
            raise ValueError("You attempted to parse one loop but the source "
                             "you provided had more than one loop. Please "
                             "either parse all loops as a saveframe or only "
                             "parse one loop. Loops detected:"
                             " " + str(tmp_entry[0].loops))

        # Copy the first parsed saveframe into ourself
        self.columns = tmp_entry[0][0].columns
        self.data = tmp_entry[0][0].data
        self.category = tmp_entry[0][0].category

    def __len__(self):
        """Return the number of rows of data."""

        return len(self.data)

    def __lt__(self, other):
        """Returns True if this loop sorts lower than the compared
        loop, false otherwise."""

        return self.category < other.category

    def __repr__(self):
        """Returns a description of the loop."""

        if ALLOW_V2_ENTRIES and self.category is None:
            common = os.path.commonprefix(self.columns)
            if common.endswith("_"):
                common = common[:-1]
            if common == "":
                common = "Unknown"
            return "<bmrb.Loop '%s'>" % common
        else:
            return "<bmrb.Loop '%s'>" % self.category

    def __setitem__(self, key, item):
        """Set all of the instances of a tag to the provided value.
        If there are 5 rows of data in the loop, you will need to
        assign a list with 5 elements."""

        tag = _format_tag(key)

        # Check that their tag is in the loop
        if tag not in self.columns:
            raise ValueError("Cannot assign to tag '%s' as it does not exist "
                             "in this loop." % key)

        # Determine where to assign
        column = self.columns.index(tag)

        # Make sure they provide a list of the correct length
        if len(self[key]) != len(item):
            raise ValueError("To assign to a tag you must provide a list (or "
                             "iterable) of a length equal to the number of "
                             "values that currently exist for that tag. The tag"
                             " '%s' current has %d values and you supplied "
                             "%d values." % (key, len(self[key]), len(item)))

        # Do the assignment
        for pos, row in enumerate(self.data):
            row[column] = item[pos]

    def __str__(self):
        """Returns the loop in STAR format as a string."""

        # Check if there is any data in this loop
        if len(self.data) == 0:
            # They do not want us to print empty loops
            if SKIP_EMPTY_LOOPS:
                return ""
            else:
                # If we have no columns than return the empty loop
                if len(self.columns) == 0:
                    return "\n   loop_\n\n   stop_\n"

        if len(self.columns) == 0:
            raise ValueError("Impossible to print data if there are no "
                             "associated tags. Loop: '%s'." % self.category)

        # Make sure that if there is data, it is the same width as the
        #  column tags
        if len(self.data) > 0:
            for row in self.data:
                if len(self.columns) != len(row):
                    raise ValueError("The number of column tags must match"
                                     "width of the data. Loop: '%s'." %
                                     self.category)

        # Start the loop
        ret_string = "\n   loop_\n"
        # Print the columns
        pstring = "      %-s\n"


        # Check to make sure our category is set
        if self.category is None and not ALLOW_V2_ENTRIES:
            raise ValueError("The category was never set for this loop. Either "
                             "add a column with the category intact, specify it"
                             " when generating the loop, or set it using "
                             "set_category.")

        # Print the categories
        if self.category is None:
            for column in self.columns:
                ret_string += pstring % (column)
        else:
            for column in self.columns:
                ret_string += pstring % (self.category + "." + column)

        ret_string += "\n"

        row_strings = []

        if len(self.data) != 0:

            # Make a copy of the data
            working_data = []
            # Put quotes as needed on the data
            for datum in self.data:
                working_data.append([clean_value(x) for x in datum])

            # The nightmare below creates a list of the maximum length of
            #  elements in each column in the self.data matrix. Don't try to
            #   understand it. It's an incomprehensible list comprehension.
            title_widths = [max([len(str(x))+3 for x in col]) for
                            col in [[row[x] for row in working_data] for
                                    x in range(0, len(working_data[0]))]]

            # TODO: Replace with a smarter title_widths algorithm - or in C
            # It needs to not count the length of items that will go on their
            # own line...

            # Generate the format string
            pstring = "     " + "%-*s"*len(self.columns) + " \n"

            # Print the data, with the columns sized appropriately
            for datum in working_data:
                for pos, item in enumerate(datum):
                    if "\n" in item:
                        datum[pos] = "\n;\n%s;\n" % item

                # Print the data (combine the column's widths with their data)
                column_width_list = [d for d in zip(title_widths, datum)]
                row_strings.append(pstring % tuple(_from_iterable(column_width_list)))

        # Close the loop
        ret_string += "".join(row_strings) + "   stop_\n"
        return ret_string

    @classmethod
    def from_file(cls, the_file, csv=False):
        """Create a saveframe by loading in a file. Specify csv=True if
        the file is a CSV file. If the_file starts with http://,
        https://, or ftp:// then we will use those protocols to attempt
        to open the file."""

        return cls(file_name=the_file, csv=csv)

    @classmethod
    def from_json(cls, json_dict):
        """Create a loop from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python "
                                 "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ['tags', 'category', 'data']:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a dictionary and"
                                 " must contain the key '%s' - even if the key "
                                 "points to None." % check)

        # Create a loop from scratch and populate it
        ret = Loop.from_scratch()
        ret.columns = json_dict['tags']
        ret.category = json_dict['category']
        ret.data = json_dict['data']
        ret.source = "from_json()"

        # Return the new loop
        return ret

    @classmethod
    def from_scratch(cls, category=None, source="from_scratch()"):
        """Create an empty saveframe that you can programatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""

        return cls(category=category, source=source)

    @classmethod
    def from_string(cls, the_string, csv=False):
        """Create a saveframe by parsing a string. Specify csv=True is
        the string is in CSV format and not NMR-STAR format."""

        return cls(the_string=the_string, csv=csv)

    @classmethod
    def from_template(cls, tag_prefix, all_tags=False, schema=None):
        """ Create a loop that has all of the tags from the schema present.
        No values will be assigned. Specify the tag prefix of the loop.

        The optional argument all_tags forces all tags to be included
        rather than just the mandatory tags."""

        return cls(tag_prefix=tag_prefix, all_tags=all_tags,
                   schema=schema, source="from_template()")

    def _tag_index(self, tag_name):
        """ Helper method to do a case-insensitive check for the presence
        of a given tag in this loop. Returns the index of the tag if found
        and None if not found."""

        try:
            lc_col = [x.lower() for x in self.columns]
            return lc_col.index(_format_tag(str(tag_name)).lower())
        except ValueError:
            return None

    def add_column(self, name, ignore_duplicates=False):
        """Add a column to the column list. Does a bit of validation
        and parsing. Set ignore_duplicates to true to ignore attempts
        to add the same tag more than once rather than raise an
        exception.

        You can also pass a list of column names to add more than one
        column at a time."""

        # If they have passed multiple columns to add, call ourself
        #  on each of them in succession
        if isinstance(name, (list, tuple)):
            for item in name:
                self.add_column(item, ignore_duplicates=ignore_duplicates)
            return

        name = name.strip()

        if "." in name:
            if name[0] != ".":
                category = name[0:name.index(".")]
                if category[:1] != "_":
                    category = "_" + category

                if self.category is None:
                    self.category = category
                elif self.category.lower() != category.lower():
                    raise ValueError("One loop cannot have columns with "
                                     "different categories (or columns that "
                                     "don't match the set prefix)!")
                name = name[name.index(".")+1:]
            else:
                name = name[1:]

        # Ignore duplicate tags
        if self._tag_index(name) is not None:
            if ignore_duplicates:
                return
            else:
                raise ValueError("There is already a column with the name"
                                 " '%s'." % name)
        if "." in name:
            raise ValueError("There cannot be more than one '.' in a tag name.")
        if " " in name:
            raise ValueError("Column names can not contain spaces.")
        self.columns.append(name)

    def add_data(self, the_list, rearrange=False):
        """Add a list to the data field. Items in list can be any type,
        they will be converted to string and formatted correctly. The
        list must have the same cardinality as the column names or you
        must set the rearrange variable to true and have already set all
        the columns in the loop. Rearrange will break a longer list into
        rows based on the number of columns."""

        # Add one row of data
        if not rearrange:
            if len(the_list) != len(self.columns):
                raise ValueError("The list must have the same number of "
                                 "elements as the number of columns! Insert "
                                 "column names first.")
            # Add the user data
            self.data.append(the_list)
            return

        # Break their data into chunks based on the number of columns
        processed_data = [the_list[x:x + len(self.columns)] for
                          x in range(0, len(the_list), len(self.columns))]
        if len(processed_data[-1]) != len(self.columns):
            raise ValueError("The number of data elements in the loop " +
                             self.category +
                             " does not match the number of columns!")

        # Auto convert datatypes if option set
        if CONVERT_DATATYPES:
            tschem = _get_schema()
            for row in processed_data:
                for column, datum in enumerate(row):
                    row[column] = tschem.convert_tag(self.category + "." +
                                                     self.columns[column],
                                                     datum,
                                                     linenum="Loop %s" %
                                                     self.category)

        self.data = processed_data

    def add_data_by_column(self, column_id, value):
        """Add data to the loop one element at a time, based on column.
        Useful when adding data from SANS parsers."""

        # Make sure the category matches - if provided
        if "." in column_id:
            supplied_category = _format_category(str(column_id))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your column '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        pos = self._tag_index(column_id)
        if pos is None:
            raise ValueError("The column tag '%s' to which you are attempting "
                             "to add data does not yet exist. Create the "
                             "columns before adding data." % column_id)
        if len(self.data) == 0:
            self.data.append([])
        if len(self.data[-1]) == len(self.columns):
            self.data.append([])
        if len(self.data[-1]) != pos:
            raise ValueError("You cannot add data out of column order.")
        self.data[-1].append(value)

    def clear_data(self):
        """Erases all data in this loop. Does not erase the data columns
        or loop category."""

        self.data = []

    def compare(self, other):
        """Returns the differences between two loops as a list. Order of
        loops being compared does not make a difference on the specific
        errors detected."""

        diffs = []

        # Check if this is literally the same object
        if self is other:
            return []
        # Check if the other object is our string representation
        if isinstance(other, str):
            if str(self) == other:
                return []
            else:
                return ['String was not exactly equal to loop.']

        # We need to do this in case of an extra "\n" on the end of one tag
        if str(other) == str(self):
            return []

        # Do STAR comparison
        try:
            # Check category of loops
            if str(self.category).lower() != str(other.category).lower():
                diffs.append("\t\tCategory of loops does not match: '%s' vs "
                             "'%s'." % (self.category, other.category))

            # Check columns of loops
            if ([x.lower() for x in self.columns] !=
                    [x.lower() for x in other.columns]):
                diffs.append("\t\tLoop columns do not match for loop with "
                             "category '%s'." % self.category)

            # No point checking if data is the same if the columns aren't
            else:
                # Only sort the data if it is not already equal
                if self.data != other.data:

                    # Check data of loops
                    self_data = sorted(deepcopy(self.data))
                    other_data = sorted(deepcopy(other.data))

                    if self_data != other_data:
                        diffs.append("\t\tLoop data does not match for loop "
                                     "with category '%s'." % self.category)

        except AttributeError as err:
            diffs.append("\t\tAn exception occured while comparing: '%s'." %
                         err)

        return diffs

    def delete_data_by_tag_value(self, tag, value, index_tag=None):
        """Deletes all rows which contain the provided value in the
        provided column. If index_tag is provided, that column is
        renumbered starting with 1. Returns the deleted rows."""

        # Make sure the category matches - if provided
        if "." in tag:
            supplied_category = _format_category(str(tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your column '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        search_column = self._tag_index(tag)
        if search_column is None:
            raise ValueError("The tag you provided '%s' isn't in this loop!" %
                             tag)

        deleted = []

        # Delete all rows in which the user-provided tag matched
        cur_row = 0
        while cur_row < len(self.data):
            if self.data[cur_row][search_column] == value:
                deleted.append(self.data.pop(cur_row))
                continue
            cur_row += 1

        # Re-number if they so desire
        if index_tag is not None:
            self.renumber_rows(index_tag)

        return deleted

    def filter(self, tag_list, ignore_missing_tags=False):
        """ Returns a new loop containing only the specified tags.
        Specify ignore_missing_tags=True to bypass missing tags rather
        than raising an error."""

        result = Loop.from_scratch()
        valid_tags = []

        # If they only provide one tag make it a list
        if not isinstance(tag_list, (list, tuple)):
            tag_list = [tag_list]

        # Make sure all the tags specified exist
        for tag in tag_list:

            # Handle an invalid tag
            if self._tag_index(tag) is None:
                if not ignore_missing_tags:
                    raise ValueError("Cannot filter tag '%s' as it isn't "
                                     "present in this loop." % tag)
                continue

            valid_tags.append(tag)
            result.add_column(tag)

        # Add the data for the tags to the new loop
        for row in self.get_data_by_tag(valid_tags):
            result.add_data(row)

        # Assign the category of the new loop
        if result.category is None:
            result.category = self.category

        return result

    def get_columns(self):
        """ Return the columns for this entry with the category
        included. Throws ValueError if the category was never set."""

        if not self.category:
            raise ValueError("You never set the category of this loop.")

        return [self.category + "." + x for x in self.columns]

    def get_data_as_csv(self, header=True, show_category=True):
        """Return the data contained in the loops, properly CSVd, as a
        string. Set header to False to omit the header. Set
        show_category to false to omit the loop category from the
        headers."""

        csv_buffer = StringIO()
        cwriter = csv_writer(csv_buffer)

        if header:
            if show_category:
                cwriter.writerow(
                    [str(self.category)+"."+str(x) for x in self.columns])
            else:
                cwriter.writerow([str(x) for x in self.columns])

        for row in self.data:

            data = []
            for piece in row:
                data.append(piece)

            cwriter.writerow(data)

        csv_buffer.seek(0)
        return csv_buffer.read().replace('\r\n', '\n')

    def get_data_by_tag(self, tags=None):
        """ Identical to get_tag but wraps the results in a list even if
        only fetching one tag. Primarily exists for legacy code."""

        results = self.get_tag(tags=tags)

        if isinstance(tags, list):
            if len(tags) == 1:
                results = [results]
        elif isinstance(tags, str):
            results = [results]

        return results

    def get_json(self, serialize=True):
        """ Returns the loop in JSON format. If serialize is set to
        False a dictionary representation of the loop that is
        serializeable is returned."""

        loop_dict = {
            "category": self.category,
            "tags": self.columns,
            "data": self.data
        }

        if serialize:
            return json.dumps(loop_dict, default=_json_serialize)
        else:
            return loop_dict

    def get_tag(self, tags=None, whole_tag=False):
        """Provided a tag name (or a list of tag names), or ordinals
        corresponding to columns, return the selected tags by row as
        a list of lists."""

        # All tags
        if tags is None:
            return self.data
        # Turn single elements into lists
        if not isinstance(tags, list):
            tags = [tags]

        # Make a copy of the tags to fetch - don't modify the
        # list that was passed
        lower_tags = deepcopy(tags)

        # Strip the category if they provide it (also validate
        #  it during the process)
        for pos, item in enumerate([str(x) for x in lower_tags]):
            if ("." in item and
                    _format_category(item).lower() != self.category.lower()):
                raise ValueError("Cannot fetch data with column '%s' because "
                                 "the category does not match the category of "
                                 "this loop '%s'." % (item, self.category))
            lower_tags[pos] = _format_tag(item).lower()

        # Make a lower case copy of the columns
        columns_lower = [x.lower() for x in self.columns]

        # Map column name to column position in list
        column_mapping = dict(zip(reversed(columns_lower),
                                  reversed(range(len(columns_lower)))))

        # Make sure their fields are actually present in the entry
        column_ids = []
        for query in lower_tags:
            if str(query) in column_mapping:
                column_ids.append(column_mapping[query])
            elif isinstance(query, int):
                column_ids.append(query)
            else:
                if ALLOW_V2_ENTRIES:
                    return []
                else:
                    raise ValueError("Could not locate the the column with name"
                                     " or ID: '%s' in loop '%s'." %
                                     (query, str(self.category)))

        # Use a list comprehension to pull the correct tags out of the rows
        if whole_tag:
            return [[self.category + "." + self.columns[col_id], row[col_id]]
                    for col_id in column_ids for row in self.data]
        else:
            # If only returning one tag (the usual behavior) then don't wrap
            # the results in a list
            if len(lower_tags) == 1:
                return [row[col_id] for col_id in column_ids for
                        row in self.data]
            else:
                return [[row[col_id] for col_id in column_ids] for
                        row in self.data]

    def print_tree(self):
        """Prints a summary, tree style, of the loop."""

        print(repr(self))

    def renumber_rows(self, index_tag, start_value=1, maintain_ordering=False):
        """Renumber a given column incrementally. Set start_value to
        initial value if 1 is not acceptable. Set maintain_ordering to
        preserve sequence with offset.

        E.g. 2,3,3,5 would become 1,2,2,4."""

        # Make sure the category matches
        if "." in str(index_tag):
            supplied_category = _format_category(str(index_tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your tag '%s' does not "
                                 "match this loop's category '%s'." %
                                 (supplied_category, self.category))

        renum_col = self._tag_index(index_tag)

        # The column to replace in is the column they specify
        if renum_col is None:
            # Or, perhaps they specified an integer to represent the column?
            try:
                renum_col = int(index_tag)
            except ValueError:
                raise ValueError("The renumbering column you provided '%s' "
                                 "isn't in this loop!" % index_tag)

        # Verify the renumbering column ID
        if renum_col >= len(self.columns) or renum_col < 0:
            raise ValueError("The renumbering column ID you provided '%s' is "
                             "too large or too small! Value column ids are"
                             "0-%d." % (index_tag, len(self.columns)-1))

        # Do nothing if we have no data
        if len(self.data) == 0:
            return

        if maintain_ordering:
            # If they have a string buried somewhere in the row, we'll
            #  have to restore the original values
            data_copy = deepcopy(self.data)

            for pos in range(0, len(self.data)):
                try:
                    if pos == 0:
                        offset = start_value - int(self.data[0][renum_col])
                    new_data = int(self.data[pos][renum_col]) + offset
                    self.data[pos][renum_col] = new_data
                except ValueError:
                    self.data = data_copy
                    raise ValueError("You can't renumber a row containing "
                                     "anything that can't be coerced into an "
                                     "integer using maintain_ordering. I.e. "
                                     "what am I suppose to renumber '%s' to?" %
                                     self.data[pos][renum_col])

        # Simple renumbering algorithm if we don't need to maintain the ordering
        else:
            for pos in range(0, len(self.data)):
                self.data[pos][renum_col] = pos + start_value

    def set_category(self, category):
        """ Set the category of the loop. Useful if you didn't know the
        category at loop creation time."""

        self.category = _format_category(category)

    def sort_tags(self, schema=None):
        """ Rearranges the columns and data in the loop to match the order
        from the schema. Uses the BMRB schema unless one is provided."""

        current_order = self.get_columns()

        # Sort the tags
        loc_key = lambda x: _tag_key(x, schema=schema)
        sorted_order = sorted(current_order, key=loc_key)

        # Don't touch the data if the tags are already in order
        if sorted_order == current_order:
            return
        else:
            self.data = self.get_tag(sorted_order)
            self.columns = [_format_tag(x) for x in sorted_order]

    def sort_rows(self, tags, key=None):
        """ Sort the data in the rows by their values for a given column
        or columns. Specify the columns using their names or ordinals.
        Accepts a list or an int/float. By default we will sort
        numerically. If that fails we do a string sort. Supply a
        function as key and we will order the elements based on the
        keys it provides. See the help for sorted() for more details. If
        you provide multiple columns to sort by, they are interpreted as
        increasing order of sort priority."""

        # Do nothing if we have no data
        if len(self.data) == 0:
            return

        # This will determine how we sort
        sort_ordinals = []

        processing_list = []
        if isinstance(tags, list):
            processing_list = tags
        else:
            processing_list = [tags]

        # Process their input to determine which columns to operate on
        for cur_tag in [str(x) for x in processing_list]:

            # Make sure the category matches
            if "." in cur_tag:
                supplied_category = _format_category(cur_tag)
                if supplied_category.lower() != self.category.lower():
                    raise ValueError("Category provided in your tag '%s' does "
                                     "not match this loop's category '%s'." %
                                     (supplied_category, self.category))

            renumber_column = self._tag_index(cur_tag)

            # They didn't specify a valid column
            if renumber_column is None:
                # Perhaps they specified an integer to represent the column?
                try:
                    renumber_column = int(cur_tag)
                except ValueError:
                    raise ValueError("The sorting column you provided '%s' "
                                     "isn't in this loop!" % cur_tag)

            # Verify the renumbering column ID
            if renumber_column >= len(self.columns) or renumber_column < 0:
                raise ValueError("The sorting column ID you provided '%s' is "
                                 "too large or too small! Value column ids"
                                 " are 0-%d." % (cur_tag, len(self.columns)-1))

            sort_ordinals.append(renumber_column)

        # Do the sort(s)
        for column in sort_ordinals:
            # Going through each column, first attempt to sort as integer.
            #  Then fallback to string sort.
            try:
                if key is None:
                    tmp_data = sorted(self.data,
                                      key=lambda x, pos=column: float(x[pos]))
                else:
                    tmp_data = sorted(self.data, key=key)
            except ValueError:
                if key is None:
                    tmp_data = sorted(self.data,
                                      key=lambda x, pos=column: x[pos])
                else:
                    tmp_data = sorted(self.data, key=key)
            self.data = tmp_data

    def validate(self, validate_schema=True, schema=None,
                 validate_star=True, category=None):
        """Validate a loop in a variety of ways. Returns a list of
        errors found. 0-length list indicates no errors found. By
        default all validation modes are enabled.

        validate_schema - Determines if the entry is validated against
        the NMR-STAR schema. You can pass your own custom schema if desired,
        otherwise the schema will be fetched from the BMRB servers.

        validate_star - Determines if the STAR syntax checks are ran."""

        errors = []

        if validate_schema:
            # Get the default schema if we are not passed a schema
            my_schema = _get_schema(schema)

            # Check the data
            for rownum, row in enumerate(self.data):
                for pos, datum in enumerate(row):
                    lineno = str(rownum) + " column " + str(pos) + " of loop"
                    errors.extend(my_schema.val_type(self.category + "." +
                                                     self.columns[pos], datum,
                                                     category=category,
                                                     linenum=lineno))

        if validate_star:
            # Check for wrong data size
            num_cols = len(self.columns)
            for rownum, row in enumerate(self.data):
                # Make sure the width matches
                if len(row) != num_cols:
                    errors.append("Loop '%s' data width does not match it's "
                                  "column tag width on row '%d'." %
                                  (self.category, rownum))

        return errors

def called_directly():
    """ Figure out what to do if we were called on the command line
    rather than imported as a module."""

    # Specify some basic information about our command
    optparser = optparse.OptionParser(usage="usage: %prog",
                                      version=_VERSION,
                                      description="NMR-STAR handling python "
                                                  "module. Usually you'll want "
                                                  "to import this. When ran "
                                                  "without arguments a unit "
                                                  "test is performed.")
    optparser.add_option("--diff", metavar="FILE1 FILE2", action="store",
                         dest="diff", default=None, type="string", nargs=2,
                         help="Print a comparison of two entries.")
    optparser.add_option("--validate", metavar="FILE", action="store",
                         dest="validate", default=None, type="string",
                         help="Print the validation report for an entry.")
    optparser.add_option("--tag", metavar="FILE TAG", action="store",
                         dest="fetch_tag", default=None, nargs=2, type="string",
                         help="Print all of the values of the specified tags "
                              "separated by newlines. Existing newlines in data"
                              " are escaped. You can query multiple tags by "
                              "comma separating them; if you do that the "
                              "results will be truncated to the length of the "
                              "tag with the fewest results, and the values for"
                              " the tags will be separated with tabs.")
    optparser.add_option("--quick", action="store_true", default=False,
                         dest="quick_test", help=SUPPRESS_HELP)

    # Options, parse 'em
    (options, cmd_input) = optparser.parse_args()

    if len(cmd_input) > 0:
        print("No arguments are allowed. Please see the options using --help.")
        sys.exit(0)

    # Check for command misuse
    if sum(1 for x in [options.validate,
                       options.diff, options.fetch_tag] if x) > 1:
        print("You can only use one of the --diff, --validate, and --tag "
              "options at once.")
        sys.exit(1)

    # Validate an entry
    if options.validate is not None:
        validate(Entry.from_file(options.validate))

    # Print the diff report
    elif options.diff is not None:
        diff(Entry.from_file(options.diff[0]), Entry.from_file(options.diff[1]))

    # Fetch a tag and print it
    elif options.fetch_tag is not None:

        # Build an Entry from their file
        entry = Entry.from_file(options.fetch_tag[0])

        # Figure out if they want one or more tags
        if "," in options.fetch_tag[1]:
            query_tags = options.fetch_tag[1].split(",")
        else:
            query_tags = [options.fetch_tag[1]]

        # Get the tags they queried
        result = entry.get_tags(query_tags)
        result = [result[tag] for tag in query_tags]

        results_lengths = [len(x) for x in result]
        max_length = max(results_lengths)

        if len(set(results_lengths)) != 1:
            sys.stderr.write("Warning! Not all queried tags had the same number"
                             " of values. It is not recommended to combine tags "
                             "from saveframes and loops. Please ensure that "
                             "your script is separating columns by one tab and "
                             "not by whitespace or this output may be "
                             "misinterpreted.\n")

        # Lengthen the short tags
        for x, tag in enumerate(result):
            while len(tag) < max_length:
                tag.append("")

        result = zip(*result)

        for row in result:
            print("\t".join([x.replace("\n", "\\n").replace("\t", "\\t")
                             for x in row]))

    # Run unit tests with no special mode invoked
    else:
        print("Running unit tests...")
        try:
            #pylint: disable=relative-import,wrong-import-order
            from unit_tests import bmrb_test
        except ImportError:
            print("No testing module available with this installation.")
            sys.exit(0)

        # Only do a quick test
        if options.quick_test:
            bmrb_test.quick_test = True
            sys.argv.pop()

        bmrb_test.start_tests()

    sys.exit(0)

# Allow using diff or validate if ran directly
if __name__ == '__main__':
    called_directly()
else:
    #############################################
    #          Module initializations           #
    #############################################

    # This makes sure that when decimals are printed a lower case "e" is used
    decimal.getcontext().capitals = 0

    # This loads the comments
    _load_comments()
