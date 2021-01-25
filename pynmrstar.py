#!/usr/bin/env python

"""This module provides Entry, Saveframe, and Loop objects. Use python's
built in help function for documentation.

There are eight module variables you can set to control our behavior.

* Setting VERBOSE to True will print some of what is going on to
the terminal.

* Setting RAISE_PARSE_WARNINGS to True will raise an exception if
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

* Setting ALLOW_V2_ENTRIES will allow parsing of NMR-STAR version
2.1 entries. Most other methods will not operate correctly on parsed
2.1 entries. This is only to allow you parse and access the data in
these entries - nothing else. Only set this if you have a really good
reason to. Attempting to print a 2.1 entry will 'work' but tags that
were after loops will be moved to before loops.

* Setting DONT_SHOW_COMMENTS to True will suppress the printing of
comments before saveframes.

* Setting CONVERT_DATATYPES to True will automatically convert
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

from itertools import chain
from optparse import SUPPRESS_HELP
from copy import deepcopy
from csv import reader as csv_reader, writer as csv_writer
from datetime import date
from gzip import GzipFile

# See if we have zlib
try:
    import zlib
except ImportError:
    zlib = None

try:
    import warnings
except ImportError:
    class WarningsImposter:
        def warn(self, warning_message, warning_type):
            sys.stderr.write("%s\n" % warning_message)


    warnings = WarningsImposter()

# Determine if we are running in python3
PY3 = (sys.version_info[0] == 3)

# pylint: disable=wrong-import-position,no-name-in-module
# pylint: disable=import-error,wrong-import-order
# Python version dependent loads
if PY3:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError, URLError
    from io import StringIO, BytesIO
else:
    from urllib2 import urlopen, HTTPError, URLError, Request
    from cStringIO import StringIO

    BytesIO = StringIO

if PY3:
    class _NeverMatches:
        pass


    unicode = _NeverMatches


# This is an odd place for this, but it can't really be avoided if
#  we want to keep the import at the top.
def _build_extension():
    """ Try to compile the c extension. """
    import subprocess

    cur_dir = os.getcwd()
    try:
        src_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        os.chdir(os.path.join(src_dir, "c"))

        # Use the appropriate build command
        build_cmd = ['make']
        if PY3:
            build_cmd.append("python3")

        process = subprocess.Popen(build_cmd, stderr=subprocess.STDOUT,
                                   stdout=subprocess.PIPE)
        process.communicate()
        ret_code = process.poll()
        # The make command exited with a non-zero status
        if ret_code:
            return False

        # We were able to build the extension?
        return True
    except OSError:
        # There was an error going into the c dir
        return False
    finally:
        # Go back to the directory we were in before exiting
        os.chdir(cur_dir)

    # We should never make it here, but if we do the null return
    #  prevents the attempted importing of the c module.


# See if we can use the fast tokenizer
try:
    import cnmrstar

    if "version" not in dir(cnmrstar) or cnmrstar.version() < "2.2.8":
        print("Recompiling cnmrstar module due to API changes. You may "
              "experience a segmentation fault immediately following this "
              "message but should have no issues the next time you run your "
              "script or this program.")
        _build_extension()
        sys.exit(0)

except ImportError as e:
    cnmrstar = None

    # Check for the 'no c module' file before continuing
    if not os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                       ".nocompile")):

        if _build_extension():
            try:
                import cnmrstar
            except ImportError:
                cnmrstar = None

#############################################
#            Global Variables               #
#############################################

# Set this to allow import * from bmrb to work sensibly
__all__ = ['Entry', 'Saveframe', 'Loop', 'Schema', 'diff', 'validate',
           'enable_nef_defaults', 'enable_nmrstar_defaults',
           'delete_empty_saveframes', '__version__']

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
STR_CONVERSION_DICT = {None: "."}

# Used internally
_STANDARD_SCHEMA = None
_COMMENT_DICTIONARY = {}
_API_URL = "http://api.bmrb.io/v2"
_SCHEMA_URL = 'https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/master/xlschem_ann.csv'
_WHITESPACE = " \t\n\v"
__version__ = "2.6.6"


#############################################
#             Module methods                #
#############################################

# Public use methods
def enable_nef_defaults():
    """ Sets the module variables such that our behavior matches the NEF
    standard. Specifically, suppress printing empty loops by default and
    convert True -> "true" and False -> "false" when printing."""

    warnings.warn("""This feature will be removed in the v3 branch. You can still work with NEF files by using
the appropriate parameters when writing out files. Specifically:

Before writing out objects as strings, perform these two steps:

Update the global string conversion dictionary:
pynmrstar.definitions.STR_CONVERSION_DICT = {None: ".", True: "true", False: "false"}

Rather than using str(obj) to render as a string, use obj.format(show_comments=False, skip_empty_loops=True).

