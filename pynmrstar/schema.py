import decimal
import logging
import os
import re
from csv import DictReader
from datetime import date
from functools import lru_cache
from io import StringIO
from typing import Union, List, Optional, Any, Dict, IO

from pynmrstar import definitions, utils
from pynmrstar._internal import _interpret_file, load_dictionary

logger = logging.getLogger('pynmrstar')


def _is_valid_date(value: str) -> bool:
    """Whether a value which already matched one of the dictionary's date type
    patterns is actually a date. The patterns are loose -- they accept a two
    digit year, month 13, day 32 -- so the fields have to be checked as well."""

    fields = value.split(':', 1)[0].split('-')
    if len(fields[0]) != 4:
        return False
    try:
        date(int(fields[0]),
             int(fields[1]) if len(fields) > 1 else 1,
             int(fields[2]) if len(fields) > 2 else 1)
    except ValueError:
        return False
    return True


class Schema(object):
    """A BMRB schema. Used to validate NMR-STAR files. Unless you need to
       choose a specific schema version, PyNMR-STAR will automatically load
       a schema for you. If you do need a specific schema version, you can
       create an object of this class and then pass it to the methods
       which allow the specification of a schema. """

    def __init__(self, schema_file: Union[str, IO] = None, version: str = None) -> None:
        """Initialize a BMRB schema. With no arguments the current dictionary
        distribution is loaded -- fetched from the internet and cached under
        ``~/.cache/pynmrstar`` (see ``_internal.load_dictionary``); repeat and
        command-line invocations then reuse the cache without the network. Pass
        ``version`` to select a specific cached release (3.2.14.0 or above).
        Alternatively pass a URL or a file via ``schema_file`` to load just a tag
        table from there; its enumerations still come from the distribution."""

        self.headers: List[str] = []
        self.schema: Dict[str, Dict[str, str]] = {}
        self.schema_order: List[str] = []
        self.category_order: List[str] = []
        self.version: str = "unknown"
        self.data_types: Dict[str, str] = {}
        # tag (lowercase) -> {'closed': bool, 'values': set of allowed values}
        self.enumerations: Dict[str, Dict[str, Any]] = {}

        enum_hdr: Optional[str] = None
        enum_dtl: Optional[str] = None
        if schema_file is not None:
            # Explicit tag table (URL/file). Enumerations, if reachable, still
            # come from the cached/packaged distribution.
            self.schema_file = schema_file
            xlschem_text = _interpret_file(schema_file).read()
            try:
                distribution, _ = load_dictionary(version)
                enum_hdr, enum_dtl = distribution['adit_enum_hdr.csv'], distribution['adit_enum_dtl.csv']
            except (ValueError, OSError, IOError):
                pass
        else:
            distribution, _ = load_dictionary(version)
            self.schema_file = definitions.DICTIONARY_URL
            xlschem_text = distribution['xlschem_ann.csv']
            enum_hdr, enum_dtl = distribution['adit_enum_hdr.csv'], distribution['adit_enum_dtl.csv']

        self._parse_tag_table(xlschem_text)
        self._load_data_types()
        if enum_hdr is not None and enum_dtl is not None:
            self._build_enumerations(enum_hdr, enum_dtl)

    def _parse_tag_table(self, xlschem_text: str) -> None:
        """Populate the tag schema from an xlschem_ann.csv body."""

        fix_newlines = StringIO('\n'.join(xlschem_text.splitlines()))
        csv_reader_instance = DictReader(fix_newlines)
        self.headers = csv_reader_instance.fieldnames

        # Skip the header descriptions and index values before the real data
        tmp_line = next(csv_reader_instance)
        try:
            while tmp_line['Dictionary sequence'] != "TBL_BEGIN":
                tmp_line = next(csv_reader_instance)
        except IndexError:
            raise ValueError(f"Could not parse a schema from: {self.schema_file}")
        self.version = tmp_line['ADIT category view type']

        for line in csv_reader_instance:
            if line['Dictionary sequence'] == "TBL_END":
                break
            single_tag_data: Dict[str, any] = dict(line)
            # Convert nulls
            if single_tag_data['Nullable'] == "NOT NULL":
                single_tag_data['Nullable'] = False
            else:
                single_tag_data['Nullable'] = True
            if '' in single_tag_data:
                del single_tag_data['']
            self.schema[single_tag_data['Tag'].lower()] = single_tag_data
            self.schema_order.append(single_tag_data['Tag'])
            formatted = utils.format_category(single_tag_data['Tag'])
            if formatted not in self.category_order:
                self.category_order.append(formatted)

    def _load_data_types(self) -> None:
        """Load the value-type regular expressions from the packaged reference."""

        try:
            types_file = _interpret_file(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                      "reference_files/data_types.csv"))
        except IOError:
            raise ValueError("Could not load the data type definition file from disk!")
        csv_reader_instance = DictReader(types_file, fieldnames=['type_name', 'type_definition'])
        for item in csv_reader_instance:
            self.data_types[item['type_name']] = f"^{item['type_definition']}$"

    def _build_enumerations(self, enum_hdr_text: str, enum_dtl_text: str) -> None:
        """Build enumeration value lists by joining the dictionary's
        adit_enum_hdr (enumeration id -> tag) with adit_enum_dtl (id -> values).
        The closed/open flag comes from the already-parsed tag table. Values are
        stored as the dictionary spells them, alongside a case-folded index so
        that a value which differs from the dictionary only in capitalization can
        be reported as such rather than as an unknown value."""

        id_to_tag: Dict[str, str] = {}
        for row in DictReader(StringIO(enum_hdr_text)):
            eid = row.get('Enumeration ID')
            if eid in (None, 'TBL_BEGIN', 'TBL_END', '?'):
                continue
            id_to_tag[eid] = row.get('Tag')

        for row in DictReader(StringIO(enum_dtl_text)):
            eid = row.get('Enumeration ID')
            if eid in (None, 'TBL_BEGIN', 'TBL_END', '?'):
                continue
            tag = id_to_tag.get(eid)
            if not tag:
                continue
            value = (row.get('Enum value') or '').strip()
            if value == '':
                continue
            tag_lower = tag.lower()
            entry = self.enumerations.get(tag_lower)
            if entry is None:
                closed = self.schema.get(tag_lower, {}).get('Item enumeration closed') == 'Y'
                entry = self.enumerations[tag_lower] = {'closed': closed, 'values': set(), 'folded': {}}
            entry['values'].add(value)
            entry['folded'][value.lower()] = value

    def __repr__(self) -> str:
        """Return how we can be initialized."""

        return f"pynmrstar.Schema(schema_file='{self.schema_file}') version {self.version}"

    def __str__(self) -> str:
        """Print the schema that we are adhering to."""

        return self.string_representation()

    def add_tag(self, tag: str, tag_type: str, null_allowed: bool, sf_category: str, loop_flag: bool,
                after: str = None):
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

        # Add the underscore preceding the tag
        if tag[0] != "_":
            tag = "_" + tag

        # See if the tag is already in the schema
        if tag.lower() in self.schema:
            raise ValueError("Cannot add a tag to the schema that is already in"
                             f" the schema: {tag}")

        # Check the tag type
        tag_type = tag_type.upper()
        if tag_type not in ["INTEGER", "FLOAT", "TEXT", "DATETIME year to day"]:
            if tag_type.startswith("CHAR(") or tag_type.startswith("VARCHAR("):
                # This will allow things through that have extra junk on the end, but in general it is
                # okay to be forgiving as long as we can guess what they mean.
                length = tag_type[tag_type.index("(") + 1:tag_type.index(")")]
                # Check the length for non-numbers and 0
                try:
                    1 / int(length)
                except (ValueError, ZeroDivisionError):
                    raise ValueError(f"Illegal length specified in tag type: {length}")

                # Cut off anything that might be at the end
                tag_type = tag_type[0:tag_type.index(")") + 1]
            else:
                raise ValueError("The tag type you provided is not valid. Please use a type as specified in the help "
                                 "for this method.")

        # Check the null allowed
        if str(null_allowed).lower() == "false":
            null_allowed = False
        if str(null_allowed).lower() == "true":
            null_allowed = True
        if not (null_allowed is True or null_allowed is False):
            raise ValueError("Please specify whether null is allowed with True/False")

        # Check the category
        if not sf_category:
            raise ValueError("Please provide the sf_category of the parent saveframe.")

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
                    raise ValueError("The tag you specified to insert this tag after does not exist in the schema.")
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

        def _test_pos(position, schema) -> int:
            for item in schema.schema.values():
                if float(item["Dictionary sequence"]) == position:
                    return _test_pos(position + 1, schema)
            return position

        new_tag_pos = _test_pos(new_tag_pos, self)

        self.schema[tag.lower()] = {"Data Type": tag_type, "Loopflag": loop_flag,
                                    "Nullable": null_allowed, "public": "Y",
                                    "SFCategory": sf_category, "Tag": tag,
                                    "Dictionary sequence": new_tag_pos}

    @lru_cache(maxsize=1024, typed=True)
    def convert_tag(self, tag: str, value: Any) -> \
            Optional[Union[str, int, decimal.Decimal, date]]:
        """ Converts the provided tag from string to the appropriate
        type as specified in this schema."""

        # If we don't know what the tag is, just return it
        if tag.lower() not in self.schema:
            if tag != '_internal.use':
                logger.warning(f"Couldn't convert tag data type because it is not in the dictionary: {tag}")
            return value

        full_tag = self.schema[tag.lower()]

        # Get the type
        value_type, null_allowed = full_tag["Data Type"], full_tag["Nullable"]

        # Check for null
        if value in definitions.NULL_VALUES:
            return None

        # Keep strings strings
        if "CHAR" in value_type or "VARCHAR" in value_type or "TEXT" in value_type:
            return value

        # Convert ints
        if "INTEGER" in value_type:
            try:
                return int(value)
            except (ValueError, TypeError):
                raise ValueError("Could not parse the file because a value that should be an INTEGER is not. Either "
                                 f"do not specify convert_data_types or fix the file. Tag: '{tag}'.")

        # Convert floats
        if "FLOAT" in value_type:
            try:
                # If we used int() we would lose the precision
                return decimal.Decimal(value)
            except (decimal.InvalidOperation, TypeError):
                raise ValueError("Could not parse the file because a value that should be a FLOAT is not. Either "
                                 f"do not specify convert_data_types or fix the file. Tag: '{tag}'.")

        if "DATETIME year to day" in value_type:
            try:
                year, month, day = [int(x) for x in value.split("-")]
                return date(year, month, day)
            except (ValueError, TypeError):
                raise ValueError("Could not parse the file because a value that should be a DATETIME is not. Please "
                                 f"do not specify convert_data_types or fix the file. Tag: '{tag}'.")

        # We don't know the data type, so just keep it a string
        return value

    def string_representation(self, search: bool = None) -> str:
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

        text = f"""BMRB schema from: '{self.schema_file}' version '{self.version}'
{''}
  {'Tag_Prefix':<{lengths[0]}} {'Tag':<{lengths[1] - 6}} {'Type':<{lengths[2]}} {'Null_Allowed':<{lengths[3]}} {'SF_Category'}
"""
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

    def val_type(self, tag: str, value: Any, category: str = None):
        """ Validates that a tag matches the type it should have
        according to this schema."""

        if tag.lower() not in self.schema:
            return [f"Tag '{tag}' not found in schema."]

        # We will skip type checks for None's
        is_none = value is None

        # Allow manual specification of conversions for booleans, Nones, etc.
        if value in definitions.STR_CONVERSION_DICT:
            if any(isinstance(value, type(x)) for x in definitions.STR_CONVERSION_DICT):
                value = definitions.STR_CONVERSION_DICT[value]

        # Value should always be string
        if not isinstance(value, str):
            value = str(value)

        # Check that it isn't a string None
        if value in definitions.NULL_VALUES:
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
                return [f"The tag '{capitalized_tag}' in category '{category}' should be in category "
                        f"'{allowed_category}'."]

        if is_none:
            if not null_allowed:
                return [f"Value cannot be NULL but is: {capitalized_tag}':'{value}'."]
            return []
        else:
            # Don't run these checks on unassigned tags
            if "CHAR" in val_type:
                length = int(val_type[val_type.index("(") + 1:val_type.index(")")])
                if len(str(value)) > length:
                    return [f"Length of '{len(value)}' is too long for '{val_type}': '{capitalized_tag}':'{value}'."]

            # Check that the value matches the regular expression for the type
            if not re.match(self.data_types[bmrb_type], str(value)):
                return [f"Value does not match specification: '{capitalized_tag}':'{value}'.\n"
                        f"     Type specified: {bmrb_type}\n"
                        f"     Regular expression for type: '{self.data_types[bmrb_type]}'"]

            if bmrb_type.startswith('yyyy-mm-dd') and not _is_valid_date(value):
                return [f"Value is not a valid date: '{capitalized_tag}':'{value}'."]

            # Check closed-enumeration membership. Only *closed* enumerations are
            # enforced; open ones are advisory and not flagged. A value that is in
            # the enumeration but spelled with different capitalization gets its
            # own message, since the fix is not the same one.
            enum = self.enumerations.get(tag.lower())
            if enum is not None and enum['closed'] and value not in enum['values']:
                capitalized_value = enum['folded'].get(value.lower())
                if capitalized_value is not None:
                    return [f"Value '{value}' of tag '{capitalized_tag}' is improperly capitalized but otherwise "
                            f"valid. Should be '{capitalized_value}'."]
                return [f"Value '{value}' is not in the closed enumeration for tag '{capitalized_tag}'."]

        # Check the tag capitalization
        if tag != capitalized_tag:
            return [f"The tag '{tag}' is improperly capitalized but otherwise valid. Should be '{capitalized_tag}'."]
        return []

    def tag_key(self, x) -> int:
        """ Helper function to figure out how to sort the tags."""

        try:
            return self.schema_order.index(x)
        except ValueError:
            # Generate an arbitrary sort order for tags that aren't in the
            #  schema but make sure that they always come after tags in the
            #   schema
            return len(self.schema_order) + abs(hash(x))
