import hashlib
import json
import logging
import warnings
from io import StringIO
from typing import TextIO, BinaryIO, Union, List, Optional, Dict, Any, Tuple

from pynmrstar import definitions, utils, loop as loop_mod, parser as parser_mod, saveframe as saveframe_mod
from pynmrstar._internal import _json_serialize, _interpret_file, _get_entry_from_database, write_to_file
from pynmrstar.exceptions import InvalidStateError
from pynmrstar.schema import Schema

logger = logging.getLogger('pynmrstar')


class Entry(object):
    """An object oriented representation of a BMRB entry. You can initialize this
    object several ways; (e.g. from a file, from the official database,
    from scratch) see the class methods below. """

    def __contains__(self, item: Any):
        """ Check if the given item is present in the entry. """

        # Prepare for processing
        if isinstance(item, (list, tuple)):
            to_process: List[Union[str, saveframe_mod.Saveframe, loop_mod.Loop]] = list(item)
        elif isinstance(item, (loop_mod.Loop, saveframe_mod.Saveframe, str)):
            to_process = [item]
        else:
            return False

        for item in to_process:
            if isinstance(item, saveframe_mod.Saveframe):
                if item not in self._frame_list:
                    return False
            elif isinstance(item, (loop_mod.Loop, str)):
                found = False
                for saveframe in self._frame_list:
                    if item in saveframe:
                        found = True
                        break
                if not found:
                    return False
            else:
                return False
        return True

    def __delitem__(self, item: Union['saveframe_mod.Saveframe', int, str]) -> None:
        """Remove the indicated saveframe."""

        if isinstance(item, int):
            try:
                del self._frame_list[item]
            except IndexError:
                raise IndexError(f'Index out of range: no saveframe at index: {item}')
        else:
            self.remove_saveframe(item)

    def __eq__(self, other) -> bool:
        """Returns True if this entry is equal to another entry, false
        if it is not equal."""

        if not isinstance(other, Entry):
            return False

        return (self.entry_id, self._frame_list) == (other.entry_id, other._frame_list)

    def __getitem__(self, item: Union[int, str]) -> 'saveframe_mod.Saveframe':
        """Get the indicated saveframe."""

        try:
            return self._frame_list[item]
        except TypeError:
            return self.get_saveframe_by_name(item)

    def __init__(self, **kwargs) -> None:
        """ You should not directly instantiate an Entry using this method.
            Instead use the class methods:

            :py:meth:`Entry.from_database`, :py:meth:`Entry.from_file`,
            :py:meth:`Entry.from_string`, :py:meth:`Entry.from_scratch`,
            :py:meth:`Entry.from_json`, and :py:meth:`Entry.from_template`"""

        # Default initializations
        self._entry_id: Union[str, int] = 0
        self._frame_list: List[saveframe_mod.Saveframe] = []
        self.source: Optional[str] = None

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate an Entry using this method. Instead use the "
                             "class methods: Entry.from_database(), Entry.from_file(), Entry.from_string(), "
                             "Entry.from_scratch(), and Entry.from_json().")

        if 'the_string' in kwargs:
            # Parse from a string by wrapping it in StringIO
            star_buffer: StringIO = StringIO(kwargs['the_string'])
            self.source = "from_string()"
        elif 'file_name' in kwargs:
            star_buffer = _interpret_file(kwargs['file_name'])
            self.source = f"from_file('{kwargs['file_name']}')"
        # Creating from template (schema)
        elif 'all_tags' in kwargs:
            self._entry_id = kwargs['entry_id']

            saveframe_categories: dict = {}
            schema = utils.get_schema(kwargs['schema'])
            schema_obj = schema.schema
            for tag in [schema_obj[x.lower()] for x in schema.schema_order]:
                category = tag['SFCategory']
                if category not in saveframe_categories:
                    saveframe_categories[category] = True
                    templated_saveframe = saveframe_mod.Saveframe.from_template(category, category + "_1",
                                                                                entry_id=self._entry_id,
                                                                                all_tags=kwargs['all_tags'],
                                                                                default_values=kwargs['default_values'],
                                                                                schema=schema)
                    self._frame_list.append(templated_saveframe)
            entry_saveframe = self.get_saveframes_by_category('entry_information')[0]
            entry_saveframe['NMR_STAR_version'] = schema.version
            entry_saveframe['Original_NMR_STAR_version'] = schema.version
            return
        else:
            # Initialize a blank entry
            self._entry_id = kwargs['entry_id']
            self.source = "from_scratch()"
            return

        # Load the BMRB entry from the file
        parser: parser_mod.Parser = parser_mod.Parser(entry_to_parse_into=self)
        parser.parse(star_buffer.read(), source=self.source, convert_data_types=kwargs.get('convert_data_types', False),
                     raise_parse_warnings=kwargs.get('raise_parse_warnings', False))

    def __iter__(self) -> saveframe_mod.Saveframe:
        """ Yields each of the saveframes contained within the entry. """

        for saveframe in self._frame_list:
            yield saveframe

    def __len__(self) -> int:
        """ Returns the number of saveframes in the entry."""

        return len(self._frame_list)

    def __repr__(self) -> str:
        """Returns a description of the entry."""

        return f"<pynmrstar.Entry '{self._entry_id}' {self.source}>"

    def __setitem__(self, key: Union[int, str], item: 'saveframe_mod.Saveframe') -> None:
        """Set the indicated saveframe."""

        # It is a saveframe
        if isinstance(item, saveframe_mod.Saveframe):
            # Add by ordinal
            if isinstance(key, int):
                self._frame_list[key] = item

            # TODO: Consider stripping this behavior out - it isn't clear it is useful
            else:
                # Add by key
                contains_frame: bool = False
                for pos, frame in enumerate(self._frame_list):
                    if frame.name == key:
                        if contains_frame:
                            raise ValueError(f"Cannot replace the saveframe with the name '{frame.name} "
                                             f"because multiple saveframes in the entry have the same name. "
                                             f'This library does not allow that normally, as it is '
                                             f'invalid NMR-STAR. Did you manually edit the Entry.frame_list '
                                             f'object? Please use the Entry.add_saveframe() method instead to '
                                             f'add new saveframes.')
                        self._frame_list[pos] = item
                        contains_frame = True

                if not contains_frame:
                    raise ValueError(f"Saveframe with name '{key}' does not exist and therefore cannot be "
                                     f"written to. Use the add_saveframe() method to add new saveframes.")
        else:
            raise ValueError("You can only assign a saveframe to an entry splice. You attempted to assign: "
                             f"'{repr(item)}'")

    def __str__(self, skip_empty_loops: bool = False, skip_empty_tags: bool = False, show_comments: bool = True) -> str:
        """Returns the entire entry in STAR format as a string."""

        sf_strings = []
        seen_saveframes = {}
        for saveframe_obj in self:
            if saveframe_obj.category in seen_saveframes:
                sf_strings.append(saveframe_obj.format(skip_empty_loops=skip_empty_loops,
                                                       skip_empty_tags=skip_empty_tags, show_comments=False))
            else:
                sf_strings.append(saveframe_obj.format(skip_empty_loops=skip_empty_loops,
                                                       skip_empty_tags=skip_empty_tags, show_comments=show_comments))
                seen_saveframes[saveframe_obj.category] = True

        return f"data_{self.entry_id}\n\n" + "\n".join(sf_strings)

    @property
    def category_list(self) -> List[str]:
        """ Returns a list of the unique categories present in the entry. """

        category_list = []
        for saveframe in self._frame_list:
            category = saveframe.category
            if category and category not in category_list:
                category_list.append(category)
        return list(category_list)

    @property
    def empty(self) -> bool:
        """ Check if the entry has no data. Ignore the structural tags."""

        for saveframe in self._frame_list:
            if not saveframe.empty:
                return False

        return True

    @property
    def entry_id(self) -> Union[str, int]:
        """ When read, fetches the entry ID.

        When set, updates the entry ID for the Entry, and updates all the tags which
        are foreign keys of the Entry_ID. (For example, Entry.ID and
        Citation.Entry_ID will be updated, if present.)
        """
        return self._entry_id

    @entry_id.setter
    def entry_id(self, value: Union[str, int]) -> None:
        self._entry_id = value

        schema = utils.get_schema()
        for saveframe in self._frame_list:
            for tag in saveframe.tags:
                fqtn = (saveframe.tag_prefix + "." + tag[0]).lower()

                try:
                    if schema.schema[fqtn]['entryIdFlg'] == 'Y':
                        tag[1] = self._entry_id
                except KeyError:
                    pass

            for loop in saveframe.loops:
                for tag in loop.tags:
                    fqtn = (loop.category + "." + tag).lower()
                    try:
                        if schema.schema[fqtn]['entryIdFlg'] == 'Y':
                            loop[tag] = [self._entry_id] * len(loop[tag])
                    except KeyError:
                        pass

    @property
    def frame_dict(self) -> Dict[str, 'saveframe_mod.Saveframe']:
        """Returns a dictionary of saveframe name -> saveframe object mappings."""

        fast_dict = dict((frame.name, frame) for frame in self._frame_list)

        # If there are no duplicates then continue
        if len(fast_dict) == len(self._frame_list):
            return fast_dict

        # Figure out where the duplicate is
        frame_dict = {}

        for frame in self._frame_list:
            if frame.name in frame_dict:
                raise InvalidStateError("The entry has multiple saveframes with the same name. That is not allowed in "
                                        "the NMR-STAR format. Please remove or rename one. Duplicate name: "
                                        f"'{frame.name}'. Furthermore, please use Entry.add_saveframe() and "
                                        f"Entry.remove_saveframe() rather than manually editing the Entry.frame_list "
                                        f"list, which will prevent this state from existing in the future.")
            frame_dict[frame.name] = frame

        return frame_dict

    @property
    def frame_list(self) -> List['saveframe_mod.Saveframe']:
        return self._frame_list

    @classmethod
    def from_database(cls, entry_num: Union[str, int], convert_data_types: bool = False):
        """Create an entry corresponding to the most up to date entry on
        the public BMRB server. (Requires ability to initiate outbound
        HTTP connections.)

        Setting convert_data_types to True will automatically convert
        the data loaded from the file into the corresponding python type as
        determined by loading the standard BMRB schema. This would mean that
        all floats will be represented as decimal.Decimal objects, all integers
        will be python int objects, strings and vars will remain strings, and
        dates will become datetime.date objects. When printing str() is called
        on all objects. Other that converting uppercase "E"s in scientific
        notation floats to lowercase "e"s this should not cause any change in
        the way re-printed NMR-STAR objects are displayed."""

        return _get_entry_from_database(entry_num, convert_data_types=convert_data_types)

    @classmethod
    def from_file(cls, the_file: Union[str, TextIO, BinaryIO], convert_data_types: bool = False,
                  raise_parse_warnings: bool = False):
        """Create an entry by loading in a file. If the_file starts with
        http://, https://, or ftp:// then we will use those protocols to
        attempt to open the file.
        
        Setting convert_data_types to True will automatically convert
        the data loaded from the file into the corresponding python type as
        determined by loading the standard BMRB schema. This would mean that
        all floats will be represented as decimal.Decimal objects, all integers
        will be python int objects, strings and vars will remain strings, and
        dates will become datetime.date objects. When printing str() is called
        on all objects. Other that converting uppercase "E"s in scientific
        notation floats to lowercase "e"s this should not cause any change in
        the way re-printed NMR-STAR objects are displayed.

        Setting raise_parse_warnings to True will result in the raising of a
        ParsingError rather than logging a warning when non-valid (but
        ignorable) issues are found. """

        return cls(file_name=the_file, convert_data_types=convert_data_types,
                   raise_parse_warnings=raise_parse_warnings)

    @classmethod
    def from_json(cls, json_dict: Union[dict, str]):
        """Create an entry from JSON (serialized or unserialized JSON)."""

        # If they provided a string, try to load it using JSON
        if not isinstance(json_dict, dict):
            try:
                json_dict = json.loads(json_dict)
            except (TypeError, ValueError):
                raise ValueError("The JSON you provided was neither a Python dictionary nor a JSON string.")

        # Make sure it has the correct keys
        if "saveframes" not in json_dict:
            raise ValueError("The JSON you provide must be a hash and must contain the key 'saveframes' - even if the "
                             "key points to 'None'.")
        if "entry_id" not in json_dict and "bmrb_id" not in json_dict:
            raise ValueError("The JSON you provide must be a hash and must contain the key 'entry_id' - even if the"
                             " key points to 'None'.")
        # Until the migration is complete, 'bmrb_id' is a synonym for
        #  'entry_id'
        if 'entry_id' not in json_dict:
            json_dict['entry_id'] = json_dict['bmrb_id']

        # Create an entry from scratch and populate it
        ret = Entry.from_scratch(json_dict['entry_id'])
        ret._frame_list = [saveframe_mod.Saveframe.from_json(x) for x in json_dict['saveframes']]
        ret.source = "from_json()"

        # Return the new loop
        return ret

    @classmethod
    def from_string(cls, the_string: str, convert_data_types: bool = False,
                    raise_parse_warnings: bool = False):
        """Create an entry by parsing a string.


        Setting convert_data_types to True will automatically convert
        the data loaded from the file into the corresponding python type as
        determined by loading the standard BMRB schema. This would mean that
        all floats will be represented as decimal.Decimal objects, all integers
        will be python int objects, strings and vars will remain strings, and
        dates will become datetime.date objects. When printing str() is called
        on all objects. Other that converting uppercase "E"s in scientific
        notation floats to lowercase "e"s this should not cause any change in
        the way re-printed NMR-STAR objects are displayed.

        Setting raise_parse_warnings to True will result in the raising of a
        ParsingError rather than logging a warning when non-valid (but
        ignorable) issues are found."""

        return cls(the_string=the_string, convert_data_types=convert_data_types,
                   raise_parse_warnings=raise_parse_warnings)

    @classmethod
    def from_scratch(cls, entry_id: Union[str, int]):
        """Create an empty entry that you can programmatically add to.
        You must pass a value corresponding to the Entry ID.
        (The unique identifier "xxx" from "data_xxx".)"""

        return cls(entry_id=entry_id)

    @classmethod
    def from_template(cls, entry_id, all_tags=False, default_values=False, schema=None) -> 'Entry':
        """ Create an entry that has all of the saveframes and loops from the
        schema present. No values will be assigned. Specify the entry
        ID when calling this method.

        The optional argument 'all_tags' forces all tags to be included
        rather than just the mandatory tags.

        The optional argument 'default_values' will insert the default
        values from the schema.

        The optional argument 'schema' allows providing a custom schema."""

        schema = utils.get_schema(schema)
        entry = cls(entry_id=entry_id, all_tags=all_tags, default_values=default_values, schema=schema)
        entry.source = f"from_template({schema.version})"
        return entry

    def add_saveframe(self, frame) -> None:
        """Add a saveframe to the entry."""

        if not isinstance(frame, saveframe_mod.Saveframe):
            raise ValueError("You can only add instances of saveframes using this method. You attempted to add "
                             f"the object: '{repr(frame)}'.")

        # Do not allow the addition of saveframes with the same name
        #  as a saveframe which already exists in the entry
        if frame.name in self.frame_dict:
            raise ValueError(f"Cannot add a saveframe with name '{frame.name}' since a saveframe with that "
                             f"name already exists in the entry.")

        self._frame_list.append(frame)

    def compare(self, other) -> List[str]:
        """Returns the differences between two entries as a list.
        Non-equal entries will always be detected, but specific differences
        detected depends on order of entries."""

        diffs = []
        if self is other:
            return []
        if isinstance(other, str):
            if str(self) == other:
                return []
            else:
                return ['String was not exactly equal to entry.']
        elif not isinstance(other, Entry):
            return ['Other object is not of class Entry.']
        try:
            if str(self.entry_id) != str(other.entry_id):
                diffs.append(f"Entry ID does not match between entries: '{self.entry_id}' vs '{other.entry_id}'.")
            if len(self._frame_list) != len(other.frame_list):
                diffs.append(f"The number of saveframes in the entries are not equal: '{len(self._frame_list)}' vs "
                             f"'{len(other.frame_list)}'.")
            for frame in self._frame_list:
                other_frame_dict = other.frame_dict
                if frame.name not in other_frame_dict:
                    diffs.append(f"No saveframe with name '{frame.name}' in other entry.")
                else:
                    comp = frame.compare(other_frame_dict[frame.name])
                    if len(comp) > 0:
                        diffs.append(f"Saveframes do not match: '{frame.name}'.")
                        diffs.extend(comp)

        except AttributeError as err:
            diffs.append(f"An exception occurred while comparing: '{err}'.")

        return diffs

    def add_missing_tags(self, schema: 'Schema' = None, all_tags: bool = False) -> None:
        """ Automatically adds any missing tags (according to the schema)
        to all saveframes and loops and sorts the tags. """

        for saveframe in self._frame_list:
            saveframe.add_missing_tags(schema=schema, all_tags=all_tags)

    def delete_empty_saveframes(self) -> None:
        """ Deprecated. Please use `py:meth:pynmrstar.Entry.remove_empty_saveframes`. """

        warnings.warn('Deprecated. Please use remove_empty_saveframes() instead.', DeprecationWarning)
        return self.remove_empty_saveframes()

    def format(self, skip_empty_loops: bool = True, skip_empty_tags: bool = False, show_comments: bool = True) -> str:
        """ The same as calling str(Entry), except that you can pass options
        to customize how the entry is printed.

        skip_empty_loops will omit printing loops with no tags at all. (A loop with null tags is not "empty".)
        skip_empty_tags will omit tags in the saveframes and loops which have no non-null values.
        show_comments will show the standard comments before a saveframe."""

        return self.__str__(skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags,
                            show_comments=show_comments)

    def get_json(self, serialize: bool = True) -> Union[dict, str]:
        """ Returns the entry in JSON format. If serialize is set to
        False a dictionary representation of the entry that is
        serializeable is returned instead."""

        frames = [x.get_json(serialize=False) for x in self._frame_list]

        entry_dict = {
            "entry_id": self.entry_id,
            "saveframes": frames
        }

        if serialize:
            return json.dumps(entry_dict, default=_json_serialize)
        else:
            return entry_dict

    def get_loops_by_category(self, value: str) -> List['loop_mod.Loop']:
        """Allows fetching loops by category."""

        value = utils.format_category(value).lower()

        results = []
        for frame in self._frame_list:
            for one_loop in frame.loops:
                if one_loop.category.lower() == value:
                    results.append(one_loop)
        return results

    def get_saveframe_by_name(self, saveframe_name: str) -> 'saveframe_mod.Saveframe':
        """Allows fetching a saveframe by name."""

        frames = self.frame_dict
        if saveframe_name in frames:
            return frames[saveframe_name]
        else:
            raise KeyError(f"No saveframe with name '{saveframe_name}'")

    def get_saveframes_by_category(self, value: str) -> List['saveframe_mod.Saveframe']:
        """Allows fetching saveframes by category."""

        return self.get_saveframes_by_tag_and_value("sf_category", value)

    def get_saveframes_by_tag_and_value(self, tag_name: str, value: Any) -> List['saveframe_mod.Saveframe']:
        """Allows fetching saveframe(s) by tag and tag value."""

        ret_frames = []

        for frame in self._frame_list:
            results = frame.get_tag(tag_name)
            if results != [] and results[0] == value:
                ret_frames.append(frame)

        return ret_frames

    def get_tag(self, tag: str, whole_tag: bool = False) -> list:
        """ Given a tag (E.g. _Assigned_chem_shift_list.Data_file_name)
        return a list of all values for that tag. Specify whole_tag=True
        and the [tag_name, tag_value] pair will be returned."""

        if "." not in str(tag):
            raise ValueError("You must provide the tag category to call this method at the entry level. For "
                             "example, you must provide 'Entry.Title' rather than 'Title' as the tag if calling"
                             " this at the Entry level. You can call Saveframe.get_tag('Title') without issue.")

        results = []
        for frame in self._frame_list:
            results.extend(frame.get_tag(tag, whole_tag=whole_tag))

        return results

    def get_tags(self, tags: list) -> Dict[str, list]:
        """ Given a list of tags, get all of the tags and return the
        results in a dictionary."""

        # All tags
        if tags is None or not isinstance(tags, list):
            raise ValueError("Please provide a list of tags.")

        results = {}
        for tag in tags:
            results[tag] = self.get_tag(tag)

        return results

    def normalize(self, schema: Optional['Schema'] = None) -> None:
        """ Sorts saveframes, loops, and tags according to the schema
        provided (or BMRB default if none provided).

        Also re-assigns ID tag values and updates tag links to ID values."""

        # Assign all the ID tags, and update all links to ID tags
        my_schema = utils.get_schema(schema)

        # Sort the saveframes according to ID, if an ID exists. Otherwise, still sort by category
        ordering = my_schema.category_order

        def sf_key(_: saveframe_mod.Saveframe) -> [int, Union[int, float]]:
            """ Helper function to sort the saveframes.
            Returns (category order, saveframe order) """

            # If not a real category, generate an artificial but stable order > the real saveframes
            try:
                category_order = ordering.index(_.tag_prefix)
            except (ValueError, KeyError):
                if _.category is None:
                    category_order = float('infinity')
                else:
                    category_order = len(ordering) + abs(int(hashlib.sha1(str(_.category).encode()).hexdigest(), 16))

            # See if there is an ID tag, and it is a number
            saveframe_id = float('infinity')
            try:
                saveframe_id = int(_.get_tag("ID")[0])
            except (ValueError, KeyError, IndexError, TypeError):
                # Either there is no ID, or it is not a number. By default it will sort at the end of saveframes of its
                # category. Note that the entry_information ID tag has a different meaning, but since there should
                # only ever be one saveframe of that category, the sort order for it can be any value.
                pass

            return category_order, saveframe_id

        def loop_key(_) -> Union[int, float]:
            """ Helper function to sort the loops."""

            try:
                return ordering.index(_.category)
            except ValueError:
                # Generate an arbitrary sort order for loops that aren't in the schema but make sure that they
                #  always come after loops in the schema
                return len(ordering) + abs(int(hashlib.sha1(str(_.category).encode()).hexdigest(), 16))

        # Go through all the saveframes
        for each_frame in self._frame_list:
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
        self._frame_list.sort(key=sf_key)

        # Calculate all the categories present
        categories: set = set()
        for each_frame in self._frame_list:
            categories.add(each_frame.category)

        # tag_prefix -> tag -> original value -> mapped value
        mapping: dict = {}

        # Reassign the ID tags first
        for each_category in categories:

            # First in the saveframe tags
            id_counter: int = 1
            for each_frame in self.get_saveframes_by_category(each_category):
                for tag in each_frame.tags:
                    tag_schema = my_schema.schema.get(f"{each_frame.tag_prefix}.{tag[0]}".lower())
                    if not tag_schema:
                        continue

                    # Make sure the capitalization of the tag is correct
                    tag[0] = tag_schema['Tag field']

                    if tag_schema['lclSfIdFlg'] == 'Y':
                        # If it's an Entry_ID tag, set it that way
                        if tag_schema['entryIdFlg'] == 'Y':
                            mapping[f'{each_frame.tag_prefix[1:]}.{tag[0]}.{tag[1]}'] = self._entry_id
                            tag[1] = self._entry_id
                        # Must be an integer to avoid renumbering the chem_comp ID, for example
                        elif tag_schema['BMRB data type'] == "int":
                            prev_tag = tag[1]
                            if isinstance(tag[1], str):
                                tag[1] = str(id_counter)
                                mapping[f'{each_frame.tag_prefix[1:]}.{tag[0]}.{prev_tag}'] = str(id_counter)
                            else:
                                tag[1] = id_counter
                                mapping[f'{each_frame.tag_prefix[1:]}.{tag[0]}.{prev_tag}'] = id_counter
                        # We need to still store all the other tag values too
                        else:
                            mapping[f'{each_frame.tag_prefix[1:]}.{tag[0]}.{tag[1]}'] = tag[1]
                    else:
                        mapping[f'{each_frame.tag_prefix[1:]}.{tag[0]}.{tag[1]}'] = tag[1]

                # Then in the loop
                for loop in each_frame:
                    for x, tag in enumerate(loop.tags):
                        tag_schema = my_schema.schema.get(f"{loop.category}.{tag}".lower())
                        if not tag_schema:
                            continue

                        # Make sure the tags have the proper capitalization
                        loop.tags[x] = tag_schema['Tag field']

                        for row in loop.data:
                            # We don't re-map loop IDs, but we should still store them
                            mapping[f'{loop.category[1:]}.{tag}.{row[x]}'] = row[x]

                            if tag_schema['lclSfIdFlg'] == 'Y':
                                # If it's an Entry_ID tag, set it that way
                                if tag_schema['entryIdFlg'] == 'Y':
                                    row[x] = self._entry_id
                                # Must be an integer to avoid renumbering the chem_comp ID, for example
                                elif tag_schema['BMRB data type'] == "int":
                                    if row[x] in definitions.NULL_VALUES:
                                        if isinstance(row[x], str):
                                            row[x] = str(id_counter)
                                        else:
                                            row[x] = id_counter
                                # Handle chem_comp and it's ilk
                                else:
                                    parent_id_tag = f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']}"
                                    parent_id_value = each_frame.get_tag(parent_id_tag)[0]
                                    if isinstance(row[x], str):
                                        row[x] = str(parent_id_value)
                                    else:
                                        row[x] = parent_id_value
                id_counter += 1

        # Now fix any other references
        for saveframe in self:
            for tag in saveframe.tags:
                tag_schema = my_schema.schema.get(f"{saveframe.tag_prefix}.{tag[0]}".lower())
                if not tag_schema:
                    continue
                if tag_schema['Foreign Table'] and tag_schema['Sf pointer'] != 'Y':

                    if tag[1] in definitions.NULL_VALUES:
                        if tag_schema['Nullable']:
                            continue
                        else:
                            logger.warning("A foreign key tag that is not nullable was set to "
                                           f"a null value. Tag: {saveframe.tag_prefix}.{tag[1]} Primary key: "
                                           f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']} "
                                           f"Value: {tag[1]}")

                    try:
                        tag[1] = mapping[f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']}.{tag[1]}"]
                    except KeyError:
                        logger.warning(f'The tag {saveframe.tag_prefix}.{tag[0]} has value {tag[1]} '
                                       f'but there is no valid primary key.')

            # Now apply the remapping to loops...
            for loop in saveframe:
                for x, tag in enumerate(loop.tags):
                    tag_schema = my_schema.schema.get(f"{loop.category}.{tag}".lower())
                    if not tag_schema:
                        continue
                    if tag_schema['Foreign Table'] and tag_schema['Sf pointer'] != 'Y':
                        for row in loop.data:
                            if row[x] in definitions.NULL_VALUES:
                                if tag_schema['Nullable']:
                                    continue
                                else:
                                    logger.warning("A foreign key reference tag that is not nullable was set to "
                                                   f"a null value. Tag: {loop.category}.{tag} Foreign key: "
                                                   f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']} "
                                                   f"Value: {row[x]}")
                            try:
                                row[x] = mapping[
                                    f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']}.{row[x]}"]
                            except KeyError:
                                if (loop.category == '_Atom_chem_shift' or loop.category == '_Entity_comp_index') and \
                                        (tag == 'Atom_ID' or tag == 'Comp_ID'):
                                    continue
                                logger.warning(f'The tag {loop.category}.{tag} has value {row[x]} '
                                               f'but there is no valid primary key '
                                               f"{tag_schema['Foreign Table']}.{tag_schema['Foreign Column']} "
                                               f"with the tag value.")

                    # If there is both a label tag and an ID tag, do the reassignment

                    # We found a framecode reference
                    if tag_schema['Foreign Table'] and tag_schema['Foreign Column'] == 'Sf_framecode':

                        # Check if there is a tag pointing to the 'ID' tag
                        for conditional_tag in loop.tags:
                            conditional_tag_schema = my_schema.schema.get(f"{loop.category}.{conditional_tag}".lower())
                            if not conditional_tag_schema:
                                continue
                            if conditional_tag_schema['Foreign Table'] == tag_schema['Foreign Table'] and \
                                    conditional_tag_schema['Foreign Column'] == 'ID' and \
                                    conditional_tag_schema['entryIdFlg'] != 'Y':
                                # We found the matching tag
                                tag_pos = loop.tag_index(conditional_tag)

                                for row in loop.data:
                                    # Check if the tag is null
                                    if row[x] in definitions.NULL_VALUES:
                                        if tag_schema['Nullable']:
                                            continue
                                        else:
                                            logger.warning(f"A foreign saveframe reference tag that is not nullable was"
                                                           f" set to a null value. Tag: {loop.category}.{tag} "
                                                           f"Foreign saveframe: {tag_schema['Foreign Table']}"
                                                           f".{tag_schema['Foreign Column']}")
                                            continue
                                    try:
                                        row[tag_pos] = self.get_saveframe_by_name(row[x][1:]).get_tag('ID')[0]
                                    except KeyError:
                                        logger.warning(f"Missing frame of type {tag} pointed to by {conditional_tag}")

        # Renumber the 'ID' column in a loop
        for each_frame in self._frame_list:
            for loop in each_frame.loops:
                if loop.tag_index('ID') is not None and loop.category != '_Experiment':
                    loop.renumber_rows('ID')

    def print_tree(self) -> None:
        """Prints a summary, tree style, of the frames and loops in
        the entry."""

        print(repr(self))
        frame: saveframe_mod.Saveframe
        for pos, frame in enumerate(self):
            print(f"\t[{pos}] {repr(frame)}")
            for pos2, one_loop in enumerate(frame):
                print(f"\t\t[{pos2}] {repr(one_loop)}")

    def remove_empty_saveframes(self) -> None:
        """ This method will remove all empty saveframes in an entry
        (the loops in the saveframe must also be empty for the saveframe
        to be deleted). "Empty" means no values in tags, not no tags present."""

        self._frame_list = [_ for _ in self._frame_list if not _.empty]

    def remove_saveframe(self, item: Union[str, List[str], Tuple[str], 'saveframe_mod.Saveframe',
                                           List['saveframe_mod.Saveframe'], Tuple['saveframe_mod.Saveframe']]) -> None:
        """ Removes one or more saveframes from the entry. You can remove saveframes either by passing the saveframe
        object itself, the saveframe name (as a string), or a list or tuple of either."""

        parsed_list: list
        if isinstance(item, tuple):
            parsed_list = list(item)
        elif isinstance(item, list):
            parsed_list = item
        elif isinstance(item, (str, saveframe_mod.Saveframe)):
            parsed_list = [item]
        else:
            raise ValueError('The item you provided was not one or more saveframe objects or saveframe names (strings).'
                             f' Item type: {type(item)}')

        frames_to_remove = []
        for saveframe in parsed_list:
            if isinstance(saveframe, str):
                try:
                    frames_to_remove.append(self.frame_dict[saveframe])
                except KeyError:
                    raise ValueError('At least one saveframe specified to remove was not found in this saveframe. '
                                     f'First missing saveframe: {saveframe}')
            elif isinstance(saveframe, saveframe_mod.Saveframe):
                if saveframe not in self._frame_list:
                    raise ValueError('At least one loop specified to remove was not found in this saveframe. First '
                                     f'missing loop: {saveframe}')
                frames_to_remove.append(saveframe)
            else:
                raise ValueError('One of the items you provided was not a saveframe object or saveframe name '
                                 f'(string). Item: {repr(saveframe)}')

        self._frame_list = [_ for _ in self._frame_list if _ not in frames_to_remove]

    def rename_saveframe(self, original_name: str, new_name: str) -> None:
        """ Renames a saveframe and updates all pointers to that
        saveframe in the entry with the new name."""

        # Strip off the starting $ in the names
        if original_name.startswith("$"):
            original_name = original_name[1:]
        if new_name.startswith("$"):
            new_name = new_name[1:]

        # Make sure there is no saveframe called what the new name is
        if [x.name for x in self._frame_list].count(new_name) > 0:
            raise ValueError(f"Cannot rename the saveframe '{original_name}' as '{new_name}' because a "
                             f"saveframe with that name already exists in the entry.")

        # This can raise a ValueError, but no point catching it since it really is a ValueError if they provide a name
        #  of a saveframe that doesn't exist in the entry.
        change_frame = self.get_saveframe_by_name(original_name)

        # Update the saveframe
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

    def validate(self, validate_schema: bool = True, schema: 'Schema' = None,
                 validate_star: bool = True) -> List[str]:
        """Validate an entry in a variety of ways. Returns a list of
        errors found. 0-length list indicates no errors found. By
        default all validation modes are enabled.

        validate_schema - Determines if the entry is validated against
        the NMR-STAR schema. You can pass your own custom schema if desired,
        otherwise the cached schema will be used.

        validate_star - Determines if the STAR syntax checks are ran."""

        errors = []

        # They should validate for something...
        if not validate_star and not validate_schema:
            errors.append("Validate() should be called with at least one validation method enabled.")

        if validate_star:

            # Check for saveframes with same name
            saveframe_names = sorted(x.name for x in self)
            for ordinal in range(0, len(saveframe_names) - 2):
                if saveframe_names[ordinal] == saveframe_names[ordinal + 1]:
                    errors.append(f"Multiple saveframes with same name: '{saveframe_names[ordinal]}'")

            # Check for dangling references
            fdict = self.frame_dict

            for each_frame in self:
                # Iterate through the tags
                for each_tag in each_frame.tags:
                    tag_copy = str(each_tag[1])
                    if (tag_copy.startswith("$")
                            and tag_copy[1:] not in fdict):
                        errors.append(f"Dangling saveframe reference '{each_tag[1]}' in "
                                      f"tag '{each_frame.tag_prefix}.{each_tag[0]}'")

                # Iterate through the loops
                for each_loop in each_frame:
                    for each_row in each_loop:
                        for pos, val in enumerate(each_row):
                            val = str(val)
                            if val.startswith("$") and val[1:] not in fdict:
                                errors.append(f"Dangling saveframe reference '{val}' in tag "
                                              f"'{each_loop.category}.{each_loop.tags[pos]}'")

        # Ask the saveframes to check themselves for errors
        for frame in self:
            errors.extend(frame.validate(validate_schema=validate_schema, schema=schema, validate_star=validate_star))

        return errors

    def write_to_file(self, file_name: str, format_: str = "nmrstar", show_comments: bool = True,
                      skip_empty_loops: bool = False, skip_empty_tags: bool = False) -> None:
        """ Writes the entry to the specified file in NMR-STAR format.

        Optionally specify:
        show_comments=False to disable the comments that are by default inserted. Ignored when writing json.
        skip_empty_loops=False to force printing loops with no tags at all (loops with null tags are still printed)
        skip_empty_tags=True will omit tags in the saveframes and loops which have no non-null values.
        format_=json to write to the file in JSON format."""

        write_to_file(self, file_name=file_name, format_=format_, show_comments=show_comments,
                      skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags)