""", DeprecationWarning)

    global STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS, DONT_SHOW_COMMENTS
    STR_CONVERSION_DICT = {None: ".", True: "true", False: "false"}
    SKIP_EMPTY_LOOPS = True
    DONT_SHOW_COMMENTS = True


def enable_nmrstar_defaults():
    """ Sets the module variables such that our behavior matches the
    BMRB standard (NMR-STAR). This is the default behavior of this module.
    This method only exists to revert after calling enable_nef_defaults()."""

    warnings.warn("This feature has been removed from the v3 branch. You can still work with NEF files by using"
                  "the appropriate parameters when loading and writing out files.", DeprecationWarning)

    global STR_CONVERSION_DICT, SKIP_EMPTY_LOOPS, DONT_SHOW_COMMENTS
    STR_CONVERSION_DICT = {None: "."}
    SKIP_EMPTY_LOOPS = False
    DONT_SHOW_COMMENTS = False


def delete_empty_saveframes(entry_object, tags_to_ignore=None, allowed_null_values=None):
    """ This method will delete all empty saveframes in an entry
    (the loops in the saveframe must also be empty for the saveframe
    to be deleted). "Empty" means no values in tags, not no tags present."""

    if not tags_to_ignore:
        tags_to_ignore = ["sf_category", "sf_framecode"]
    if not allowed_null_values:
        allowed_null_values = [".", "?", None]
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
            if loop.data:
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


def iter_entries(metabolomics=False):
    """ Returns a generator that will yield an Entry object for every
        macromolecule entry in the current BMRB database. Perfect for performing
        an operation across the entire BMRB database. Set `metabolomics=True`
        in order to get all the entries in the metabolomics database."""

    warnings.warn('This function will move to utils.iter_entries() in version 3.0.', DeprecationWarning)

    api_url = "%s/list_entries?database=macromolecules" % _API_URL
    if metabolomics:
        api_url = "%s/list_entries?database=metabolomics" % _API_URL

    for entry in json.loads(_interpret_file(api_url).read()):
        yield Entry.from_database(entry)


def validate(entry_to_validate, schema=None):
    """Deprecated. Please call .validate() on the object for which you want
    a validation report instead."""

    warnings.warn('This function will be removed in a future release. Please call '
                  '.validate() on the object instead.', DeprecationWarning)

    validation = entry_to_validate.validate(schema=schema)
    if len(validation) == 0:
        print("No problems found during validation.")
    for pos, err in enumerate(validation):
        print("%d: %s" % (pos + 1, err))


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

    warnings.warn('This function will move to utils.quote_value() in release 3.0.', DeprecationWarning)

    # Allow manual specification of conversions for booleans, Nones, etc.
    if value in STR_CONVERSION_DICT:
        if any(isinstance(value, type(x)) for x in STR_CONVERSION_DICT):
            value = STR_CONVERSION_DICT[value]

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
            next_char = value[pos + 1:pos + 2]

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


# Internal use only methods
def _json_serialize(obj):
    """JSON serializer for objects not serializable by default json code"""

    # Serialize datetime.date objects by calling str() on them
    if isinstance(obj, (date, decimal.Decimal)):
        return str(obj)
    raise TypeError("Type not serializable: %s" % type(obj))


def _format_tag(value):
    """Strips anything before the '.'"""

    if '.' in value:
        value = value[value.index('.') + 1:]
    return value


def _format_category(value):
    """Adds a '_' to the front of a tag (if not present) and strips out
    anything after a '.'"""

    if value:
        if not value.startswith("_"):
            value = "_" + value
        if "." in value:
            value = value[:value.index(".")]
    return value


def _get_schema(passed_schema=None):
    """If passed a schema (not None) it returns it. If passed none,
    it checks if the default schema has been initialized. If not
    initialized, it initializes it. Then it returns the default schema."""

    global _STANDARD_SCHEMA
    if passed_schema is None:
        passed_schema = _STANDARD_SCHEMA
    if passed_schema is None:

        # Try to load the local file first
        try:
            schema_file = os.path.join(os.path.dirname(os.path.realpath(__file__)))
            schema_file = os.path.join(schema_file, "reference_files/schema.csv")

            _STANDARD_SCHEMA = Schema(schema_file=schema_file)
        except IOError:
            # Try to load from the internet
            try:
                _STANDARD_SCHEMA = Schema()
            except (HTTPError, URLError):
                raise ValueError("Could not load a BMRB schema from the "
                                 "internet or from the local repository.")

        return _STANDARD_SCHEMA
    return passed_schema


def _interpret_file(the_file):
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read') and hasattr(the_file, 'readline'):
        star_buffer = the_file
    elif isinstance(the_file, (str, unicode)):
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
        # Load the comments from Github if we can't find them locally
        try:
            comment_url = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v2/reference_files/comments.str"
            comment_entry = Entry.from_file(_interpret_file(comment_url))
        except Exception:
            # No comments will be printed
            return

    # Load the comments
    comments = comment_entry[0][0].get_tag(["category", "comment", "every_flag"])
    comment_map = {'N': False, 'Y': True}
    for comment in comments:
        if comment[1] != ".":
            _COMMENT_DICTIONARY[comment[0]] = {'comment': comment[1].rstrip() + "\n\n",
                                               'every_flag': comment_map[comment[2]]}


def _tag_key(x, schema=None):
    """ Helper function to figure out how to sort the tags."""
    try:
        return _get_schema(schema).schema_order.index(x)
    except ValueError:
        # Generate an arbitrary sort order for tags that aren't in the
        #  schema but make sure that they always come after tags in the
        #   schema
        return len(_get_schema(schema).schema_order) + abs(hash(x))


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

        if cnmrstar is not None:
            return self.line_number
        else:
            return self.full_data[0:self.index].count("\n") + 1

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
                                if self.token[pos + 1:pos + 4] != "   ":
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
    def index_handle(haystack, needle, start_pos=None):
        """ Finds the index while catching ValueError and returning
        None instead."""

        try:
            return haystack.index(needle, start_pos)
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

        if cnmrstar is not None:
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
        while self.get_token() is not None:

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
            while self.get_token() is not None:

                if self.token == "loop_":
                    if self.delimiter != " ":
                        raise ValueError("The loop_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.get_line_number())

                    curloop = Loop.from_scratch(source=source)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.get_token() is not None:

                        # Add a tag
                        if self.token.startswith("_"):
                            if self.delimiter != " ":
                                raise ValueError("Loop tags may not be quoted "
                                                 "or semicolon-delineated.",
                                                 self.get_line_number())
                            if seen_data:
                                raise ValueError("Cannot have more loop tags "
                                                 "after loop data.")
                            curloop.add_tag(self.token)

                        # On to data
                        else:

                            # Now that we have the tags we can add the loop
                            #  to the current saveframe
                            curframe.add_loop(curloop)

                            # We are in the data block of a loop
                            while self.token is not None:
                                if self.token == "stop_":
                                    if self.delimiter != " ":
                                        raise ValueError("The stop_ keyword may"
                                                         " not be quoted or "
                                                         "semicolon-delineated.",
                                                         self.get_line_number())
                                    if len(curloop.tags) == 0:
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
                                    if len(curloop.tags) == 0:
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
                                     curframe.name + "': '" + self.token +
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
        if cnmrstar is not None:
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
                newline_index = self.full_data.index("\n", self.index + 1)
                raw_tmp = self.full_data[self.index:newline_index]
            except ValueError:
                # End of file
                self.token = self.full_data[self.index:].lstrip(_WHITESPACE)
                if self.token == "":
                    self.token = None
                self.index = len(self.full_data)
                return

            newline_index = self.full_data.index("\n", self.index + 1)
            raw_tmp = self.full_data[self.index:newline_index + 1]
            tmp = raw_tmp.lstrip(_WHITESPACE)

        # If it is a multi-line comment, recalculate our viewing window
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
                    self.token = tmp[0:until + 1]
                    self.index += until + 4
                    self.delimiter = ";"
                    return

                # The line was terminated improperly
                else:
                    if self.next_whitespace(tmp[until + 2:]) == 0:
                        if (RAISE_PARSE_WARNINGS and
                                "bad-multiline" not in WARNINGS_TO_IGNORE):
                            raise ValueError("Warning: Technically invalid line"
                                             " found in file. Multiline values "
                                             "should terminate with \\n;\\n but"
                                             " in this file only \\n; with "
                                             "non-return whitespace following "
                                             "was found.",
                                             self.get_line_number())
                        self.token = tmp[0:until + 1]
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
                while tmp[until + 1:until + 2] not in _WHITESPACE:
                    until = self.index_handle(tmp, "'", until + 1)
            except TypeError:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
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
                while tmp[until + 1:until + 2] not in _WHITESPACE:
                    until = self.index_handle(tmp, '"', until + 1)
            except TypeError:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.get_line_number())

            self.token = tmp[1:until]
            self.index += until + 1
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
        schema_stream = _interpret_file(schema_file)
        fix_newlines = StringIO('\n'.join(schema_stream.read().splitlines()))

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

        try:
            # Read in the data types
            types_file = _interpret_file(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                      "reference_files/data_types.csv"))
        except IOError:
            # Load the data types from Github if we can't find them locally
            types_url = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v2/reference_files/data_types.csv"
            try:
                types_file = _interpret_file(types_url)
            except Exception:
                raise ValueError("Could not load the data type definition file from disk or the internet!")

        csv_reader_instance = csv_reader(types_file)
        for item in csv_reader_instance:
            self.data_types[item[0]] = "^" + item[1] + "$"

    def __repr__(self):
        """Return how we can be initialized."""

        return "pynmrstar.Schema(schema_file='%s') version %s" % (self.schema_file,
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

        format_parameters = (self.schema_file, self.version, "Tag_Prefix", lengths[0],
                             "Tag", lengths[1] - 6, "Type", lengths[2], "Null_Allowed",
                             lengths[3], "SF_Category")
        text = """BMRB schema from: '%s' version '%s'
%s
  %-*s %-*s %-*s %-*s
