import json
from csv import reader as csv_reader, writer as csv_writer
from io import StringIO
from typing import TextIO, BinaryIO, Union, List, Optional, Any, Dict, Iterable

from pynmrstar import definitions, entry as entry_mod, loop as loop_mod, parser as parser_mod, utils
from pynmrstar._internal import _get_comments, _json_serialize, _interpret_file
from pynmrstar.exceptions import FormattingError
from pynmrstar.schema import Schema


class Saveframe(object):
    """A saveframe object. Create using the class methods, see below."""

    def __contains__(self, item: str) -> bool:
        """ Check if the saveframe contains a tag or a loop name."""

        try:
            self.__getitem__(item)
            return True
        except KeyError:
            return False

    def __delitem__(self, item: Union[int, str, 'loop_mod.Loop']) -> None:
        """Remove the indicated tag or loop."""

        # If they specify the specific loop to delete, go ahead and delete it
        if isinstance(item, loop_mod.Loop):
            del self.loops[self.loops.index(item)]
            return

        # See if the result of get(item) is a loop. If so, delete it
        # (calls this method recursively)
        to_delete = self.__getitem__(item)
        if isinstance(to_delete, loop_mod.Loop):
            del self.loops[self.loops.index(to_delete)]
            return

        # It must be a tag. Try to delete the tag
        else:
            self.delete_tag(item)

    def __eq__(self, other) -> bool:
        """Returns True if this saveframe is equal to another saveframe,
        False if it is equal."""

        if not isinstance(other, (Saveframe, str)):
            return False

        return len(self.compare(other)) == 0

    def __getitem__(self, item: Union[int, str]) -> Union[list, 'loop_mod.Loop']:
        """Get the indicated loop or tag."""

        try:
            return self.loops[item]
        except TypeError:
            results = self.get_tag(item)
            if results:
                return results
            else:
                try:
                    return self.loop_dict[item.lower()]
                except KeyError:
                    raise KeyError("No tag or loop matching '%s'" % item)

    def __len__(self) -> int:
        """Return the number of loops in this saveframe."""

        return len(self.loops)

    def __lt__(self, other) -> bool:
        """Returns True if this saveframe sorts lower than the compared
        saveframe, false otherwise. The alphabetical ordering of the
        saveframe category is used to perform the comparison."""

        if not isinstance(other, Saveframe):
            return NotImplemented

        return self.tag_prefix < other.tag_prefix

    def __init__(self, **kwargs) -> None:
        """Don't use this directly. Use the class methods to construct:
             Saveframe.from_scratch()
             Saveframe.from_string()
             Saveframe.from_template()
             Saveframe.from_file()
             Saveframe.from_json()"""

        # They initialized us wrong
        if len(kwargs) == 0:
            raise ValueError("You should not directly instantiate a Saveframe using this method. Instead use the class"
                             " methods: Saveframe.from_scratch(), Saveframe.from_string(), Saveframe.from_template(), "
                             "Saveframe.from_file(), and Saveframe.from_json().")

        # Initialize our local variables
        self.tags: List[Any] = []
        self.loops: List[loop_mod.Loop] = []
        self.name: str = ""
        self.source: str = "unknown"
        self.category: Optional[str] = None
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
            self.source = "from_file('%s')" % kwargs['file_name']
        # Creating from template (schema)
        elif 'all_tags' in kwargs:
            schema_obj = utils.get_schema(kwargs['schema'])
            schema = schema_obj.schema
            self.category = kwargs['category']

            self.name = self.category
            if 'saveframe_name' in kwargs and kwargs['saveframe_name']:
                self.name = kwargs['saveframe_name']

            # Make sure it is a valid category
            if self.category not in [x["SFCategory"] for x in schema.values()]:
                raise ValueError("The saveframe category '%s' was not found in the dictionary." % self.category)

            s = sorted(schema.values(), key=lambda _: float(_["Dictionary sequence"]))

            loops_added = []

            for item in s:
                if item["SFCategory"] == self.category:

                    # It is a tag in this saveframe
                    if item["Loopflag"] == "N":

                        ft = utils.format_tag(item["Tag"])
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
            self.name = kwargs['saveframe_name']
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
        self.tags = tmp_entry[0].tags
        self.loops = tmp_entry[0].loops
        self.name = tmp_entry[0].name
        self.tag_prefix = tmp_entry[0].tag_prefix

    @property
    def empty(self) -> bool:
        """ Check if the saveframe has no data. Ignore the structural tags."""

        for tag in self.tags:
            tag_lower = tag[0].lower()
            if tag_lower not in ['sf_category', 'sf_framecode', 'id', 'entry_id', 'nmr_star_version',
                                 'original_nmr_star_version']:
                if tag[1] not in definitions.NULL_VALUES:
                    return False

        for loop in self.loops:
            if not loop.empty:
                return False

        return True

    @property
    def loop_dict(self) -> Dict[str, 'loop_mod.Loop']:
        """Returns a hash of loop category -> loop."""

        res = {}
        for each_loop in self.loops:
            if each_loop.category is not None:
                res[each_loop.category.lower()] = each_loop
        return res

    @property
    def tag_dict(self) -> Dict[str, str]:
        """Returns a hash of (tag name).lower() -> tag value."""

        return {x[0].lower(): x[1] for x in self.tags}

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
                raise ValueError("The JSON you provided was neither a Python "
                                 "dictionary nor a JSON string.")

        # Make sure it has the correct keys
        for check in ["name", "tag_prefix", "tags", "loops"]:
            if check not in json_dict:
                raise ValueError("The JSON you provide must be a hash and must contain the key '%s' - even if the key "
                                 "points to None." % check)

        # Create a saveframe from scratch and populate it
        ret = Saveframe.from_scratch(json_dict['name'])
        ret.tag_prefix = json_dict['tag_prefix']
        ret.category = json_dict.get('category', None)
        ret.tags = json_dict['tags']
        ret.loops = [loop_mod.Loop.from_json(x) for x in json_dict['loops']]
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
                   source="from_template(%s)" % schema.version)

    def __repr__(self) -> str:
        """Returns a description of the saveframe."""

        return "<pynmrstar.Saveframe '%s'>" % self.name

    def __setitem__(self, key: Union[str, int], item: Union[str, 'loop_mod.Loop']) -> None:
        """Set the indicated loop or tag."""

        # It's a loop
        if isinstance(item, loop_mod.Loop):
            try:
                integer = int(str(key))
                self.loops[integer] = item
            except ValueError:
                if key.lower() in self.loop_dict:
                    for pos, tmp_loop in enumerate(self.loops):
                        if tmp_loop.category.lower() == key.lower():
                            self.loops[pos] = item
                else:
                    raise KeyError("Loop with category '%s' does not exist and therefore cannot be written to. Use "
                                   "add_loop instead." % key)
        else:
            # If the tag already exists, set its value
            self.add_tag(key, item, update=True)

    def __str__(self, first_in_category: bool = True, skip_empty_loops: bool = False,
                skip_empty_tags: bool = False, show_comments: bool = True) -> str:
        """Returns the saveframe in STAR format as a string."""

        if self.tag_prefix is None:
            raise ValueError("The tag prefix was never set!")

        # Make sure this isn't a dummy saveframe before proceeding
        try:
            width = max([len(self.tag_prefix + "." + x[0]) for x in self.tags])
        except ValueError:
            return "\nsave_%s\n\nsave_\n" % self.name

        ret_string = ""

        # Insert the comment if not disabled
        if show_comments:
            if self.category in _get_comments():
                this_comment = _get_comments()[self.category]
                if first_in_category or this_comment['every_flag']:
                    ret_string = _get_comments()[self.category]['comment']

        # Print the saveframe
        ret_string += "save_%s\n" % self.name
        pstring = "   %%-%ds  %%s\n" % width
        mstring = "   %%-%ds\n;\n%%s;\n" % width

        # Print the tags
        for each_tag in self.tags:
            if skip_empty_tags and each_tag[1] in definitions.NULL_VALUES:
                continue
            try:
                clean_tag = utils.quote_value(each_tag[1])
            except ValueError:
                raise FormattingError('Cannot generate NMR-STAR for entry, as empty strings are not valid tag values '
                                      'in NMR-STAR. Please either replace the empty strings with None objects, '
                                      'or set pynmrstar.definitions.STR_CONVERSION_DICT[\'\'] = None.\n'
                                      f'Saveframe: {self.name} Tag: {each_tag[0]}')

            formatted_tag = self.tag_prefix + "." + each_tag[0]
            if "\n" in clean_tag:
                ret_string += mstring % (formatted_tag, clean_tag)
            else:
                ret_string += pstring % (formatted_tag, clean_tag)

        # Print any loops
        for each_loop in self.loops:
            ret_string += each_loop.format(skip_empty_loops=skip_empty_loops, skip_empty_tags=skip_empty_tags)

        # Close the saveframe
        ret_string += "\nsave_\n"
        return ret_string

    def add_loop(self, loop_to_add: 'loop_mod.Loop') -> None:
        """Add a loop to the saveframe loops."""

        if (loop_to_add.category in self.loop_dict or
                str(loop_to_add.category).lower() in self.loop_dict):
            if loop_to_add.category is None:
                raise ValueError("You cannot have two loops with the same category in one saveframe. You are getting "
                                 "this error because you haven't yet set your loop categories.")
            else:
                raise ValueError("You cannot have two loops with the same category in one saveframe. Category: '%s'." %
                                 loop_to_add.category)

        self.loops.append(loop_to_add)

    def add_tag(self, name: str, value: Any, line_num: Optional[int] = None, update: bool = False,
                convert_data_types: bool = False) -> None:
        """Add a tag to the tag list. Does a bit of validation and
        parsing. Set update to true to update a tag if it exists rather
        than raise an exception."""

        if "." in name:
            if name[0] != ".":
                prefix = utils.format_category(name)
                if self.tag_prefix is None:
                    self.tag_prefix = prefix
                elif self.tag_prefix != prefix:
                    raise ValueError("One saveframe cannot have tags with different categories (or tags that don't "
                                     "match the set category)! '%s' vs '%s'." % (self.tag_prefix, prefix))
                name = name[name.index(".") + 1:]
            else:
                name = name[1:]

        # No duplicate tags
        if self.get_tag(name):
            if not update:
                raise ValueError("There is already a tag with the name '%s'." % name)
            else:
                self.get_tag(name, whole_tag=True)[0][1] = value
                return

        if "." in name:
            raise ValueError("There cannot be more than one '.' in a tag name.")
        if " " in name:
            raise ValueError("Tag names can not contain spaces.")

        # See if we need to convert the data type
        if convert_data_types:
            new_tag = [name, utils.get_schema().convert_tag(
                self.tag_prefix + "." + name, value, line_num=line_num)]
        else:
            new_tag = [name, value]

        # Set the category if the tag we are loading is the category
        tag_name_lower = name.lower()
        if tag_name_lower == "sf_category":
            self.category = value

        if line_num:
            new_tag.append(line_num)

        self.tags.append(new_tag)

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
                raise ValueError("You provided an invalid tag/value to add: '%s'." % tag_pair)

    def add_missing_tags(self, schema: 'Schema' = None, all_tags: bool = False,
                         recursive: bool = True) -> None:
        """ Automatically adds any missing tags (according to the schema)
        and sorts the tags.

        Set recursive to False to only operate on the tags in this saveframe,
        and not those in child loops."""

        if not self.tag_prefix:
            raise ValueError("You must first specify the tag prefix of this Saveframe before calling this method. "
                             "You can do this by adding a fully qualified tag (i.e. _Entry.Sf_framecode), "
                             "by specifying the tag_prefix when calling from_scratch() or by modifying the .tag_prefix "
                             "attribute.")

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
            for loop in self.loops:
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
                diffs.append("\tSaveframe names do not match: '%s' vs '%s'." % (self.name, other.name))
                return diffs

            if str(self.tag_prefix) != str(other.tag_prefix):
                # No point comparing apples to oranges. If the tags are
                #  this different just return
                diffs.append("\tTag prefix does not match: '%s' vs '%s'." % (self.tag_prefix, other.tag_prefix))
                return diffs

            if len(self.tags) < len(other.tags):
                diffs.append("\tNumber of tags does not match: '%d' vs '%d'. The compared entry has at least one "
                             "tag this entry does not." % (len(self.tags), len(other.tags)))

            for tag in self.tags:
                other_tag = other.get_tag(tag[0])

                if not other_tag:
                    diffs.append("\tNo tag with name '%s.%s' in compared entry." % (self.tag_prefix, tag[0]))
                    continue

                # Compare the string version of the tags in case there are
                #  non-string types. Use the conversion dict to get to str
                if (str(definitions.STR_CONVERSION_DICT.get(tag[1], tag[1])) !=
                        str(definitions.STR_CONVERSION_DICT.get(other_tag[0], other_tag[0]))):
                    diffs.append("\tMismatched tag values for tag '%s.%s': '%s' vs '%s'." %
                                 (self.tag_prefix, tag[0], str(tag[1]).replace("\n", "\\n"),
                                  str(other_tag[0]).replace("\n", "\\n")))

            if len(self.loops) != len(other.loops):
                diffs.append("\tNumber of children loops does not match: '%d' vs '%d'." %
                             (len(self.loops), len(other.loops)))

            compare_loop_dict = other.loop_dict
            for each_loop in self.loops:
                if each_loop.category.lower() in compare_loop_dict:
                    compare = each_loop.compare(compare_loop_dict[each_loop.category.lower()])
                    if len(compare) > 0:
                        diffs.append("\tLoops do not match: '%s'." % each_loop.category)
                        diffs.extend(compare)
                else:
                    diffs.append("\tNo loop with category '%s' in other entry." % each_loop.category)

        except AttributeError as err:
            diffs.append("\tAn exception occurred while comparing: '%s'." % err)

        return diffs

    def delete_tag(self, tag: str) -> None:
        """Deletes a tag from the saveframe based on tag name."""

        tag = utils.format_tag(tag).lower()

        for position, each_tag in enumerate(self.tags):
            # If the tag is a match, remove it
            if each_tag[0].lower() == tag:
                return self.tags.pop(position)

        raise KeyError("There is no tag with name '%s' to remove." % tag)

    def get_data_as_csv(self, header: bool = True, show_category: bool = True) -> str:
        """Return the data contained in the loops, properly CSVd, as a
        string. Set header to False omit the header. Set show_category
        to False to omit the loop category from the headers."""

        csv_buffer = StringIO()
        csv_writer_object = csv_writer(csv_buffer)

        if header:
            if show_category:
                csv_writer_object.writerow([str(self.tag_prefix) + "." + str(x[0]) for x in self.tags])
            else:
                csv_writer_object.writerow([str(x[0]) for x in self.tags])

        data = []
        for each_tag in self.tags:
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
            "category": self.category,
            "tag_prefix": self.tag_prefix,
            "tags": [[x[0], x[1]] for x in self.tags],
            "loops": [x.get_json(serialize=False) for x in self.loops]
        }

        if serialize:
            return json.dumps(saveframe_data, default=_json_serialize)
        else:
            return saveframe_data

    def get_loop_by_category(self, name: str) -> 'loop_mod.Loop':
        """Return a loop based on the loop name (category)."""

        name = utils.format_category(name).lower()
        for each_loop in self.loops:
            if str(each_loop.category).lower() == name:
                return each_loop
        raise KeyError("No loop with category '%s'." % name)

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
        for each_loop in self.loops:
            if ((each_loop.category is not None and tag_prefix is not None and
                 each_loop.category.lower() == tag_prefix.lower())):
                results.extend(each_loop.get_tag(query, whole_tag=whole_tag))

        # Check our tags
        query = utils.format_tag(query).lower()
        if tag_prefix is not None and tag_prefix.lower() == self.tag_prefix.lower():
            for tag in self.tags:
                if query == tag[0].lower():
                    if whole_tag:
                        results.append(tag)
                    else:
                        results.append(tag[1])

        return results

    def loop_iterator(self) -> Iterable['loop_mod.Loop']:
        """Returns an iterator for saveframe loops."""

        return iter(self.loops)

    def print_tree(self) -> None:
        """Prints a summary, tree style, of the loops in the saveframe."""

        print(repr(self))
        for pos, each_loop in enumerate(self):
            print("\t[%d] %s" % (pos, repr(each_loop)))

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

        self.tags.sort(key=sort_key)

    def tag_iterator(self) -> Iterable[list]:
        """Returns an iterator for saveframe tags."""

        return iter(self.tags)

    def validate(self, validate_schema: bool = True, schema: Schema = None, validate_star: bool = True):
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
            errors.append("Cannot properly validate saveframe: '%s'. No saveframe category defined." % self.name)
            my_category = None

        if validate_schema:
            # Get the default schema if we are not passed a schema
            my_schema = utils.get_schema(schema)

            for tag in self.tags:
                line_number = str(tag[2]) + " of original file" if len(tag) > 2 else None
                formatted_tag = self.tag_prefix + "." + tag[0]
                cur_errors = my_schema.val_type(formatted_tag, tag[1], category=my_category, line_number=line_number)
                errors.extend(cur_errors)

        # Check the loops for errors
        for each_loop in self.loops:
            errors.extend(each_loop.validate(validate_schema=validate_schema, schema=schema,
                                             validate_star=validate_star, category=my_category))

        return errors

    def write_to_file(self, file_name: str, format_: str = "nmrstar", show_comments: bool = True,
                      skip_empty_loops: bool = True, skip_empty_tags: bool = False):
        """ Writes the saveframe to the specified file in NMR-STAR format.

        Optionally specify:
        show_comments=False to disable the comments that are by default inserted. Ignored when writing json.
        skip_empty_loops=False to force printing loops with no tags at all (loops with null tags are still printed)
        skip_empty_tags=True will omit tags in the saveframes and loops which have no non-null values.
        format_=json to write to the file in JSON format."""

        if format_ not in ["nmrstar", "json"]:
            raise ValueError("Invalid output format.")

        data_to_write = ''
        if format_ == "nmrstar":
            data_to_write = self.format(show_comments=show_comments, skip_empty_loops=skip_empty_loops,
                                        skip_empty_tags=skip_empty_tags)
        elif format_ == "json":
            data_to_write = self.get_json()

        out_file = open(file_name, "w")
        out_file.write(data_to_write)
        out_file.close()
