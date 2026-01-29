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

    def test_from_string(self):
        """Test Loop.from_string parsing."""
        test_loop = self.file_entry[0][0]

        # Round-trip through string
        self.assertEqual(Loop.from_string(str(test_loop)), test_loop)

        # Round-trip through CSV
        self.assertEqual(test_loop, Loop.from_string(test_loop.get_data_as_csv(), csv=True))

    def test_from_file(self):
        """Test that from_file methods support pathlib.Path objects."""
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

    def test_getitem(self):
        """Test Loop.__getitem__ for accessing tags and rows."""
        test_loop = self.file_entry[0][0]

        # Access by tag name (string)
        self.assertEqual(test_loop['_Entry_author.Ordinal'], ['1', '2', '3', '4', '5'])

        # Access by list of tag names
        self.assertEqual(test_loop[['_Entry_author.Ordinal', '_Entry_author.Middle_initials']],
                         [['1', 'C.'], ['2', '.'], ['3', 'B.'], ['4', 'H.'], ['5', 'L.']])

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
        self.assertRaises(ValueError, test_loop.__setitem__, '_Wrong_loop.Ordinal', [1, 2, 3, 4, 5])

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
