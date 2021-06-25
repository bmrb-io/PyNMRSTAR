import json
import warnings
from csv import reader as csv_reader, writer as csv_writer
from io import StringIO
from typing import TextIO, BinaryIO, Union, List, Optional, Any, Dict, Iterable, Tuple

from pynmrstar import definitions, entry as entry_mod, loop as loop_mod, parser as parser_mod, utils
from pynmrstar._internal import _get_comments, _json_serialize, _interpret_file, get_clean_tag_list, write_to_file
from pynmrstar.exceptions import InvalidStateError
from pynmrstar.schema import Schema


class Saveframe(object):
    """A saveframe object. Create using the class methods, see below."""

    def __contains__(self, item: any) -> bool:
        """ Check if the saveframe contains a tag or a loop name."""

        # Prepare for processing
        if isinstance(item, (list, tuple)):
            to_process: List[Union[str, loop_mod.Loop]] = list(item)
        elif isinstance(item, (loop_mod.Loop, str)):
            to_process = [item]
        else:
            return False

        lc_tags = self._lc_tags
        loop_dict = self.loop_dict

        for item in to_process:
            if isinstance(item, loop_mod.Loop):
                if item not in self.loops:
                    return False
            elif isinstance(item, str):
                if item.startswith("_") and "." not in item:
                    if item.lower() not in loop_dict:
                        return False
                else:
                    if utils.format_tag(item).lower() not in lc_tags:
                        return False
            else:
                return False
        return True

    def __delitem__(self, item: Union[int, str, 'loop_mod.Loop']) -> None:
        """Remove the indicated tag or loop."""

        # If they specify the specific loop to delete, go ahead and delete it
        if isinstance(item, loop_mod.Loop):
            self.remove_loop(item)
        elif isinstance(item, int):
            try:
                self.remove_loop(self._loops[item])
            except IndexError:
                raise IndexError(f'Index out of range: no loop at index: {item}')
        elif isinstance(item, str):
            # Assume it is a loop category based on the proceeding underscore
            #  and lack of the '.' category and tag separator
            if item.startswith("_") and "." not in item:
                self.remove_loop(item)
            else:
                self.remove_tag(item)
        else:
            raise ValueError(f'Item of invalid type provided: {type(item)}')

    def __eq__(self, other) -> bool:
        """Returns True if this saveframe is equal to another saveframe,
        False if it is equal."""

        if not isinstance(other, Saveframe):
            return False

        return (self.name, self._category, self._tags, self._loops) == \
               (other.name, other._category, other._tags, other._loops)

    def __getitem__(self, item: Union[int, str]) -> Union[list, 'loop_mod.Loop']:
        """Get the indicated loop or tag."""

        if isinstance(item, int):
            try:
                return self._loops[item]
            except KeyError:
                raise KeyError(f"No loop with index '{item}'.")
        elif isinstance(item, str):
            # Assume it is a loop category based on the proceeding underscore
            #  and lack of the '.' category and tag separator
            if item.startswith("_") and "." not in item:
                try:
                    return self.loop_dict[item.lower()]
                except KeyError:
                    raise KeyError(f"No loop matching '{item}'.")
            else:
                results = self.get_tag(item)
                if not results:
                    raise KeyError(f"No tag matching '{item}'.")
                return results

    def __iter__(self) -> Iterable["loop_mod.Loop"]:
        """ Yields each of the loops contained within the saveframe. """

        return iter(self._loops)

    def __len__(self) -> int:
        """Return the number of loops in this saveframe."""

        return len(self._loops)

    def __lt__(self, other) -> bool:
        """Returns True if this saveframe sorts lower than the compared
        saveframe, false otherwise. The alphabetical ordering of the
        saveframe category is used to perform the comparison."""

        if not isinstance(other, Saveframe):
            return NotImplemented

        return self.tag_prefix < other.tag_prefix

    def __init__(self, **kwargs) -> None:
        """Don't use this directly. Use the class methods to construct:
           :py:meth:`Saveframe.from_scratch`, :py:meth:`Saveframe.from_string`,
           :py:meth:`Saveframe.from_template`, :py:meth:`Saveframe.from_file`,
           :py:meth:`Saveframe.from_json`"""

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate a Saveframe using this method. Instead use the class"
                             " methods: Saveframe.from_scratch(), Saveframe.from_string(), Saveframe.from_template(), "
                             "Saveframe.from_file(), and Saveframe.from_json().")

        # Initialize our local variables
        self._tags: List[Any] = []
        self._loops: List[loop_mod.Loop] = []
        self._name: str = ""
        self.source: str = "unknown"
        self._category: Optional[str] = None
        self.tag_prefix: Optional[str] = None

        star_buffer: StringIO = StringIO('')

        # Update our source if it provided
        if 'source' in kwargs:
            self.source = kwargs['source']

        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = f"from_file('{kwargs['file_name']}')"
        # Creating from template (schema)
        elif 'all_tags' in kwargs:
            schema_obj = utils.get_schema(kwargs['schema'])
            schema = schema_obj.schema
            self._category = kwargs['category']

            self._name = self._category
            if 'saveframe_name' in kwargs and kwargs['saveframe_name']:
                self._name = kwargs['saveframe_name']

            # Make sure it is a valid category
            if self._category not in [x["SFCategory"] for x in schema.values()]:
                raise ValueError(f"The saveframe category '{self._category}' was not found in the dictionary.")

            s = sorted(schema.values(), key=lambda _: float(_["Dictionary sequence"]))

            loops_added = []

            for item in s:
                if item["SFCategory"] == self._category:

                    # It is a tag in this saveframe
                    if item["Loopflag"] == "N":

                        ft = utils.format_tag(item["Tag"])
                        # Set the value for sf_category and sf_framecode
                        if ft == "Sf_category":
                            self.add_tag(item["Tag"], self._category)
                        elif ft == "Sf_framecode":
                            self.add_tag(item["Tag"], self.name)
                        # If the tag is the entry ID tag, set the entry ID
                        elif item["entryIdFlg"] == "Y":
                            self.add_tag(item["Tag"], kwargs['entry_id'])
                        else:
                            tag_value = None
                            if kwargs['default_values']:
                                if item['default value'] not in definitions.NULL_VALUES:
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
                        cat_formatted = utils.format_category(item["Tag"])
                        if cat_formatted not in loops_added:
                            loops_added.append(cat_formatted)
                            try:
                                self.add_loop(loop_mod.Loop.from_template(cat_formatted,
                                                                          all_tags=kwargs['all_tags'],
                                                                          schema=schema_obj))
                            except ValueError:
                                pass
            return

        elif 'saveframe_name' in kwargs:
            # If they are creating from scratch, just get the saveframe name
            self._name = kwargs['saveframe_name']
            if 'tag_prefix' in kwargs:
                self.tag_prefix = utils.format_category(kwargs['tag_prefix'])
            return

        # If we are reading from a CSV file, go ahead and parse it
        if 'csv' in kwargs and kwargs['csv']:
            csv_reader_object = csv_reader(star_buffer)
            tags = next(csv_reader_object)
            values = next(csv_reader_object)
            if len(tags) != len(values):
                raise ValueError("Your CSV data is invalid. The header length does not match the data length.")
            for ordinal in range(0, len(tags)):
                self.add_tag(tags[ordinal], values[ordinal])
            return

        tmp_entry = entry_mod.Entry.from_scratch(0)

        # Load the BMRB entry from the file
        star_buffer = StringIO("data_1 " + star_buffer.read())
        parser = parser_mod.Parser(entry_to_parse_into=tmp_entry)
        parser.parse(star_buffer.read(), source=self.source, convert_data_types=kwargs.get('convert_data_types', False))

        # Copy the first parsed saveframe into ourself
        if len(tmp_entry.frame_list) > 1:
            raise ValueError("You attempted to parse one saveframe but the source you provided had more than one "
                             "saveframe. Please either parse all saveframes as an entry or only parse one saveframe. "
                             "Saveframes detected: " + str(tmp_entry.frame_list))
        self._tags = tmp_entry[0].tags
        self._loops = tmp_entry[0].loops
        self._name = tmp_entry[0].name
        self._category = tmp_entry[0].category
        self.tag_prefix = tmp_entry[0].tag_prefix

    @property
    def _lc_tags(self) -> Dict[str, int]:
        return {_[1][0].lower(): _[0] for _ in enumerate(self._tags)}

    @property
    def category(self) -> str:
        return self._category

    @category.setter
    def category(self, category):
        """ Updates the saveframe category. """

        if category in definitions.NULL_VALUES:
            raise ValueError("Cannot set the saveframe category to a null-equivalent value.")

        # Update the sf_category tag too
        lc_tags = self._lc_tags
        if 'sf_category' in lc_tags:
            self.tags[lc_tags['sf_category']] = category
        self._category = category

    @property
    def empty(self) -> bool:
        """ Check if the saveframe has no data. Ignore the structural tags."""

        for tag in self._tags:
            tag_lower = tag[0].lower()
            if tag_lower not in ['sf_category', 'sf_framecode', 'id', 'entry_id', 'nmr_star_version',
                                 'original_nmr_star_version']:
                if tag[1] not in definitions.NULL_VALUES:
                    return False

        for loop in self._loops:
            if not loop.empty:
                return False

        return True

    @property
    def loops(self) -> List['loop_mod.Loop']:
        return self._loops

    @property
    def loop_dict(self) -> Dict[str, 'loop_mod.Loop']:
        """Returns a hash of loop category -> loop."""

        res = {}
        for each_loop in self._loops:
            if each_loop.category is not None:
                res[each_loop.category.lower()] = each_loop
        return res

    @property
    def name(self) -> Any:
        """ Returns the name of the saveframe."""

        return self._name

    @name.setter
    def name(self, name):
        """ Updates the saveframe name. """

        for char in str(name):
            if char in utils.definitions.WHITESPACE:
                raise ValueError("Saveframe names can not contain whitespace characters.")
        if name in definitions.NULL_VALUES:
            raise ValueError("Cannot set the saveframe name to a null-equivalent value.")

        # Update the sf_framecode tag too
        lc_tags = self._lc_tags
        if 'sf_framecode' in lc_tags:
            self.tags[lc_tags['sf_framecode']][1] = name
        self._name = name

    @property
    def tags(self) -> List[List[any]]:
        return self._tags

    @property
    def tag_dict(self) -> Dict[str, str]:
        """Returns a hash of (tag name).lower() -> tag value."""

        return {x[0].lower(): x[1] for x in self._tags}

    @classmethod
    def from_scratch(cls, sf_name: str, tag_prefix: str = None, source: str = "from_scratch()"):
        """Create an empty saveframe that you can programmatically add
        to. You may also pass the tag prefix as the second argument. If
        you do not pass the tag prefix it will be set the first time you
        add a tag."""

        return cls(saveframe_name=sf_name, tag_prefix=tag_prefix, source=source)

    @classmethod
    def from_file(cls, the_file: Union[str, TextIO, BinaryIO], csv: bool = False, convert_data_types: bool = False):
        """Create a saveframe by loading in a file. Specify csv=True is
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
        """Create a saveframe from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ["name", "tag_prefix", "tags", "loops"]:
            if check not in json_dict:
                raise ValueError(f"The JSON you provide must be a hash and must contain the key '{check}' - even if "
                                 "the key points to None.")

        # Create a saveframe from scratch and populate it
        ret = Saveframe.from_scratch(json_dict['name'])
        ret.tag_prefix = json_dict['tag_prefix']
        ret._category = json_dict.get('category', None)
        ret._tags = json_dict['tags']
        ret._loops = [loop_mod.Loop.from_json(x) for x in json_dict['loops']]
        ret.source = "from_json()"

        # Return the new loop
        return ret

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
    def from_template(cls, category: str, name: str = None, entry_id: Union[str, int] = None, all_tags: bool = False,
                      default_values: bool = False, schema: Schema = None):
        """ Create a saveframe that has all of the tags and loops from the
        schema present. No values will be assigned. Specify the category
        when calling this method. Optionally also provide the name of the
        saveframe as the 'name' argument.

        The optional argument 'all_tags' forces all tags to be included
        rather than just the mandatory tags.

        The optional argument 'default_values' will insert the default
        values from the schema."""

        schema = utils.get_schema(schema)
        return cls(category=category, saveframe_name=name, entry_id=entry_id,
                   all_tags=all_tags, default_values=default_values, schema=schema,
                   source=f"from_template({schema.version})")

    def __repr__(self) -> str:
        """Returns a description of the saveframe."""

        return f"<pynmrstar.Saveframe '{self.name}'>"

    def __setitem__(self, key: Union[str, int], item: Union[str, 'loop_mod.Loop']) -> None:
        """Set the indicated loop or tag."""

        # It's a loop
        if isinstance(item, loop_mod.Loop):
            try:
                integer = int(str(key))
                self._loops[integer] = item
            except ValueError:
                if key.lower() in self.loop_dict:
                    for pos, tmp_loop in enumerate(self._loops):
                        if tmp_loop.category.lower() == key.lower():
                            self._loops[pos] = item
                else:
                    raise KeyError(f"Loop with category '{key}' does not exist and therefore cannot be written to. Use "
                                   "add_loop instead.")
        else:
            # If the tag already exists, set its value
            self.add_tag(key, item, update=True)

    def __str__(self,
                first_in_category: bool = True,
                skip_empty_loops: bool = False,
                skip_empty_tags: bool = False,
                show_comments: bool = True) -> str:
        """Returns the saveframe in STAR format as a string. Please use :py:meth:`Saveframe.format`
        when you want to pass arguments."""

        if self.tag_prefix is None:
            raise InvalidStateError(f"The tag prefix was never set! Error in saveframe named '{self.name}'.")

        return_chunks = []

        # Insert the comment if not disabled
        if show_comments:
            if self._category in _get_comments():
                this_comment = _get_comments()[self._category]
                if first_in_category or this_comment['every_flag']:
                    return_chunks.append(_get_comments()[self._category]['comment'])

        # Print the saveframe
        return_chunks.append(f"save_{self.name}\n")

        if len(self._tags) > 0:
            width = max([len(self.tag_prefix + "." + x[0]) for x in self._tags])
            pstring = "   %%-%ds  %%s\n" % width
            mstring = "   %%-%ds\n;\n%%s;\n" % width

            # Print the tags
            for each_tag in self._tags:
                if skip_empty_tags and each_tag[1] in definitions.NULL_VALUES:
                    continue
                try:
                    clean_tag = utils.quote_value(each_tag[1])
                except ValueError:
                    raise InvalidStateError('Cannot generate NMR-STAR for entry, as empty strings are not valid tag'
                                            ' values in NMR-STAR. Please either replace the empty strings with None '
                                            'objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[\'\'] = None. '
                                            f'Saveframe: {self.name} Tag: {each_tag[0]}')

                formatted_tag = self.tag_prefix + "." + each_tag[0]
                if "\n" in clean_tag:
                    return_chunks.append(mstring % (formatted_tag, clean_tag))
                else:
                    return_chunks.append(pstring % (formatted_tag, clean_tag))

        # Print any loops
        for each_loop in self._loops:
            return_chunks.append(each_loop.format(skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags))

        # Close the saveframe
        return "".join(return_chunks) + "\nsave_\n"

    def add_loop(self, loop_to_add: 'loop_mod.Loop') -> None:
        """Add a loop to the saveframe loops."""

        if loop_to_add.category in self.loop_dict or str(loop_to_add.category).lower() in self.loop_dict:
            if loop_to_add.category is None:
                raise ValueError("You cannot have two loops with the same category in one saveframe. You are getting "
                                 "this error because you haven't yet set your loop categories.")
            else:
                raise ValueError("You cannot have two loops with the same category in one saveframe. Category: "
                                 f"'{loop_to_add.category}'.")

        self._loops.append(loop_to_add)

    def add_tag(self, name: str, value: Any, update: bool = False, convert_data_types: bool = False) -> None:
        """Add a tag to the tag list. Does a bit of validation and
        parsing.

        Set update to True to update a tag if it exists rather
        than raise an exception.

        Set convert_data_types to True to convert the tag value from str to
        whatever type the tag is as defined in the schema."""

        if not isinstance(name, str):
            raise ValueError('Tag names must be strings.')

        if "." in name:
            if name[0] != ".":
                prefix = utils.format_category(name)
                if self.tag_prefix is None:
                    self.tag_prefix = prefix
                elif self.tag_prefix != prefix:
                    raise ValueError(
                        "One saveframe cannot have tags with different categories (or tags that don't "
                        f"match the set category)! Saveframe tag prefix is '{self.tag_prefix}' but the added tag, "
                        f"'{name}' has prefix '{prefix}'.")
                name = name[name.index(".") + 1:]
            else:
                name = name[1:]

        if name in definitions.NULL_VALUES:
            raise ValueError(f"Cannot use a null-equivalent value as a tag name. Invalid tag name: '{name}'")
        if "." in name:
            raise ValueError(f"There cannot be more than one '.' in a tag name. Invalid tag name: '{name}'")
        for char in name:
            if char in utils.definitions.WHITESPACE:
                raise ValueError(f"Tag names can not contain whitespace characters. Invalid tag name: '{name}'")

        # No duplicate tags
        if self.get_tag(name):
            if not update:
                raise ValueError(f"There is already a tag with the name '{name}' in the saveframe '{self.name}."
                                 f" Set update=True if you want to override its value.")
            else:
                tag_name_lower = name.lower()
                if tag_name_lower == "sf_category":
                    self._category = value
                if tag_name_lower == "sf_framecode":
                    if value in definitions.NULL_VALUES:
                        raise ValueError("Cannot set the saveframe name tag (Sf_framecode) to a null-equivalent "
                                         f"value. Invalid value: '{name}'")
                    self._name = value
                self.get_tag(name, whole_tag=True)[0][1] = value
                return

        # See if we need to convert the data type
        if convert_data_types:
            new_tag = [name, utils.get_schema().convert_tag(self.tag_prefix + "." + name, value)]
        else:
            new_tag = [name, value]

        # Set the category if the tag we are loading is the category
        tag_name_lower = name.lower()
        if tag_name_lower == "sf_category":
            self._category = value
        if tag_name_lower == "sf_framecode":
            if not self._name:
                self._name = value
            elif self._name != value:
                raise ValueError('The Sf_framecode tag cannot be different from the saveframe name. Error '
                                 f'occurred in tag {self.tag_prefix}.Sf_framecode with value {value} which '
                                 f'conflicts with with the saveframe name {self._name}.')
        self._tags.append(new_tag)

    def add_tags(self, tag_list: list, update: bool = False) -> None:
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
                raise ValueError(f"You provided an invalid tag/value to add: '{tag_pair}'.")

    def add_missing_tags(self, schema: 'Schema' = None, all_tags: bool = False,
                         recursive: bool = True) -> None:
        """ Automatically adds any missing tags (according to the schema)
        and sorts the tags.

        Set recursive to False to only operate on the tags in this saveframe,
        and not those in child loops."""

        if not self.tag_prefix:
            raise InvalidStateError("You must first specify the tag prefix of this Saveframe before calling this "
                                    "method. You can do this by adding a fully qualified tag "
                                    "(i.e. _Entry.Sf_framecode), by specifying the tag_prefix when calling "
                                    "from_scratch() or by modifying the .tag_prefix attribute.")

        schema = utils.get_schema(schema)
        tag_prefix: str = self.tag_prefix.lower() + '.'

        for item in schema.schema_order:

            # The tag is in the loop
            if item.lower().startswith(tag_prefix):

                try:
                    # Unconditional add
                    if all_tags:
                        self.add_tag(item, None)
                    # Conditional add
                    else:
                        if schema.schema[item.lower()]["public"] != "I":
                            self.add_tag(item, None)
                except ValueError:
                    pass

        if recursive:
            for loop in self._loops:
                try:
                    loop.add_missing_tags(schema=schema, all_tags=all_tags)
                except ValueError:
                    pass

        self.sort_tags()

    def compare(self, other) -> List[str]:
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
        elif not isinstance(other, Saveframe):
            return ['Other object is not of class Saveframe.']

        # We need to do this in case of an extra "\n" on the end of one tag
        if str(other) == str(self):
            return []

        # Do STAR comparison
        try:
            if str(self.name) != str(other.name):
                # No point comparing apples to oranges. If the tags are
                #  this different just return
                diffs.append(f"\tSaveframe names do not match: '{self.name}' vs '{other.name}'.")
                return diffs

            if str(self.tag_prefix) != str(other.tag_prefix):
                # No point comparing apples to oranges. If the tags are
                #  this different just return
                diffs.append(f"\tTag prefix does not match: '{self.tag_prefix}' vs '{other.tag_prefix}'.")
                return diffs

            if len(self._tags) < len(other.tags):
                diffs.append(f"\tNumber of tags does not match: '{len(self._tags)}' vs '{len(other.tags)}'. The "
                             f"compared entry has at least one tag this entry does not.")

            for tag in self._tags:
                other_tag = other.get_tag(tag[0])

                if not other_tag:
                    diffs.append(f"\tNo tag with name '{self.tag_prefix}.{tag[0]}' in compared entry.")
                    continue

                # Compare the string version of the tags in case there are
                #  non-string types. Use the conversion dict to get to str
                if (str(definitions.STR_CONVERSION_DICT.get(tag[1], tag[1])) !=
                        str(definitions.STR_CONVERSION_DICT.get(other_tag[0], other_tag[0]))):
                    newline_stripped_tag = str(tag[1]).replace("\n", "\\n")
                    newline_stripped_other_tag = str(other_tag[0]).replace("\n", "\\n")
                    diffs.append(f"\tMismatched tag values for tag '{self.tag_prefix}.{tag[0]}': '"
                                 f"{newline_stripped_tag}' vs '{newline_stripped_other_tag}'.")

            if len(self._loops) != len(other.loops):
                diffs.append(f"\tNumber of children loops does not match: '{len(self._loops)}' vs "
                             f"'{len(other.loops)}'.")

            compare_loop_dict = other.loop_dict
            for each_loop in self._loops:
                if each_loop.category.lower() in compare_loop_dict:
                    compare = each_loop.compare(compare_loop_dict[each_loop.category.lower()])
                    if len(compare) > 0:
                        diffs.append(f"\tLoops do not match: '{each_loop.category}'.")
                        diffs.extend(compare)
                else:
                    diffs.append(f"\tNo loop with category '{each_loop.category}' in other entry.")

        except AttributeError as err:
            diffs.append(f"\tAn exception occurred while comparing: '{err}'.")

        return diffs

    def delete_tag(self, tag: str) -> None:
        """ Deprecated, please see :py:meth:`pynmrstar.Saveframe.remove_tag`. """

        warnings.warn('This method name has been renamed to remove_tag. Please update your code.', DeprecationWarning)
        return self.remove_tag(tag)

    def get_data_as_csv(self, header: bool = True, show_category: bool = True) -> str:
        """Return the data contained in the loops, properly CSVd, as a
        string. Set header to False omit the header. Set show_category
        to False to omit the loop category from the headers."""

        csv_buffer = StringIO()
        csv_writer_object = csv_writer(csv_buffer)

        if header:
            if show_category:
                csv_writer_object.writerow([str(self.tag_prefix) + "." + str(x[0]) for x in self._tags])
            else:
                csv_writer_object.writerow([str(x[0]) for x in self._tags])

        data = []
        for each_tag in self._tags:
            data.append(each_tag[1])

        csv_writer_object.writerow(data)

        csv_buffer.seek(0)
        return csv_buffer.read().replace('\r\n', '\n')

    def format(self, skip_empty_loops: bool = True, skip_empty_tags: bool = False, show_comments: bool = True) -> str:
        """ The same as calling str(Saveframe), except that you can pass options
        to customize how the saveframe is printed.

        skip_empty_loops will omit printing loops with no tags at all. (A loop with null tags is not "empty".)
        skip_empty_tags will omit tags in the saveframe and child loops which have no non-null values.
        show_comments will show the standard comments before a saveframe."""

        return self.__str__(skip_empty_loops=skip_empty_loops, show_comments=show_comments,
                            skip_empty_tags=skip_empty_tags)

    def get_json(self, serialize: bool = True) -> Union[dict, str]:
        """ Returns the saveframe in JSON format. If serialize is set to
        False a dictionary representation of the saveframe that is
        serializeable is returned."""

        saveframe_data = {
            "name": self.name,
            "category": self._category,
            "tag_prefix": self.tag_prefix,
            "tags": [[x[0], x[1]] for x in self._tags],
            "loops": [x.get_json(serialize=False) for x in self._loops]
        }

        if serialize:
            return json.dumps(saveframe_data, default=_json_serialize)
        else:
            return saveframe_data

    def get_loop(self, name: str) -> 'loop_mod.Loop':
        """Return a loop based on the loop name (category)."""

        name = utils.format_category(name).lower()
        for each_loop in self._loops:
            if str(each_loop.category).lower() == name:
                return each_loop
        raise KeyError(f"No loop with category '{name}'.")

    def get_loop_by_category(self, name: str) -> 'loop_mod.Loop':
        """ Deprecated. Please use :py:meth:`pynmrstar.Saveframe.get_loop` instead. """

        warnings.warn('Deprecated. Please use get_loop() instead.', DeprecationWarning)
        return self.get_loop(name)

    def get_tag(self, query: str, whole_tag: bool = False) -> list:
        """Allows fetching the value of a tag by tag name. Returns
        a list of all matching tag values.

        Specify whole_tag=True and the [tag_name, tag_value] pair will be
        returned instead of just the value"""

        results = []

        # Make sure this is the correct saveframe if they specify a tag
        #  prefix
        if "." in query:
            tag_prefix = utils.format_category(query)
        else:
            tag_prefix = self.tag_prefix

        # Check the loops
        for each_loop in self._loops:
            if ((each_loop.category is not None and tag_prefix is not None and
                 each_loop.category.lower() == tag_prefix.lower())):
                results.extend(each_loop.get_tag(query, whole_tag=whole_tag))

        # Check our tags
        query = utils.format_tag(query).lower()
        if tag_prefix is not None and tag_prefix.lower() == self.tag_prefix.lower():
            for tag in self._tags:
                if query == tag[0].lower():
                    if whole_tag:
                        results.append(tag)
                    else:
                        results.append(tag[1])

        return results

    def loop_iterator(self) -> Iterable['loop_mod.Loop']:
        """Returns an iterator for saveframe loops."""

        return iter(self._loops)

    def print_tree(self) -> None:
        """Prints a summary, tree style, of the loops in the saveframe."""

        print(repr(self))
        for pos, each_loop in enumerate(self):
            print(f"\t[{pos}] {repr(each_loop)}")

    def remove_loop(self, item: Union[str, List[str], Tuple[str],
                                      'loop_mod.Loop', List['loop_mod.Loop'], Tuple['loop_mod.Loop']]) -> None:
        """ Removes one or more loops from the saveframe. You can remove loops either by passing the loop object itself,
        the loop category (as a string), or a list or tuple of either."""

        parsed_list: list
        if isinstance(item, tuple):
            parsed_list = list(item)
        elif isinstance(item, list):
            parsed_list = item
        elif isinstance(item, (str, loop_mod.Loop)):
            parsed_list = [item]
        else:
            raise ValueError('The item you provided was not one or more loop objects or loop categories (strings). '
                             f'Item type: {type(item)}')

        loop_names = self.loop_dict

        loops_to_remove = []
        for loop in parsed_list:
            if isinstance(loop, str):
                formatted_loop = loop.lower()
                if not formatted_loop.startswith('_'):
                    formatted_loop = f"_{loop}"
                if formatted_loop not in loop_names:
                    raise ValueError('At least one loop specified to remove was not found in this saveframe. First '
                                     f'missing loop: {loop}')
                loops_to_remove.append(loop_names[formatted_loop])
            elif isinstance(loop, loop_mod.Loop):
                if loop not in self._loops:
                    raise ValueError('At least one loop specified to remove was not found in this saveframe. First '
                                     f'missing loop: {loop}')
                loops_to_remove.append(loop)
            else:
                raise ValueError('One of the items you provided was not a loop object or loop category (string). '
                                 f'Item: {repr(loop)}')

        self._loops = [_ for _ in self._loops if _ not in loops_to_remove]

    def remove_tag(self, item: Union[str, List[str], Tuple[str]]) -> None:
        """Removes one or more tags from the saveframe based on tag name(s).
        Provide either a tag name or a list or tuple containing tag names. """

        tags = get_clean_tag_list(item)
        lc_tags = self._lc_tags

        for item in tags:
            if item["formatted"] not in lc_tags:
                raise KeyError(f"There is no tag with name '{item['original']}' to remove.")

        # Create a new list stripping out all of the deleted tags
        positions = [lc_tags[_["formatted"]] for _ in tags]
        self._tags = [_[1] for _ in enumerate(self._tags) if _[0] not in positions]

    def set_tag_prefix(self, tag_prefix: str) -> None:
        """Set the tag prefix for this saveframe."""

        self.tag_prefix = utils.format_category(tag_prefix)

    def sort_tags(self, schema: Schema = None) -> None:
        """ Sort the tags so they are in the same order as a BMRB
        schema. Will automatically use the standard schema if none
        is provided."""

        schema = utils.get_schema(schema)

        def sort_key(x) -> int:
            return schema.tag_key(self.tag_prefix + "." + x[0])

        self._tags.sort(key=sort_key)

    def tag_iterator(self) -> Iterable[Tuple[str, str]]:
        """Returns an iterator for saveframe tags."""
        # :py:attr:`pynmrstar.Saveframe.tags`
        return iter(self._tags)

    def validate(self, validate_schema: bool = True, schema: Schema = None, validate_star: bool = True):
        """Validate a saveframe in a variety of ways. Returns a list of
        errors found. 0-length list indicates no errors found. By
        default all validation modes are enabled.

        validate_schema - Determines if the entry is validated against
        the NMR-STAR schema. You can pass your own custom schema if desired,
        otherwise the schema will be fetched from the BMRB servers.

        validate_star - Determines if the STAR syntax checks are ran."""

        errors = []

        my_category = self._category
        if not my_category:
            errors.append(f"Cannot properly validate saveframe: '{self.name}'. No saveframe category defined.")
            my_category = None

        if validate_schema:
            # Get the default schema if we are not passed a schema
            my_schema = utils.get_schema(schema)

            for tag in self._tags:
                formatted_tag = self.tag_prefix + "." + tag[0]
                cur_errors = my_schema.val_type(formatted_tag, tag[1], category=my_category)
                errors.extend(cur_errors)

        # Check the loops for errors
        for each_loop in self._loops:
            errors.extend(each_loop.validate(validate_schema=validate_schema, schema=schema,
                                             validate_star=validate_star, category=my_category))

        return errors

    def write_to_file(self,
                      file_name: str,
                      format_: str = "nmrstar",
                      show_comments: bool = True,
                      skip_empty_loops: bool = False,
                      skip_empty_tags: bool = False) -> None:
        """ Writes the saveframe to the specified file in NMR-STAR format.

        Optionally specify:
        show_comments=False to disable the comments that are by default inserted. Ignored when writing json.
        skip_empty_loops=False to force printing loops with no tags at all (loops with null tags are still printed)
        skip_empty_tags=True will omit tags in the saveframes and loops which have no non-null values.
        format_=json to write to the file in JSON format."""

        write_to_file(self, file_name=file_name, format_=format_, show_comments=show_comments,
                      skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags)
