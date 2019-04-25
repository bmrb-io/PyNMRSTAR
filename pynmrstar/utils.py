#!/usr/bin/env python3

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

import os
import sys
import json
import decimal
import optparse
from datetime import date
from gzip import GzipFile
from io import StringIO, BytesIO
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from typing import Union, Optional, Dict, Iterable, Any
from typing import IO

from . import definitions
from . import entry as entry_mod
from . import schema as schema_mod


# This is an odd place for this, but it can't really be avoided if
#  we want to keep the import at the top.
def _build_extension() -> bool:
    """ Try to compile the c extension. """
    import subprocess

    cur_dir = os.getcwd()
    try:
        src_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        os.chdir(os.path.join(src_dir, "c"))

        # Use the appropriate build command
        process = subprocess.Popen(['make', 'python3'], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
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
    if not os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".nocompile")):

        if _build_extension():
            try:
                import cnmrstar
            except ImportError:
                cnmrstar = None

#############################################
#            Global Variables               #
#############################################

# Set this to allow import * from pynmrstar to work sensibly
__all__ = ['diff', 'validate', 'interpret_file', 'get_schema', 'format_category', 'format_tag']

# May be set by calling code
VERBOSE = False

ALLOW_V2_ENTRIES: bool = False
RAISE_PARSE_WARNINGS: bool = False
WARNINGS_TO_IGNORE = []
SKIP_EMPTY_LOOPS: bool = False
DONT_SHOW_COMMENTS: bool = False
CONVERT_DATATYPES: bool = False

# WARNING: STR_CONVERSION_DICT cannot contain both booleans and
# arithmetic types. Attempting to use both will cause an issue since
# boolean True == 1 in python and False == 0.

_STANDARD_SCHEMA: Optional['schema_mod.Schema'] = None
_COMMENT_RECORDS: Dict[str, Dict[str, str]] = {}


#############################################
#             Module methods                #
#############################################

def diff(entry1: 'entry_mod.Entry', entry2: 'entry_mod.Entry') -> None:
    """Prints the differences between two entries. Non-equal entries
    will always be detected, but specific differences detected depends
    on order of entries."""

    diffs = entry1.compare(entry2)
    if len(diffs) == 0:
        print("Identical entries.")
    for difference in diffs:
        print(difference)


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


# Internal use only methods
def _json_serialize(obj: object) -> str:
    """JSON serializer for objects not serializable by default json code"""

    # Serialize datetime.date objects by calling str() on them
    if isinstance(obj, (date, decimal.Decimal)):
        return str(obj)
    raise TypeError("Type not serializable: %s" % type(obj))


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

    buffer: BytesIO

    if isinstance(the_file, StringIO):
        buffer = BytesIO(the_file.read().encode())
    elif isinstance(the_file, BytesIO):
        buffer = BytesIO(the_file.read())
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


def _get_comments() -> Dict[str, Dict[str, str]]:
    """ Loads the comments that should be placed in written files. """

    # Comment dictionary already exists
    global _COMMENT_RECORDS
    if _COMMENT_RECORDS:
        return _COMMENT_RECORDS

    file_to_load = os.path.join(os.path.dirname(os.path.realpath(__file__)))
    file_to_load = os.path.join(file_to_load, "../reference_files/comments.str")

    try:
        comment_entry = entry_mod.Entry.from_file(file_to_load)
    except IOError:
        # Load the comments from Github if we can't find them locally
        try:
            comment_url = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v2/reference_files/comments.str"
            comment_entry = entry_mod.Entry.from_file(interpret_file(comment_url))
        except Exception:
            # No comments will be printed
            return {}

    # Load the comments
    comment_records = comment_entry[0][0].get_tag(["category", "comment", "every_flag"])
    comment_map = {'N': False, 'Y': True}
    for comment in comment_records:
        if comment[1] != ".":
            _COMMENT_RECORDS[comment[0]] = {'comment': comment[1].rstrip() + "\n\n",
                                            'every_flag': comment_map[comment[2]]}

    return _COMMENT_RECORDS


def _tag_key(x, schema: 'schema_mod.Schema' = None) -> int:
    """ Helper function to figure out how to sort the tags."""

    try:
        return get_schema(schema).schema_order.index(x)
    except ValueError:
        # Generate an arbitrary sort order for tags that aren't in the
        #  schema but make sure that they always come after tags in the
        #   schema
        return len(get_schema(schema).schema_order) + abs(hash(x))


def _called_directly() -> None:
    """ Figure out what to do if we were called on the command line
    rather than imported as a module."""

    # Specify some basic information about our command
    optparser = optparse.OptionParser(usage="usage: %prog",
                                      version=1,
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
                         dest="quick_test", help=optparse.SUPPRESS_HELP)

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
        validate(entry_mod.Entry.from_file(options.validate))

    # Print the diff report
    elif options.diff is not None:
        diff(entry_mod.Entry.from_file(options.diff[0]), entry_mod.Entry.from_file(options.diff[1]))

    # Fetch a tag and print it
    elif options.fetch_tag is not None:

        # Build an Entry from their file
        entry_local = entry_mod.Entry.from_file(options.fetch_tag[0])

        # Figure out if they want one or more tags
        if "," in options.fetch_tag[1]:
            query_tags = options.fetch_tag[1].split(",")
        else:
            query_tags = [options.fetch_tag[1]]

        # Get the tags they queried
        result = entry_local.get_tags(query_tags)
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