""" % format_parameters

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
                length = tag_type[tag_type.index("(") + 1:tag_type.index(")")]
                # Check the length for non-numbers and 0
                try:
                    1 / int(length)
                except (ValueError, ZeroDivisionError):
                    raise ValueError("Illegal length specified in tag type: "
                                     "%s " % length)

                # Cut off anything that might be at the end
                tag_type = tag_type[0:tag_type.index(")") + 1]
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
        if loop_flag is not True and loop_flag:
            raise ValueError("Invalid loop_flag. Please specify True or False.")

        # Conditionally check the tag to insert after
        new_tag_pos = len(self.schema_order)
        if after is not None:
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

        self.schema[tag.lower()] = {"Data Type": tag_type, "Loopflag": loop_flag,
                                    "Nullable": null_allowed, "public": "Y",
                                    "SFCategory": sf_category, "Tag": tag,
                                    "Dictionary sequence": new_tag_pos}

    def convert_tag(self, tag, value, line_num=None):
        """ Converts the provided tag from string to the appropriate
        type as specified in this schema."""

        # If we don't know what the tag is, just return it
        if tag.lower() not in self.schema:
            if (RAISE_PARSE_WARNINGS and
                    "tag-not-in-schema" not in WARNINGS_TO_IGNORE):
                raise ValueError("There is a tag in the file that isn't in the"
                                 " schema: '%s' on line '%s'" % (tag, line_num))
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
                                 "line '%s'" % (tag, line_num))
            else:
                return None

        # Keep strings strings
        if "CHAR" in valtype or "VARCHAR" in valtype or "TEXT" in valtype:
            return value

        # Convert ints
        if "INTEGER" in valtype:
            try:
                return int(value)
            except (ValueError, TypeError):
                raise ValueError("Could not parse the file because a value "
                                 "that should be an INTEGER is not. Please "
                                 "turn off CONVERT_DATATYPES or fix the file. "
                                 "Tag: '%s' on line '%s'" % (tag, line_num))

        # Convert floats
        if "FLOAT" in valtype:
            try:
                # If we used int() we would lose the precision
                return decimal.Decimal(value)
            except (decimal.InvalidOperation, TypeError):
                raise ValueError("Could not parse the file because a value "
                                 "that should be a FLOAT is not. Please turn "
                                 "off CONVERT_DATATYPES or fix the file. Tag: "
                                 "'%s' on line '%s'" % (tag, line_num))

        if "DATETIME year to day" in valtype:
            try:
                year, month, day = [int(x) for x in value.split("-")]
                return date(year, month, day)
            except (ValueError, TypeError):
                raise ValueError("Could not parse the file because a value "
                                 "that should be a DATETIME is not. Please "
                                 "turn off CONVERT_DATATYPES or fix the file. "
                                 "Tag: '%s' on line '%s'" % (tag, line_num))

        # We don't know the data type, so just keep it a string
        return value

    def val_type(self, tag, value, category=None, linenum=None):
        """ Validates that a tag matches the type it should have
        according to this schema."""

        if tag.lower() not in self.schema:
            return ["Tag '%s' not found in schema. Line '%s'." %
                    (tag, linenum)]

        # We will skip type checks for None's
        is_none = value is None

        # Allow manual specification of conversions for booleans, Nones, etc.
        if value in STR_CONVERSION_DICT:
            if any(isinstance(value, type(x)) for x in STR_CONVERSION_DICT):
                value = STR_CONVERSION_DICT[value]

        # Value should always be string
        if not isinstance(value, str):
            value = str(value)

        # Check that it isn't a string None
        if value == "." or value == "?":
            is_none = True

        # Make local copies of the fields we care about
        full_tag = self.schema[tag.lower()]
        bmrb_type = full_tag["BMRB data type"]
        val_type = full_tag["Data Type"]
        null_allowed = full_tag["Nullable"]
        allowed_category = full_tag["SFCategory"]
        capitalized_tag = full_tag["Tag"]

        if category is not None:
            if category != allowed_category:
                return ["The tag '%s' in category '%s' should be in category "
                        "'%s'." % (capitalized_tag, category, allowed_category)]

        if is_none:
            if not null_allowed:
                return ["Value cannot be NULL but is: '%s':'%s' on line '%s'."
                        % (capitalized_tag, value, linenum)]
            return []
        else:
            # Don't run these checks on unassigned tags
            if "CHAR" in val_type:
                length = int(val_type[val_type.index("(") + 1:val_type.index(")")])
                if len(str(value)) > length:
                    return ["Length of '%d' is too long for %s: "
                            "'%s':'%s' on line '%s'." %
                            (len(value), val_type, capitalized_tag, value, linenum)]

            # Check that the value matches the regular expression for the type
            if not re.match(self.data_types[bmrb_type], str(value)):
                return ["Value does not match specification: '%s':'%s' on line '%s'"
                        ".\n     Type specified: %s\n     Regular expression for "
                        "type: '%s'" % (capitalized_tag, value, linenum, bmrb_type,
                                        self.data_types[bmrb_type])]

        # Check the tag capitalization
        if tag != capitalized_tag:
            return ["The tag '%s' is improperly capitalized but otherwise "
                    "valid. Should be '%s'." % (tag, capitalized_tag)]
        return []

    def get_json(self, serialize=True, full=False):
        """ Returns the schema in JSON format. """

        s = {'data_types': self.data_types,
             'headers': self.headers,
             'version': self.version}

        if not full:
            s['headers'] = ['Tag', 'SFCategory', 'BMRB data type',
                            'Prompt', 'Interface', 'default value', 'Example',
                            'ADIT category view name', 'User full view',
                            'Foreign Table', 'Sf pointer']

        compacted_schema = []
        for tag in self.schema_order:
            stag = self.schema[tag.lower()]
            compacted_tag = []
            for header in s['headers']:
                try:
                    compacted_tag.append(stag[header].replace("$", ","))
                except AttributeError:
                    compacted_tag.append(stag[header])
                except KeyError:
                    if header == 'Sf pointer':
                        try:
                            compacted_tag.append(stag['Framecode value flag'])
                        except KeyError:
                            compacted_tag.append(None)
                    elif header == 'BMRB data type':
                        compacted_tag.append('any')
                    else:
                        compacted_tag.append(None)

            compacted_schema.append(compacted_tag)

        s['tags'] = compacted_schema

        if serialize:
            return json.dumps(s, default=_json_serialize)
        else:
            return s


class Entry(object):
    """An OO representation of a BMRB entry. You can initialize this
    object several ways; (e.g. from a file, from the official database,
    from scratch) see the class methods below."""

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

    def __init__(self, **kwargs):
        """ You should not directly instantiate an Entry using this method.
            Instead use the class methods:"
              Entry.from_database()
              Entry.from_file()
              Entry.from_string()
              Entry.from_scratch()
              Entry.from_json()
              Entry.from_template()"""

        # Default initializations
        self.entry_id = 0
        self.frame_list = []
        self.source = None

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate an Entry "
                             "using this method. Instead use the class methods:"
                             " Entry.from_database(), Entry.from_file(), "
                             "Entry.from_string(), Entry.from_scratch(), and "
                             "Entry.from_json().")

        # Initialize our local variables
        self.frame_list = []

        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = "from_file('%s')" % kwargs['file_name']
        elif 'entry_num' in kwargs:
            self.source = "from_database(%s)" % kwargs['entry_num']

            # The location to fetch entries from
            entry_number = kwargs['entry_num']
            url = 'https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr%s/bmr%s_3.str' % (entry_number, entry_number)

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
        # Creating from template (schema)
        elif 'all_tags' in kwargs:
            self.entry_id = kwargs['entry_id']

            saveframe_categories = {}
            schema = _get_schema(kwargs['schema'])
            schema_obj = schema.schema
            for tag in [schema_obj[x.lower()] for x in schema.schema_order]:
                category = tag['SFCategory']
                if category not in saveframe_categories:
                    saveframe_categories[category] = True
                    self.frame_list.append(Saveframe.from_template(category, category + "_1",
                                                                   entry_id=self.entry_id,
                                                                   all_tags=kwargs['all_tags'],
                                                                   default_values=kwargs['default_values'],
                                                                   schema=schema))
            entry_saveframe = self.get_saveframes_by_category('entry_information')[0]
            entry_saveframe['NMR_STAR_version'] = schema.version
            entry_saveframe['Original_NMR_STAR_version'] = schema.version

            return
        else:
            # Initialize a blank entry
            self.entry_id = kwargs['entry_id']
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

        return "<pynmrstar.Entry '%s' %s>" % (self.entry_id, self.source)

    def __setitem__(self, key, item):
        """Set the indicated saveframe."""

        # It is a saveframe
        if isinstance(item, Saveframe):
            # Add by ordinal
            try:
                self.frame_list[key] = item
            except TypeError:
                # Add by key
                if key in self.frame_dict:
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

        sf_strings = []
        seen_saveframes = {}
        for saveframe in self:
            if saveframe.category in seen_saveframes:
                sf_strings.append(saveframe.__str__(first_in_category=False))
            else:
                sf_strings.append(saveframe.__str__(first_in_category=True))
                seen_saveframes[saveframe.category] = True

        return "data_%s\n\n%s" % (self.entry_id, "\n".join(sf_strings))

    @property
    def category_list(self):
        """ Returns a list of the unique categories present in the entry. """

        category_list = []
        for saveframe in self.frame_list:
            category = saveframe.category
            if category and category not in category_list:
                category_list.append(category)
        return list(category_list)

    @property
    def empty(self):
        """ Check if the entry has no data. Ignore the structural tags."""

        for saveframe in self.frame_list:
            if not saveframe.empty:
                return False

        return True

    @property
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

        return frame_dict

    @classmethod
    def from_database(cls, entry_num):
        """Create an entry corresponding to the most up to date entry on
        the public BMRB server. (Requires ability to initiate outbound
        HTTP connections.)"""

        # Try to load the entry using JSON
        try:
            entry_url = _API_URL + "/entry/%s"
            entry_url = entry_url % entry_num

            # If we have zlib get the compressed entry
            if zlib:
                entry_url += "?format=zlib"

            # Download the entry
            try:
                req = Request(entry_url)
                req.add_header('Application', 'PyNMRSTAR %s' % __version__)
                url_request = urlopen(req)

                if url_request.getcode() == 404:
                    raise IOError("Entry '%s' does not exist in the public "
                                  "database." % entry_num)
                else:
                    serialized_ent = url_request.read()

                url_request.close()

            except HTTPError as err:
                if err.code == 404:
                    raise IOError("Entry '%s' does not exist in the public "
                                  "database." % entry_num)
                else:
                    raise err

            # If we have zlib decompress
            if zlib:
                serialized_ent = zlib.decompress(serialized_ent)

            # Convert bytes to string if python3
            if PY3:
                serialized_ent = serialized_ent.decode()

            # Parse JSON string to dictionary
            json_data = json.loads(serialized_ent)
            if "error" in json_data:
                # Something up with the API server, try the FTP site
                return cls(entry_num=entry_num)

            # If pure zlib there is no wrapping
            if zlib:
                entry_dictionary = json_data
            else:
                entry_dictionary = json_data[str(entry_num)]

            ent = Entry.from_json(entry_dictionary)

            # Update the entry source
            ent_source = "from_database(%s)" % entry_num
            ent.source = ent_source
            for each_saveframe in ent:
                each_saveframe.source = ent_source
                for each_loop in each_saveframe:
                    each_loop.source = ent_source

            if CONVERT_DATATYPES:
                schema = _get_schema()
                for each_saveframe in ent:
                    for tag in each_saveframe.tags:
                        cur_tag = each_saveframe.tag_prefix + "." + tag[0]
                        tag[1] = schema.convert_tag(cur_tag, tag[1],
                                                    line_num="SF %s" %
                                                             each_saveframe.name)
                    for loop in each_saveframe:
                        for row in loop.data:
                            for pos in range(0, len(row)):
                                category = loop.category + "." + loop.tags[pos]
                                line_num = "Loop %s" % loop.category
                                row[pos] = schema.convert_tag(category, row[pos],
                                                              line_num=line_num)

            return ent
        # The entry doesn't exist
        except KeyError:
            raise IOError("Entry '%s' does not exist in the public database." %
                          entry_num)
        except URLError:
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
        """Create an empty entry that you can programmatically add to.
        You must pass a value corresponding to the Entry ID.
        (The unique identifier "xxx" from "data_xxx".)"""

        return cls(entry_id=entry_id)

    @classmethod
    def from_template(cls, entry_id, all_tags=False, default_values=False, schema=None):
        """ Create an entry that has all of the saveframes and loops from the
        schema present. No values will be assigned. Specify the entry
        ID when calling this method.

        The optional argument 'all_tags' forces all tags to be included
        rather than just the mandatory tags.

        The optional argument 'default_values' will insert the default
        values from the schema.

        The optional argument 'schema' allows providing a custom schema."""

        schema = _get_schema(schema)
        entry = cls(entry_id=entry_id, all_tags=all_tags, default_values=default_values, schema=schema)
        entry.source = "from_template(%s)" % schema.version
        return entry

    def add_saveframe(self, frame):
        """Add a saveframe to the entry."""

        if not isinstance(frame, Saveframe):
            raise ValueError("You can only add instances of saveframes "
                             "using this method.")

        # Do not allow the addition of saveframes with the same name
        #  as a saveframe which already exists in the entry
        if frame.name in self.frame_dict:
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
            for frame in self.frame_dict:
                if other.frame_dict.get(frame, None) is None:
                    diffs.append("No saveframe with name '%s' in other entry." %
                                 self.frame_dict[frame].name)
                else:
                    comp = self.frame_dict[frame].compare(
                        other.frame_dict[frame])
                    if len(comp) > 0:
                        diffs.append("Saveframes do not match: '%s'." %
                                     self.frame_dict[frame].name)
                        diffs.extend(comp)

        except AttributeError as err:
            diffs.append("An exception occurred while comparing: '%s'." % err)

        return diffs

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

        frames = self.frame_dict
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

        my_schema = _get_schema(schema)

        # The saveframe/loop order
        ordering = my_schema.category_order

        # Use these to sort saveframes and loops
        def sf_key(x):
            """ Helper function to sort the saveframes."""

            try:
                return ordering.index(x.tag_prefix), x.get_tag("ID")
            except ValueError:
                # Generate an arbitrary sort order for saveframes that aren't
                #  in the schema but make sure that they always come after
                #   saveframes in the schema
                return len(ordering) + hash(x), x.get_tag("ID")

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
            each_frame.sort_tags(schema=my_schema)
            # Iterate through the loops
            for each_loop in each_frame:
                each_loop.sort_tags(schema=my_schema)

                # See if we can sort the rows (in addition to tags)
                try:
                    each_loop.sort_rows("Ordinal")
                except ValueError:
                    pass
            each_frame.loops.sort(key=loop_key)
        self.frame_list.sort(key=sf_key)

    def nef_string(self):
        """ Returns a string representation of the entry in NEF. """

        warnings.warn("""Specifically:

