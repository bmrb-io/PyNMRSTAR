import json
import warnings
from copy import deepcopy
from csv import reader as csv_reader, writer as csv_writer
from io import StringIO
from itertools import chain
from typing import TextIO, BinaryIO, Union, List, Optional, Any, Dict, Callable, Tuple

from pynmrstar import definitions, utils, entry as entry_mod
from pynmrstar._internal import _json_serialize, _interpret_file
from pynmrstar.exceptions import InvalidStateError
from pynmrstar.parser import Parser
from pynmrstar.schema import Schema


class Loop(object):
    """A BMRB loop object. Create using the class methods, see below."""

    def __contains__(self, item: Any) -> bool:
        """ Check if the loop contains one or more tags. """

        # Prepare for processing
        if isinstance(item, (list, tuple)):
            to_process: List[str] = list(item)
        elif isinstance(item, str):
            to_process = [item]
        else:
            return False

        lc_tags = self._lc_tags
        for tag in to_process:
            if utils.format_tag(tag).lower() not in lc_tags:
                return False
        return True

    def __eq__(self, other) -> bool:
        """Returns True if this loop is equal to another loop, False if
        it is different."""

        if not isinstance(other, Loop):
            return False

        return (self.category, self._tags, self.data) == \
               (other.category, other._tags, other.data)

    def __getitem__(self, item: Union[int, str, List[str], Tuple[str]]) -> list:
        """Get the indicated row from the data array."""

        try:
            return self.data[item]
        except TypeError:
            if isinstance(item, tuple):
                item = list(item)
            return self.get_tag(tags=item)

    def __init__(self, **kwargs) -> None:
        """ You should not directly instantiate a Loop using this method.
            Instead use the class methods:

            :py:meth:`Loop.from_scratch`, :py:meth:`Loop.from_string`,
            :py:meth:`Loop.from_template`, :py:meth:`Loop.from_file`,
            :py:meth:`Loop.from_json`"""

        # Initialize our local variables
        self._tags: List[str] = []
        self.data: List[List[Any]] = []
        self.category: Optional[str] = None
        self.source: str = "unknown"

        star_buffer: StringIO = StringIO("")

        # Update our source if it provided
        if 'source' in kwargs:
            self.source = kwargs['source']

        # Update our category if provided
        if 'category' in kwargs:
            self.category = utils.format_category(kwargs['category'])
            return

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate a Loop using this method. Instead use the "
                             "class methods: Loop.from_scratch(), Loop.from_string(), Loop.from_template(), "
                             "Loop.from_file(), and Loop.from_json().")

        # Parsing from a string
        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        # Parsing from a file
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = f"from_file('{kwargs['file_name']}')"
        # Creating from template (schema)
        elif 'tag_prefix' in kwargs:

            tags = Loop._get_tags_from_schema(kwargs['tag_prefix'], all_tags=kwargs['all_tags'],
                                              schema=kwargs['schema'])
            for tag in tags:
                self.add_tag(tag)

            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kwargs and kwargs['csv']:
            csv_file = csv_reader(star_buffer)
            self.add_tag(next(csv_file))
            for row in csv_file:
                self.add_data(row, convert_data_types=kwargs.get('convert_data_types', False))
            self.source = f"from_csv('{kwargs['csv']}')"
            return

        tmp_entry = entry_mod.Entry.from_scratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO(f"data_0 save_internaluseyoushouldntseethis_frame _internal.use internal "
                               f"{star_buffer.read()} save_")
        parser = Parser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source, convert_data_types=kwargs.get('convert_data_types', False))

        # Check that there was only one loop here
        if len(tmp_entry[0].loops) > 1:
            raise ValueError("You attempted to parse one loop but the source you provided had more than one loop. "
                             "Please either parse all loops as a saveframe or only parse one loop. Loops detected: " +
                             str(tmp_entry[0].loops))

        # Copy the first parsed saveframe into ourself
        self._tags = tmp_entry[0][0].tags
        self.data = tmp_entry[0][0].data
        self.category = tmp_entry[0][0].category

    def __iter__(self) -> list:
        """ Yields each of the rows contained within the loop. """

        for row in self.data:
            yield row

    def __len__(self) -> int:
        """Return the number of rows of data."""

        return len(self.data)

    def __lt__(self, other) -> bool:
        """Returns True if this loop sorts lower than the compared
        loop, false otherwise."""

        if not isinstance(other, Loop):
            return NotImplemented

        return self.category < other.category

    def __repr__(self) -> str:
        """Returns a description of the loop."""

        return f"<pynmrstar.Loop '{self.category}'>"

    def __setitem__(self, key: str, item: Any) -> None:
        """Set all of the instances of a tag to the provided value.
        If there are 5 rows of data in the loop, you will need to
        assign a list with 5 elements."""

        tag = utils.format_tag(key)

        # Check that their tag is in the loop
        if tag not in self._tags:
            raise ValueError(f"Cannot assign to tag '{key}' as it does not exist in this loop.")

        # Determine where to assign
        tag_id = self._tags.index(tag)

        # Make sure they provide a list of the correct length
        if len(self[key]) != len(item):
            raise ValueError("To assign to a tag you must provide a list (or iterable) of a length equal to the "
                             f"number of values that currently exist for that tag. The tag '{key}' currently has"
                             f" {len(self[key])} values and you supplied {len(item)} values.")

        # Do the assignment
        for pos, row in enumerate(self.data):
            row[tag_id] = item[pos]

    def __str__(self, skip_empty_loops: bool = False, skip_empty_tags: bool = False) -> str:
        """Returns the loop in STAR format as a string."""

        # Check if there is any data in this loop
        if len(self.data) == 0:
            # They do not want us to print empty loops
            if skip_empty_loops:
                return ""
            else:
                # If we have no tags than return the empty loop
                if len(self._tags) == 0:
                    return "\n   loop_\n\n   stop_\n"

        if len(self._tags) == 0:
            raise InvalidStateError("Impossible to print data if there are no associated tags. Error in loop "
                                    f"'{self.category}' which contains data but hasn't had any tags added.")

        # Make sure the tags and data match
        self._check_tags_match_data()

        # If skipping null tags, it's easier to filter out a loop with only real tags and then print
        if skip_empty_tags:
            has_data = [not all([_ in definitions.NULL_VALUES for _ in column]) for column in zip(*self.data)]
            return self.filter([tag for x, tag in enumerate(self._tags) if has_data[x]]).format()

        # Start the loop
        return_chunks = ["\n   loop_\n"]
        # Print the tags
        format_string = "      %-s\n"

        # Check to make sure our category is set
        if self.category is None:
            raise InvalidStateError("The category was never set for this loop. Either add a tag with the category "
                                    "intact, specify it when generating the loop, or set it using Loop.set_category().")

        # Print the categories
        if self.category is None:
            for tag in self._tags:
                return_chunks.append(format_string % tag)
        else:
            for tag in self._tags:
                return_chunks.append(format_string % (self.category + "." + tag))

        return_chunks.append("\n")

        if len(self.data) != 0:

            # Make a copy of the data
            working_data = []
            title_widths = [4]*len(self.data[0])

            # Put quotes as needed on the data
            for row_pos, row in enumerate(self.data):
                clean_row = []
                for col_pos, x in enumerate(row):
                    try:
                        clean_val = utils.quote_value(x)
                        clean_row.append(clean_val)
                        length = len(clean_val) + 3
                        if length > title_widths[col_pos] and "\n" not in clean_val:
                            title_widths[col_pos] = length

                    except ValueError:
                        raise InvalidStateError('Cannot generate NMR-STAR for entry, as empty strings are not valid '
                                                'tag values in NMR-STAR. Please either replace the empty strings with'
                                                ' None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT['
                                                '\'\'] = None.\n'
                                                f'Loop: {self.category} Row: {row_pos} Column: {col_pos}')

                working_data.append(clean_row)

            # Generate the format string
            format_string = "     " + "%-*s" * len(self._tags) + " \n"

            # Print the data, with the tags sized appropriately
            for datum in working_data:
                for pos, item in enumerate(datum):
                    if "\n" in item:
                        datum[pos] = "\n;\n%s;\n" % item

                # Print the data (combine the tags' widths with their data)
                tag_width_list = [d for d in zip(title_widths, datum)]
                return_chunks.append(format_string % tuple(chain.from_iterable(tag_width_list)))

        # Close the loop
        return "".join(return_chunks) + "\n   stop_\n"

    @property
    def _lc_tags(self) -> Dict[str, int]:
        return {_[1].lower(): _[0] for _ in enumerate(self._tags)}

    @property
    def empty(self) -> bool:
        """ Check if the loop has no data. """

        for row in self.data:
            for col in row:
                if col not in definitions.NULL_VALUES:
                    return False

        return True

    @property
    def tags(self) -> List[str]:
        return self._tags

    @classmethod
    def from_file(cls, the_file: Union[str, TextIO, BinaryIO], csv: bool = False, convert_data_types: bool = False):
        """Create a saveframe by loading in a file. Specify csv=True if
        the file is a CSV file. If the_file starts with http://,
        https://, or ftp:// then we will use those protocols to attempt
        to open the file.

        Setting convert_data_types to True will automatically convert
        the data loaded from the file into the corresponding python type as
        determined by loading the standard BMRB schema. This would mean that
        all floats will be represented as decimal.Decimal objects, all integers
        will be python int objects, strings and vars will remain strings, and
        dates will become datetime.date objects. When printing str() is called
        on all objects. Other that converting uppercase "E"s in scientific
        notation floats to lowercase "e"s this should not cause any change in
        the way re-printed NMR-STAR objects are displayed."""

        return cls(file_name=the_file, csv=csv, convert_data_types=convert_data_types)

    @classmethod
    def from_json(cls, json_dict: Union[dict, str]):
        """Create a loop from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ['tags', 'category', 'data']:
            if check not in json_dict:
                raise ValueError(f"The JSON you provide must be a dictionary and must contain the key '{check}' - even"
                                 f" if the key points to None.")

        # Create a loop from scratch and populate it
        ret = Loop.from_scratch()
        ret._tags = json_dict['tags']
        ret.category = json_dict['category']
        ret.data = json_dict['data']
        ret.source = "from_json()"

        # Return the new loop
        return ret

    @classmethod
    def from_scratch(cls, category: str = None, source: str = "from_scratch()"):
        """Create an empty saveframe that you can programmatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""

        return cls(category=category, source=source)

    @classmethod
    def from_string(cls, the_string: str, csv: bool = False, convert_data_types: bool = False):
        """Create a saveframe by parsing a string. Specify csv=True is
        the string is in CSV format and not NMR-STAR format.

        Setting convert_data_types to True will automatically convert
        the data loaded from the file into the corresponding python type as
        determined by loading the standard BMRB schema. This would mean that
        all floats will be represented as decimal.Decimal objects, all integers
        will be python int objects, strings and vars will remain strings, and
        dates will become datetime.date objects. When printing str() is called
        on all objects. Other that converting uppercase "E"s in scientific
        notation floats to lowercase "e"s this should not cause any change in
        the way re-printed NMR-STAR objects are displayed."""

        return cls(the_string=the_string, csv=csv, convert_data_types=convert_data_types)

    @classmethod
    def from_template(cls, tag_prefix: str, all_tags: bool = False, schema: Schema = None):
        """ Create a loop that has all of the tags from the schema present.
        No values will be assigned. Specify the tag prefix of the loop.

        The optional argument all_tags forces all tags to be included
        rather than just the mandatory tags."""

        schema = utils.get_schema(schema)
        return cls(tag_prefix=tag_prefix, all_tags=all_tags,
                   schema=schema, source=f"from_template({schema.version})")

    @staticmethod
    def _get_tags_from_schema(category: str, schema: Schema = None, all_tags: bool = False) -> List[str]:
        """ Returns the tags from the schema for the category of this
        loop. """

        schema = utils.get_schema(schema)

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
            raise InvalidStateError(f"The tag prefix '{category}' has no corresponding tags in the dictionary.")

        return tags

    def _check_tags_match_data(self) -> bool:
        """ Ensures that each row of the data has the same number of
        elements as there are tags for the loop. This is necessary to
        print or do some other operations on loops that count on the values
        matching. """

        # Make sure that if there is data, it is the same width as the
        #  tag names
        if len(self.data) > 0:
            for x, row in enumerate(self.data):
                if len(self._tags) != len(row):
                    raise InvalidStateError(f"The number of tags must match the width of the data. Error in loop "
                                            f"'{self.category}'. In this case, there are {len(self._tags)} tags, and "
                                            f"row number {x} has {len(row)} tags.")

        return True

    def add_data(self, the_list: List[Any], rearrange: bool = False, convert_data_types: bool = False):
        """Add a list to the data field. Items in list can be any type,
        they will be converted to string and formatted correctly. The
        list must have the same cardinality as the tag names or you
        must set the rearrange variable to true and have already set all
        the tag names in the loop. Rearrange will break a longer list into
        rows based on the number of tags."""

        # Add one row of data
        if not rearrange:
            if len(the_list) != len(self._tags):
                raise ValueError("The list must have the same number of elements as the number of tags when adding a "
                                 "single row of values! Insert tag names first by calling Loop.add_tag().")
            # Add the user data
            self.data.append(the_list)
            return

        # Break their data into chunks based on the number of tags
        processed_data = [the_list[x:x + len(self._tags)] for x in range(0, len(the_list), len(self._tags))]
        if len(processed_data[-1]) != len(self._tags):
            raise ValueError(f"The number of data elements in the list you provided is not an even multiple of the "
                             f"number of tags which are set in the loop. Please either add missing tags using "
                             f"Loop.add_tag() or modify the list of tag values you are adding to be an even multiple "
                             f"of the number of tags. Error in loop '{self.category}'.")

        # Auto convert data types if option set
        if convert_data_types:
            schema = utils.get_schema()
            for row in processed_data:
                for tag_id, datum in enumerate(row):
                    row[tag_id] = schema.convert_tag(self.category + "." + self._tags[tag_id], datum)

        self.data.extend(processed_data)

    def add_data_by_tag(self, tag_name: str, value) -> None:
        """Deprecated: It is recommended to use add_data() instead for most use
        cases.

        Add data to the loop one element at a time, based on tag.
        Useful when adding data from SANS parsers."""

        warnings.warn("Deprecated: It is recommended to use Loop.add_data() instead for most use cases.",
                      DeprecationWarning)

        # Make sure the category matches - if provided
        if "." in tag_name:
            supplied_category = utils.format_category(str(tag_name))
            if supplied_category.lower() != self.category.lower():
                raise ValueError(f"Category provided in your tag '{supplied_category}' does not match this loop's "
                                 f"category '{self.category}'.")

        pos = self.tag_index(tag_name)
        if pos is None:
            raise ValueError(f"The tag '{tag_name}' to which you are attempting to add data does not yet exist. Create "
                             f"the tags using Loop.add_tag() before adding data.")
        if len(self.data) == 0:
            self.data.append([])
        if len(self.data[-1]) == len(self._tags):
            self.data.append([])
        if len(self.data[-1]) != pos:
            raise ValueError("You cannot add data out of tag order.")
        self.data[-1].append(value)

    def add_missing_tags(self, schema: 'Schema' = None, all_tags: bool = False) -> None:
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
            ordinal_idx = self.tag_index("Ordinal")

            # If we are in another row, assign to the previous row
            for pos, row in enumerate(self.data):
                row[ordinal_idx] = pos + 1

    def add_tag(self, name: Union[str, List[str]], ignore_duplicates: bool = False, update_data: bool = False) -> None:
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
                self.add_tag(item, ignore_duplicates=ignore_duplicates, update_data=update_data)
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
                    raise ValueError("One loop cannot have tags with different categories (or tags that don't "
                                     f"match the loop category)! The loop category is '{self.category}' while "
                                     f"the category in the tag was '{category}'.")
                name = name[name.index(".") + 1:]
            else:
                name = name[1:]

        # Ignore duplicate tags
        if self.tag_index(name) is not None:
            if ignore_duplicates:
                return
            else:
                raise ValueError(f"There is already a tag with the name '{name}' in the loop '{self.category}'.")
        if name in definitions.NULL_VALUES:
            raise ValueError(f"Cannot use a null-equivalent value as a tag name. Invalid tag name: '{name}'")
        if "." in name:
            raise ValueError(f"There cannot be more than one '.' in a tag name. Invalid tag name: '{name}'")
        for char in str(name):
            if char in utils.definitions.WHITESPACE:
                raise ValueError(f"Tag names can not contain whitespace characters. Invalid tag name: '{name}")

        # Add the tag
        self._tags.append(name)

        # Add None's to the rows of data
        if update_data:

            for row in self.data:
                row.append(None)

    def clear_data(self) -> None:
        """Erases all data in this loop. Does not erase the tag names
        or loop category."""

        self.data = []

    def compare(self, other) -> List[str]:
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
        elif not isinstance(other, Loop):
            return ['Other object is not of class Loop.']

        # We need to do this in case of an extra "\n" on the end of one tag
        if str(other) == str(self):
            return []

        # Do STAR comparison
        try:
            # Check category of loops
            if str(self.category).lower() != str(other.category).lower():
                diffs.append(f"\t\tCategory of loops does not match: '{self.category}' vs '{other.category}'.")

            # Check tags of loops
            if ([x.lower() for x in self._tags] !=
                    [x.lower() for x in other.tags]):
                diffs.append(f"\t\tLoop tag names do not match for loop with category '{self.category}'.")

            # No point checking if data is the same if the tag names aren't
            else:
                # Only sort the data if it is not already equal
                if self.data != other.data:

                    # Check data of loops
                    self_data = sorted(deepcopy(self.data))
                    other_data = sorted(deepcopy(other.data))

                    if self_data != other_data:
                        diffs.append(f"\t\tLoop data does not match for loop with category '{self.category}'.")

        except AttributeError as err:
            diffs.append(f"\t\tAn exception occurred while comparing: '{err}'.")

        return diffs

    def delete_tag(self, tag: Union[str, List[str]]) -> None:
        """ Deprecated. Please use `py:meth:pynmrstar.Loop.remove_tag` instead. """

        warnings.warn('Please use remove_tag() instead.', DeprecationWarning)
        return self.remove_tag(tag)

    def delete_data_by_tag_value(self, tag: str, value: Any, index_tag: str = None) -> List[List[Any]]:
        """ Deprecated. Please use `py:meth:pynmrstar.Loop.remove_data_by_tag_value` instead. """

        warnings.warn('Please use remove_data_by_tag_value() instead.', DeprecationWarning)
        return self.remove_data_by_tag_value(tag, value, index_tag)

    def filter(self, tag_list: Union[str, List[str], Tuple[str]], ignore_missing_tags: bool = False):
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
            tag_match_index = self.tag_index(tag)
            if tag_match_index is None:
                if not ignore_missing_tags:
                    raise KeyError(f"Cannot filter tag '{tag}' as it isn't present in this loop.")
                continue

            valid_tags.append(tag)
            result.add_tag(self._tags[tag_match_index])

        # Add the data for the tags to the new loop
        results = self.get_tag(valid_tags)

        # If there is only a single tag, we can't add data the same way
        if len(valid_tags) == 1:
            for item in results:
                result.add_data([item])
        else:
            for row in results:
                # We know it's a row because we didn't specify dict_result=True to get_tag()
                assert isinstance(row, list)
                result.add_data(row)

        # Assign the category of the new loop
        if result.category is None:
            result.category = self.category

        return result

    def format(self, skip_empty_loops: bool = True, skip_empty_tags: bool = False) -> str:
        """ The same as calling str(Loop), except that you can pass options
        to customize how the loop is printed.

        skip_empty_loops will omit printing loops with no tags at all. (A loop with null tags is not "empty".)
        skip_empty_tags will omit tags in the loop which have no non-null values."""

        return self.__str__(skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags)

    def get_data_as_csv(self, header: bool = True, show_category: bool = True) -> str:
        """Return the data contained in the loops, properly CSVd, as a
        string. Set header to False to omit the header. Set
        show_category to false to omit the loop category from the
        headers."""

        csv_buffer = StringIO()
        csv_writer_object = csv_writer(csv_buffer)

        if header:
            if show_category:
                csv_writer_object.writerow(
                    [str(self.category) + "." + str(x) for x in self._tags])
            else:
                csv_writer_object.writerow([str(x) for x in self._tags])

        for row in self.data:

            data = []
            for piece in row:
                data.append(piece)

            csv_writer_object.writerow(data)

        csv_buffer.seek(0)
        return csv_buffer.read().replace('\r\n', '\n')

    def get_json(self, serialize: bool = True) -> Union[dict, str]:
        """ Returns the loop in JSON format. If serialize is set to
        False a dictionary representation of the loop that is
        serializeable is returned."""

        loop_dict = {
            "category": self.category,
            "tags": self._tags,
            "data": self.data
        }

        if serialize:
            return json.dumps(loop_dict, default=_json_serialize)
        else:
            return loop_dict

    def get_tag_names(self) -> List[str]:
        """ Return the tag names for this entry with the category
        included. Throws ValueError if the category was never set.

        To fetch tag values use get_tag()."""

        if not self.category:
            raise InvalidStateError("You never set the category of this loop. You must set the category before calling "
                                    "this method, either by setting the loop category directly when creating the loop "
                                    "using the Loop.from_scratch() class method, by calling loop.set_category(), or by "
                                    "adding a fully qualified tag which includes the loop category (for example, "
                                    "adding '_Citation_author.Family_name' rather than just 'Family_name').")

        return [self.category + "." + x for x in self._tags]

    def get_tag(self, tags: Optional[Union[str, List[str]]] = None, whole_tag: bool = False,
                dict_result: bool = False) -> Union[List[Any], List[Dict[str, Any]]]:
        """Provided a tag name (or a list of tag names) return the selected tags by row as
        a list of lists.

        If whole_tag=True return the full tag name along with the tag
        value, or if dict_result=True, as the tag key.

        If dict_result=True, return the tags as a list of dictionaries
        in which the tag value points to the tag."""

        # All tags
        if tags is None:
            if not dict_result:
                return self.data
            else:
                tags = [self._tags]
        # Turn single elements into lists
        if not isinstance(tags, list):
            tags = [tags]

        # Make a copy of the tags to fetch - don't modify the
        # list that was passed
        lower_tags = deepcopy(tags)

        # Strip the category if they provide it (also validate
        #  it during the process)
        for pos, item in enumerate([str(x) for x in lower_tags]):
            if "." in item and utils.format_category(item).lower() != self.category.lower():
                raise ValueError(f"Cannot fetch data with tag '{item}' because the category does not match the "
                                 f"category of this loop '{self.category}'.")
            lower_tags[pos] = utils.format_tag(item).lower()

        # Make a lower case copy of the tags
        tags_lower = [x.lower() for x in self._tags]

        # Map tag name to tag position in list
        tag_mapping = dict(zip(reversed(tags_lower), reversed(range(len(tags_lower)))))

        # Make sure their fields are actually present in the entry
        tag_ids = []
        for pos, query in enumerate(lower_tags):
            if str(query) in tag_mapping:
                tag_ids.append(tag_mapping[query])
            elif isinstance(query, int):
                tag_ids.append(query)
            else:
                raise KeyError(f"Could not locate the tag with name or ID: '{tags[pos]}' in loop '{self.category}'.")

        # First build the tags as a list
        if not dict_result:

            # Use a list comprehension to pull the correct tags out of the rows
            if whole_tag:
                result = [[[self.category + "." + self._tags[col_id], row[col_id]]
                           for col_id in tag_ids] for row in self.data]
            else:
                result = [[row[col_id] for col_id in tag_ids] for row in self.data]

            # Strip the extra list if only one tag
            if len(lower_tags) == 1:
                return [x[0] for x in result]
            else:
                return result
        # Make a dictionary
        else:
            if whole_tag:
                result = [dict((self.category + "." + self._tags[col_id], row[col_id]) for col_id in tag_ids) for
                          row in self.data]
            else:
                result = [dict((self._tags[col_id], row[col_id]) for col_id in tag_ids) for row in self.data]

        return result

    def print_tree(self) -> None:
        """Prints a summary, tree style, of the loop."""

        print(repr(self))

    def remove_data_by_tag_value(self, tag: str, value: Any, index_tag: str = None) -> List[List[Any]]:
        """Removes all rows which contain the provided value in the
        provided tag name. If index_tag is provided, that tag is
        renumbered starting with 1. Returns the deleted rows."""

        # Make sure the category matches - if provided
        if "." in tag:
            supplied_category = utils.format_category(str(tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError(f"The category provided in your tag '{supplied_category}' does not match this loop's "
                                 f"category '{self.category}'.")

        search_tag = self.tag_index(tag)
        if search_tag is None:
            raise ValueError(f"The tag you provided '{tag}' isn't in this loop!")

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

    def remove_tag(self, tag: Union[str, List[str]]) -> None:
        """Removes one or more tags from the loop based on tag name. Also removes any data for the given tag.
        Provide either a tag or list of tags."""

        if not isinstance(tag, list):
            tag = [tag]

        # Check if the tags exist first
        for each_tag in tag:
            if self.tag_index(each_tag) is None:
                raise KeyError(f"There is no tag with name '{each_tag}' to remove in loop '{self.category}'.")

        # Calculate the tag position each time, because it will change as the previous tag is deleted
        for each_tag in tag:
            tag_position: int = self.tag_index(each_tag)
            del self._tags[tag_position]
            for row in self.data:
                del row[tag_position]

    def renumber_rows(self, index_tag: str, start_value: int = 1, maintain_ordering: bool = False):
        """Renumber a given tag incrementally. Set start_value to
        initial value if 1 is not acceptable. Set maintain_ordering to
        preserve sequence with offset.

        E.g. 2,3,3,5 would become 1,2,2,4."""

        # Make sure the category matches
        if "." in str(index_tag):
            supplied_category = utils.format_category(str(index_tag))
            if supplied_category.lower() != self.category.lower():
                raise ValueError(f"Category provided in your tag '{supplied_category}' does not match this loop's "
                                 f"category '{self.category}'.")

        # Determine which tag ID to renumber
        renumber_tag = self.tag_index(index_tag)

        # The tag to replace in is the tag they specify
        if renumber_tag is None:
            # Or, perhaps they specified an integer to represent the tag?
            try:
                renumber_tag = int(index_tag)
            except ValueError:
                raise ValueError(f"The renumbering tag you provided '{index_tag}' isn't in this loop!")

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

                    if isinstance(self.data[pos][renumber_tag], str):
                        self.data[pos][renumber_tag] = str(new_data)
                    else:
                        self.data[pos][renumber_tag] = new_data
                except ValueError:
                    self.data = data_copy
                    raise ValueError("You can't renumber a row containing anything that can't be coerced into an "
                                     "integer using maintain_ordering. I.e. what am I suppose to renumber "
                                     f"'{self.data[pos][renumber_tag]}' to?")

        # Simple renumbering algorithm if we don't need to maintain the ordering
        else:
            for pos in range(0, len(self.data)):
                if isinstance(self.data[pos][renumber_tag], str):
                    self.data[pos][renumber_tag] = str(pos + start_value)
                else:
                    self.data[pos][renumber_tag] = pos + start_value

    def set_category(self, category: str) -> None:
        """ Set the category of the loop. Useful if you didn't know the
        category at loop creation time."""

        self.category = utils.format_category(category)

    def sort_tags(self, schema: 'Schema' = None) -> None:
        """ Rearranges the tag names and data in the loop to match the order
        from the schema. Uses the BMRB schema unless one is provided."""

        schema = utils.get_schema(schema)
        current_order = self.get_tag_names()

        # Sort the tags
        def sort_key(_) -> int:
            return schema.tag_key(_)

        sorted_order = sorted(current_order, key=sort_key)

        # Don't touch the data if the tags are already in order
        if sorted_order == current_order:
            return
        else:
            self.data = self.get_tag(sorted_order)
            self._tags = [utils.format_tag(x) for x in sorted_order]

    def sort_rows(self, tags: Union[str, List[str]], key: Callable = None) -> None:
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
                supplied_category = utils.format_category(cur_tag)
                if supplied_category.lower() != self.category.lower():
                    raise ValueError(f"The category provided in your tag '{supplied_category}' does not match this "
                                     f"loop's category '{self.category}'.")

            renumber_tag = self.tag_index(cur_tag)

            # They didn't specify a valid tag
            if renumber_tag is None:
                # Perhaps they specified an integer to represent the tag?
                try:
                    renumber_tag = int(cur_tag)
                except ValueError:
                    raise ValueError(f"The sorting tag you provided '{cur_tag}' isn't in this loop!")

            sort_ordinals.append(renumber_tag)

        # Do the sort(s)
        for tag in sort_ordinals:
            # Going through each tag, first attempt to sort as integer.
            #  Then fallback to string sort.
            try:
                if key is None:
                    tmp_data = sorted(self.data, key=lambda _, pos=tag: float(_[pos]))
                else:
                    tmp_data = sorted(self.data, key=key)
            except ValueError:
                if key is None:
                    tmp_data = sorted(self.data, key=lambda _, pos=tag: _[pos])
                else:
                    tmp_data = sorted(self.data, key=key)
            self.data = tmp_data

    def tag_index(self, tag_name: str) -> Optional[int]:
        """ Helper method to do a case-insensitive check for the presence
        of a given tag in this loop. Returns the index of the tag if found
        and None if not found.

        This is useful if you need to get the index of a certain tag to
        iterate through the data and modify it."""

        try:
            lc_col = [x.lower() for x in self._tags]
            return lc_col.index(utils.format_tag(str(tag_name)).lower())
        except ValueError:
            return None

    def validate(self, validate_schema: bool = True, schema: 'Schema' = None,
                 validate_star: bool = True, category: str = None) -> List[str]:
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
            my_schema = utils.get_schema(schema)

            # Check the data
            for row_num, row in enumerate(self.data):
                for pos, datum in enumerate(row):
                    errors.extend(my_schema.val_type(f"{self.category}.{self._tags[pos]}", datum, category=category))

        if validate_star:
            # Check for wrong data size
            num_cols = len(self._tags)
            for row_num, row in enumerate(self.data):
                # Make sure the width matches
                if len(row) != num_cols:
                    errors.append(f"Loop '{self.category}' data width does not match it's tag width on "
                                  f"row '{row_num}'.")

        return errors
