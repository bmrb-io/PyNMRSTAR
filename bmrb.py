#!/usr/bin/env python2

"""This module provides entry, saveframe, and loop objects. Use python's
built in help function for documentation.

There are seven module variables you can set to control our behavior.

*Setting bmrb.verbose to True will print some of what is going on to
the terminal.

*Setting bmrb.raise_parse_warnings to True will raise an exception if
the parser encounters something problematic. Normally warnings are
suppressed.

*Setting skip_empty_loops to True will suppress the printing of empty
loops when calling __str__ methods.

*Adding key->value pairs to str_conversion_dict will automatically
convert tags whose value matches "key" to the string "value" when
printing. This allows you to set the default conversion value for
Booleans or other objects.

*Setting bmrb.allow_v2_entries will allow parsing of NMR-STAR version
2.1 entries. Most other methods will not operate correctly on parsed
2.1 entries. This is only to allow you parse and access the data in
these entries - nothing else. Only set this if you have a really good
reason to. Attempting to print a 2.1 entry will 'work' but tags that
were after loops will be moved to before loops.

* Setting bmrb.dont_show_comments to True will supress the printing of
comments before saveframes.

* Setting bmrb.convert_datatypes to True will automatically convert
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

# Make sure print functions work in python2 and python3
from __future__ import print_function

__all__ = ['entry', 'saveframe', 'loop', 'schema', 'diff', 'validate', 'PY3']

#############################################
#                 Imports                   #
#############################################

# Standard library imports
import os
import sys
import decimal

from copy import deepcopy
from csv import reader as csv_reader, writer as csv_writer
from datetime import date
from gzip import GzipFile

# Determine if we are running in python3
PY3 = (sys.version_info[0] == 3)

# Python version dependent loads
if PY3:
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from io import StringIO, BytesIO
else:
    from urllib2 import urlopen, HTTPError
    from cStringIO import StringIO
    BytesIO = StringIO

#############################################
#            Global Variables               #
#############################################

# May be set by calling code
verbose = False

allow_v2_entries = False
raise_parse_warnings = False
skip_empty_loops = False
dont_show_comments = False
convert_datatypes = False

# WARNING: str_conversion_dict cannot contain both booleans and
# arithmetic types. Attempting to use both will cause an issue since
# boolean True == 1 in python and False == 0.
str_conversion_dict = {None:"."}

# Used internally
standard_schema = None
comment_dictionary = {}

# Get the svn revision number of this file
try:
    svn_revision = "$Revision: 185 $".split()[1]
# If they wget the file from the SVN or something
except IndexError:
    svn_revision = "UNKNOWN"

#############################################
#             Module methods                #
#############################################

# Public use methods
def enableNEFDefaults():
    """ Sets the module variables such that our behavior matches the NEF
    standard. Specifically, suppress printing empty loops by default and
    convert True -> "true" and False -> "false" when printing."""
    global str_conversion_dict, skip_empty_loops
    str_conversion_dict = {None:".", True:"true", False:"false"}
    skip_empty_loops = True

def enableBMRBDefaults():
    """ Sets the module variables such that our behavior matches the
    BMRB standard. This is the default behavior of this module. This
    method only exists to revert after calling enableNEFDefaults()."""
    global str_conversion_dict, skip_empty_loops
    str_conversion_dict = {None:"."}
    skip_empty_loops = False

def diff(entry1, entry2):
    """Prints the differences between two entries. Non-equal entries
    will always be detected, but specific differences detected depends
    on order of entries."""
    diffs = entry1.compare(entry2)
    if len(diffs) == 0:
        print("Identical entries.")
    for difference in diffs:
        print(difference)

def validate(entry_to_validate, validation_schema=None):
    """Prints a validation report of an entry."""
    validation = entry_to_validate.validate(validation_schema)
    if len(validation) == 0:
        print("No problems found during validation.")
    for err in validation:
        print(err)

def cleanValue(value):
    """Automatically quotes the value in the appropriate way. Don't
    quote values you send to this method or they will show up in
    another set of quotes as part of the actual data. E.g.:

    cleanValue('"e. coli"') returns '\'"e. coli"\''

    while

    cleanValue("e. coli") returns "'e. coli'"

    This will automatically be called on all values when you use a str()
    method (so don't call it before inserting values into tags or loops).

    Be mindful of the value of str_conversion_dict as it will effect the
    way the value is converted to a string.

    """

    # Allow manual specification of conversions for booleans, Nones, etc.
    if value in str_conversion_dict:
        if any(isinstance(value, type(x)) for x in str_conversion_dict):
        # The additional check prevents numerical types from being
        # interpreted as booleans. This is PROVIDED the dictionary
        # does not contain both numericals and booleans
            value = str_conversion_dict[value]

    # Convert non-string types to string
    if not isinstance(value, str):
        value = str(value)

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

            if next_char != "" and next_char in " \t\n\v":
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
            value = '"%s"' % value
        # Either there is a double quote or no quotes
        else:
            value = "'%s'" % value

    # It's good to go
    return value

# Internal use only methods

def _formatCategory(value):
    """Adds a '_' to the front of a tag (if not present) and strips out
    anything after a '.'"""
    if value:
        if not value.startswith("_"):
            value = "_" + value
        if "." in value:
            value = value[:value.index(".")]
    return value

def _formatTag(value):
    """Strips anything before the '.'"""
    if '.' in value:
        value = value[value.index('.')+1:]
    return value

def _fromIterable(iterables):
    """ A simple implementation of chain.from_iterable.
    As such: _fromIterable(['ABC', 'DEF']) --> A B C D E F """

    for item in iterables:
        for element in item:
            yield element

def _getSchema(passed_schema=None):
    """If passed a schema (not None) it returns it. If passed none,
    it checks if the default schema has been initialized. If not
    initialzed, it initializes it. Then it returns the default schema."""

    global standard_schema
    if passed_schema is None:
        passed_schema = standard_schema
    if passed_schema is None:
        # If we fail to get the schema don't do anything
        try:
            standard_schema = schema()
        except HTTPError:
            try:
                standard_schema = schema(schema_file="reference_files/schema")
            except:
                raise ValueError("Could not load a BMRB schema from the "
                                 "internet or from the local repository.")
        passed_schema = standard_schema

    return passed_schema

def _interpretFile(the_file):
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read') and hasattr(the_file, 'readline'):
        star_buffer = the_file
    elif isinstance(the_file, str):
        if (the_file.startswith("http://") or the_file.startswith("https://") or
                the_file.startswith("ftp://")):
            star_buffer = BytesIO(urlopen(the_file).read())
        else:
            with open(the_file, 'rb') as data_source:
                star_buffer = BytesIO(data_source.read())
    else:
        raise ValueError("Cannot figure out how to interpret the file "
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

def _loadComments(file_to_load=None):
    """ Loads the comments that should be placed in written files. """

    # Figure out where to load the file from
    if file_to_load is None:
        file_to_load = "reference_files/comments"

    try:
        comment_entry = entry.fromFile(file_to_load)
    except IOError:
        return

    # Load the comments
    categories = comment_entry.getTag("_comment.category")
    comments = comment_entry.getTag("_comment.comment")

    for pos, val in enumerate(categories):
        comment = comments[pos]
        if comment != ".":
            comment_dictionary[val] = comments[pos].rstrip() + "\n\n"

#############################################
#                Classes                    #
#############################################

# Internal use class
class _fastParser(object):
    """Parses an entry quickly. You should not ever use this class directly."""

    ent = None
    to_process = ""
    token = ""

    def __init__(self, entry_to_parse_into=None):
        if entry_to_parse_into is None:
            raise ValueError("You must provide an entry to parse into. Also, "
                             "why are you using this class?")
        self.ent = entry_to_parse_into
        self.full_data = ""
        self.index = 0
        self.token = ""
        self.source = "unknown"
        self.last_delineator = ""
        self.reserved = ["stop_", "loop_", "save_", "data_", "global_"]

    def getLineNumber(self):
        """ Returns the current line number that is in the process of
        being parsed."""
        return self.full_data[0:self.index].count("\n")+1

    def getToken(self):
        """ Returns the next token in the parsing process."""
        self.realgetToken()
        if verbose:
            if self.token:
                print("'" + self.token + "'")
            else:
                print("No more tokens.")
        return self.token

    @staticmethod
    def indexHandle(haystack, needle, startpos=None):
        """ Finds the index while catching ValueError and returning
        None instead."""
        try:
            pos = haystack.index(needle, startpos)
            return pos
        except ValueError:
            return None

    @staticmethod
    def nextWhitespace(data):
        """ Returns the position of the next whitespace character in the
        provided string. If no whitespace it returns the length of the
        string."""
        whitespace = " \t\n\v"
        for pos, char in enumerate(data):
            if char in whitespace:
                return pos
        return len(data)

    def parse(self, data, source="unknown"):
        """ Parses the string provided as data as an NMR-STAR entry
        and returns the parsed entry. Raises ValueError on exceptions."""

        # Fix DOS line endings
        self.full_data = data.replace("\r\n", "\n").replace("\r", "\n") + "\n"

        # Create the NMRSTAR object
        curframe = None
        curloop = None
        curtag = None
        curdata = []

        # Get the first token
        self.getToken()

        # Make sure this is actually a STAR file
        if not self.token.startswith("data_"):
            raise ValueError("Invalid file. NMR-STAR files must start with"
                             " 'data_'. Did you accidentally select the wrong"
                             " file?", self.getLineNumber())

        # Make sure there is a data name
        elif len(self.token) < 6:
            raise ValueError("'data_' must be followed by data name. Simply "
                             "'data_' is not allowed.", self.getLineNumber())

        if self.last_delineator != "":
            raise ValueError("The data_ keyword may not be quoted or "
                             "semicolon-delineated.")

        # Set the bmrb_id
        self.ent.bmrb_id = self.token[5:]
        self.source = source

        # We are expecting to get saveframes
        while self.getToken() != None:

            if not self.token.startswith("save_"):
                raise ValueError("Only 'save_NAME' is valid in the body of a "
                                 "NMR-STAR file. Found '" + self.token + "'.",
                                 self.getLineNumber())

            if len(self.token) < 6:
                raise ValueError("'save_' must be followed by saveframe name. "
                                 "You have a 'save_' tag which is illegal "
                                 "without a specified saveframe name.",
                                 self.getLineNumber())

            if self.last_delineator != "":
                raise ValueError("The save_ keyword may not be quoted or "
                                 "semicolon-delineated.", self.getLineNumber())

            # Add the saveframe
            curframe = saveframe.fromScratch(self.token[5:], source=source)
            self.ent.addSaveframe(curframe)

            # We are in a saveframe
            while self.getToken() != None:

                if self.token == "loop_":
                    if self.last_delineator != "":
                        raise ValueError("The loop_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.getLineNumber())

                    curloop = loop.fromScratch(source=source)
                    curframe.addLoop(curloop)

                    # We are in a loop
                    seen_data = False
                    in_loop = True
                    while in_loop and self.getToken() != None:

                        # Add a column
                        if self.token.startswith("_"):
                            if self.last_delineator != "":
                                raise ValueError("Loop tags may not be quoted "
                                                 "or semicolon-delineated.",
                                                 self.getLineNumber())
                            if seen_data == True:
                                raise ValueError("Cannot have more loop tags "
                                                 "after loop data.")
                            curloop.addColumn(self.token)

                        # On to data
                        else:

                            # We are in the data block of a loop
                            while self.token != None:
                                if self.token == "stop_":
                                    if self.last_delineator != "":
                                        raise ValueError("The stop_ keyword may"
                                                         " not be quoted or "
                                                         "semicolon-delineated."
                                                         , self.getLineNumber())
                                    if len(curloop.columns) == 0:
                                        if raise_parse_warnings:
                                            lineno = self.getLineNumber()
                                            raise ValueError("Loop with no ",
                                                             "tags.", lineno)
                                        curloop = None
                                    elif (len(curloop.data) == 0 and
                                          raise_parse_warnings):
                                        raise ValueError("Loop with no data.",
                                                         self.getLineNumber())
                                    else:
                                        curloop.addData(curdata, rearrange=True)
                                        curloop = None
                                        curdata = []

                                    curloop = None
                                    in_loop = False
                                    break
                                else:
                                    if len(curloop.columns) == 0:
                                        raise ValueError("Data found in loop "
                                                         "before loop tags.",
                                                         self.getLineNumber())

                                    if (self.token in self.reserved and
                                            self.last_delineator == ""):
                                        raise ValueError("Cannot use keywords "
                                                         "as data values unless"
                                                         " quoted or semi-colon"
                                                         " delineated. Perhaps "
                                                         "this is a loop that "
                                                         "wasn't properly "
                                                         "terminated? Illegal "
                                                         "value: " + self.token,
                                                         self.getLineNumber())
                                    curdata.append(self.token)
                                    seen_data = True

                                # Get the next token
                                self.getToken()

                    if self.token != "stop_":
                        raise ValueError("Loop improperly terminated at end of "
                                         "file.", self.getLineNumber())

                # Close saveframe
                elif self.token == "save_":
                    if self.last_delineator != "":
                        raise ValueError("The save_ keyword may not be quoted "
                                         "or semicolon-delineated.",
                                         self.getLineNumber())
                    if not allow_v2_entries:
                        if curframe.tag_prefix is None:
                            raise ValueError("The tag prefix was never set! "
                                             "Either the saveframe had no tags,"
                                             " you tried to read a version 2.1 "
                                             "file without setting "
                                             "allow_v2_entries to True, or "
                                             "there is something else wrong "
                                             "with your file. Saveframe error "
                                             "occured: '%s'" % curframe.name)
                    curframe = None
                    break

                # Invalid content in saveframe
                elif not self.token.startswith("_"):
                    raise ValueError("Invalid token found in saveframe '" +
                                     curframe.name +  "': '" + self.token +
                                     "'", self.getLineNumber())

                # Add a tag
                else:
                    if self.last_delineator != "":
                        raise ValueError("Saveframe tags may not be quoted or "
                                         "semicolon-delineated.",
                                         self.getLineNumber())
                    curtag = self.token

                    # We are in a saveframe and waiting for the saveframe tag
                    self.getToken()
                    if (self.token in self.reserved and
                            self.last_delineator == ""):
                        raise ValueError("Cannot use keywords as data values "
                                         "unless quoted or semi-colon "
                                         "delineated. Illegal value: " +
                                         self.token, self.getLineNumber())
                    curframe.addTag(curtag, self.token, self.getLineNumber())

            if self.token != "save_":
                raise ValueError("Saveframe improperly terminated at end of "
                                 "file.", self.getLineNumber())

        # Free the memory of the original copy of the data we parsed
        self.full_data = None

        return self.ent

    def realgetToken(self):
        """ Actually processes the input data to find a token. getToken
        is just a wrapper around this with some exception handling."""

        # Reset the delineator
        self.last_delineator = ""

        # Nothing left
        if self.token == None:
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
                self.token = self.full_data[self.index:].lstrip(" \t\n\v")
                if self.token == "":
                    self.token = None
                self.index = len(self.full_data)
                return

            newline_index = self.full_data.index("\n", self.index+1)
            raw_tmp = self.full_data[self.index:newline_index+1]
            tmp = raw_tmp.lstrip(" \t\n\v")

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
            return self.getToken()

        # Handle multi-line values
        if tmp.startswith(";\n"):
            tmp = tmp[2:]

            # Search for end of multi-line value
            if "\n;" in tmp:
                until = tmp.index("\n;")
                valid = self.indexHandle(tmp, "\n;\n")

                # The line is terminated properly
                if valid == until:
                    self.token = tmp[0:until+1]
                    self.index += until+4
                    self.last_delineator = ";"
                    return

                # The line was terminated improperly
                else:
                    if self.nextWhitespace(tmp[until+2:]) == 0:
                        if raise_parse_warnings:
                            raise ValueError("Warning: Technically invalid line"
                                             " found in file. Multiline values "
                                             "should terminate with \\n;\\n but"
                                             " in this file only \\n; with "
                                             "non-return whitespace following "
                                             "was found.",
                                             self.getLineNumber())
                        self.token = tmp[0:until+1]
                        self.index += until + 4
                        self.last_delineator = ";"
                        return
                    else:
                        raise ValueError('Invalid file. A multi-line value '
                                         'ended with a "\\n;" and then a '
                                         'non-whitespace value. Multi-line '
                                         'values should end with "\\n;\\n".',
                                         self.getLineNumber())
            else:
                raise ValueError("Invalid file. Multi-line comment never ends. "
                                 "Multi-line comments must terminate with a "
                                 "line that consists ONLY of a ';' without "
                                 "characters before or after. (Other than the "
                                 "newline.)", self.getLineNumber())

        # Handle values quoted with '
        if tmp.startswith("'"):
            until = self.indexHandle(tmp, "'", 1)

            if until is None:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.getLineNumber())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until+1:until+2] not in " \t\n":
                    until = self.indexHandle(tmp, "'", until+1)
            except TypeError:
                raise ValueError("Invalid file. Single quoted value was never "
                                 "terminated.", self.getLineNumber())

            self.token = tmp[1:until]
            self.index += until+1
            self.last_delineator = "'"
            return

        # Handle values quoted with "
        if tmp.startswith('"'):
            until = self.indexHandle(tmp, '"', 1)

            if until is None:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.getLineNumber())

            # Make sure we don't stop for quotes that are not followed
            #  by whitespace
            try:
                while tmp[until+1:until+2] not in " \t\n":
                    until = self.indexHandle(tmp, '"', until+1)
            except TypeError:
                raise ValueError("Invalid file. Double quoted value was never "
                                 "terminated.", self.getLineNumber())

            self.token = tmp[1:until]
            self.index += until+1
            self.last_delineator = '"'
            return

        # Figure out where this token ends
        white = self.nextWhitespace(tmp)
        if white == len(tmp):
            self.token = tmp
            self.index += len(self.token) + 1
            return

        # The token isn't anything special, just return it
        self.index += white
        self.token = tmp[0:white]
        return

class schema(object):
    """A BMRB schema. Used to validate STAR files."""

    headers = []

    schema_order = []
    schema = {}
    types = {}
    schema_file = None

    def __init__(self, schema_file=None):
        """Initialize a BMRB schema. With no arguments the most
        up-to-date schema will be fetched from the BMRB FTP site.
        Otherwise pass a URL or a file to load a schema from using the
        schema_url or schema_file optional arguments."""

        self.headers = []
        self.schema = {}
        self.types = {}

        if schema_file is None:
            schema_file = 'http://svn.bmrb.wisc.edu/svn/nmr-star-dictionary/bmrb_star_v3_files/adit_input/xlschem_ann.csv'
        self.schema_file = schema_file

        schem_stream = _interpretFile(schema_file)
        fix_newlines = StringIO('\n'.join(schem_stream.read().splitlines()))

        csv_reader_instance = csv_reader(fix_newlines)
        self.headers = next(csv_reader_instance)

        # Skip the header descriptions and header index values and anything
        #  else before the real data starts
        try:
            while next(csv_reader_instance)[0] != "TBL_BEGIN":
                pass
        except IndexError:
            raise ValueError("Could not parse a schema from the specified "
                             "URL: %s" % schema_file)

        for line in csv_reader_instance:

            # Stop at the end
            if line[0] == "TBL_END":
                break

            if line[8].count(".") == 1:
                null_allowed = False if line[28] == "NOT NULL" else True
                self.schema[line[8].lower()] = (line[27], null_allowed,
                                                line[1], line[8])
                self.types[line[8][:line[8].index(".")]] = (line[1], line[42])
                self.schema_order.append(line[8])
            else:
                if verbose:
                    print("Detected invalid tag in schema: %s" % line)

    def __repr__(self):
        """Return how we can be initialized."""
        return "bmrb.schema(schema_file='%s')" % self.schema_file

    def __str__(self):
        """Print the schema that we are adhering to."""
        return "BMRB schema loaded from: '%s'" % self.schema_file

    def convertTag(self, tag, value, linenum=None):
        """ Converts the provided tag from string to the appropriate
        type as specified in this schema."""

        # If we don't know what the tag is, just return it
        if not tag.lower() in self.schema:
            if raise_parse_warnings:
                raise ValueError("There is a tag in the file that isn't in the "
                                 "schema: '%s' on line '%s'" % (tag, linenum))
            else:
                if verbose:
                    print("Couldn't convert tag because it is not in the "
                          "dictionary: " + tag)
                return value

        # Get the type
        valtype, null_allowed = self.schema[tag.lower()][0:2]

        # Check for null
        if value == "." or value == "?":
            if not null_allowed and raise_parse_warnings:
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
                raise ValueError("Could not parse the file because a value that"
                                 " should be an INTEGER is not. Please turn off"
                                 " convert_datatypes or fix the file. Tag: '%s'"
                                 " on line '%s'" % (tag, linenum))

        # Convert floats
        if "FLOAT" in valtype:
            try:
                # If we used int() we would lose the precision
                return decimal.Decimal(value)
            except:
                raise ValueError("Could not parse the file because a value that"
                                 " should be a FLOAT is not. Please turn off "
                                 "convert_datatypes or fix the file. Tag: '%s' "
                                 "on line '%s'" % (tag, linenum))

        if "DATETIME year to day" in valtype:
            try:
                year, month, day = [int(x) for x in value.split("-")]
                return date(year, month, day)
            except:
                raise ValueError("Could not parse the file because a value that"
                                 " should be a DATETIME is not. Please turn off"
                                 " convert_datatypes or fix the file. Tag: '%s'"
                                 " on line '%s'" % (tag, linenum))

        # We don't know the data type, so just keep it a string
        return value

    def valType(self, tag, value, category=None, linenum=None):
        """ Validates that a tag matches the type it should have
        according to this schema."""

        if not tag.lower() in self.schema:
            return ["Tag '%s' not found in schema. Line '%s'." % (tag, linenum)]

        (valtype, null_allowed, allowed_category,
         capitalized_tag) = self.schema[tag.lower()]

        if category != None:
            if category != allowed_category:
                return ["The tag '%s' in category '%s' should be in category "
                        "'%s'." % (capitalized_tag, category, allowed_category)]

        if value == ".":
            if not null_allowed:
                return ["Value cannot be NULL but is: '%s':'%s' on line '%s'."
                        % (capitalized_tag, value, linenum)]
            return []

        if "VARCHAR" in valtype:
            length = int(valtype[valtype.index("(")+1:valtype.index(")")])
            if len(str(value)) > length:
                return ["Length of value '%d' is too long for VARCHAR(%d): "
                        "'%s':'%s' on line '%s'." %
                        (len(value), length, capitalized_tag, value, linenum)]
        elif "CHAR" in valtype:
            length = int(valtype[valtype.index("(")+1:valtype.index(")")])
            if len(str(value)) > length:
                return ["Length of value '%d' is too long for CHAR(%d): "
                        "'%s':'%s' on line '%s'." %
                        (len(value), length, capitalized_tag, value, linenum)]
        elif "FLOAT" in valtype:
            try:
                float(value)
            except ValueError:
                return ["Value is not of type FLOAT.:'%s':'%s' on line '%s'." %
                        (capitalized_tag, value, linenum)]
        elif "INTEGER" in valtype:
            try:
                int(value)
            except ValueError:
                return ["Value is not of type INTEGER.:'%s':'%s' on line '%s'."
                        % (capitalized_tag, value, linenum)]

        if tag != capitalized_tag:
            return ["The tag '%s' is improperly capitalized but otherwise valid"
                    ". Should be '%s'." % (tag, capitalized_tag)]
        return []

class entry(object):
    """An OO representation of a BMRB entry. You can initialize this
    object several ways; (e.g. from a file, from the official database,
    from scratch) see the classmethods."""

    # Put these here for reference
    bmrb_id = 0
    frame_list = []
    source = None

    def __delitem__(self, item):
        """Remove the indicated saveframe."""

        if isinstance(item, saveframe):
            del self.frame_list[self.frame_list.index(item)]
            return
        else:
            self.__delitem__(self.__getitem__(item))

    def __eq__(self, other):
        """Returns True if this entry is equal to another entry, false
        if it is not equal."""
        return len(self.compare(other)) == 0

    def __getitem__(self, item):
        """Get the indicated saveframe."""
        try:
            return self.frame_list[item]
        except TypeError:
            return self.getSaveframeByName(item)

    def __init__(self, **kargs):
        """Don't use this directly, use fromFile, fromScratch,
        fromString, or fromDatabase to construct."""

        # They initialized us wrong
        if len(kargs) == 0:
            raise ValueError("You must provide either a BMRB ID, a file name, "
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
            self.source = "fromString()"
        elif 'file_name' in kargs:
            star_buffer = _interpretFile(kargs['file_name'])
            self.source = "fromFile('%s')" % kargs['file_name']
        elif 'entry_num' in kargs:
            self.source = "fromDatabase(%s)" % kargs['entry_num']

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
        else:
            # Initialize a blank entry
            self.bmrb_id = kargs['bmrb_id']
            self.source = "fromScratch()"
            return

        # Load the BMRB entry from the file
        parser = _fastParser(entry_to_parse_into=self)
        parser.parse(star_buffer.read(), source=self.source)

    def __lt__(self, other):
        """Returns true if this entry is less than another entry."""
        return self.bmrb_id > other.bmrb_id

    def __repr__(self):
        """Returns a description of the entry."""
        return "<bmrb.entry '%s' %s>" % (self.bmrb_id, self.source)

    def __setitem__(self, key, item):
        """Set the indicated saveframe."""

        # It is a saveframe
        if isinstance(item, saveframe):
            # Add by ordinal
            try:
                self.frame_list[key] = item
            except TypeError:
                # Add by key
                if key in self.frameDict():
                    dict((frame.name, frame) for frame in self.frame_list)
                    for pos, frame in enumerate(self.frame_list):
                        if frame.name == key:
                            self.frame_list[pos] = item
                else:
                    raise KeyError("Saveframe with name '%s' does not exist and"
                                   " therefore cannot be written to. Use the "
                                   "addSaveframe method to add new saveframes."
                                   % key)
        else:
            raise ValueError("You can only assign an entry to a saveframe"
                             " splice.")

    def __str__(self):
        """Returns the entire entry in STAR format as a string."""
        ret_string = "data_%s\n\n" % self.bmrb_id
        for frame in self.frame_list:
            ret_string += str(frame) + "\n"
        return ret_string

    @classmethod
    def fromDatabase(cls, entry_num):
        """Create an entry corresponding to the most up to date entry on
        the public BMRB server. (Requires ability to initiate outbound
        HTTP connections.)"""
        return cls(entry_num=entry_num)

    @classmethod
    def fromFile(cls, the_file):
        """Create an entry by loading in a file. If the_file starts with
        http://, https://, or ftp:// then we will use those protocols to
        attempt to open the file."""
        return cls(file_name=the_file)

    @classmethod
    def fromJSON(cls, json_dict):
        """Create an entry from JSON (unserialized JSON - a python
        dictionary)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            raise ValueError("The JSON you provided was neither a Python "
                             "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ["bmrb_id", "saveframes"]:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a hash and must "
                                 "contain the key '%s' - even if the key points"
                                 " to None." % check)

        # Create an entry from scratch and populate it
        ret = entry.fromScratch(json_dict['bmrb_id'])
        ret.frame_list = [saveframe.fromJSON(x) for x in
                          json_dict['saveframes']]
        ret.source = "fromJSON()"

        # Return the new loop
        return ret

    @classmethod
    def fromString(cls, the_string):
        """Create an entry by parsing a string."""
        return cls(the_string=the_string)

    @classmethod
    def fromScratch(cls, bmrb_id):
        """Create an empty entry that you can programatically add to.
        You must pass a number corresponding to the BMRB ID. If this
        is not a "real" BMRB entry, use 0 as the BMRB ID."""
        return cls(bmrb_id=bmrb_id)

    def addSaveframe(self, frame):
        """Add a saveframe to the entry."""

        if not isinstance(frame, saveframe):
            raise ValueError("You can only add instances of saveframes "
                             "using this method.")

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
            if str(self.bmrb_id) != str(other.bmrb_id):
                diffs.append("BMRB ID does not match between entries: "
                             "'%s' vs '%s'." % (self.bmrb_id, other.bmrb_id))
            if len(self.frame_list) != len(other.frame_list):
                diffs.append("The number of saveframes in the entries are not"
                             " equal: '%d' vs '%d'." %
                             (len(self.frame_list), len(other.frame_list)))
            for frame in self.frameDict():
                if other.frameDict().get(frame, None) is None:
                    diffs.append("No saveframe with name '%s' in other entry." %
                                 self.frameDict()[frame].name)
                else:
                    comp = self.frameDict()[frame].compare(
                        other.frameDict()[frame])
                    if len(comp) > 0:
                        diffs.append("Saveframes do not match: '%s'." %
                                     self.frameDict()[frame].name)
                        diffs.extend(comp)

        # We could get many different (and unknown Exceptions), so catch
        #  generic Exception
        except Exception as e:
            diffs.append("An exception occured while comparing: '%s'." % e)

        return diffs

    def frameDict(self):
        """Returns a dictionary of saveframe name -> saveframe object"""
        return dict((frame.name, frame) for frame in self.frame_list)

    def getJSON(self):
        """ Returns this entry in a form that can be serialized. Note
        that you must still import json and call json.dumps() on the
        result to serialize the entry."""

        return {
            "bmrb_id": self.bmrb_id,
            "saveframes": [x.getJSON() for x in self.frame_list]
        }

    def getLoopsByCategory(self, value):
        """Allows fetching loops by category."""

        value = _formatCategory(value).lower()

        results = []
        for frame in self.frame_list:
            for one_loop in frame.loops:
                if one_loop.category.lower() == value:
                    results.append(one_loop)
        return results

    def getSaveframeByName(self, frame):
        """Allows fetching a saveframe by name."""
        frames = self.frameDict()
        if frame in frames:
            return frames[frame]
        else:
            raise KeyError("No saveframe with name '%s'" % frame)

    def getSaveframesByCategory(self, value):
        """Allows fetching saveframes by category."""
        return self.getSaveframesByTagAndValue("sf_category", value)

    def getSaveframesByTagAndValue(self, tag_name, value):
        """Allows fetching saveframe(s) by tag and tag value."""

        ret_frames = []

        for frame in self.frame_list:
            results = frame.getTag(tag_name)
            if results != [] and results[0] == value:
                ret_frames.append(frame)

        return ret_frames

    def getTag(self, tag, whole_tag=False):
        """ Given a tag (E.g. _Assigned_chem_shift_list.Data_file_name)
        return a list of all values for that tag. Specify whole_tag=True
        and the [tag_name, tag_value (,tag_linenumber)] pair will be
        returned."""

        if not "." in str(tag) and not allow_v2_entries:
            raise ValueError("You must provide the tag category to call this"
                             " method at the entry level.")

        results = []
        for frame in self.frame_list:
            results.extend(frame.getTag(tag, whole_tag=whole_tag))

        return results

    def getTags(self, tags):
        """ Given a list of tags, get all of the tags and return the
        results in a dictionary."""

        # All tags
        if tags is None or not isinstance(tags, list):
            raise ValueError("Please provide a list of tags.")

        results = {}
        for tag in tags:
            results[tag] = self.getTag(tag)

        return results

    def nefString(self):
        """ Returns a string representation of the entry in NEF. """

        # Store the current values of these module variables
        global str_conversion_dict, skip_empty_loops
        tmp_dict, tmp_loops_state = str_conversion_dict, skip_empty_loops

        # Change to NEF defaults and get the string representation
        enableNEFDefaults()
        result = str(self)

        # Revert module variables
        str_conversion_dict, skip_empty_loops = tmp_dict, tmp_loops_state
        return result

    def printTree(self):
        """Prints a summary, tree style, of the frames and loops in
        the entry."""
        print(repr(self))
        for pos, frame in enumerate(self):
            print("\t[%d] %s" % (pos, repr(frame)))
            for pos2, one_loop in enumerate(frame):
                print("\t\t[%d] %s" % (pos2, repr(one_loop)))

    def validate(self, validation_schema=None):
        """Validate an entry against a STAR schema. You can pass your
        own custom schema if desired, otherwise the schema will be
        fetched from the BMRB servers. Returns a list of errors found.
        0-length list indicates no errors found."""

        errors = []

        # Ask the saveframes to check themselves for errors
        for frame in self:
            errors.extend(frame.validate(validation_schema=validation_schema))

        # Check for saveframes with same name
        saveframe_names = sorted(x.name for x in self)
        for x in range(0, len(saveframe_names)-2):
            if saveframe_names[x] == saveframe_names[x+1]:
                errors.append("Multiple saveframes with same name: " +
                              saveframe_names[x])

        return errors

class saveframe(object):
    """A saveframe. Use the classmethod fromScratch to create one."""

    tags = []
    loops = []
    name = ""
    tag_prefix = None
    source = "unknown"

    def __delitem__(self, item):
        """Remove the indicated tag or loop."""

        # If they specify the specific loop to delete, go ahead and delete it
        if isinstance(item, loop):
            del self.loops[self.loops.index(item)]
            return

        # See if the result of get(item) is a loop. If so, delete it
        # (calls this method recursively)
        to_delete = self.__getitem__(item)
        if isinstance(to_delete, loop):
            self.__delitem__(to_delete)
            return

        # It must be a tag. Try to delete the tag
        else:
            self.deleteTag(item)

    def __eq__(self, other):
        """Returns True if this saveframe is equal to another saveframe,
        False if it is equal."""
        return len(self.compare(other)) == 0

    def __getitem__(self, item):
        """Get the indicated loop or tag."""
        try:
            return self.loops[item]
        except TypeError:
            results = self.getTag(item)
            if results != []:
                return results
            else:
                try:
                    return self.loopDict()[item.lower()]
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
        self.source = "unknown"

        # Update our source if it provided
        if 'source' in kargs:
            self.source = kargs['source']

        if 'the_string' in kargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kargs['the_string'])
            self.source = "fromString()"
        elif 'file_name' in kargs:
            star_buffer = _interpretFile(kargs['file_name'])
            self.source = "fromFile('%s')" % kargs['file_name']
        elif 'saveframe_name' in kargs:
            # If they are creating from scratch, just get the saveframe name
            self.name = kargs['saveframe_name']
            if 'tag_prefix' in kargs:
                self.tag_prefix = _formatCategory(kargs['tag_prefix'])
            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kargs and kargs['csv']:
            csvreader = csv_reader(star_buffer)
            tags = next(csvreader)
            values = next(csvreader)
            if len(tags) != len(values):
                raise ValueError("Your CSV data is invalid. The header length"
                                 " does not match the data length.")
            for x in range(0, len(tags)):
                self.addTag(tags[x], values[x])
            return


        tmp_entry = entry.fromScratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_1 " + star_buffer.read())
        parser = _fastParser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source)

        # Copy the first parsed saveframe into ourself
        self.tags = tmp_entry[0].tags
        self.loops = tmp_entry[0].loops
        self.name = tmp_entry[0].name
        self.tag_prefix = tmp_entry[0].tag_prefix

    @classmethod
    def fromScratch(cls, sf_name, tag_prefix=None, source="fromScratch()"):
        """Create an empty saveframe that you can programatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""
        return cls(saveframe_name=sf_name, tag_prefix=tag_prefix, source=source)

    @classmethod
    def fromFile(cls, the_file, csv=False):
        """Create a saveframe by loading in a file. Specify csv=True is
        the file is a CSV file. If the_file starts with http://,
        https://, or ftp:// then we will use those protocols to attempt
        to open the file."""
        return cls(file_name=the_file, csv=csv)

    @classmethod
    def fromJSON(cls, json_dict):
        """Create a saveframe from JSON (unserialized JSON - a python
        dictionary)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            raise ValueError("The JSON you provided was neither a Python "
                             "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ["name", "tag_prefix", "tags", "loops"]:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a hash and must "
                                 "contain the key '%s' - even if the key points"
                                 " to None." % check)

        # Create a saveframe from scratch and populate it
        ret = saveframe.fromScratch(json_dict['name'])
        ret.tag_prefix = json_dict['tag_prefix']
        ret.tags = json_dict['tags']
        ret.loops = [loop.fromJSON(x) for x in json_dict['loops']]
        ret.source = "fromJSON()"

        # Return the new loop
        return ret

    @classmethod
    def fromString(cls, the_string, csv=False):
        """Create a saveframe by parsing a string. Specify csv=True is
        the string is in CSV format and not NMR-STAR format."""
        return cls(the_string=the_string, csv=csv)

    def __repr__(self):
        """Returns a description of the saveframe."""
        return "<bmrb.saveframe '%s'>" % self.name

    def __setitem__(self, key, item):
        """Set the indicated loop or tag."""

        # It's a loop
        if isinstance(item, loop):
            try:
                integer = int(str(key))
                self.loops[integer] = item
            except ValueError:
                if key.lower() in self.loopDict():
                    for pos, tmp_loop in enumerate(self.loops):
                        if tmp_loop.category.lower() == key.lower():
                            self.loops[pos] = item
                else:
                    raise KeyError("Loop with category '%s' does not exist and "
                                   "therefore cannot be written to. Use addLoop"
                                   " instead." % key)
        else:
            # If the tag already exists, set its value
            self.addTag(key, item, update=True)

    def __str__(self):
        """Returns the saveframe in STAR format as a string."""

        if allow_v2_entries:
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
        if not dont_show_comments:
            # Figure out what the entry category is
            try:
                our_category = self.getTag("Sf_category")[0]
            except IndexError:
                try:
                    our_category = self.getTag("_Saveframe_category")[0]
                except IndexError:
                    our_category = None

            if our_category in comment_dictionary:
                ret_string = comment_dictionary[our_category]

        # Print the saveframe
        ret_string += "save_%s\n" % self.name
        pstring = "   %%-%ds  %%s\n" % width
        mstring = "   %%-%ds\n;\n%%s;\n" % width

        # Print the tags
        for each_tag in self.tags:
            cleanTag = cleanValue(each_tag[1])

            if allow_v2_entries and self.tag_prefix is None:
                if "\n" in cleanTag:
                    ret_string += mstring % (each_tag[0], cleanTag)
                else:
                    ret_string += pstring % (each_tag[0], cleanTag)
            else:
                formatted_tag = self.tag_prefix+"."+each_tag[0]
                if "\n" in cleanTag:
                    ret_string += mstring % (formatted_tag, cleanTag)
                else:
                    ret_string += pstring % (formatted_tag, cleanTag)

        # Print any loops
        for each_loop in self.loops:
            ret_string += str(each_loop)

        # Close the saveframe
        ret_string += "save_\n"
        return ret_string

    def addLoop(self, loop_to_add):
        """Add a loop to the saveframe loops."""

        if (loop_to_add.category in self.loopDict() or
                str(loop_to_add.category).lower() in self.loopDict()):
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

    def addTag(self, name, value, linenum=None, update=False):
        """Add a tag to the tag list. Does a bit of validation and
        parsing. Set update to true to update a tag if it exists rather
        than raise an exception."""

        if "." in name:
            if name[0] != ".":
                prefix = _formatCategory(name)
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
        if self.getTag(name) != []:
            if not update:
                raise ValueError("There is already a tag with the name '%s'." %
                                 name)
            else:
                self.getTag(name, whole_tag=True)[0][1] = value
                return

        if "." in name:
            raise ValueError("There cannot be more than one '.' in a tag name.")
        if " " in name:
            raise ValueError("Tag names can not contain spaces.")

        # See if we need to convert the datatype
        if convert_datatypes:
            new_tag = [name, _getSchema().convertTag(
                self.tag_prefix + "." + name, value, linenum=linenum)]
        else:
            new_tag = [name, value]

        if linenum:
            new_tag.append(linenum)

        if verbose:
            print("Adding tag: '%s' with value '%s'" % (name, value))

        self.tags.append(new_tag)

    def addTags(self, tag_list, update=False):
        """Adds multiple tags to the list. Input should be a list of
        tuples that are either [key, value] or [key]. In the latter case
        the value will be set to ".".  Set update to true to update a
        tag if it exists rather than raise an exception."""
        for tag_pair in tag_list:
            if len(tag_pair) == 2:
                self.addTag(tag_pair[0], tag_pair[1], update=update)
            elif len(tag_pair) == 1:
                self.addTag(tag_pair[0], ".", update=update)
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
                other_tag = other.getTag(tag[0])

                if other_tag == []:
                    diffs.append("\tNo tag with name '%s.%s' in compared "
                                 "entry." % (self.tag_prefix, tag[0]))
                    continue

                if tag[1] != other_tag[0]:
                    diffs.append("\tMismatched tag values for tag '%s.%s':"
                                 " '%s' vs '%s'." %
                                 (self.tag_prefix, tag[0],
                                  str(tag[1]).replace("\n", "\\n"),
                                  str(other_tag[0]).replace("\n", "\\n")))

            if len(self.loops) != len(other.loops):
                diffs.append("\tNumber of children loops does not match: "
                             "'%d' vs '%d'." %
                             (len(self.loops), len(other.loops)))

            compare_loop_dict = other.loopDict()
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

        except Exception as e:
            diffs.append("\tAn exception occured while comparing: '%s'." % e)

        return diffs

    def deleteTag(self, tag):
        """Deletes a tag from the saveframe based on tag name."""
        tag = _formatTag(tag).lower()

        for position, each_tag in enumerate(self.tags):
            # If the tag is a match, remove it
            if each_tag[0].lower() == tag:
                return self.tags.pop(position)

        raise KeyError("There is no tag with name '%s' to remove." % tag)

    def getDataAsCSV(self, header=True, show_category=True):
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

    def getJSON(self):
        """ Returns this saveframe in a form that can be serialized.
        Note that you must still import json and call json.dumps() on
        the result to serialize the entry."""

        return {
            "name": self.name,
            "tag_prefix": self.tag_prefix,
            "tags": [[x[0], x[1]] for x in self.tags],
            "loops": [x.getJSON() for x in self.loops]
        }

    def getLoopByCategory(self, name):
        """Return a loop based on the loop name (category)."""
        name = _formatCategory(name).lower()
        for each_loop in self.loops:
            if str(each_loop.category).lower() == name:
                return each_loop
        raise KeyError("No loop with category '%s'." % name)

    def getTag(self, query, whole_tag=False):
        """Allows fetching the value of a tag by tag name. Specify
        whole_tag=True and the [tag_name, tag_value] pair will be
        returned."""

        results = []

        # Make sure this is the correct saveframe if they specify a tag prefix
        if "." in query:
            tag_prefix = _formatCategory(query)
        else:
            tag_prefix = self.tag_prefix

        # Check the loops
        for each_loop in self.loops:
            if ((each_loop.category is not None and tag_prefix is not None and
                    each_loop.category.lower() == tag_prefix.lower()) or
                        allow_v2_entries):
                results.extend(each_loop.getTag(query, whole_tag=whole_tag))

        # Check our tags
        query = _formatTag(query).lower()
        if (allow_v2_entries or
                (tag_prefix is not None and
                 tag_prefix.lower() == self.tag_prefix.lower())):
            for tag in self.tags:
                if query == tag[0].lower():
                    if whole_tag:
                        results.append(tag)
                    else:
                        results.append(tag[1])

        return results

    def loopDict(self):
        """Returns a hash of loop category -> loop."""
        res = {}
        for each_loop in self.loops:
            if each_loop.category is not None:
                res[each_loop.category.lower()] = each_loop
        return res

    def loopIterator(self):
        """Returns an iterator for saveframe loops."""
        return iter(self.loops)

    def setTagPrefix(self, tag_prefix):
        """Set the tag prefix for this saveframe."""
        self.tag_prefix = _formatCategory(tag_prefix)

    def sortTags(self, validation_schema=None):
        """ Sort the tags so they are in the same order as a BMRB
        schema. Will automatically use the standard schema if none
        is provided."""

        new_tag_list = []

        for check in _getSchema(validation_schema).schema_order:
            # Only proceed if it has the same category as us
            if _formatCategory(check).lower() == self.tag_prefix.lower():
                tag_name = _formatTag(check)
                # If we currently have the tag, add it to the new tag list
                existing = self.getTag(tag_name, whole_tag=True)
                if existing != []:
                    new_tag_list.extend(existing)

        if len(self.tags) != len(new_tag_list):
            raise ValueError("Refusing to sort. There are tags in the saveframe"
                             " that do not exist in the schema.")

        self.tags = new_tag_list

    def tagIterator(self):
        """Returns an iterator for saveframe tags."""
        return iter(self.tags)

    def printTree(self):
        """Prints a summary, tree style, of the loops in the saveframe."""
        print(repr(self))
        for pos, each_loop in enumerate(self):
            print("\t[%d] %s" % (pos, repr(each_loop)))

    def validate(self, validation_schema=None):
        """Validate a saveframe against a STAR schema. You can pass your
        own custom schema if desired, otherwise the schema will be
        fetched from the BMRB servers. Returns a list of errors found.
        0-length list indicates no errors found."""

        # Get the default schema if we are not passed a schema
        my_schema = _getSchema(validation_schema)

        errors = []

        try:
            my_category = self.getTag("Sf_category")[0]
        except IndexError:
            errors.append("Cannot properly validate saveframe: '" + self.name +
                          "'. No saveframe category defined.")
            my_category = None

        for tag in self.tags:
            lineno = str(tag[2]) + " of original file" if len(tag) > 2 else None
            formatted_tag = self.tag_prefix + "." + tag[0]
            cur_errors = my_schema.valType(formatted_tag, tag[1],
                                           category=my_category, linenum=lineno)
            errors.extend(cur_errors)

        for each_loop in self.loops:
            errors.extend(
                each_loop.validate(
                    validation_schema=validation_schema, category=my_category))

        return errors

