#!/usr/bin/env python3
import os
import unittest
from copy import deepcopy as copy
from decimal import Decimal
from pathlib import Path

from pynmrstar import Loop, Entry, Schema
from pynmrstar.exceptions import ParsingError

our_path = os.path.dirname(os.path.realpath(__file__))
sample_file_location = os.path.join(our_path, "sample_files", "bmr15000_3.str")
sample_loop_location = os.path.join(our_path, "sample_files", "loop.txt")
file_entry = Entry.from_file(sample_file_location)


class TestLoop(unittest.TestCase):

    def setUp(self):
        self.file_entry = copy(file_entry)
        self.maxDiff = None

    def test_init(self):
        """Test Loop initialization and from_scratch."""
        # Cannot instantiate Loop directly without arguments
        self.assertRaises(ValueError, Loop)

        # from_scratch with category
        test = Loop.from_scratch(category="test")
        self.assertEqual(test.category, "_test")

    def test_category_whitespace_validation(self):
        """Test that loop category rejects whitespace characters."""

        # ASCII whitespace should be rejected
        with self.assertRaises(ValueError):
            Loop.from_scratch(category="test category")
        with self.assertRaises(ValueError):
            Loop.from_scratch(category="test\tcategory")

        # Unicode whitespace should also be rejected
        with self.assertRaises(ValueError):
            Loop.from_scratch(category="test\u3000category")  # ideographic space
        with self.assertRaises(ValueError):
            Loop.from_scratch(category="test\u00a0category")  # no-break space
        with self.assertRaises(ValueError):
            Loop.from_scratch(category="test\u1680category")  # ogham space mark

        # Setting category directly should also validate
        loop = Loop.from_scratch(category="test")
        with self.assertRaises(ValueError):
            loop.category = "_has space"
        with self.assertRaises(ValueError):
            loop.category = "_has\u3000ideographic_space"

        # set_category should also validate
        with self.assertRaises(ValueError):
            loop.set_category("has space")

        # None should be allowed
        loop.category = None
        self.assertIsNone(loop.category)

        # Valid categories should still work
        loop.category = "_valid_category"
        self.assertEqual(loop.category, "_valid_category")

        # Ensure that adding a tag with a category is also checked
        loop.category = None
        self.assertRaises(ValueError, loop.add_tag, "invalid tag.tag", "value")

    def test_from_string(self):
        """Test Loop.from_string parsing."""
        test_loop = self.file_entry[0][0]

        # Round-trip through string
        self.assertEqual(Loop.from_string(str(test_loop)), test_loop)

        # Round-trip through CSV
        self.assertEqual(test_loop, Loop.from_string(test_loop.get_data_as_csv(), csv=True))

    def test_from_file_path_support(self):
        """Test that from_file methods support pathlib.Path objects."""

        # Test Loop.from_file with Path object
        loop_from_str = Loop.from_file(sample_loop_location)
        loop_from_path = Loop.from_file(Path(sample_loop_location))
        self.assertEqual(loop_from_str, loop_from_path)
        self.assertEqual(loop_from_path.category, '_Test')
        self.assertEqual(loop_from_path.tags, ['ID', 'Name'])
        self.assertEqual(loop_from_path.data, [['1', 'First'], ['2', 'Second']])

    def test_from_template(self):
        """Test Loop.from_template with schema."""
        self.assertEqual(Loop.from_template("atom_chem_shift", all_tags=False),
                         Loop.from_string("""
loop_
      _Atom_chem_shift.ID
      _Atom_chem_shift.Assembly_atom_ID
      _Atom_chem_shift.Entity_assembly_ID
      _Atom_chem_shift.Entity_assembly_asym_ID
      _Atom_chem_shift.Entity_ID
      _Atom_chem_shift.Comp_index_ID
      _Atom_chem_shift.Seq_ID
      _Atom_chem_shift.Comp_ID
      _Atom_chem_shift.Atom_ID
      _Atom_chem_shift.Atom_type
      _Atom_chem_shift.Atom_isotope_number
      _Atom_chem_shift.Val
      _Atom_chem_shift.Val_err
      _Atom_chem_shift.Assign_fig_of_merit
      _Atom_chem_shift.Ambiguity_code
      _Atom_chem_shift.Ambiguity_set_ID
      _Atom_chem_shift.Occupancy
      _Atom_chem_shift.Resonance_ID
      _Atom_chem_shift.Auth_entity_assembly_ID
      _Atom_chem_shift.Auth_asym_ID
      _Atom_chem_shift.Auth_seq_ID
      _Atom_chem_shift.Auth_comp_ID
      _Atom_chem_shift.Auth_atom_ID
      _Atom_chem_shift.Original_PDB_strand_ID
      _Atom_chem_shift.Original_PDB_residue_no
      _Atom_chem_shift.Original_PDB_residue_name
      _Atom_chem_shift.Original_PDB_atom_name
      _Atom_chem_shift.Details
      _Atom_chem_shift.Entry_ID
      _Atom_chem_shift.Assigned_chem_shift_list_ID


   stop_
"""))

        self.assertEqual(Loop.from_template("atom_chem_shift", all_tags=True),
                         Loop.from_string("""
   loop_
      _Atom_chem_shift.ID
      _Atom_chem_shift.Assembly_atom_ID
      _Atom_chem_shift.Entity_assembly_ID
      _Atom_chem_shift.Entity_assembly_asym_ID
      _Atom_chem_shift.Entity_ID
      _Atom_chem_shift.Comp_index_ID
      _Atom_chem_shift.Seq_ID
      _Atom_chem_shift.Comp_ID
      _Atom_chem_shift.Atom_ID
      _Atom_chem_shift.Atom_type
      _Atom_chem_shift.Atom_isotope_number
      _Atom_chem_shift.Val
      _Atom_chem_shift.Val_err
      _Atom_chem_shift.Assign_fig_of_merit
      _Atom_chem_shift.Ambiguity_code
      _Atom_chem_shift.Ambiguity_set_ID
      _Atom_chem_shift.Occupancy
      _Atom_chem_shift.Resonance_ID
      _Atom_chem_shift.Auth_entity_assembly_ID
      _Atom_chem_shift.Auth_asym_ID
      _Atom_chem_shift.Auth_seq_ID
      _Atom_chem_shift.Auth_comp_ID
      _Atom_chem_shift.Auth_atom_ID
      _Atom_chem_shift.PDB_record_ID
      _Atom_chem_shift.PDB_model_num
      _Atom_chem_shift.PDB_strand_ID
      _Atom_chem_shift.PDB_ins_code
      _Atom_chem_shift.PDB_residue_no
      _Atom_chem_shift.PDB_residue_name
      _Atom_chem_shift.PDB_atom_name
      _Atom_chem_shift.Original_PDB_strand_ID
      _Atom_chem_shift.Original_PDB_residue_no
      _Atom_chem_shift.Original_PDB_residue_name
      _Atom_chem_shift.Original_PDB_atom_name
      _Atom_chem_shift.Details
      _Atom_chem_shift.Sf_ID
      _Atom_chem_shift.Entry_ID
      _Atom_chem_shift.Assigned_chem_shift_list_ID


   stop_
"""))

        # Test adding a tag to the schema
        my_schema = Schema()
        my_schema.add_tag("_Atom_chem_shift.New_Tag", "VARCHAR(100)", True, "assigned_chemical_shifts", True,
                          "_Atom_chem_shift.Atom_ID")
        self.assertEqual(Loop.from_template("atom_chem_shift", all_tags=True, schema=my_schema),
                         Loop.from_string(
                             "loop_ _Atom_chem_shift.ID _Atom_chem_shift.Assembly_atom_ID "
                             "_Atom_chem_shift.Entity_assembly_ID _Atom_chem_shift.Entity_ID "
                             "_Atom_chem_shift.Comp_index_ID _Atom_chem_shift.Seq_ID "
                             "_Atom_chem_shift.Comp_ID _Atom_chem_shift.Atom_ID _Atom_chem_shift.New_Tag "
                             "_Atom_chem_shift.Atom_type _Atom_chem_shift.Atom_isotope_number "
                             "_Atom_chem_shift.Val _Atom_chem_shift.Val_err _Atom_chem_shift.Assign_fig_of_merit "
                             "_Atom_chem_shift.Ambiguity_code _Atom_chem_shift.Ambiguity_set_ID "
                             "_Atom_chem_shift.Occupancy _Atom_chem_shift.Resonance_ID "
                             "_Atom_chem_shift.Auth_entity_assembly_ID _Atom_chem_shift.Auth_asym_ID "
                             "_Atom_chem_shift.Auth_seq_ID _Atom_chem_shift.Auth_comp_ID "
                             "_Atom_chem_shift.Auth_atom_ID _Atom_chem_shift.PDB_record_ID "
                             "_Atom_chem_shift.PDB_model_num _Atom_chem_shift.PDB_strand_ID "
                             "_Atom_chem_shift.PDB_ins_code _Atom_chem_shift.PDB_residue_no "
                             "_Atom_chem_shift.PDB_residue_name _Atom_chem_shift.PDB_atom_name "
                             "_Atom_chem_shift.Original_PDB_strand_ID _Atom_chem_shift.Original_PDB_residue_no "
                             "_Atom_chem_shift.Original_PDB_residue_name _Atom_chem_shift.Original_PDB_atom_name "
                             "_Atom_chem_shift.Details _Atom_chem_shift.Sf_ID _Atom_chem_shift.Entry_ID "
                             "_Atom_chem_shift.Assigned_chem_shift_list_ID stop_ "))

    def test_parsing_errors(self):
        """Test that parsing errors are raised appropriately."""
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test.one _test.two 1 loop_")
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test.one _test.two 1 stop_")
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test.one _test.two 1 2 3 stop_")
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test.one _test.two 1 2 3")
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test.one _test.two 1 save_ stop_")

    def test_eq(self):
        """Test Loop.__eq__ comparison."""
        test_loop = self.file_entry[0][0]

        # Same loop should be equal
        self.assertEqual(test_loop == self.file_entry[0][0], True)
        # Different loop should not be equal
        self.assertEqual(test_loop != self.file_entry[0][1], True)

        # Comparing to non-Loop objects should return False
        self.assertFalse(test_loop == "not a loop")
        self.assertFalse(test_loop is None)
        self.assertFalse(test_loop == 123)
        self.assertFalse(test_loop == {'category': test_loop.category})

    def test_len(self):
        """Test Loop.__len__ returns number of data rows."""
        test_loop = self.file_entry[0][0]
        self.assertEqual(len(test_loop), len(test_loop.data))

    def test_lt(self):
        """Test Loop.__lt__ comparison for sorting."""
        test_loop = self.file_entry[0][0]
        self.assertEqual(test_loop < self.file_entry[0][1], True)

        # Comparing to non-Loop should return NotImplemented
        self.assertEqual(test_loop.__lt__("not a loop"), NotImplemented)
        self.assertEqual(test_loop.__lt__(123), NotImplemented)

    def test_contains(self):
        """Test Loop.__contains__ for checking if tags exist."""
        test_loop = self.file_entry[0][0]

        # Single tag as string
        self.assertTrue('Ordinal' in test_loop)
        self.assertTrue('_Entry_author.Ordinal' in test_loop)
        self.assertFalse('NonexistentTag' in test_loop)

        # Multiple tags as list
        self.assertTrue(['Ordinal', 'Family_name'] in test_loop)
        self.assertFalse(['Ordinal', 'NonexistentTag'] in test_loop)

        # Multiple tags as tuple
        self.assertTrue(('Ordinal', 'Family_name') in test_loop)
        self.assertFalse(('Ordinal', 'NonexistentTag') in test_loop)

        # Non-string/list/tuple items should return False
        self.assertFalse(123 in test_loop)
        self.assertFalse(None in test_loop)

        # Non-string items inside a list should return False (not raise)
        self.assertFalse(['Ordinal', 123] in test_loop)

    def test_getitem(self):
        """Test Loop.__getitem__ for accessing tags and rows."""
        test_loop = self.file_entry[0][0]

        # Access by tag name (string)
        self.assertEqual(test_loop['_Entry_author.Ordinal'], ['1', '2', '3', '4', '5'])

        # Access by list of tag names
        self.assertEqual(test_loop[['_Entry_author.Ordinal', '_Entry_author.Middle_initials']],
                         [['1', 'C.'], ['2', '.'], ['3', 'B.'], ['4', 'H.'], ['5', 'L.']])

        # Access by tuple of tag names
        self.assertEqual(test_loop[('_Entry_author.Ordinal', '_Entry_author.Middle_initials')],
                         [['1', 'C.'], ['2', '.'], ['3', 'B.'], ['4', 'H.'], ['5', 'L.']])

        # Access by integer index (row access)
        self.assertEqual(test_loop[0], test_loop.data[0])

    def test_setitem(self):
        """Test Loop.__setitem__ for setting tag values."""
        test_loop = self.file_entry[0][0]

        # Set all values for a tag
        test_loop['_Entry_author.Ordinal'] = [1] * 5
        self.assertEqual(test_loop['_Entry_author.Ordinal'], [1, 1, 1, 1, 1])
        test_loop['_Entry_author.Ordinal'] = ['1', '2', '3', '4', '5']

        # Wrong number of values should raise
        self.assertRaises(ValueError, test_loop.__setitem__, '_Entry_author.Ordinal', [1])

        # Non-existent tag should raise
        self.assertRaises(ValueError, test_loop.__setitem__, 'NonexistentTag', [1, 2, 3, 4, 5])

    def test_str_and_format(self):
        """Test Loop.__str__ and Loop.format output."""
        # Empty loop formatting
        self.assertEqual(Loop.from_scratch().format(skip_empty_loops=False), "\n   loop_\n\n   stop_\n")
        self.assertEqual(Loop.from_scratch().format(skip_empty_loops=True), "")

        # Loop with data but no tags should raise
        tmp_loop = Loop.from_scratch()
        tmp_loop.data = [[1, 2, 3]]
        self.assertRaises(ValueError, tmp_loop.__str__)

        # Loop with mismatched tags/data should raise
        tmp_loop.add_tag("tag1")
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.add_tag("tag2")
        tmp_loop.add_tag("tag3")
        self.assertRaises(ValueError, tmp_loop.__str__)

        # Once category is set, should work
        tmp_loop.set_category("test")
        self.assertEqual(str(tmp_loop), "\n   loop_\n      _test.tag1\n      _test.tag2\n      _test.tag3\n\n     "
                                        "1   2   3    \n\n   stop_\n")
        self.assertEqual(tmp_loop.category, "_test")

    def test_syntax_outliers(self):
        """Make sure the case of semi-colon delineated data in a data
        value is properly escaped."""
        ml = copy(self.file_entry[0][0])
        # Should always work once
        ml[0][0] = str(ml)
        self.assertEqual(ml, Loop.from_string(str(ml)))
        # Twice could trigger bug
        ml[0][0] = str(ml)
        self.assertEqual(ml, Loop.from_string(str(ml)))
        self.assertEqual(ml[0][0], Loop.from_string(str(ml))[0][0])
        # Third time is a charm
        ml[0][0] = str(ml)
        self.assertEqual(ml, Loop.from_string(str(ml)))
        # Check the data too
        self.assertEqual(ml[0][0], Loop.from_string(str(ml))[0][0])

    def test_add_tag(self):
        """Test Loop.add_tag for adding tags to a loop."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.data = [[1, 2, 3]]
        tmp_loop.add_tag("tag1")
        tmp_loop.add_tag("tag2")
        tmp_loop.add_tag("tag3")

        # Different category should raise
        self.assertRaises(ValueError, tmp_loop.add_tag, "invalid.tag")

        # Duplicate tag should raise
        self.assertRaises(ValueError, tmp_loop.add_tag, "test.tag3")

        # Duplicate tag with ignore_duplicates should not raise
        self.assertEqual(tmp_loop.add_tag("test.tag3", ignore_duplicates=True), None)

        # Space in tag should raise
        self.assertRaises(ValueError, tmp_loop.add_tag, "test. tag")

        # Multiple periods in tag should raise
        self.assertRaises(ValueError, tmp_loop.add_tag, "test.tag.test")

    def test_add_tag_with_update_data(self):
        """Test adding a tag updates existing data rows with None."""
        tmp_loop = Loop.from_string("loop_ _Atom_chem_shift.ID stop_")
        tmp_loop.data = [[1]]
        tmp_loop.add_tag("Assembly_atom_ID", update_data=True)
        self.assertEqual(tmp_loop.data, [[1, None]])
        self.assertEqual(tmp_loop.tags, ["ID", "Assembly_atom_ID"])

    def test_add_data(self):
        """Test Loop.add_data with various data formats."""
        # Format 1: List of dictionaries (row-oriented)
        test1 = Loop.from_scratch('test')
        test1.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test1.add_data, None)
        self.assertRaises(ValueError, test1.add_data, [])
        self.assertRaises(ValueError, test1.add_data, {})
        self.assertRaises(ValueError, test1.add_data, {'not_present': 1})
        test1.add_data([{'name': 'Jeff', 'location': 'Connecticut'}, {'name': 'Chad', 'location': 'Madison'}])

        # Format 2: Dictionary of lists (column-oriented)
        test2 = Loop.from_scratch('test')
        test2.add_tag(['Name', 'Location'])
        test2.add_data({'name': ['Jeff', 'Chad'], 'location': ['Connecticut', 'Madison']})

        # Format 3: List of lists (matrix)
        test3 = Loop.from_scratch('test')
        test3.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test3.add_data, [['Jeff', 'Connecticut'], ['Chad']])
        test3.add_data([['Jeff', 'Connecticut'], ['Chad', 'Madison']])

        # Format 4: Flat list with rearrange
        test4 = Loop.from_scratch('test')
        test4.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test4.add_data, ['Jeff', 'Connecticut', 'Chad', 'Madison'])
        test4.add_data(['Jeff', 'Connecticut', 'Chad', 'Madison'], rearrange=True)

        # All formats should produce the same result
        self.assertEqual(test1, test2)
        self.assertEqual(test2, test3)
        self.assertEqual(test3, test4)

    def test_add_data_simple(self):
        """Test adding data row by row."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])

        # Wrong length should raise
        self.assertRaises(ValueError, tmp_loop.add_data, [1, 2, 3, 4])

        # Add valid data
        tmp_loop.add_data([1, 2, 3])
        tmp_loop.add_data([4, 5, 6])
        tmp_loop.add_data([7, 8, 9])
        self.assertEqual(tmp_loop.data, [[1, 2, 3], [4, 5, 6], [7, 8, 9]])

    def test_add_data_convert_data_types(self):
        """Test add_data with convert_data_types option."""
        test = Loop.from_scratch('_Atom_chem_shift')
        test.add_tag(['Val', 'Entry_ID', 'Details'])
        test.add_data([{'details': 'none', 'vAL': '1.2'}, {'val': 5, 'details': '.'}], convert_data_types=True)
        self.assertEqual(test.data, [[Decimal('1.2'), None, 'none'], [Decimal(5), None, None]])

        test.clear_data()
        test.add_data([{'details': 'none', 'vAL': '1.2'}, {'val': 5, 'details': '.'}])
        self.assertEqual(test.data, [['1.2', None, 'none'], [5, None, '.']])

    def test_add_missing_tags(self):
        """Test Loop.add_missing_tags adds schema tags."""
        tmp_loop = Loop.from_string("loop_ _Atom_chem_shift.ID stop_")
        tmp_loop.add_missing_tags()
        self.assertEqual(tmp_loop, Loop.from_template("atom_chem_shift"))

    def test_filter(self):
        """Test Loop.filter for selecting specific tags."""
        test_loop = self.file_entry[0][0]

        self.assertEqual(test_loop.filter(['_Entry_author.Ordinal', '_Entry_author.Middle_initials']),
                         Loop.from_string(
                             "loop_ _Entry_author.Ordinal _Entry_author.Middle_initials 1 C. 2 . 3 B. 4 H. 5 L. stop_"))

    def test_get_tag(self):
        """Test Loop.get_tag for retrieving tag values."""
        test_loop = self.file_entry[0][0]

        # Create a simple loop for basic tests
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([[1, 5, 6], [2, 8, 9]])

        # Invalid category should raise
        self.assertRaises(ValueError, tmp_loop.get_tag, "invalid.tag1")

        # Get single tag
        self.assertEqual(tmp_loop.get_tag("tag1"), [1, 2])

        # Get multiple tags
        self.assertEqual(tmp_loop.get_tag(["tag1", "tag2"]), [[1, 5], [2, 8]])

        # Get with whole_tag=True
        self.assertEqual(tmp_loop.get_tag("tag1", whole_tag=True), [['_test.tag1', 1], ['_test.tag1', 2]])

    def test_get_tag_dict_result(self):
        """Test Loop.get_tag with dict_result option."""
        test_loop = self.file_entry[0][0]

        self.assertEqual(
            test_loop.get_tag(['_Entry_author.Ordinal', '_Entry_author.Middle_initials'], dict_result=True),
            [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
             {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
             {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
             {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
             {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

        # Test case preservation in dict keys
        self.assertEqual(
            test_loop.get_tag(['ORdinal', 'MIddle_initials'], dict_result=True),
            [{'MIddle_initials': 'C.', 'ORdinal': '1'},
             {'MIddle_initials': '.', 'ORdinal': '2'},
             {'MIddle_initials': 'B.', 'ORdinal': '3'},
             {'MIddle_initials': 'H.', 'ORdinal': '4'},
             {'MIddle_initials': 'L.', 'ORdinal': '5'}])

        # Test dict_result with whole_tag
        self.assertEqual(
            test_loop.get_tag(['Ordinal', 'Middle_initials'], dict_result=True, whole_tag=True),
            [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
             {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
             {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
             {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
             {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

        self.assertEqual(
            test_loop.get_tag(['_Entry_author.Ordinal', '_Entry_author.Middle_initials'], dict_result=True,
                              whole_tag=True),
            [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
             {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
             {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
             {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
             {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

    def test_get_data_as_csv(self):
        """Test Loop.get_data_as_csv output."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([[1, 5, 6], [2, 8, 9]])

        self.assertEqual(tmp_loop.get_data_as_csv(), "_test.tag1,_test.tag2,_test.tag3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False), "tag1,tag2,tag3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(header=False), "1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False, header=False), "1,5,6\n2,8,9\n")

    def test_remove_data_by_tag_value(self):
        """Test Loop.remove_data_by_tag_value for deleting rows."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([[1, 2, 3], [4, 5, 6], [7, 8, 9]])

        # Delete row and renumber
        self.assertEqual(tmp_loop.remove_data_by_tag_value("tag1", 1, index_tag=0), [[1, 2, 3]])
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

        # Non-existent tag should raise
        self.assertRaises(ValueError, tmp_loop.remove_data_by_tag_value, "tag4", "data")

    def test_sort_rows(self):
        """Test Loop.sort_rows for sorting data."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([[1, 5, 6], [2, 8, 9]])

        def simple_key(x):
            return -int(x[2])

        # Sort with custom key
        tmp_loop.sort_rows(["tag2"], key=simple_key)
        self.assertEqual(tmp_loop.data, [[2, 8, 9], [1, 5, 6]])

        # Sort numerically (default)
        tmp_loop.sort_rows(["tag2"])
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

    def test_clear_data(self):
        """Test Loop.clear_data removes all data."""
        tmp_loop = Loop.from_scratch()
        tmp_loop.set_category("test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([[1, 2, 3], [4, 5, 6]])

        tmp_loop.clear_data()
        self.assertEqual(tmp_loop.data, [])

    def test_empty(self):
        """Test Loop.empty property."""
        # Loop with no data is empty
        tmp_loop = Loop.from_scratch(category="test")
        tmp_loop.add_tag(["tag1", "tag2"])
        self.assertTrue(tmp_loop.empty)

        # Loop with only null values is empty
        tmp_loop.add_data([['.', '.'], ['?', '?']])
        self.assertTrue(tmp_loop.empty)

        # Loop with actual data is not empty
        tmp_loop.add_data([['value', '.']])
        self.assertFalse(tmp_loop.empty)

    def test_from_json(self):
        """Test Loop.from_json for creating loops from JSON."""
        # Create a loop and convert to JSON, then back
        original = Loop.from_scratch(category="_test")
        original.add_tag(["tag1", "tag2"])
        original.add_data([["a", "b"], ["c", "d"]])

        # From JSON string
        json_str = original.get_json(serialize=True)
        from_str = Loop.from_json(json_str)
        self.assertEqual(from_str.category, original.category)
        self.assertEqual(from_str.tags, original.tags)
        self.assertEqual(from_str.data, original.data)

        # From dict
        json_dict = original.get_json(serialize=False)
        from_dict = Loop.from_json(json_dict)
        self.assertEqual(from_dict.category, original.category)

        # Invalid JSON string should raise
        with self.assertRaises(ValueError):
            Loop.from_json("not valid json")

        # Missing required key should raise
        with self.assertRaises(ValueError):
            Loop.from_json({"tags": [], "category": "_test"})  # missing 'data'

    def test_get_json(self):
        """Test Loop.get_json for serializing loops."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        tmp_loop.add_data([["a", "b"]])

        # Serialized (string) output
        json_str = tmp_loop.get_json(serialize=True)
        self.assertIsInstance(json_str, str)
        self.assertIn('"category"', json_str)
        self.assertIn('"_test"', json_str)

        # Unserialized (dict) output
        json_dict = tmp_loop.get_json(serialize=False)
        self.assertIsInstance(json_dict, dict)
        self.assertEqual(json_dict['category'], '_test')
        self.assertEqual(json_dict['tags'], ['tag1', 'tag2'])
        self.assertEqual(json_dict['data'], [['a', 'b']])

    def test_get_tag_names(self):
        """Test Loop.get_tag_names returns fully qualified tag names."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])

        self.assertEqual(tmp_loop.get_tag_names(), ["_test.tag1", "_test.tag2"])

        # Without category set, should raise
        from pynmrstar.exceptions import InvalidStateError
        tmp_loop2 = Loop.from_scratch()
        tmp_loop2._tags = ["tag1"]  # Add tag without category
        with self.assertRaises(InvalidStateError):
            tmp_loop2.get_tag_names()

    def test_compare(self):
        """Test Loop.compare for comparing two loops."""
        test_loop = self.file_entry[0][0]

        # Comparing to itself should return empty list
        self.assertEqual(test_loop.compare(test_loop), [])

        # Comparing to string representation
        self.assertEqual(test_loop.compare(str(test_loop)), [])
        self.assertEqual(test_loop.compare(str(test_loop) + "extra"), ['String was not exactly equal to loop.'])

        # Comparing to non-Loop object
        self.assertEqual(test_loop.compare(123), ['Other object is not of class Loop.'])

        # Comparing loops with different categories
        loop1 = Loop.from_scratch(category="_test1")
        loop1.add_tag(["tag1", "tag2"])
        loop1.add_data([["a", "b"]])

        loop2 = Loop.from_scratch(category="_test2")
        loop2.add_tag(["tag1", "tag2"])
        loop2.add_data([["a", "b"]])
        diffs = loop1.compare(loop2)
        self.assertTrue(any("Category of loops does not match" in d for d in diffs))

        # Comparing loops with different tags
        loop3 = Loop.from_scratch(category="_test")
        loop3.add_tag(["tag1", "tag2"])
        loop3.add_data([["a", "b"]])

        loop4 = Loop.from_scratch(category="_test")
        loop4.add_tag(["tag1", "different"])
        loop4.add_data([["a", "b"]])
        diffs = loop3.compare(loop4)
        self.assertTrue(any("Loop tag names do not match" in d for d in diffs))

        # Comparing loops with different data (sorted comparison)
        loop5 = Loop.from_scratch(category="_test")
        loop5.add_tag(["tag1", "tag2"])
        loop5.add_data([["a", "b"], ["c", "d"]])

        loop6 = Loop.from_scratch(category="_test")
        loop6.add_tag(["tag1", "tag2"])
        loop6.add_data([["x", "y"], ["z", "w"]])
        diffs = loop5.compare(loop6)
        self.assertTrue(any("Loop data does not match" in d for d in diffs))

    def test_remove_tag(self):
        """Test Loop.remove_tag for removing tags."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([["a", "b", "c"], ["d", "e", "f"]])

        # Remove single tag
        tmp_loop.remove_tag("tag2")
        self.assertEqual(tmp_loop.tags, ["tag1", "tag3"])
        self.assertEqual(tmp_loop.data, [["a", "c"], ["d", "f"]])

        # Remove tag as list
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop2.add_data([["a", "b", "c"]])
        tmp_loop2.remove_tag(["tag1", "tag3"])
        self.assertEqual(tmp_loop2.tags, ["tag2"])
        self.assertEqual(tmp_loop2.data, [["b"]])

        # Non-existent tag should raise
        tmp_loop3 = Loop.from_scratch(category="_test")
        tmp_loop3.add_tag(["tag1"])
        with self.assertRaises(KeyError):
            tmp_loop3.remove_tag("nonexistent_tag")

    def test_renumber_rows(self):
        """Test Loop.renumber_rows for renumbering tag values."""
        # Basic renumbering
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["ID", "Name"])
        tmp_loop.add_data([["5", "a"], ["10", "b"], ["15", "c"]])
        tmp_loop.renumber_rows("ID")
        self.assertEqual(tmp_loop.data, [["1", "a"], ["2", "b"], ["3", "c"]])

        # Renumber with start_value
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["ID", "Name"])
        tmp_loop2.add_data([[5, "a"], [10, "b"], [15, "c"]])
        tmp_loop2.renumber_rows("ID", start_value=10)
        self.assertEqual(tmp_loop2.data, [[10, "a"], [11, "b"], [12, "c"]])

        # Renumber with maintain_ordering
        tmp_loop3 = Loop.from_scratch(category="_test")
        tmp_loop3.add_tag(["ID", "Name"])
        tmp_loop3.add_data([["2", "a"], ["3", "b"], ["3", "c"], ["5", "d"]])
        tmp_loop3.renumber_rows("ID", start_value=1, maintain_ordering=True)
        self.assertEqual(tmp_loop3.data, [["1", "a"], ["2", "b"], ["2", "c"], ["4", "d"]])

        # Renumber with integer tag index
        tmp_loop4 = Loop.from_scratch(category="_test")
        tmp_loop4.add_tag(["ID", "Name"])
        tmp_loop4.add_data([[5, "a"], [10, "b"]])
        tmp_loop4.renumber_rows(0)  # Use integer index
        self.assertEqual(tmp_loop4.data, [[1, "a"], [2, "b"]])

        # Empty loop should do nothing
        tmp_loop5 = Loop.from_scratch(category="_test")
        tmp_loop5.add_tag(["ID", "Name"])
        tmp_loop5.renumber_rows("ID")  # Should not raise
        self.assertEqual(tmp_loop5.data, [])

        # Invalid tag name should raise
        tmp_loop6 = Loop.from_scratch(category="_test")
        tmp_loop6.add_tag(["ID", "Name"])
        tmp_loop6.add_data([[1, "a"]])
        with self.assertRaises(ValueError):
            tmp_loop6.renumber_rows("nonexistent")

        # Category mismatch should raise
        tmp_loop7 = Loop.from_scratch(category="_test")
        tmp_loop7.add_tag(["ID", "Name"])
        tmp_loop7.add_data([[1, "a"]])
        with self.assertRaises(ValueError):
            tmp_loop7.renumber_rows("_different.ID")

        # Maintain ordering with non-integer value should raise
        tmp_loop8 = Loop.from_scratch(category="_test")
        tmp_loop8.add_tag(["ID", "Name"])
        tmp_loop8.add_data([["not_a_number", "a"]])
        with self.assertRaises(ValueError):
            tmp_loop8.renumber_rows("ID", maintain_ordering=True)

        # Maintain ordering with integer values (not strings)
        tmp_loop9 = Loop.from_scratch(category="_test")
        tmp_loop9.add_tag(["ID", "Name"])
        tmp_loop9.add_data([[2, "a"], [3, "b"], [3, "c"], [5, "d"]])
        tmp_loop9.renumber_rows("ID", start_value=1, maintain_ordering=True)
        self.assertEqual(tmp_loop9.data, [[1, "a"], [2, "b"], [2, "c"], [4, "d"]])

    def test_filter_edge_cases(self):
        """Test Loop.filter edge cases."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([["a", "b", "c"], ["d", "e", "f"]])

        # Filter with single tag (not a list)
        result = tmp_loop.filter("tag1")
        self.assertEqual(result.tags, ["tag1"])
        self.assertEqual(result.data, [["a"], ["d"]])

        # Filter with non-existent tag should raise
        with self.assertRaises(KeyError):
            tmp_loop.filter("nonexistent_tag")

        # Filter with ignore_missing_tags
        result2 = tmp_loop.filter(["tag1", "nonexistent_tag"], ignore_missing_tags=True)
        self.assertEqual(result2.tags, ["tag1"])

    def test_str_skip_empty_tags(self):
        """Test Loop.__str__ with skip_empty_tags option."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        # tag2 has all null values
        tmp_loop.add_data([["a", ".", "c"], ["d", ".", "f"]])

        # Without skip_empty_tags, all tags appear
        result_all = tmp_loop.format(skip_empty_tags=False)
        self.assertIn("tag2", result_all)

        # With skip_empty_tags, tag2 should be omitted
        result_skip = tmp_loop.format(skip_empty_tags=True)
        self.assertNotIn("tag2", result_skip)
        self.assertIn("tag1", result_skip)
        self.assertIn("tag3", result_skip)

    def test_parsing_edge_cases(self):
        """Test parsing edge cases like multiple loops or empty string."""
        # Multiple loops with different categories should raise
        with self.assertRaises(ParsingError):
            Loop.from_string("loop_ _test1.tag1 a stop_ loop_ _test2.tag2 b stop_")

        # Empty string should raise
        with self.assertRaises(ParsingError):
            Loop.from_string("")

    def test_get_tags_from_schema_invalid_prefix(self):
        """Test _get_tags_from_schema with invalid tag prefix."""
        from pynmrstar.exceptions import InvalidStateError
        with self.assertRaises(InvalidStateError):
            Loop._get_tags_from_schema("nonexistent_category_xyz")

    def test_add_data_edge_cases(self):
        """Test add_data edge cases."""
        # Format 2 with uneven lists (IndexError in format_two_to_one)
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        # Uneven lists - tag1 has 3 values, tag2 has 1 value
        tmp_loop.add_data({"tag1": ["a", "b", "c"], "tag2": ["x"]})
        self.assertEqual(tmp_loop.data, [["a", "x"], ["b", None], ["c", None]])

        # Tag not in loop (Format 1)
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["tag1", "tag2"])
        with self.assertRaises(ValueError):
            tmp_loop2.add_data([{"tag1": "a", "nonexistent": "b"}])

        # Flat list with rearrange but wrong length
        tmp_loop3 = Loop.from_scratch(category="_test")
        tmp_loop3.add_tag(["tag1", "tag2"])
        with self.assertRaises(ValueError):
            tmp_loop3.add_data(["a", "b", "c"], rearrange=True)  # 3 is not multiple of 2

    def test_add_data_by_tag_deprecated(self):
        """Test deprecated add_data_by_tag method."""
        import warnings
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tmp_loop.add_data_by_tag("tag1", "a")
            tmp_loop.add_data_by_tag("tag2", "b")
            # After completing a row, add another row
            tmp_loop.add_data_by_tag("tag1", "c")
            tmp_loop.add_data_by_tag("tag2", "d")
            self.assertEqual(len(w), 4)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))

        self.assertEqual(tmp_loop.data, [["a", "b"], ["c", "d"]])

        # Category mismatch should raise
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with self.assertRaises(ValueError):
                tmp_loop.add_data_by_tag("_different.tag1", "e")

        # Non-existent tag should raise
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with self.assertRaises(ValueError):
                tmp_loop.add_data_by_tag("nonexistent", "e")

        # Adding data out of order should raise
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["tag1", "tag2"])
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            tmp_loop2.add_data_by_tag("tag1", "a")
            with self.assertRaises(ValueError):
                tmp_loop2.add_data_by_tag("tag1", "c")  # Out of order - should be tag2

    def test_add_missing_tags_sort_exception(self):
        """Test add_missing_tags when sort_rows raises TypeError."""
        tmp_loop = Loop.from_string("loop_ _Atom_chem_shift.ID _Atom_chem_shift.Ordinal stop_")
        # Use None values which can cause TypeError when sorting
        tmp_loop.add_data([["1", None], ["2", None]])
        # This should handle TypeError from sort_rows and renumber
        tmp_loop.add_missing_tags()
        # Check that ordinal was renumbered
        ordinal_idx = tmp_loop.tag_index("Ordinal")
        self.assertEqual(tmp_loop.data[0][ordinal_idx], 1)
        self.assertEqual(tmp_loop.data[1][ordinal_idx], 2)

    def test_add_tag_edge_cases(self):
        """Test add_tag edge cases."""
        # Tag starting with a period (just the tag name)
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(".tag1")
        self.assertEqual(tmp_loop.tags, ["tag1"])

        # Null value as tag name should raise
        tmp_loop2 = Loop.from_scratch(category="_test")
        with self.assertRaises(ValueError):
            tmp_loop2.add_tag(".")  # "." is a null value

        with self.assertRaises(ValueError):
            tmp_loop2.add_tag("?")  # "?" is also a null value

    def test_deprecated_delete_methods(self):
        """Test deprecated delete_tag and delete_data_by_tag_value methods."""
        import warnings

        # delete_tag
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        tmp_loop.add_data([["a", "b"]])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tmp_loop.delete_tag("tag2")
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(tmp_loop.tags, ["tag1"])

        # delete_data_by_tag_value
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["tag1", "tag2"])
        tmp_loop2.add_data([["a", "b"], ["c", "d"]])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tmp_loop2.delete_data_by_tag_value("tag1", "a")
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
        self.assertEqual(tmp_loop2.data, [["c", "d"]])

    def test_get_tag_edge_cases(self):
        """Test get_tag edge cases."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2", "tag3"])
        tmp_loop.add_data([["a", "b", "c"], ["d", "e", "f"]])

        # With tags=None and dict_result=False (default) - returns raw data
        result_raw = tmp_loop.get_tag(tags=None)
        self.assertEqual(result_raw, [["a", "b", "c"], ["d", "e", "f"]])

        # With tags=None and dict_result=True
        result = tmp_loop.get_tag(tags=None, dict_result=True)
        self.assertEqual(result, [
            {"tag1": "a", "tag2": "b", "tag3": "c"},
            {"tag1": "d", "tag2": "e", "tag3": "f"}
        ])

        # Invalid tag name should raise
        with self.assertRaises(KeyError):
            tmp_loop.get_tag("nonexistent_tag")

    def test_print_tree(self):
        """Test Loop.print_tree outputs representation."""
        import io
        import sys

        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1"])

        # Capture stdout
        captured = io.StringIO()
        sys.stdout = captured
        tmp_loop.print_tree()
        sys.stdout = sys.__stdout__

        self.assertIn("_test", captured.getvalue())

    def test_remove_data_by_tag_value_category_mismatch(self):
        """Test remove_data_by_tag_value with category mismatch."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        tmp_loop.add_data([["a", "b"]])

        with self.assertRaises(ValueError):
            tmp_loop.remove_data_by_tag_value("_different.tag1", "a")

    def test_sort_rows_edge_cases(self):
        """Test sort_rows edge cases."""
        # Category mismatch in tag should raise
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        tmp_loop.add_data([["a", "b"]])
        with self.assertRaises(ValueError):
            tmp_loop.sort_rows("_different.tag1")

        # Sort with string values (fallback to string sort)
        tmp_loop2 = Loop.from_scratch(category="_test")
        tmp_loop2.add_tag(["tag1", "tag2"])
        tmp_loop2.add_data([["b", "2"], ["a", "1"], ["c", "3"]])
        tmp_loop2.sort_rows("tag1")  # Will fallback to string sort since "a", "b", "c" aren't numbers
        self.assertEqual(tmp_loop2.data, [["a", "1"], ["b", "2"], ["c", "3"]])

        # Sort with custom key on string values
        tmp_loop3 = Loop.from_scratch(category="_test")
        tmp_loop3.add_tag(["tag1", "tag2"])
        tmp_loop3.add_data([["b", "2"], ["a", "1"], ["c", "3"]])

        def custom_key(row):
            return row[0]

        tmp_loop3.sort_rows("tag1", key=custom_key)
        self.assertEqual(tmp_loop3.data, [["a", "1"], ["b", "2"], ["c", "3"]])

    def test_validate_row_width_mismatch(self):
        """Test validate catches row width mismatches."""
        tmp_loop = Loop.from_scratch(category="_test")
        tmp_loop.add_tag(["tag1", "tag2"])
        tmp_loop.data = [["a", "b"], ["c"]]  # Second row has wrong width

        errors = tmp_loop.validate(validate_schema=False, validate_star=True)
        self.assertTrue(any("data width does not match" in e for e in errors))
