import json
from io import StringIO
from urllib2 import urlopen, HTTPError, URLError, Request

import pynmrstar
import parser as parsermod
import saveframe


class Entry(object):
    """An OO representation of a BMRB entry. You can initialize this
    object several ways; (e.g. from a file, from the official database,
    from scratch) see the class methods below."""

    def __delitem__(self, item):
        """Remove the indicated saveframe."""

        if isinstance(item, saveframe.Saveframe):
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
        if len(kwargs) == 0 or len(kwargs) > 3:
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
            star_buffer = pynmrstar._interpret_file(kwargs['file_name'])
            self.source = "from_file('%s')" % kwargs['file_name']
        elif 'entry_num' in kwargs:
            self.source = "from_database(%s)" % kwargs['entry_num']

            # The location to fetch entries from
            entry_number = kwargs['entry_num']
            url = 'http://rest.bmrb.wisc.edu/bmrb/NMR-STAR3/%s' % entry_number

            # Parse from the official BMRB library
            try:
                if pynmrstar.PY3:
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
            schema = pynmrstar._get_schema(kwargs['schema'])
            schema_obj = schema.schema
            for tag in schema_obj.values():
                category = tag['SFCategory']
                if category not in saveframe_categories:
                    saveframe_categories[category] = True
                    self.frame_list.append(saveframe.Saveframe.from_template(category, category,
                                                                             entry_id=self.entry_id,
                                                                             all_tags=kwargs['all_tags']))
            self.get_saveframes_by_category('entry_information')[0]['NMR_STAR_version'] = schema.version
            return
        else:
            # Initialize a blank entry
            self.entry_id = kwargs['entry_id']
            self.source = "from_scratch()"
            return

        # Load the BMRB entry from the file
        parser = parsermod.Parser(entry_to_parse_into=self)
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
        if isinstance(item, saveframe.Saveframe):
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
        for saveframe_obj in self:
            if saveframe_obj.category in seen_saveframes:
                sf_strings.append(saveframe_obj.__str__(first_in_category=False))
            else:
                sf_strings.append(saveframe_obj.__str__(first_in_category=True))
                seen_saveframes[saveframe_obj.category] = True

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
            entry_url = pynmrstar._API_URL + "/entry/%s"
            entry_url = entry_url % entry_num

            # If we have zlib get the compressed entry
            if pynmrstar.zlib:
                entry_url += "?format=zlib"

            # Download the entry
            try:
                req = Request(entry_url)
                req.add_header('Application', 'PyNMRSTAR %s' % pynmrstar.__version__)
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
            if pynmrstar.zlib:
                serialized_ent = pynmrstar.zlib.decompress(serialized_ent)

            # Convert bytes to string if python3
            if pynmrstar.PY3:
                serialized_ent = serialized_ent.decode()

            # Parse JSON string to dictionary
            json_data = json.loads(serialized_ent)
            if "error" in json_data:
                # Something up with the API server, try the FTP site
                return cls(entry_num=entry_num)

            # If pure zlib there is no wrapping
            if pynmrstar.zlib:
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

            if pynmrstar.CONVERT_DATATYPES:
                schema = pynmrstar._get_schema()
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
            if pynmrstar.VERBOSE:
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
        ret.frame_list = [saveframe.Saveframe.from_json(x) for x in
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
    def from_template(cls, entry_id, all_tags=False, schema=None):
        """ Create an entry that has all of the saveframes and loops from the
        schema present. No values will be assigned. Specify the entry
        ID when calling this method.

        The optional argument 'all_tags' forces all tags to be included
        rather than just the mandatory tags.

        The optional argument 'schema' allows providing a custom schema."""

        entry = cls(entry_id=entry_id, all_tags=all_tags, schema=schema)
        entry.source = "from_template()"
        return entry

    def add_saveframe(self, frame):
        """Add a saveframe to the entry."""

        if not isinstance(frame, saveframe.Saveframe):
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
            diffs.append("An exception occured while comparing: '%s'." % err)

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
            return json.dumps(entry_dict, default=pynmrstar._json_serialize)
        else:
            return entry_dict

    def get_loops_by_category(self, value):
        """Allows fetching loops by category."""

        value = pynmrstar._format_category(value).lower()

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

        if "." not in str(tag) and not pynmrstar.ALLOW_V2_ENTRIES:
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
        ordering = pynmrstar._get_schema(schema).category_order

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
            each_frame.sort_tags()
            # Iterate through the loops
            for each_loop in each_frame:
                each_loop.sort_tags()

                # See if we can sort the rows (in addition to tags)
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
        pynmrstar.enable_nef_defaults()
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
            if char in pynmrstar._WHITESPACE:
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

        out_file = open(file_name, "w")
        if format_ == "nmrstar":
            out_file.write(str(self))
        elif format_ == "json":
            out_file.write(self.get_json())

        out_file.close()
