import decimal
import json
import os
import re
from csv import reader as csv_reader
from datetime import date

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    import utils
except ImportError:
    from . import utils


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
            schema_file = utils._SCHEMA_URL
        self.schema_file = schema_file

        # Get the schema from the internet, wrap in StringIO and pass that
        #  to the csv reader
        schema_stream = utils.interpret_file(schema_file)
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
            raise ValueError("Could not parse a schema from the specified URL: %s" % schema_file)
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
            formatted = utils.format_category(line[tag_field])
            if formatted not in self.category_order:
                self.category_order.append(formatted)

        try:
            # Read in the data types
            types_file = utils.interpret_file(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                           "../reference_files/data_types.csv"))
        except IOError:
            # Load the data types from Github if we can't find them locally
            types_url = "https://raw.githubusercontent.com/uwbmrb/PyNMRSTAR/v2/reference_files/data_types.csv"
            try:
                types_file = utils.interpret_file(types_url)
            except Exception:
                raise ValueError("Could not load the data type definition file from disk or the internet!")

        csv_reader_instance = csv_reader(types_file)
        for item in csv_reader_instance:
            self.data_types[item[0]] = "^" + item[1] + "$"

    def __repr__(self):
        """Return how we can be initialized."""

        return "pynmrstar.Schema(schema_file='%s') version %s" % (self.schema_file, self.version)

    def __str__(self):
        """Print the schema that we are adhering to."""

        return self.string_representation()

    def string_representation(self, search=None):
        """ Prints all the tags in the schema if search is not specified
        and prints the tags that contain the search string if it is."""

        # Get the longest lengths
        lengths = [max([len(utils.format_tag(x)) for x in self.schema_order])]

        values = []
        for key in self.schema.keys():
            sc = self.schema[key]
            values.append((sc["Data Type"], sc["Nullable"], sc["SFCategory"], sc["Tag"]))

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
            tag_cat = utils.format_category(tag)
            if st:
                if tag_cat != last_tag:
                    last_tag = tag_cat
                    text += "\n%-30s\n" % tag_cat

                text += "  %-*s %-*s %-*s  %-*s\n" % (lengths[0], utils.format_tag(tag),
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
            search = utils.format_category(tag.lower())
            for pos, stag in enumerate([x.lower() for x in self.schema_order]):
                if stag.startswith(search):
                    new_tag_pos = pos + 1

        # Add the new tag to the tag order and tag list
        self.schema_order.insert(new_tag_pos, tag)
        self.category_order.insert(new_tag_pos, "_" + utils.format_tag(tag))

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
            if (utils.RAISE_PARSE_WARNINGS and
                    "tag-not-in-schema" not in utils.WARNINGS_TO_IGNORE):
                raise ValueError("There is a tag in the file that isn't in the"
                                 " schema: '%s' on line '%s'" % (tag, line_num))
            else:
                if utils.VERBOSE:
                    print("Couldn't convert tag because it is not in the "
                          "dictionary: " + tag)
                return value

        full_tag = self.schema[tag.lower()]

        # Get the type
        valtype, null_allowed = full_tag["Data Type"], full_tag["Nullable"]

        # Check for null
        if value == "." or value == "?":
            if (not null_allowed and utils.RAISE_PARSE_WARNINGS and
                    "invalid-null-value" not in utils.WARNINGS_TO_IGNORE):
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
        if value in utils.STR_CONVERSION_DICT:
            if any(isinstance(value, type(x)) for x in utils.STR_CONVERSION_DICT):
                value = utils.STR_CONVERSION_DICT[value]

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
            return json.dumps(s, default=utils._json_serialize)
        else:
            return s