Before writing out objects as strings, perform these two steps:

Update the global string conversion dictionary:
pynmrstar.definitions.STR_CONVERSION_DICT = {None: ".", True: "true", False: "false"}

Rather than using str(obj) to render as a string, use obj.format(show_comments=False, skip_empty_loops=True).""",
                      DeprecationWarning)

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

    def print_tree(self):
        """Prints a summary, tree style, of the frames and loops in
        the entry."""

        print(repr(self))
        for pos, frame in enumerate(self):
            print("\t[%d] %s" % (pos, repr(frame)))
            for pos2, one_loop in enumerate(frame):
                print("\t\t[%d] %s" % (pos2, repr(one_loop)))

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
            for ordinal in range(0, len(saveframe_names) - 2):
                if saveframe_names[ordinal] == saveframe_names[ordinal + 1]:
                    errors.append("Multiple saveframes with same name: '%s'" %
                                  saveframe_names[ordinal])

            # Check for dangling references
            fdict = self.frame_dict

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
                                               each_loop.tags[pos]))

        # Ask the saveframes to check themselves for errors
        for frame in self:
            errors.extend(frame.validate(validate_schema=validate_schema,
                                         schema=schema,
                                         validate_star=validate_star))

        return errors

    def write_to_file(self, file_name, format_="nmrstar"):
        """ Writes the entry to the specified file in NMR-STAR format.

        Optionally specify format_=json to write to the file in JSON format."""

        if format_ not in ["nmrstar", "json"]:
            raise ValueError("Invalid output format.")

        data_to_write = ''
        if format_ == "nmrstar":
            data_to_write = str(self)
        elif format_ == "json":
            data_to_write = self.get_json()

        out_file = open(file_name, "w")
        out_file.write(data_to_write)
        out_file.close()


class Saveframe(object):
    """A saveframe object. Create using the class methods, see below."""

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
            del self.loops[self.loops.index(to_delete)]
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
            if results:
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

    def __init__(self, **kwargs):
        """Don't use this directly. Use the class methods to construct:
             Saveframe.from_scratch()
             Saveframe.from_string()
             Saveframe.from_template()
             Saveframe.from_file()
             Saveframe.from_json()"""

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate a Saveframe "
                             "using this method. Instead use the class methods:"
                             " Saveframe.from_scratch(), Saveframe.from_string()"
                             ", Saveframe.from_template(), Saveframe.from_file()"
                             ", and Saveframe.from_json().")

        # Initialize our local variables
        self.tags = []
        self.loops = []
        self.name = ""
        self.source = "unknown"
        self.category = None
        self.tag_prefix = None

        star_buffer = ""

        # Update our source if it provided
        if 'source' in kwargs:
            self.source = kwargs['source']

        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = "from_file('%s')" % kwargs['file_name']
        # Creating from template (schema)
        elif 'all_tags' in kwargs:
            schema_obj = _get_schema(kwargs['schema'])
            schema = schema_obj.schema
            self.category = kwargs['category']

            self.name = self.category
            if 'saveframe_name' in kwargs and kwargs['saveframe_name']:
                self.name = kwargs['saveframe_name']

            # Make sure it is a valid category
            if self.category not in [x["SFCategory"] for x in schema.values()]:
                raise ValueError("The saveframe category '%s' was not found "
                                 "in the dictionary." % self.category)

            s = sorted(schema.values(),
                       key=lambda _: float(_["Dictionary sequence"]))

            loops_added = []

            for item in s:
                if item["SFCategory"] == self.category:

                    # It is a tag in this saveframe
                    if item["Loopflag"] == "N":

                        ft = _format_tag(item["Tag"])
                        # Set the value for sf_category and sf_framecode
                        if ft == "Sf_category":
                            self.add_tag(item["Tag"], self.category)
                        elif ft == "Sf_framecode":
                            self.add_tag(item["Tag"], self.name)
                        # If the tag is the entry ID tag, set the entry ID
                        elif item["entryIdFlg"] == "Y":
                            self.add_tag(item["Tag"], kwargs['entry_id'])
                        else:
                            tag_value = None
                            if kwargs['default_values']:
                                if item['default value'] != "?" and item['default value'] != '':
                                    tag_value = item['default value']
                            # Unconditional add
                            if kwargs['all_tags']:
                                self.add_tag(item["Tag"], tag_value)
                            # Conditional add
                            else:
                                if item["public"] != "I":
                                    self.add_tag(item["Tag"], tag_value)

                    # It is a contained loop tag
                    else:
                        cat_formatted = _format_category(item["Tag"])
                        if cat_formatted not in loops_added:
                            loops_added.append(cat_formatted)
                            try:
                                self.add_loop(Loop.from_template(cat_formatted,
                                                                 all_tags=kwargs['all_tags'],
                                                                 schema=schema_obj))
                            except ValueError:
                                pass
            return

        elif 'saveframe_name' in kwargs:
            # If they are creating from scratch, just get the saveframe name
            self.name = kwargs['saveframe_name']
            if 'tag_prefix' in kwargs:
                self.tag_prefix = _format_category(kwargs['tag_prefix'])
            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kwargs and kwargs['csv']:
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

    @property
    def empty(self):
        """ Check if the saveframe has no data. Ignore the structural tags."""

        for tag in self.tags:
            tag_lower = tag[0].lower()
            if tag_lower not in ['sf_category', 'sf_framecode', 'id', 'entry_id', 'nmr_star_version',
                                 'original_nmr_star_version']:
                if tag[1] not in [None, '', '.', '?']:
                    return False

        for loop in self.loops:
            if not loop.empty:
                return False

        return True

    @classmethod
    def from_scratch(cls, sf_name, tag_prefix=None, source="from_scratch()"):
        """Create an empty saveframe that you can programmatically add
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
        ret.category = json_dict.get('category', None)
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
    def from_template(cls, category, name=None, entry_id=None, all_tags=False, default_values=False, schema=None):
        """ Create a saveframe that has all of the tags and loops from the
        schema present. No values will be assigned. Specify the category
        when calling this method. Optionally also provide the name of the
        saveframe as the 'name' argument.

        The optional argument 'all_tags' forces all tags to be included
        rather than just the mandatory tags.

        The optional argument 'default_values' will insert the default
        values from the schema."""

        schema = _get_schema(schema)
        return cls(category=category, saveframe_name=name, entry_id=entry_id,
                   all_tags=all_tags, default_values=default_values, schema=schema,
                   source="from_template(%s)" % schema.version)

    def __repr__(self):
        """Returns a description of the saveframe."""

        return "<pynmrstar.Saveframe '%s'>" % self.name

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

    def __str__(self, first_in_category=True):
        """Returns the saveframe in STAR format as a string."""

        if ALLOW_V2_ENTRIES:
            if self.tag_prefix is None:
                width = max([len(x[0]) for x in self.tags])
            else:
                width = max([len(self.tag_prefix + "." + x[0]) for x in self.tags])
        else:
            if self.tag_prefix is None:
                raise ValueError("The tag prefix was never set!")

            # Make sure this isn't a dummy saveframe before proceeding
            try:
                width = max([len(self.tag_prefix + "." + x[0]) for x in self.tags])
            except ValueError:
                return "\nsave_%s\n\nsave_\n" % self.name

        ret_string = ""

        # Insert the comment if not disabled
        if not DONT_SHOW_COMMENTS:
            if self.category in _COMMENT_DICTIONARY:
                this_comment = _COMMENT_DICTIONARY[self.category]
                if first_in_category or this_comment['every_flag']:
                    ret_string = _COMMENT_DICTIONARY[self.category]['comment']

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
        ret_string += "\nsave_\n"
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
                name = name[name.index(".") + 1:]
            else:
                name = name[1:]

        # No duplicate tags
        if self.get_tag(name):
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
                self.tag_prefix + "." + name, value, line_num=linenum)]
        else:
            new_tag = [name, value]

        # Set the category if the tag we are loading is the category
        tagname_lower = name.lower()
        if tagname_lower == "sf_category" or tagname_lower == "_saveframe_category":
            if not self.category:
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
                             "entry does not." %
                             (len(self.tags), len(other.tags)))

            for tag in self.tags:
                other_tag = other.get_tag(tag[0])

                if not other_tag:
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
                                 " entry." % each_loop.category)

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
                    [str(self.tag_prefix) + "." + str(x[0]) for x in self.tags])
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

        def sort_key(x):
            return _tag_key(self.tag_prefix + "." + x[0], schema=schema)

        self.tags.sort(key=sort_key)

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
        if not my_category:
            errors.append("Cannot properly validate saveframe: '" + self.name +
                          "'. No saveframe category defined.")
            my_category = None

        if validate_schema:
            # Get the default schema if we are not passed a schema
            my_schema = _get_schema(schema)

            for tag in self.tags:
                line_number = str(tag[2]) + " of original file" if len(tag) > 2 else None
                formatted_tag = self.tag_prefix + "." + tag[0]
                cur_errors = my_schema.val_type(formatted_tag, tag[1],
                                                category=my_category,
                                                linenum=line_number)
                errors.extend(cur_errors)

        # Check the loops for errors
        for each_loop in self.loops:
            errors.extend(
                each_loop.validate(validate_schema=validate_schema,
                                   schema=schema,
                                   validate_star=validate_star,
                                   category=my_category))

        return errors

    def write_to_file(self, file_name, format_="nmrstar"):
        """ Writes the saveframe to the specified file in NMR-STAR format.

        Optionally specify format_=json to write to the file in JSON format."""

        if format_ not in ["nmrstar", "json"]:
            raise ValueError("Invalid output format.")

        data_to_write = ''
        if format_ == "nmrstar":
            data_to_write = str(self)
        elif format_ == "json":
            data_to_write = self.get_json()

        out_file = open(file_name, "w")
        out_file.write(data_to_write)
        out_file.close()


