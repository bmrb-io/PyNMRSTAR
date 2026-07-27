#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
import warnings
from copy import deepcopy as copy
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pynmrstar import Saveframe, Loop, definitions, Entry
from pynmrstar.exceptions import InvalidStateError

our_path = os.path.dirname(os.path.realpath(__file__))
sample_file_location = os.path.join(our_path, "sample_files", "bmr15000_3.str")
sample_saveframe_location = os.path.join(our_path, "sample_files", "saveframe.txt")
file_entry = Entry.from_file(sample_file_location)


class TestSaveframe(unittest.TestCase):

    def setUp(self):
        self.file_entry = copy(file_entry)
        self.maxDiff = None

    def test_odd_strings(self):
        """ Make sure the library can handle odd strings. """

        # Don't run the naughty strings test in GitHub, since it won't
        # recursively checkout the "naughty strings" module on platforms
        # other than linux.
        if "GITHUB_WORKFLOW" in os.environ:
            return

        saveframe = Saveframe.from_scratch('test', 'citations')
        with open(os.path.join(our_path, 'naughty-strings/blns.json')) as odd_string_file:
            odd_strings = json.load(odd_string_file)
        for x, string in enumerate(odd_strings):
            if string == '':
                continue
            # Try using the weird string as the tag name and not just value. If it can't be used as the name due
            #  to whitespace or containing a ".", use an integer for the name and use it for the value.
            try:
                saveframe.add_tag(string, string, update=True)
            except ValueError:
                saveframe.add_tag(str(x), string)

        self.assertEqual(saveframe, Saveframe.from_string(str(saveframe)))

    def test_from_file_path_support(self):
        """Test that from_file methods support pathlib.Path objects."""

        # Test Saveframe.from_file with Path object
        saveframe_from_path = Saveframe.from_file(Path(sample_saveframe_location))
        self.assertEqual(saveframe_from_path, self.file_entry[0])

    def test_from_file_string_path(self):
        """Test that from_file works with a string path."""

        saveframe_from_str = Saveframe.from_file(sample_saveframe_location)
        self.assertEqual(saveframe_from_str, self.file_entry[0])

    def test_from_file_file_handle(self):
        """Test that from_file works with an open file handle."""

        with open(sample_saveframe_location) as f:
            saveframe_from_handle = Saveframe.from_file(f)
        self.assertEqual(saveframe_from_handle, self.file_entry[0])

    # ──────────────── __init__ ────────────────

    def test_init_no_args_raises(self):
        """Bare Saveframe() instantiation should raise ValueError."""
        self.assertRaises(ValueError, Saveframe)

    def test_init_multiple_saveframes_raises(self):
        """Parsing source with more than one saveframe should raise ValueError."""

        two_sf = str(self.file_entry[0]) + "\n" + str(self.file_entry[1])
        with self.assertRaises(ValueError):
            Saveframe.from_string(two_sf)

    # ──────────────── from_scratch ────────────────

    def test_from_scratch_basic(self):
        """Create an empty saveframe from scratch."""

        sf = Saveframe.from_scratch("test_sf")
        self.assertEqual(sf.name, "test_sf")
        self.assertIsNone(sf.tag_prefix)
        self.assertEqual(len(sf.tags), 0)

    def test_from_scratch_with_tag_prefix(self):
        """from_scratch with a tag_prefix sets it correctly."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        self.assertEqual(sf.tag_prefix, "_test")
        self.assertEqual(str(sf), "save_test\n\nsave_\n")

    # ──────────────── from_string ────────────────

    def test_from_string_roundtrip(self):
        """Round-trip through str -> from_string should produce equal saveframes."""

        frame = self.file_entry[0]
        self.assertEqual(Saveframe.from_string(str(frame)), frame)

    def test_from_string_csv(self):
        """from_string with csv=True should parse CSV data."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        tmp._loops = []
        csv_data = frame.get_data_as_csv(frame)
        self.assertEqual(Saveframe.from_string(csv_data, csv=True).compare(tmp), [])

    def test_from_string_csv_mismatched_columns(self):
        """CSV with mismatched columns should raise ValueError."""

        self.assertRaises(ValueError, Saveframe.from_string, "test.1,test.2\n2,3,4", csv=True)

    # ──────────────── from_json ────────────────

    def test_from_json_dict(self):
        """Create a saveframe from a JSON dict and verify round-trip."""

        frame = self.file_entry[0]
        json_dict = frame.get_json(serialize=False)
        reconstructed = Saveframe.from_json(json_dict)
        self.assertEqual(frame, reconstructed)

    def test_from_json_string(self):
        """Create a saveframe from a JSON string."""

        frame = self.file_entry[0]
        json_str = frame.get_json(serialize=True)
        reconstructed = Saveframe.from_json(json_str)
        self.assertEqual(frame, reconstructed)

    def test_from_json_invalid_string(self):
        """from_json with invalid input raises ValueError."""

        with self.assertRaises(ValueError):
            Saveframe.from_json(12345)

    def test_from_json_missing_key(self):
        """from_json with missing required keys raises ValueError."""

        with self.assertRaises(ValueError):
            Saveframe.from_json({"name": "test"})

    # ──────────────── from_template ────────────────

    def test_from_template_basic(self):
        """Create a saveframe from a schema template."""

        sf = Saveframe.from_template("assigned_chemical_shifts")
        self.assertEqual(sf.category, "assigned_chemical_shifts")
        self.assertIn("Sf_category", [t[0] for t in sf.tags])

    def test_from_template_with_name(self):
        """from_template with a custom name."""

        sf = Saveframe.from_template("assigned_chemical_shifts", name="my_shifts")
        self.assertEqual(sf.name, "my_shifts")

    def test_from_template_with_entry_id(self):
        """from_template with entry_id populates the entry ID tag."""

        sf = Saveframe.from_template("assigned_chemical_shifts", name="test", entry_id="99999")
        # Entry_ID tag should be set
        entry_id_values = sf.get_tag("Entry_ID")
        self.assertIn("99999", entry_id_values)

    def test_from_template_all_tags(self):
        """from_template with all_tags=True includes more tags."""

        sf_minimal = Saveframe.from_template("assigned_chemical_shifts")
        sf_all = Saveframe.from_template("assigned_chemical_shifts", all_tags=True)
        self.assertGreaterEqual(len(sf_all.tags), len(sf_minimal.tags))

    def test_from_template_default_values(self):
        """from_template with default_values=True populates defaults from schema."""

        sf = Saveframe.from_template("assigned_chemical_shifts", default_values=True)
        # Just verify it doesn't error - some tags may have default values
        self.assertIsNotNone(sf)

    def test_from_template_invalid_category(self):
        """from_template with an invalid category raises ValueError."""

        with self.assertRaises(ValueError):
            Saveframe.from_template("this_category_does_not_exist_ever")

    # ──────────────── __contains__ ────────────────

    def test_contains_tag_name(self):
        """Check if a tag name is in the saveframe."""

        frame = self.file_entry[0]
        self.assertTrue("Sf_category" in frame)
        self.assertFalse("nonexistent_tag" in frame)

    def test_contains_loop_category(self):
        """Check if a loop category string (starting with _) is in the saveframe."""

        frame = self.file_entry[0]
        self.assertTrue("_SG_project" in frame)
        self.assertFalse("_Nonexistent_loop" in frame)

    def test_contains_loop_object(self):
        """Check if a Loop object is in the saveframe."""

        frame = self.file_entry[0]
        loop = frame.loops[0]
        self.assertTrue(loop in frame)

        other_loop = Loop.from_scratch(category="not_in_frame")
        self.assertFalse(other_loop in frame)

    def test_contains_list(self):
        """Check with a list of items - all must be present."""

        frame = self.file_entry[0]
        self.assertTrue(["Sf_category", "Sf_framecode"] in frame)
        self.assertFalse(["Sf_category", "nonexistent"] in frame)

    def test_contains_tuple(self):
        """Check with a tuple of items."""

        frame = self.file_entry[0]
        self.assertTrue(("Sf_category",) in frame)

    def test_contains_invalid_type(self):
        """Non-string/non-Loop items return False."""

        frame = self.file_entry[0]
        self.assertFalse(12345 in frame)

    def test_contains_invalid_type_in_list(self):
        """A list containing a non-string/non-Loop item returns False."""

        frame = self.file_entry[0]
        self.assertFalse(["Sf_category", 12345] in frame)

    # ──────────────── __delitem__ ────────────────

    def test_delitem_by_int_index(self):
        """Delete a loop by integer index."""

        frame = copy(self.file_entry[0])
        original_len = len(frame)
        del frame[0]
        self.assertEqual(len(frame), original_len - 1)

    def test_delitem_by_int_index_out_of_range(self):
        """Delete loop by out-of-range index raises IndexError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(IndexError):
            del frame[999]

    def test_delitem_by_loop_object(self):
        """Delete a loop by Loop object."""

        frame = copy(self.file_entry[0])
        loop = frame.get_loop('_SG_project')
        original_len = len(frame)
        del frame[loop]
        self.assertEqual(len(frame), original_len - 1)

    def test_delitem_by_loop_category_string(self):
        """Delete a loop by category string (starts with _, no dot)."""

        frame = copy(self.file_entry[0])
        original_len = len(frame)
        del frame["_SG_project"]
        self.assertEqual(len(frame), original_len - 1)

    def test_delitem_by_tag_name_string(self):
        """Delete a tag by its name string (no leading _, or has a dot)."""

        frame = copy(self.file_entry[0])
        frame.add_tag("test_tag", "value")
        self.assertTrue(frame.get_tag("test_tag"))
        del frame["test_tag"]
        self.assertEqual(frame.get_tag("test_tag"), [])

    def test_delitem_by_qualified_tag_name(self):
        """Delete a tag by its fully qualified name (has a dot)."""

        frame = copy(self.file_entry[0])
        original_tags = len(frame.tags)
        del frame["_Entry.DOI"]
        self.assertEqual(len(frame.tags), original_tags - 1)

    def test_delitem_invalid_type(self):
        """Delete with an invalid type raises ValueError."""

        frame = self.file_entry[0]
        with self.assertRaises(ValueError):
            del frame[3.14]

    # ──────────────── __eq__ ────────────────

    def test_eq_same_content(self):
        """Equal saveframes should be equal."""

        frame = self.file_entry[0]
        frame_copy = copy(frame)
        self.assertEqual(frame, frame_copy)

    def test_eq_not_saveframe(self):
        """Comparing saveframe to non-saveframe returns False."""

        frame = self.file_entry[0]
        self.assertFalse(frame == "not a saveframe")
        self.assertFalse(frame == 42)
        self.assertFalse(frame == None)

    # ──────────────── __getitem__ ────────────────

    def test_getitem_int_returns_loop(self):
        """Integer index returns the corresponding loop."""

        frame = self.file_entry[0]
        self.assertEqual(frame[0], frame.loops[0])

    def test_getitem_loop_category_string(self):
        """String starting with _ returns loop by category."""

        frame = self.file_entry[0]
        self.assertEqual(frame["_SG_project"], frame.get_loop("_SG_project"))

    def test_getitem_loop_category_not_found(self):
        """KeyError when loop category string not found."""

        frame = self.file_entry[0]
        with self.assertRaises(KeyError):
            _ = frame["_Nonexistent_category"]

    def test_getitem_tag_name(self):
        """String without leading _ returns tag values."""

        frame = self.file_entry[0]
        self.assertEqual(frame["Sf_category"], ['entry_information'])

    def test_getitem_tag_not_found(self):
        """KeyError when tag name not found."""

        frame = self.file_entry[0]
        with self.assertRaises(KeyError):
            _ = frame["nonexistent_tag_xyz"]

    def test_getitem_int_out_of_range(self):
        """IndexError when integer index is out of range."""

        frame = self.file_entry[0]
        with self.assertRaises(IndexError):
            _ = frame[999]

    # ──────────────── __iter__ ────────────────

    def test_iter(self):
        """Iterating over a saveframe yields its loops."""

        frame = self.file_entry[0]
        loops = list(frame)
        self.assertEqual(loops, frame.loops)

    # ──────────────── __len__ ────────────────

    def test_len(self):
        """len() returns number of loops."""

        frame = self.file_entry[0]
        self.assertEqual(len(frame), len(frame.loops))

    # ──────────────── __lt__ ────────────────

    def test_lt_comparison(self):
        """Less-than comparison based on tag_prefix."""

        sf1 = Saveframe.from_scratch("a", tag_prefix="AAA")
        sf2 = Saveframe.from_scratch("b", tag_prefix="ZZZ")
        self.assertTrue(sf1 < sf2)
        self.assertFalse(sf2 < sf1)

    def test_lt_non_saveframe(self):
        """Comparing with non-Saveframe returns NotImplemented."""

        frame = self.file_entry[0]
        result = frame.__lt__("not a saveframe")
        self.assertEqual(result, NotImplemented)

    # ──────────────── __repr__ ────────────────

    def test_repr(self):
        """repr returns expected format."""

        frame = self.file_entry[0]
        self.assertEqual(repr(frame), "<pynmrstar.Saveframe 'entry_information'>")

    # ──────────────── __setitem__ ────────────────

    def test_setitem_tag_new(self):
        """Setting a tag value by name."""

        frame = copy(self.file_entry[0])
        frame['test_setitem'] = 1
        self.assertEqual(frame.tags[-1][1], 1)

    def test_setitem_tag_update(self):
        """Updating an existing tag value."""

        frame = copy(self.file_entry[0])
        frame['test_setitem'] = 1
        frame['tESt_setitem'] = 2
        self.assertEqual(frame.get_tag('test_setitem'), [2])

    def test_setitem_loop_by_int(self):
        """Setting a loop by integer index."""

        frame = copy(self.file_entry[0])
        frame[0] = frame[1]
        self.assertEqual(frame.loops[0], frame.loops[1])

    def test_setitem_loop_by_category_string(self):
        """Setting a loop by category string."""

        frame = copy(self.file_entry[0])
        original_loop = frame.get_loop("_SG_project")
        replacement = copy(original_loop)
        frame["_SG_project"] = replacement
        self.assertEqual(frame.get_loop("_SG_project"), replacement)

    def test_setitem_loop_by_category_not_found(self):
        """Setting a loop by nonexistent category raises KeyError."""

        frame = copy(self.file_entry[0])
        new_loop = Loop.from_scratch(category="nonexistent")
        with self.assertRaises(KeyError):
            frame["_nonexistent"] = new_loop

    # ──────────────── __str__ / format ────────────────

    def test_str_no_tag_prefix_raises(self):
        """__str__ raises InvalidStateError when tag_prefix is None."""

        sf = Saveframe.from_scratch("test")
        with self.assertRaises(InvalidStateError):
            str(sf)

    def test_str_basic(self):
        """Basic str() produces valid NMR-STAR output."""

        frame = self.file_entry[0]
        output = str(frame)
        self.assertIn("save_entry_information", output)
        self.assertTrue(output.rstrip().endswith("save_"))

    def test_format_skip_empty_loops(self):
        """format() with skip_empty_loops=True omits loops with no tags."""

        frame = copy(self.file_entry[0])
        empty_loop = Loop.from_scratch()
        frame.add_loop(empty_loop)
        # With skip_empty_loops the empty loop should not appear
        output_skip = frame.format(skip_empty_loops=True)
        output_no_skip = frame.format(skip_empty_loops=False)
        # The version without skipping should be at least as long
        self.assertGreaterEqual(len(output_no_skip), len(output_skip))

    def test_format_skip_empty_tags(self):
        """format() with skip_empty_tags=True omits null-valued tags."""

        frame = copy(self.file_entry[0])
        output_with = frame.format(skip_empty_tags=False)
        output_without = frame.format(skip_empty_tags=True)
        # Skipping empty tags should produce shorter or equal output
        self.assertGreaterEqual(len(output_with), len(output_without))

    def test_format_show_comments(self):
        """format() with show_comments=True/False."""

        frame = copy(self.file_entry[0])
        output_comments = frame.format(show_comments=True)
        output_no_comments = frame.format(show_comments=False)
        self.assertGreaterEqual(len(output_comments), len(output_no_comments))

    # ──────────────── category property ────────────────

    def test_category_getter(self):
        """category property returns the saveframe category."""

        frame = self.file_entry[0]
        self.assertEqual(frame.category, "entry_information")

    def test_category_setter(self):
        """Setting category updates both the property and the Sf_category tag."""

        frame = copy(self.file_entry[0])
        frame.category = "new_category"
        self.assertEqual(frame.category, "new_category")
        self.assertEqual(frame.get_tag("sf_category"), ["new_category"])

    def test_category_setter_null_raises(self):
        """Setting category to a null value raises ValueError."""

        frame = copy(self.file_entry[0])
        for null in definitions.NULL_VALUES:
            with self.assertRaises(ValueError):
                frame.category = null

    def test_category_setter_no_existing_tag(self):
        """Setting category when Sf_category tag doesn't exist yet adds it."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.category = "new_cat"
        self.assertEqual(sf.category, "new_cat")
        self.assertEqual(sf.get_tag("Sf_category"), ["new_cat"])

    # ──────────────── empty property ────────────────

    def test_empty_true(self):
        """A saveframe with only structural tags and null values is empty."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tag("Sf_category", "test")
        sf.add_tag("Sf_framecode", "test")
        sf.add_tag("ID", ".")
        sf.add_tag("Entry_ID", None)
        self.assertTrue(sf.empty)

    def test_empty_false_due_to_tag(self):
        """A saveframe with a non-structural, non-null tag is not empty."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tag("Sf_category", "test")
        sf.add_tag("Sf_framecode", "test")
        sf.add_tag("Custom_tag", "has_value")
        self.assertFalse(sf.empty)

    def test_empty_false_due_to_loop(self):
        """A saveframe with a non-empty loop is not empty."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tag("Sf_category", "test")
        sf.add_tag("Sf_framecode", "test")
        loop = Loop.from_scratch(category="test_loop")
        loop.add_tag("col1")
        loop.add_data(["value"])
        sf.add_loop(loop)
        self.assertFalse(sf.empty)

    # ──────────────── name property ────────────────

    def test_name_getter(self):
        """name property returns the saveframe name."""

        frame = self.file_entry[0]
        self.assertEqual(frame.name, "entry_information")

    def test_name_setter(self):
        """Setting name updates both the name and the Sf_framecode tag."""

        frame = copy(self.file_entry[0])
        frame.name = "new_name"
        self.assertEqual(frame.name, "new_name")
        self.assertEqual(frame.get_tag("sf_framecode"), ["new_name"])

    def test_name_setter_whitespace_raises(self):
        """Setting name with whitespace characters raises ValueError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(ValueError):
            frame.name = "has space"
        with self.assertRaises(ValueError):
            frame.name = "has\ttab"

    def test_name_setter_null_raises(self):
        """Setting name to null value raises ValueError."""

        frame = copy(self.file_entry[0])
        for null in definitions.NULL_VALUES:
            with self.assertRaises(ValueError):
                frame.name = null

    # ──────────────── tag_dict property ────────────────

    def test_tag_dict(self):
        """tag_dict returns a lowercase-keyed dictionary of tag values."""

        frame = self.file_entry[0]
        td = frame.tag_dict
        self.assertIsInstance(td, dict)
        self.assertIn("sf_category", td)
        self.assertEqual(td["sf_category"], "entry_information")

    # ──────────────── loop_dict property ────────────────

    def test_loop_dict(self):
        """loop_dict returns a lowercase-keyed dictionary of loop objects."""

        frame = self.file_entry[0]
        ld = frame.loop_dict
        self.assertIsInstance(ld, dict)
        self.assertIn("_sg_project", ld)
        self.assertIsInstance(ld["_sg_project"], Loop)

    # ──────────────── loops / tags properties ────────────────

    def test_loops_property(self):
        """loops property returns the list of loops."""

        frame = self.file_entry[0]
        self.assertIsInstance(frame.loops, list)
        self.assertTrue(all(isinstance(l, Loop) for l in frame.loops))

    def test_tags_property(self):
        """tags property returns the list of tags."""

        frame = self.file_entry[0]
        self.assertIsInstance(frame.tags, list)
        self.assertTrue(all(isinstance(t, list) and len(t) == 2 for t in frame.tags))

    # ──────────────── add_loop ────────────────

    def test_add_loop_success(self):
        """Adding a loop with a unique category succeeds."""

        frame = copy(self.file_entry[0])
        new_loop = Loop.from_scratch(category="unique_test")
        original_len = len(frame)
        frame.add_loop(new_loop)
        self.assertEqual(len(frame), original_len + 1)

    def test_add_loop_duplicate_raises(self):
        """Adding a loop with duplicate category raises ValueError."""

        frame = copy(self.file_entry[0])
        self.assertRaises(ValueError, frame.add_loop, frame.loops[0])

    def test_add_loop_duplicate_named_category_raises(self):
        """Adding two loops with the same named category raises ValueError."""

        one = Loop.from_scratch(category="duplicate")
        two = Loop.from_scratch(category="duplicate")
        frame = Saveframe.from_scratch('1')
        frame.add_loop(one)
        self.assertRaises(ValueError, frame.add_loop, two)

    # ──────────────── add_tag ────────────────

    def test_add_tag_basic(self):
        """Adding a basic tag."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tag("mytag", "myvalue")
        self.assertEqual(sf.get_tag("mytag"), ["myvalue"])

    def test_add_tag_duplicate_raises(self):
        """Adding duplicate tag without update raises ValueError."""

        frame = copy(self.file_entry[0])
        self.assertRaises(ValueError, frame.add_tag, "Sf_category", "test")

    def test_add_tag_update(self):
        """Adding duplicate tag with update=True updates the value."""

        frame = copy(self.file_entry[0])
        frame.add_tag("Sf_category", "updated_cat", update=True)
        self.assertEqual(frame.get_tag("Sf_category"), ["updated_cat"])
        self.assertEqual(frame.category, "updated_cat")

    def test_add_tag_update_sf_framecode_null_raises(self):
        """Updating sf_framecode to a null value raises ValueError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(ValueError):
            frame.add_tag("Sf_framecode", None, update=True)

    def test_add_tag_non_string_name_raises(self):
        """Adding a tag with non-string name raises ValueError."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        with self.assertRaises(ValueError):
            sf.add_tag(123, "value")

    def test_add_tag_null_name_raises(self):
        """Adding a tag with a null-equivalent name raises ValueError."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        with self.assertRaises(ValueError):
            sf.add_tag(".", "value")

    def test_add_tag_whitespace_in_name_raises(self):
        """Adding a tag with whitespace in name raises ValueError."""

        frame = copy(self.file_entry[0])
        self.assertRaises(ValueError, frame.add_tag, "invalid test", 1)

    def test_add_tag_double_dot_in_name_raises(self):
        """Adding a tag with more than one dot raises ValueError."""

        frame = copy(self.file_entry[0])
        self.assertRaises(ValueError, frame.add_tag, "invalid.test.test", 1)

    def test_add_tag_mismatched_prefix_raises(self):
        """Adding a fully-qualified tag with wrong prefix raises ValueError."""

        frame = copy(self.file_entry[0])
        self.assertRaises(ValueError, frame.add_tag, "invalid.test", 1, update=True)

    def test_add_tag_sets_tag_prefix(self):
        """Adding a fully-qualified tag when tag_prefix is None sets it."""

        sf = Saveframe.from_scratch("test")
        sf.add_tag("_MyPrefix.MyTag", "value")
        self.assertEqual(sf.tag_prefix, "_MyPrefix")

    def test_add_tag_sf_framecode_mismatch_raises(self):
        """Adding Sf_framecode with a different value than name raises."""

        sf = Saveframe.from_scratch("test")
        with self.assertRaises(ValueError):
            sf.add_tag("sf_framecode", "different_name")

    def test_add_tag_sf_framecode_null_on_initial_add_raises(self):
        """Adding Sf_framecode with null value raises ValueError."""

        sf = Saveframe.from_scratch("test")
        with self.assertRaises(ValueError):
            sf.add_tag("sf_framecode", None)

    def test_add_tag_convert_data_types(self):
        """Adding a tag with convert_data_types uses schema conversion."""

        sf = Saveframe.from_scratch("test", tag_prefix="_Entry")
        sf.add_tag("ID", "15000", convert_data_types=True)
        # The value should be converted (int or Decimal depending on schema)
        result = sf.get_tag("ID")
        self.assertEqual(len(result), 1)

    # ──────────────── add_tags ────────────────

    def test_add_tags_key_value_pairs(self):
        """add_tags with [key, value] pairs."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tags([['tag1', 'val1'], ['tag2', 'val2']])
        self.assertEqual(sf.get_tag('tag1'), ['val1'])
        self.assertEqual(sf.get_tag('tag2'), ['val2'])

    def test_add_tags_key_only(self):
        """add_tags with [key] pairs defaults value to '.'."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tags([['tag1'], ['tag2']])
        self.assertEqual(sf.get_tag('tag1'), ['.'])
        self.assertEqual(sf.get_tag('tag2'), ['.'])

    def test_add_tags_update(self):
        """add_tags with update=True updates existing tags."""

        frame = copy(self.file_entry[0])
        frame.add_tags([['example1'], ['example2']])
        self.assertEqual(frame.tags[-2], ['example1', "."])
        frame.add_tags([['example1', 5], ['example2']], update=True)
        self.assertEqual(frame.tags[-2], ['example1', 5])

    def test_add_tags_invalid_pair_length(self):
        """add_tags with invalid pair length raises ValueError."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        with self.assertRaises(ValueError):
            sf.add_tags([['tag1', 'val1', 'extra']])

    # ──────────────── add_missing_tags ────────────────

    def test_add_missing_tags(self):
        """add_missing_tags adds schema tags and sorts them."""

        sf = Saveframe.from_template("assigned_chemical_shifts", name="test")
        original_count = len(sf.tags)
        # Remove a tag to make room for add_missing_tags to add it back
        tag_to_remove = None
        for tag in sf.tags:
            if tag[0].lower() not in ['sf_category', 'sf_framecode']:
                tag_to_remove = tag[0]
                break
        if tag_to_remove:
            sf.remove_tag(tag_to_remove)
            self.assertEqual(len(sf.tags), original_count - 1)
            sf.add_missing_tags()
            self.assertEqual(len(sf.tags), original_count)

    def test_add_missing_tags_no_prefix_raises(self):
        """add_missing_tags without tag_prefix raises InvalidStateError."""

        sf = Saveframe.from_scratch("test")
        with self.assertRaises(InvalidStateError):
            sf.add_missing_tags()

    def test_add_missing_tags_all_tags(self):
        """add_missing_tags with all_tags=True includes internal tags."""

        sf = Saveframe.from_template("assigned_chemical_shifts", name="test")
        count_before = len(sf.tags)
        sf.add_missing_tags(all_tags=True)
        self.assertGreaterEqual(len(sf.tags), count_before)

    def test_add_missing_tags_non_recursive(self):
        """add_missing_tags with recursive=False only modifies saveframe tags."""

        sf = Saveframe.from_template("assigned_chemical_shifts", name="test")
        # Just verify it runs without error
        sf.add_missing_tags(recursive=False)

    # ──────────────── compare ────────────────

    def test_compare_same_object(self):
        """Comparing a saveframe to itself returns no differences."""

        frame = self.file_entry[0]
        self.assertEqual(frame.compare(frame), [])

    def test_compare_equal_different_objects(self):
        """Comparing equal saveframes returns no differences."""

        frame = self.file_entry[0]
        frame_copy = copy(frame)
        self.assertEqual(frame.compare(frame_copy), [])

    def test_compare_different_names(self):
        """Comparing saveframes with different names."""

        frame = self.file_entry[0]
        self.assertEqual(frame.compare(self.file_entry[1]),
                         ["\tSaveframe names do not match: 'entry_information' vs 'citation_1'."])

    def test_compare_different_prefix(self):
        """Comparing saveframes with different tag prefixes."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        tmp.tag_prefix = "test"
        self.assertEqual(frame.compare(tmp), ["\tTag prefix does not match: '_Entry' vs 'test'."])

    def test_compare_missing_tag(self):
        """Comparing when the other saveframe is missing a tag."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        tmp.tags[0][0] = "broken"
        self.assertEqual(frame.compare(tmp), ["\tNo tag with name '_Entry.Sf_category' in compared entry."])

    def test_compare_with_string_equal(self):
        """Comparing with an equal string representation."""

        frame = self.file_entry[0]
        self.assertEqual(frame.compare(str(frame)), [])

    def test_compare_with_string_not_equal(self):
        """Comparing with a non-equal string."""

        frame = self.file_entry[0]
        self.assertEqual(frame.compare("not equal"), ['String was not exactly equal to saveframe.'])

    def test_compare_with_non_saveframe(self):
        """Comparing with a non-Saveframe, non-string object."""

        frame = self.file_entry[0]
        self.assertEqual(frame.compare(42), ['Other object is not of class Saveframe.'])

    def test_compare_mismatched_tag_values(self):
        """Comparing saveframes with different tag values."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        tmp.add_tag("ID", "99999", update=True)
        diffs = frame.compare(tmp)
        self.assertTrue(any("Mismatched tag values" in d for d in diffs))

    def test_compare_mismatched_tag_counts(self):
        """Comparing when other has more tags."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        tmp.add_tag("extra_tag", "value")
        # frame has fewer tags than tmp
        diffs = frame.compare(tmp)
        self.assertTrue(any("Number of tags does not match" in d for d in diffs))

    def test_compare_mismatched_loop_counts(self):
        """Comparing saveframes with different numbers of loops."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        del tmp[0]
        diffs = frame.compare(tmp)
        self.assertTrue(any("Number of children loops" in d for d in diffs))

    def test_compare_missing_loop_category(self):
        """Comparing when other saveframe is missing a loop category."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        # Replace a loop with one that has a different category
        new_loop = Loop.from_scratch(category="different_category")
        tmp._loops[0] = new_loop
        diffs = frame.compare(tmp)
        self.assertTrue(any("No loop with category" in d for d in diffs))

    def test_compare_loop_differences(self):
        """Comparing saveframes with loops that have different data."""

        frame = self.file_entry[0]
        tmp = copy(frame)
        # Modify a loop's data so it differs
        if tmp.loops and tmp.loops[0].data:
            tmp.loops[0].data[0][0] = "modified_value_xyz"
        diffs = frame.compare(tmp)
        self.assertTrue(any("Loops do not match" in d for d in diffs))

    # ──────────────── delete_tag (deprecated) ────────────────

    def test_delete_tag_deprecated(self):
        """delete_tag raises DeprecationWarning and works like remove_tag."""

        frame = copy(self.file_entry[0])
        frame.add_tag("temp_tag", "value")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            frame.delete_tag("temp_tag")
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(frame.get_tag("temp_tag"), [])

    # ──────────────── get_data_as_csv ────────────────

    def test_get_data_as_csv_with_header_and_category(self):
        """get_data_as_csv with header=True and show_category=True."""

        frame = self.file_entry[0]
        csv = frame.get_data_as_csv(header=True, show_category=True)
        self.assertIn("_Entry.Sf_category", csv)

    def test_get_data_as_csv_with_header_no_category(self):
        """get_data_as_csv with header=True and show_category=False."""

        frame = self.file_entry[0]
        csv = frame.get_data_as_csv(header=True, show_category=False)
        self.assertIn("Sf_category", csv)
        self.assertNotIn("_Entry.Sf_category", csv)

    def test_get_data_as_csv_no_header(self):
        """get_data_as_csv with header=False."""

        frame = self.file_entry[0]
        csv = frame.get_data_as_csv(header=False)
        # First line should be data, not headers
        self.assertTrue(csv.startswith("entry_information"))

    def test_get_data_as_csv_no_header_no_category(self):
        """get_data_as_csv with header=False, show_category=False."""

        frame = self.file_entry[0]
        csv = frame.get_data_as_csv(header=False, show_category=False)
        self.assertTrue(csv.startswith("entry_information"))

    # ──────────────── get_json ────────────────

    def test_get_json_serialized(self):
        """get_json with serialize=True returns a JSON string."""

        frame = self.file_entry[0]
        result = frame.get_json(serialize=True)
        self.assertIsInstance(result, str)
        parsed = json.loads(result)
        self.assertEqual(parsed["name"], "entry_information")

    def test_get_json_unserialized(self):
        """get_json with serialize=False returns a dict."""

        frame = self.file_entry[0]
        result = frame.get_json(serialize=False)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "entry_information")
        self.assertIn("tags", result)
        self.assertIn("loops", result)
        self.assertIn("tag_prefix", result)
        self.assertIn("category", result)

    def test_get_json_roundtrip(self):
        """Round-trip through get_json -> from_json preserves equality."""

        frame = self.file_entry[0]
        json_data = frame.get_json(serialize=True)
        reconstructed = Saveframe.from_json(json_data)
        self.assertEqual(frame, reconstructed)

    # ──────────────── get_loop ────────────────

    def test_get_loop_found(self):
        """get_loop returns the loop when found."""

        frame = self.file_entry[0]
        loop = frame.get_loop("_SG_projecT")
        self.assertEqual(repr(loop), "<pynmrstar.Loop '_SG_project'>")

    def test_get_loop_not_found(self):
        """get_loop raises KeyError when loop not found."""

        frame = self.file_entry[0]
        self.assertRaises(KeyError, frame.get_loop, 'this_loop_wont_be_found')

    # ──────────────── get_loop_by_category (deprecated) ────────────────

    def test_get_loop_by_category_deprecated(self):
        """get_loop_by_category raises DeprecationWarning and returns loop."""

        frame = self.file_entry[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            loop = frame.get_loop_by_category("_SG_project")
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(loop, frame.get_loop("_SG_project"))

    # ──────────────── get_tag ────────────────

    def test_get_tag_simple(self):
        """get_tag with simple name returns values."""

        frame = self.file_entry[0]
        self.assertEqual(frame.get_tag("sf_category"), ['entry_information'])

    def test_get_tag_with_prefix(self):
        """get_tag with fully qualified name."""

        frame = self.file_entry[0]
        self.assertEqual(frame.get_tag("entry.sf_category"), ['entry_information'])

    def test_get_tag_whole_tag(self):
        """get_tag with whole_tag=True returns [name, value] pairs."""

        frame = self.file_entry[0]
        self.assertEqual(frame.get_tag("entry.sf_category", whole_tag=True),
                         [['Sf_category', 'entry_information']])

    def test_get_tag_from_loop(self):
        """get_tag can search inside loops when category matches."""

        frame = self.file_entry[0]
        # Get a tag that exists in a loop
        loop = frame.loops[0]
        if loop.tags:
            tag_name = loop.category + "." + loop.tags[0]
            result = frame.get_tag(tag_name)
            self.assertTrue(len(result) > 0)

    def test_get_tag_not_found(self):
        """get_tag returns empty list when tag not found."""

        frame = self.file_entry[0]
        self.assertEqual(frame.get_tag("nonexistent_tag_xyz"), [])

    # ──────────────── loop_iterator ────────────────

    def test_loop_iterator(self):
        """loop_iterator returns an iterator over loops."""

        frame = self.file_entry[0]
        loops = list(frame.loop_iterator())
        self.assertEqual(loops, frame.loops)

    # ──────────────── tag_iterator ────────────────

    def test_tag_iterator(self):
        """tag_iterator returns an iterator over tags."""

        frame = self.file_entry[0]
        tags = list(frame.tag_iterator())
        self.assertEqual(tags, frame.tags)

    # ──────────────── print_tree ────────────────

    def test_print_tree(self):
        """print_tree outputs to stdout."""

        frame = self.file_entry[0]
        with patch('builtins.print') as mock_print:
            frame.print_tree()
            # First call should be the saveframe repr
            mock_print.assert_any_call(repr(frame))
            # Should also print loop info
            self.assertEqual(mock_print.call_count, 1 + len(frame.loops))

    # ──────────────── remove_loop ────────────────

    def test_remove_loop_by_object(self):
        """Remove a loop by passing the loop object."""

        frame = copy(self.file_entry[0])
        loop = frame.loops[0]
        original_len = len(frame)
        frame.remove_loop(loop)
        self.assertEqual(len(frame), original_len - 1)

    def test_remove_loop_by_string_category(self):
        """Remove a loop by its category string."""

        frame = copy(self.file_entry[0])
        original_len = len(frame)
        frame.remove_loop("_SG_project")
        self.assertEqual(len(frame), original_len - 1)

    def test_remove_loop_by_string_without_underscore(self):
        """Remove a loop by lowercase category string without leading underscore."""

        frame = copy(self.file_entry[0])
        original_len = len(frame)
        frame.remove_loop("sg_project")
        self.assertEqual(len(frame), original_len - 1)

    def test_remove_loop_by_list(self):
        """Remove multiple loops by passing a list."""

        frame = copy(self.file_entry[0])
        loops_to_remove = [frame.loops[0], frame.loops[1]]
        original_len = len(frame)
        frame.remove_loop(loops_to_remove)
        self.assertEqual(len(frame), original_len - 2)

    def test_remove_loop_by_tuple(self):
        """Remove multiple loops by passing a tuple of category strings."""

        frame = copy(self.file_entry[0])
        # Get two loop categories
        cat1 = frame.loops[0].category
        cat2 = frame.loops[1].category
        original_len = len(frame)
        frame.remove_loop((cat1, cat2))
        self.assertEqual(len(frame), original_len - 2)

    def test_remove_loop_string_not_found(self):
        """Remove loop by string that doesn't exist raises ValueError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(ValueError):
            frame.remove_loop("_nonexistent_loop_category")

    def test_remove_loop_object_not_found(self):
        """Remove loop object not in saveframe raises ValueError."""

        frame = copy(self.file_entry[0])
        other_loop = Loop.from_scratch(category="not_in_frame")
        with self.assertRaises(ValueError):
            frame.remove_loop(other_loop)

    def test_remove_loop_invalid_type_raises(self):
        """Remove loop with invalid type raises ValueError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(ValueError):
            frame.remove_loop(12345)

    def test_remove_loop_invalid_item_in_list_raises(self):
        """Remove loop with invalid type in list raises ValueError."""

        frame = copy(self.file_entry[0])
        with self.assertRaises(ValueError):
            frame.remove_loop([12345])

    # ──────────────── remove_tag ────────────────

    def test_remove_tag_single(self):
        """Remove a single tag by name."""

        frame = copy(self.file_entry[0])
        frame.add_tag("temp_tag", "value")
        frame.remove_tag("temp_tag")
        self.assertEqual(frame.get_tag("temp_tag"), [])

    def test_remove_tag_list(self):
        """Remove multiple tags by passing a list."""

        frame = copy(self.file_entry[0])
        frame.add_tags([["tag1", "v1"], ["tag2", "v2"]])
        frame.remove_tag(["tag1", "tag2"])
        self.assertEqual(frame.get_tag("tag1"), [])
        self.assertEqual(frame.get_tag("tag2"), [])

    def test_remove_tag_not_found_raises(self):
        """Removing a non-existent tag raises KeyError."""

        frame = self.file_entry[0]
        self.assertRaises(KeyError, frame.remove_tag, "this_tag_will_not_exist")

    # ──────────────── set_tag_prefix ────────────────

    def test_set_tag_prefix(self):
        """set_tag_prefix sets the tag prefix with underscore."""

        frame = copy(self.file_entry[0])
        frame.set_tag_prefix("new_prefix")
        self.assertEqual(frame.tag_prefix, "_new_prefix")

    # ──────────────── sort_tags ────────────────

    def test_sort_tags(self):
        """sort_tags sorts tags according to schema order."""

        frame = copy(self.file_entry[0])
        # Move first tag to end
        frame.tags.append(frame.tags.pop(0))
        # Sf_category should no longer be first
        self.assertNotEqual(frame.tags[0][0], "Sf_category")
        frame.sort_tags()
        # After sorting, Sf_category should be first
        self.assertEqual(frame.tags[0][0], "Sf_category")

    # ──────────────── validate ────────────────

    def test_validate_valid(self):
        """Validating a valid saveframe returns no errors."""

        self.assertEqual(self.file_entry['assigned_chem_shift_list_1'].validate(), [])

    def test_validate_no_category(self):
        """Validating a saveframe with no category logs an error."""

        sf = Saveframe.from_scratch("test", tag_prefix="test")
        sf.add_tag("Sf_framecode", "test")
        errors = sf.validate()
        self.assertTrue(any("Cannot properly validate" in e for e in errors))

    def test_validate_non_ascii(self):
        """Validating a saveframe reports tag values containing non-ASCII characters."""

        frame = self.file_entry['entry_information']
        frame['Title'] = 'Solution structure of ubiquitin–like protein'
        errors = frame.validate(validate_schema=False)
        self.assertEqual(errors, ["Non-ASCII character(s) '–' (U+2013) in tag '_Entry.Title': "
                                  "'Solution structure of ubiquitin–like protein'."])

    def test_validate_schema_false(self):
        """Validating with validate_schema=False skips schema validation."""

        frame = self.file_entry[0]
        errors = frame.validate(validate_schema=False)
        self.assertIsInstance(errors, list)

    # ──────────────── write_to_file ────────────────

    def test_write_to_file_nmrstar(self):
        """Write saveframe to file in NMR-STAR format."""

        frame = self.file_entry[0]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.str', delete=False) as f:
            tmpfile = f.name
        try:
            frame.write_to_file(tmpfile)
            loaded = Saveframe.from_file(tmpfile)
            self.assertEqual(frame, loaded)
        finally:
            os.unlink(tmpfile)

    def test_write_to_file_json(self):
        """Write saveframe to file in JSON format."""

        frame = self.file_entry[0]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmpfile = f.name
        try:
            frame.write_to_file(tmpfile, format_="json")
            with open(tmpfile) as f:
                data = json.load(f)
            self.assertEqual(data["name"], "entry_information")
        finally:
            os.unlink(tmpfile)

    def test_write_to_file_path_object(self):
        """Write saveframe to file using a Path object."""

        frame = self.file_entry[0]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.str', delete=False) as f:
            tmpfile = f.name
        try:
            frame.write_to_file(Path(tmpfile))
            loaded = Saveframe.from_file(tmpfile)
            self.assertEqual(frame, loaded)
        finally:
            os.unlink(tmpfile)

    def test_write_to_file_invalid_format_raises(self):
        """Writing with invalid format raises ValueError."""

        frame = self.file_entry[0]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            tmpfile = f.name
        try:
            with self.assertRaises(ValueError):
                frame.write_to_file(tmpfile, format_="xml")
        finally:
            os.unlink(tmpfile)

    # ──────────────── additional edge cases for remaining coverage ────────────────

    def test_add_tag_update_sf_framecode_valid(self):
        """Updating sf_framecode with update=True to a valid value updates the name."""

        frame = copy(self.file_entry[0])
        frame.add_tag("Sf_framecode", "new_name", update=True)
        self.assertEqual(frame.name, "new_name")
        self.assertEqual(frame.get_tag("Sf_framecode"), ["new_name"])

    def test_compare_attribute_error(self):
        """compare handles AttributeError gracefully during comparison."""

        frame = copy(self.file_entry[0])
        other = copy(self.file_entry[0])
        # Delete tag_prefix to cause AttributeError during comparison
        del other.__dict__['tag_prefix']
        # Override __str__ on the class instance to avoid str() comparison short-circuit
        other.__class__ = type('BrokenSaveframe', (Saveframe,), {
            '__str__': lambda self, **kw: 'broken'
        })
        diffs = frame.compare(other)
        self.assertTrue(any("exception occurred" in d for d in diffs))

    def test_from_template_with_default_values_non_null(self):
        """from_template with default_values=True and all_tags=True to hit default value assignment."""

        sf = Saveframe.from_template("assigned_chemical_shifts",
                                     name="test",
                                     all_tags=True,
                                     default_values=True)
        self.assertIsNotNone(sf)
        # Verify some tags exist
        self.assertTrue(len(sf.tags) > 0)