class loop(object):
    """A BMRB loop object."""

    category = None
    columns = []
    data = []
    source = "unknown"

    def __eq__(self, other):
        """Returns True if this loop is equal to another loop, False if
        it is different."""
        return len(self.compare(other)) == 0

    def __getitem__(self, item):
        """Get the indicated row from the data array."""
        try:
            return self.data[item]
        except TypeError:
            if isinstance(item, tuple):
                item = list(item)
            return self.getTag(tags=item)

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
            self.category = _formatCategory(kargs['category'])
            return

        # They initialized us wrong
        if len(kargs) == 0:
            raise ValueError("Use the class methods to initialize.")

        if 'the_string' in kargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kargs['the_string'])
            self.source = "fromString()"
        elif 'file_name' in kargs:
            star_buffer = _interpretFile(kargs['file_name'])
            self.source = "fromFile('%s')" % kargs['file_name']
        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kargs and kargs['csv']:
            csvreader = csv_reader(star_buffer)
            self.addColumn(next(csvreader))
            for row in csvreader:
                self.addData(row)
            self.source = "fromCSV('%s')" % kargs['csv']
            return

        tmp_entry = entry.fromScratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_0 save_internaluseyoushouldntseethis_frame"
                               " _internal.use internal " + star_buffer.read() +
                               " save_")
        parser = _fastParser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source)

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
        if allow_v2_entries and self.category is None:
            common = os.path.commonprefix(self.columns)
            if common.endswith("_"):
                common = common[:-1]
            if common == "":
                common = "Unknown"
            return "<bmrb.loop '%s'>" % common
        else:
            return "<bmrb.loop '%s'>" % self.category

    def __str__(self):
        """Returns the loop in STAR format as a string."""

        # Check if there is any data in this loop
        if len(self.data) == 0:
            # They do not want us to print empty loops
            if skip_empty_loops:
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
        if self.category is None and not allow_v2_entries:
            raise ValueError("The category was never set for this loop. Either "
                             "add a column with the category intact, specify it"
                             " when generating the loop, or set it using "
                             "setCategory.")

        # Print the categories
        if self.category is None:
            for column in self.columns:
                ret_string += pstring % (column)
        else:
            for column in self.columns:
                ret_string += pstring % (self.category + "." + column)

        ret_string += "\n"

        if len(self.data) != 0:

            # Make a copy of the data
            working_data = []
            # Put quotes as needed on the data
            for datum in self.data:
                working_data.append([cleanValue(x) for x in datum])

            # The nightmare below creates a list of the maximum length of
            #  elements in each column in the self.data matrix. Don't try to
            #   understand it. It's an incomprehensible list comprehension.
            title_widths = [max([len(str(x))+3 for x in col]) for
                            col in [[row[x] for row in working_data] for
                                    x in range(0, len(working_data[0]))]]
            # Generate the format string
            pstring = "     " + "%-*s"*len(self.columns) + " \n"

            # Print the data, with the columns sized appropriately
            for datum in working_data:
                for pos, item in enumerate(datum):
                    if "\n" in item:
                        datum[pos] = "\n;\n%s;\n" % item

                # Print the data (combine the columns widths with their data)
                column_width_list = [d for d in zip(title_widths, datum)]
                ret_string += pstring % tuple(_fromIterable(column_width_list))

        # Close the loop
        ret_string += "   stop_\n"
        return ret_string

    @classmethod
    def fromFile(cls, the_file, csv=False):
        """Create a saveframe by loading in a file. Specify csv=True if
        the file is a CSV file. If the_file starts with http://,
        https://, or ftp:// then we will use those protocols to attempt
        to open the file."""
        return cls(file_name=the_file, csv=csv)

    @classmethod
    def fromJSON(cls, json_dict):
        """Create a loop from JSON (unserialized JSON - a python
        dictionary)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            raise ValueError("The JSON you provided was neither a Python "
                             "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ['tags', 'category', 'data']:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a hash and must "
                                 "contain the key '%s' - even if the key points"
                                 " to None." % check)

        # Create a loop from scratch and populate it
        ret = loop.fromScratch()
        ret.columns = json_dict['tags']
        ret.category = json_dict['category']
        ret.data = json_dict['data']
        ret.source = "fromJSON()"

        # Return the new loop
        return ret

    @classmethod
    def fromScratch(cls, category=None, source="fromScratch()"):
        """Create an empty saveframe that you can programatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""
        return cls(category=category, source=source)

    @classmethod
    def fromString(cls, the_string, csv=False):
        """Create a saveframe by parsing a string. Specify csv=True is
        the string is in CSV format and not NMR-STAR format."""
        return cls(the_string=the_string, csv=csv)

    def addColumn(self, name, ignore_duplicates=False):
        """Add a column to the column list. Does a bit of validation
        and parsing. Set ignore_duplicates to true to ignore attempts
        to add the same tag more than once rather than raise an
        exception.

        You can also pass a list of column names to add more than one
        column at a time."""

        # If they have passed multiple columns to add, call ourself
        #  on each of them in succession
        if isinstance(name, (list, tuple)):
            for x in name:
                self.addColumn(x, ignore_duplicates=ignore_duplicates)
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
        if name.lower() in [x.lower() for x in self.columns]:
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

    def addData(self, the_list, rearrange=False):
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
        if convert_datatypes:
            for row in processed_data:
                for column, datum in enumerate(row):
                    row[column] = _getSchema().convertTag(self.category + "." +
                                                          self.columns[column],
                                                          datum,
                                                          linenum="Loop %s" %
                                                          self.category)

        self.data = processed_data

    def addDataByColumn(self, column_id, value):
        """Add data to the loop one element at a time, based on column.
        Useful when adding data from SANS parsers."""

        # Make sure the category matches - if provided
        if "." in column_id:
            supplied_category = _formatCategory(str(column_id))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your column '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        column_id = _formatTag(column_id).lower()
        if not column_id in [x.lower() for x in self.columns]:
            raise ValueError("The column tag '%s' to which you are attempting "
                             "to add data does not yet exist. Create the "
                             "columns before adding data." % column_id)
        pos = [x.lower() for x in self.columns].index(column_id)
        if len(self.data) == 0:
            self.data.append([])
        if len(self.data[-1]) == len(self.columns):
            self.data.append([])
        if len(self.data[-1]) != pos:
            raise ValueError("You cannot add data out of column order.")
        self.data[-1].append(value)

    def clearData(self):
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
            # Check data of loops
            if self.data != other.data:
                diffs.append("\t\tLoop data does not match for loop with "
                             "category '%s'." % self.category)
            # Check columns of loops
            if ([x.lower() for x in self.columns] !=
                    [x.lower() for x in other.columns]):
                diffs.append("\t\tLoop columns do not match for loop with "
                             "category '%s'." % self.category)

        except Exception as e:
            diffs.append("\t\tAn exception occured while comparing: '%s'." % e)

        return diffs

    def deleteDataByTagValue(self, tag, value, index_tag=None):
        """Deletes all rows which contain the provided value in the
        provided column. If index_tag is provided, that column is
        renumbered starting with 1. Returns the deleted rows."""

        # Make sure the category matches - if provided
        if "." in tag:
            supplied_category = _formatCategory(str(tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your column '%s' does "
                                 "not match this loop's category '%s'." %
                                 (supplied_category, self.category))

        cleaned_tag = _formatTag(str(tag)).lower()
        columns_lower = [x.lower() for x in self.columns]

        try:
            search_column = columns_lower.index(cleaned_tag)
        except ValueError:
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
            self.renumberRows(index_tag)

        return deleted

    def getColumns(self):
        """ Return the columns for this entry with the category
        included. Throws ValueError if the category was never set."""
        if not self.category:
            raise ValueError("You never set the category of this loop.")

        return [self.category + "." + x for x in self.columns]

    def getDataAsCSV(self, header=True, show_category=True):
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

    def getDataByTag(self, tags=None):
        """ Identical to getTag but wraps the results in a list even if
        only fetching one tag. Primarily exists for legacy code."""

        results = self.getTag(tags=tags)

        if isinstance(tags, list):
            if len(tags) == 1:
                results = [results]
        elif isinstance(tags, str):
            results = [results]

        return results

    def getJSON(self):
        """ Returns this loop in a form that can be serialized. Note that
        you must still import json and call json.dumps() on the result to
        serialize the entry."""
        return {
            "category": self.category,
            "tags": self.columns,
            "data": self.data
        }

    def getTag(self, tags=None, whole_tag=False):
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
                    _formatCategory(item).lower() != self.category.lower()):
                raise ValueError("Cannot fetch data with column '%s' because "
                                 "the category does not match the category of "
                                 "this loop '%s'." % (item, self.category))
            lower_tags[pos] = _formatTag(item).lower()

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
                if allow_v2_entries:
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

    def printTree(self):
        """Prints a summary, tree style, of the loop."""
        print(repr(self))

    def renumberRows(self, index_tag, start_value=1, maintain_ordering=False):
        """Renumber a given column incrementally. Set start_value to
        initial value if 1 is not acceptable. Set maintain_ordering to
        preserve sequence with offset.

        E.g. 2,3,3,5 would become 1,2,2,4."""

        # Make sure the category matches
        if "." in str(index_tag):
            supplied_category = _formatCategory(str(index_tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError("Category provided in your tag '%s' does not "
                                 "match this loop's category '%s'." %
                                 (supplied_category, self.category))

        cleaned_tag = _formatTag(str(index_tag))
        columns_lower = [x.lower() for x in self.columns]

        # The column to replace in is the column they specify
        try:
            renum_col = columns_lower.index(cleaned_tag.lower())
        except ValueError:
            # Or, perhaps they specified an integer to represent the column?
            try:
                renum_col = int(index_tag)
            except ValueError:
                raise ValueError("The renumbering column you provided '%s' "
                                 "isn't in this loop!" % cleaned_tag)

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

            for x in range(0, len(self.data)):
                try:
                    if x == 0:
                        offset = start_value - int(self.data[0][renum_col])
                    self.data[x][renum_col] = int(self.data[x][renum_col]) +\
                                                  offset
                except ValueError:
                    self.data = data_copy
                    raise ValueError("You can't renumber a row containing "
                                     "anything that can't be coerced into an "
                                     "integer using maintain_ordering. I.e. "
                                     "what am I suppose to renumber '%s' to?" %
                                     self.data[x][renum_col])

        # Simple renumbering algorithm if we don't need to maintain the ordering
        else:
            for x in range(0, len(self.data)):
                self.data[x][renum_col] = x + start_value

    def setCategory(self, category):
        """ Set the category of the loop. Usefull if you didn't know the
        category at loop creation time."""
        self.category = _formatCategory(category)

    def sortRows(self, tags, key=None):
        """ Sort the data in the rows by their values for a given column
        or columns. Specify the columns using their names or ordinals.
        Accepts a list or an int/float. By default we will sort
        numerically. If that fails we do a string sort. Supply a
        function as key_func and we will order the elements based on the
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

        # Get a lower case list of columns
        columns_lower = [x.lower() for x in self.columns]

        # Process their input to determine which columns to operate on
        for cur_tag in [str(x) for x in processing_list]:

            # Make sure the category matches
            if "." in cur_tag:
                supplied_category = _formatCategory(cur_tag)
                if supplied_category.lower() != self.category.lower():
                    raise ValueError("Category provided in your tag '%s' does "
                                     "not match this loop's category '%s'." %
                                     (supplied_category, self.category))

            # Get a lower case version of the tag
            cleaned_tag = _formatTag(cur_tag)

            # The column to replace in is the column they specify
            try:
                renumber_column = columns_lower.index(cleaned_tag.lower())
            except ValueError:
                # Or, perhaps they specified an integer to represent the column?
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
                    tmp_data = sorted(self.data, key=lambda x: float(x[column]))
                else:
                    tmp_data = sorted(self.data, key=key)
            except ValueError:
                if key is None:
                    tmp_data = sorted(self.data, key=lambda x: x[column])
                else:
                    tmp_data = sorted(self.data, key=key)
            self.data = tmp_data

    def validate(self, validation_schema=None, category=None):
        """Validate a loop against a STAR schema. You can pass your own
        custom schema if desired, otherwise the schema will be fetched
        from the BMRB servers. Returns a list of errors found. 0-length
        list indicates no errors found."""

        # Get the default schema if we are not passed a schema
        my_schema = _getSchema(validation_schema)

        errors = []

        # Check the data
        for rownum, row in enumerate(self.data):
            # Make sure the width matches
            if len(row) != len(self.columns):
                errors.append("Loop '%s' data width does not match it's column "
                              "tag width on row '%d'." %
                              (self.category, rownum))
            for pos, datum in enumerate(row):
                lineno = str(rownum) + " column " + str(pos) + " of loop"
                errors.extend(my_schema.valType(self.category + "." +
                                                self.columns[pos], datum,
                                                category=category,
                                                linenum=lineno))

        return errors

# Allow using diff or validate if ran directly
if __name__ == '__main__':

    import optparse
    # Specify some basic information about our command
    optparser = optparse.OptionParser(usage="usage: %prog",
                                      version="SVN_%s" % svn_revision,
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
    # Options, parse 'em
    (options, cmd_input) = optparser.parse_args()

    if options.validate is None and options.diff is None:
        print("Running unit tests...")
        from unit_tests import bmrb_test
        bmrb_test.start_tests()
    elif options.validate is not None and options.diff is not None:
        print("You cannot validate and diff at the same time.")
        sys.exit(1)
    elif options.validate is not None:
        validate(entry.fromFile(options.validate))
    elif options.diff is not None:
        diff(entry.fromFile(options.diff[0]), entry.fromFile(options.diff[1]))
    sys.exit(0)
else:
    #############################################
    #          Module initializations           #
    #############################################

    # This makes sure that when decimals are printed a lower case "e" is used
    decimal.getcontext().capitals = 0

    # This loads the comments
    _loadComments()