class Loop(object):
    """A BMRB loop object. Create using the class methods, see below."""

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

    def __init__(self, **kwargs):
        """ You should not directly instantiate a Loop using this method.
            Instead use the class methods:
              Loop.from_scratch()
              Loop.from_string()
              Loop.from_template()
              Loop.from_file()
              Loop.from_json()"""

        # Initialize our local variables
        self.tags = []
        self.data = []
        self.category = None
        self.source = "unknown"

        star_buffer = ""

        # Update our source if it provided
        if 'source' in kwargs:
            self.source = kwargs['source']

        # Update our category if provided
        if 'category' in kwargs:
            self.category = _format_category(kwargs['category'])
            return

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate a Loop using "
                             "this method. Instead use the class methods: "
                             "Loop.from_scratch(), Loop.from_string(), "
                             "Loop.from_template(), Loop.from_file(), and "
                             "Loop.from_json().")

        # Parsing from a string
        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        # Parsing from a file
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = "from_file('%s')" % kwargs['file_name']
        # Creating from template (schema)
        elif 'tag_prefix' in kwargs:

            tags = Loop._get_tags_from_schema(kwargs['tag_prefix'],
                                              all_tags=kwargs['all_tags'],
                                              schema=kwargs['schema'])
            for tag in tags:
                self.add_tag(tag)

            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kwargs and kwargs['csv']:
            csv_file = csv_reader(star_buffer)
            self.add_tag(next(csv_file))
            for row in csv_file:
                self.add_data(row)
            self.source = "from_csv('%s')" % kwargs['csv']
            return

        tmp_entry = Entry.from_scratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_0 save_internaluseyoushouldntseethis_frame"
                               " _internal.use internal " + star_buffer.read() +
                               " save_")
        parser = _Parser(entry_to_parse_into=tmp_entry)
        try:
            parser.parse(star_buffer.read(), source=self.source)
        except ValueError as err:
            if 'internaluseyoushouldntseethis' in str(err):
                raise ValueError("Invalid loop. Loops must start with the 'loop_' keyword.", err.args[1])
            else:
                raise err

        # Check that there was only one loop here
        if len(tmp_entry[0].loops) > 1:
            raise ValueError("You attempted to parse one loop but the source "
                             "you provided had more than one loop. Please "
                             "either parse all loops as a saveframe or only "
                             "parse one loop. Loops detected:"
                             " " + str(tmp_entry[0].loops))

        # Copy the first parsed saveframe into ourself
        self.tags = tmp_entry[0][0].tags
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
            common = os.path.commonprefix(self.tags)
            if common.endswith("_"):
                common = common[:-1]
            if common == "":
                common = "Unknown"
            return "<pynmrstar.Loop '%s'>" % common
        else:
            return "<pynmrstar.Loop '%s'>" % self.category

    def __setitem__(self, key, item):
        """Set all of the instances of a tag to the provided value.
        If there are 5 rows of data in the loop, you will need to
        assign a list with 5 elements."""

        tag = _format_tag(key)

        # Check that their tag is in the loop
        if tag not in self.tags:
            raise ValueError("Cannot assign to tag '%s' as it does not exist "
                             "in this loop." % key)

        # Determine where to assign
        tag_id = self.tags.index(tag)

        # Make sure they provide a list of the correct length
        if len(self[key]) != len(item):
            raise ValueError("To assign to a tag you must provide a list (or "
                             "iterable) of a length equal to the number of "
                             "values that currently exist for that tag. The tag"
                             " '%s' current has %d values and you supplied "
                             "%d values." % (key, len(self[key]), len(item)))

        # Do the assignment
        for pos, row in enumerate(self.data):
            row[tag_id] = item[pos]

    def __str__(self):
        """Returns the loop in STAR format as a string."""

        # Check if there is any data in this loop
        if len(self.data) == 0:
            # They do not want us to print empty loops
            if SKIP_EMPTY_LOOPS:
                return ""
            else:
                # If we have no tags than return the empty loop
                if len(self.tags) == 0:
                    return "\n   loop_\n\n   stop_\n"

        if len(self.tags) == 0:
            raise ValueError("Impossible to print data if there are no "
                             "associated tags. Loop: '%s'." % self.category)

        # Make sure the tags and data match
        self._check_tags_match_data()

        # Start the loop
        ret_string = "\n   loop_\n"
        # Print the tags
        format_string = "      %-s\n"

        # Check to make sure our category is set
        if self.category is None and not ALLOW_V2_ENTRIES:
            raise ValueError("The category was never set for this loop. Either "
                             "add a tag with the category intact, specify it"
                             " when generating the loop, or set it using "
                             "set_category.")

        # Print the categories
        if self.category is None:
            for tag in self.tags:
                ret_string += format_string % tag
        else:
            for tag in self.tags:
                ret_string += format_string % (self.category + "." + tag)

        ret_string += "\n"

        row_strings = []

        if len(self.data) != 0:

            # Make a copy of the data
            working_data = []
            # Put quotes as needed on the data
            for datum in self.data:
                working_data.append([clean_value(x) for x in datum])

            # The nightmare below creates a list of the maximum length of
            #  elements in each tag in the self.data matrix. Don't try to
            #   understand it. It's an incomprehensible list comprehension.
            title_widths = [max([len(str(x)) + 3 for x in col]) for
                            col in [[row[x] for row in working_data] for
                                    x in range(0, len(working_data[0]))]]

            # TODO: Replace with a smarter title_widths algorithm - or in C
            # It needs to not count the length of items that will go on their
            # own line...

            # Generate the format string
            format_string = "     " + "%-*s" * len(self.tags) + " \n"

            # Print the data, with the tags sized appropriately
            for datum in working_data:
                for pos, item in enumerate(datum):
                    if "\n" in item:
                        datum[pos] = "\n;\n%s;\n" % item

                # Print the data (combine the tags' widths with their data)
                tag_width_list = [d for d in zip(title_widths, datum)]
                row_strings.append(format_string % tuple(chain.from_iterable(tag_width_list)))

        # Close the loop
        ret_string += "".join(row_strings) + "\n   stop_\n"
        return ret_string

    @property
    def empty(self):
        """ Check if the loop has no data. """

        for row in self.data:
            for col in row:
                if col not in [None, '', '.', '?']:
                    return False

        return True

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
        ret.tags = json_dict['tags']
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

        schema = _get_schema(schema)
        return cls(tag_prefix=tag_prefix, all_tags=all_tags,
                   schema=schema, source="from_template(%s)" % schema.version)

    @staticmethod
    def _get_tags_from_schema(category, schema=None, all_tags=False):
        """ Returns the tags from the schema for the category of this
        loop. """

        schema = _get_schema(schema)

        # Put the _ on the front for them if necessary
        if not category.startswith("_"):
            category = "_" + category
        if not category.endswith("."):
            category = category + "."

        tags = []

        for item in schema.schema_order:
            # The tag is in the loop
            if item.lower().startswith(category.lower()):

                # Unconditional add
                if all_tags:
                    tags.append(item)
                # Conditional add
                else:
                    if schema.schema[item.lower()]["public"] != "I":
                        tags.append(item)
        if len(tags) == 0:
            raise ValueError("The tag prefix '%s' has no corresponding tags"
                             " in the dictionary." % category)

        return tags

    def _tag_index(self, tag_name):
        """ Helper method to do a case-insensitive check for the presence
        of a given tag in this loop. Returns the index of the tag if found
        and None if not found."""

        try:
            lc_col = [x.lower() for x in self.tags]
            return lc_col.index(_format_tag(str(tag_name)).lower())
        except ValueError:
            return None

    def _check_tags_match_data(self):
        """ Ensures that each row of the data has the same number of
        elements as there are tags for the loop. This is necessary to
        print or do some other operations on loops that count on the values
        matching. """

        # Make sure that if there is data, it is the same width as the
        #  tag names
        if len(self.data) > 0:
            for row in self.data:
                if len(self.tags) != len(row):
                    raise ValueError("The number of tags must match the "
                                     "width of the data. Loop: '%s'." %
                                     self.category)

    def add_column(self, name, ignore_duplicates=False, update_data=False):
        """ Deprecated, please use add_tag() instead. """
        warnings.warn("add_column() is deprecated. Please use add_tag() "
                      "instead.", DeprecationWarning)
        return self.add_tag(name, ignore_duplicates, update_data)

    def add_data(self, the_list, rearrange=False):
        """Add a list to the data field. Items in list can be any type,
        they will be converted to string and formatted correctly. The
        list must have the same cardinality as the tag names or you
        must set the rearrange variable to true and have already set all
        the tag names in the loop. Rearrange will break a longer list into
        rows based on the number of tags."""

        # Add one row of data
        if not rearrange:
            if len(the_list) != len(self.tags):
                raise ValueError("The list must have the same number of "
                                 "elements as the number of tags! Insert "
                                 "tag names first.")
            # Add the user data
            self.data.append(the_list)
            return

        # Break their data into chunks based on the number of tags
        processed_data = [the_list[x:x + len(self.tags)] for
                          x in range(0, len(the_list), len(self.tags))]
        if len(processed_data[-1]) != len(self.tags):
            raise ValueError("The number of data elements in the loop %s"
                             " does not match the number of tags!" %
                             self.category)

        # Auto convert datatypes if option set
        if CONVERT_DATATYPES:
            tschem = _get_schema()
            for row in processed_data:
                for tag_id, datum in enumerate(row):
                    row[tag_id] = tschem.convert_tag(self.category + "." +
                                                     self.tags[tag_id],
                                                     datum,
                                                     line_num="Loop %s" %
                                                              self.category)

        self.data.extend(processed_data)

    def add_data_by_column(self, column_id, value):
        """ Deprecated, please use add_data_by_tag() instead. """

        warnings.warn("add_data_by_column() is deprecated. Please "
                      " use add_data_by_tag() instead.", DeprecationWarning)
        return self.add_data_by_tag(column_id, value)

    def add_data_by_tag(self, tag_id, value):
        """Add data to the loop one element at a time, based on tag.
        Useful when adding data from SANS parsers."""

        # Make sure the category matches - if provided
        if "." in tag_id:
            supplied_category = _format_category(str(tag_id))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your tag '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        pos = self._tag_index(tag_id)
        if pos is None:
            raise ValueError("The tag '%s' to which you are attempting "
                             "to add data does not yet exist. Create the "
                             "tags before adding data." % tag_id)
        if len(self.data) == 0:
            self.data.append([])
        if len(self.data[-1]) == len(self.tags):
            self.data.append([])
        if len(self.data[-1]) != pos:
            raise ValueError("You cannot add data out of tag order.")
        self.data[-1].append(value)

    def add_tag(self, name, ignore_duplicates=False, update_data=False):
        """Add a tag to the tag name list. Does a bit of validation
        and parsing. Set ignore_duplicates to true to ignore attempts
        to add the same tag more than once rather than raise an
        exception.

        You can also pass a list of tag names to add more than one
        tag at a time.

        Adding a tag will update the data array to match by adding
        None values to the rows if you specify update_data=True."""

        # If they have passed multiple tags to add, call ourself
        #  on each of them in succession
        if isinstance(name, (list, tuple)):
            for item in name:
                self.add_tag(item, ignore_duplicates=ignore_duplicates,
                             update_data=update_data)
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
                    raise ValueError("One loop cannot have tags with "
                                     "different categories (or tags that "
                                     "don't match the loop category)!")
                name = name[name.index(".") + 1:]
            else:
                name = name[1:]

        # Ignore duplicate tags
        if self._tag_index(name) is not None:
            if ignore_duplicates:
                return
            else:
                raise ValueError("There is already a tag with the name"
                                 " '%s'." % name)
        if "." in name:
            raise ValueError("There cannot be more than one '.' in a tag name.")
        if " " in name:
            raise ValueError("Tag names can not contain spaces.")

        # Add the tag
        self.tags.append(name)

        # Add None's to the rows of data
        if update_data:

            for row in self.data:
                row.append(None)

    def clear_data(self):
        """Erases all data in this loop. Does not erase the tag names
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

            # Check tags of loops
            if ([x.lower() for x in self.tags] !=
                    [x.lower() for x in other.tags]):
                diffs.append("\t\tLoop tag names do not match for loop with "
                             "category '%s'." % self.category)

            # No point checking if data is the same if the tag names aren't
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
        provided tag name. If index_tag is provided, that tag is
        renumbered starting with 1. Returns the deleted rows."""

        # Make sure the category matches - if provided
        if "." in tag:
            supplied_category = _format_category(str(tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your tag '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        search_tag = self._tag_index(tag)
        if search_tag is None:
            raise ValueError("The tag you provided '%s' isn't in this loop!" %
                             tag)

        deleted = []

        # Delete all rows in which the user-provided tag matched
        cur_row = 0
        while cur_row < len(self.data):
            if self.data[cur_row][search_tag] == value:
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
            result.add_tag(tag)

        # Add the data for the tags to the new loop
        results = self.get_tag(valid_tags)

        # If there is only a single tag, we can't add data the same way
        if len(valid_tags) == 1:
            for item in results:
                result.add_data([item])
        else:
            for row in results:
                result.add_data(row)

        # Assign the category of the new loop
        if result.category is None:
            result.category = self.category

        return result

    def get_columns(self):
        """ Deprecated alias for get_tags() """

        warnings.warn("get_columns() is deprecated. Please use get_tag_names() instead.", DeprecationWarning)
        return self.get_tag_names()

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
                    [str(self.category) + "." + str(x) for x in self.tags])
            else:
                cwriter.writerow([str(x) for x in self.tags])

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
            "tags": self.tags,
            "data": self.data
        }

        if serialize:
            return json.dumps(loop_dict, default=_json_serialize)
        else:
            return loop_dict

    def get_tag_names(self):
        """ Return the tag names for this entry with the category
        included. Throws ValueError if the category was never set.

        To fetch tag values use get_tag()."""

        if not self.category:
            raise ValueError("You never set the category of this loop.")

        return [self.category + "." + x for x in self.tags]

    def get_tag(self, tags=None, whole_tag=False, dict_result=False):
        """Provided a tag name (or a list of tag names), or ordinals
        corresponding to tags, return the selected tags by row as
        a list of lists.

        If whole_tag=True return the full tag name along with the tag
        value, or if dict_result=True, as the tag key.

        If dict_result=True, return the tags as a list of dictionaries
        in which the tag value points to the tag."""

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
                raise ValueError("Cannot fetch data with tag '%s' because "
                                 "the category does not match the category of "
                                 "this loop '%s'." % (item, self.category))
            lower_tags[pos] = _format_tag(item).lower()

        # Make a lower case copy of the tags
        tags_lower = [x.lower() for x in self.tags]

        # Map tag name to tag position in list
        tag_mapping = dict(zip(reversed(tags_lower),
                               reversed(range(len(tags_lower)))))

        # Make sure their fields are actually present in the entry
        tag_ids = []
        for query in lower_tags:
            if str(query) in tag_mapping:
                tag_ids.append(tag_mapping[query])
            elif isinstance(query, int):
                tag_ids.append(query)
            else:
                if ALLOW_V2_ENTRIES:
                    return []
                else:
                    raise ValueError("Could not locate the tag with name"
                                     " or ID: '%s' in loop '%s'." %
                                     (query, str(self.category)))

        # First build the tags as a list
        if not dict_result:

            # Use a list comprehension to pull the correct tags out of the rows
            if whole_tag:
                result = [[[self.category + "." + self.tags[col_id], row[col_id]]
                           for col_id in tag_ids] for row in self.data]
            else:
                result = [[row[col_id] for col_id in tag_ids] for
                          row in self.data]

            # Strip the extra list if only one tag
            if len(lower_tags) == 1:
                return [x[0] for x in result]
            else:
                return result
        # Make a dictionary
        else:
            if whole_tag:
                result = [dict((self.category + "." + self.tags[col_id], row[col_id]) for col_id in tag_ids) for
                          row in self.data]
            else:
                result = [dict((self.tags[col_id], row[col_id]) for col_id in tag_ids) for row in self.data]

        return result

    def add_missing_tags(self, schema=None, all_tags=False):
        """ Automatically adds any missing tags (according to the schema),
        sorts the tags, and renumbers the tags by ordinal. """

        self.add_tag(Loop._get_tags_from_schema(self.category, schema=schema, all_tags=all_tags),
                     ignore_duplicates=True, update_data=True)
        self.sort_tags()

        # See if we can sort the rows (in addition to tags)
        try:
            self.sort_rows("Ordinal")
        except ValueError:
            pass
        except TypeError:
            ordinal_idx = self._tag_index("Ordinal")

            # If we are in another row, assign to the previous row
            for pos, row in enumerate(self.data):
                row[ordinal_idx] = pos + 1

    def print_tree(self):
        """Prints a summary, tree style, of the loop."""

        print(repr(self))

    def renumber_rows(self, index_tag, start_value=1, maintain_ordering=False):
        """Renumber a given tag incrementally. Set start_value to
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

        # Determine which tag ID to renumber
        renumber_tag = self._tag_index(index_tag)

        # The tag to replace in is the tag they specify
        if renumber_tag is None:
            # Or, perhaps they specified an integer to represent the tag?
            try:
                renumber_tag = int(index_tag)
            except ValueError:
                raise ValueError("The renumbering tag you provided '%s' "
                                 "isn't in this loop!" % index_tag)

        # Verify the renumbering column ID
        if renumber_tag >= len(self.tags) or renumber_tag < 0:
            raise ValueError("The renumbering tag ID you provided '%s' is "
                             "too large or too small! Valid tag ids are"
                             "0-%d." % (index_tag, len(self.tags) - 1))

        # Do nothing if we have no data
        if len(self.data) == 0:
            return

        # Make sure the tags and data match
        self._check_tags_match_data()

        if maintain_ordering:
            # If they have a string buried somewhere in the row, we'll
            #  have to restore the original values
            data_copy = deepcopy(self.data)
            offset = 0
            for pos in range(0, len(self.data)):
                try:
                    if pos == 0:
                        offset = start_value - int(self.data[0][renumber_tag])
                    new_data = int(self.data[pos][renumber_tag]) + offset
                    self.data[pos][renumber_tag] = new_data
                except ValueError:
                    self.data = data_copy
                    raise ValueError("You can't renumber a row containing "
                                     "anything that can't be coerced into an "
                                     "integer using maintain_ordering. I.e. "
                                     "what am I suppose to renumber '%s' to?" %
                                     self.data[pos][renumber_tag])

        # Simple renumbering algorithm if we don't need to maintain the ordering
        else:
            for pos in range(0, len(self.data)):
                self.data[pos][renumber_tag] = pos + start_value

    def set_category(self, category):
        """ Set the category of the loop. Useful if you didn't know the
        category at loop creation time."""

        self.category = _format_category(category)

    def sort_tags(self, schema=None):
        """ Rearranges the tag names and data in the loop to match the order
        from the schema. Uses the BMRB schema unless one is provided."""

        current_order = self.get_tag_names()

        # Sort the tags
        def sort_key(_):
            return _tag_key(_, schema=schema)

        sorted_order = sorted(current_order, key=sort_key)

        # Don't touch the data if the tags are already in order
        if sorted_order == current_order:
            return
        else:
            self.data = self.get_tag(sorted_order)
            self.tags = [_format_tag(x) for x in sorted_order]

    def sort_rows(self, tags, key=None):
        """ Sort the data in the rows by their values for a given tag
        or tags. Specify the tags using their names or ordinals.
        Accepts a list or an int/float. By default we will sort
        numerically. If that fails we do a string sort. Supply a
        function as key and we will order the elements based on the
        keys it provides. See the help for sorted() for more details. If
        you provide multiple tags to sort by, they are interpreted as
        increasing order of sort priority."""

        # Do nothing if we have no data
        if len(self.data) == 0:
            return

        # This will determine how we sort
        sort_ordinals = []

        if isinstance(tags, list):
            processing_list = tags
        else:
            processing_list = [tags]

        # Process their input to determine which tags to operate on
        for cur_tag in [str(x) for x in processing_list]:

            # Make sure the category matches
            if "." in cur_tag:
                supplied_category = _format_category(cur_tag)
                if supplied_category.lower() != self.category.lower():
                    raise ValueError("Category provided in your tag '%s' does "
                                     "not match this loop's category '%s'." %
                                     (supplied_category, self.category))

            renumber_tag = self._tag_index(cur_tag)

            # They didn't specify a valid tag
            if renumber_tag is None:
                # Perhaps they specified an integer to represent the tag?
                try:
                    renumber_tag = int(cur_tag)
                except ValueError:
                    raise ValueError("The sorting tag you provided '%s' "
                                     "isn't in this loop!" % cur_tag)

            # Verify the renumbering column ID
            if renumber_tag >= len(self.tags) or renumber_tag < 0:
                raise ValueError("The sorting tag ID you provided '%s' is "
                                 "too large or too small! Valid tag ids"
                                 " are 0-%d." % (cur_tag, len(self.tags) - 1))

            sort_ordinals.append(renumber_tag)

        # Do the sort(s)
        for tag in sort_ordinals:
            # Going through each tag, first attempt to sort as integer.
            #  Then fallback to string sort.
            try:
                if key is None:
                    tmp_data = sorted(self.data,
                                      key=lambda _, pos=tag: float(_[pos]))
                else:
                    tmp_data = sorted(self.data, key=key)
            except ValueError:
                if key is None:
                    tmp_data = sorted(self.data,
                                      key=lambda _, pos=tag: _[pos])
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
            for row_num, row in enumerate(self.data):
                for pos, datum in enumerate(row):
                    line_no = str(row_num) + " tag " + str(pos) + " of loop"
                    if datum == "a":
                        pass
                    errors.extend(my_schema.val_type(self.category + "." +
                                                     self.tags[pos], datum,
                                                     category=category,
                                                     linenum=line_no))

        if validate_star:
            # Check for wrong data size
            num_cols = len(self.tags)
            for row_num, row in enumerate(self.data):
                # Make sure the width matches
                if len(row) != num_cols:
                    errors.append("Loop '%s' data width does not match it's "
                                  "tag width on row '%d'." %
                                  (self.category, row_num))

        return errors


def _called_directly():
    """ Figure out what to do if we were called on the command line
    rather than imported as a module."""

    # Specify some basic information about our command
    optparser = optparse.OptionParser(usage="usage: %prog",
                                      version=__version__,
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
                             "your script is separating tags by one tab and "
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
            # pylint: disable=relative-import,wrong-import-order
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
    _called_directly()
else:
    #############################################
    #          Module initializations           #
    #############################################

    # This makes sure that when decimals are printed a lower case "e" is used
    decimal.getcontext().capitals = 0

    # This loads the comments
    _load_comments()
