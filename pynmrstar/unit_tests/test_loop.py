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

    def test_from_file_path_support(self):
        """Test that from_file methods support pathlib.Path objects."""

        # Test Loop.from_file with Path object
        loop_from_str = Loop.from_file(sample_loop_location)
        loop_from_path = Loop.from_file(Path(sample_loop_location))
        self.assertEqual(loop_from_str, loop_from_path)
        self.assertEqual(loop_from_path.category, '_Test')
        self.assertEqual(loop_from_path.tags, ['ID', 'Name'])
        self.assertEqual(loop_from_path.data, [['1', 'First'], ['2', 'Second']])

    def test_loop_parsing(self):
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

    def test_loop(self):
        test_loop = self.file_entry[0][0]

        # Check filter
        self.assertEqual(test_loop.filter(['_Entry_author.Ordinal', '_Entry_author.Middle_initials']),
                         Loop.from_string(
                             "loop_ _Entry_author.Ordinal _Entry_author.Middle_initials 1 C. 2 . 3 B. 4 H. 5 L. stop_"))
        # Check eq
        self.assertEqual(test_loop == self.file_entry[0][0], True)
        self.assertEqual(test_loop != self.file_entry[0][1], True)
        # Check __getitem__
        self.assertEqual(test_loop['_Entry_author.Ordinal'], ['1', '2', '3', '4', '5'])
        self.assertEqual(test_loop[['_Entry_author.Ordinal', '_Entry_author.Middle_initials']],
                         [['1', 'C.'], ['2', '.'], ['3', 'B.'], ['4', 'H.'], ['5', 'L.']])
        # Test __setitem__
        test_loop['_Entry_author.Ordinal'] = [1] * 5
        self.assertEqual(test_loop['_Entry_author.Ordinal'], [1, 1, 1, 1, 1])
        test_loop['_Entry_author.Ordinal'] = ['1', '2', '3', '4', '5']
        self.assertRaises(ValueError, test_loop.__setitem__, '_Entry_author.Ordinal', [1])
        self.assertRaises(ValueError, test_loop.__setitem__, '_Wrong_loop.Ordinal', [1, 2, 3, 4, 5])
        # Check __init__
        self.assertRaises(ValueError, Loop)
        test = Loop.from_scratch(category="test")
        self.assertEqual(test.category, "_test")
        self.assertEqual(Loop.from_string(str(test_loop)), test_loop)
        self.assertEqual(test_loop, Loop.from_string(test_loop.get_data_as_csv(), csv=True))
        # Check len
        self.assertEqual(len(test_loop), len(test_loop.data))
        # Check lt
        self.assertEqual(test_loop < self.file_entry[0][1], True)
        # Check __str__
        self.assertEqual(Loop.from_scratch().format(skip_empty_loops=False), "\n   loop_\n\n   stop_\n")
        self.assertEqual(Loop.from_scratch().format(skip_empty_loops=True), "")
        tmp_loop = Loop.from_scratch()
        tmp_loop.data = [[1, 2, 3]]
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.add_tag("tag1")
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.add_tag("tag2")
        tmp_loop.add_tag("tag3")
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.set_category("test")
        self.assertEqual(str(tmp_loop), "\n   loop_\n      _test.tag1\n      _test.tag2\n      _test.tag3\n\n     "
                                        "1   2   3    \n\n   stop_\n")
        self.assertEqual(tmp_loop.category, "_test")
        # Check different category
        self.assertRaises(ValueError, tmp_loop.add_tag, "invalid.tag")
        # Check duplicate tag
        self.assertRaises(ValueError, tmp_loop.add_tag, "test.tag3")
        self.assertEqual(tmp_loop.add_tag("test.tag3", ignore_duplicates=True), None)
        # Check space and period in tag
        self.assertRaises(ValueError, tmp_loop.add_tag, "test. tag")
        self.assertRaises(ValueError, tmp_loop.add_tag, "test.tag.test")

        # Check add_data
        self.assertRaises(ValueError, tmp_loop.add_data, [1, 2, 3, 4])
        tmp_loop.add_data([4, 5, 6])
        tmp_loop.add_data([7, 8, 9])
        self.assertEqual(tmp_loop.data, [[1, 2, 3], [4, 5, 6], [7, 8, 9]])

        # Test delete_data_by_tag_value
        self.assertEqual(tmp_loop.remove_data_by_tag_value("tag1", 1, index_tag=0), [[1, 2, 3]])
        self.assertRaises(ValueError, tmp_loop.remove_data_by_tag_value, "tag4", "data")
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

        # Test get_data_as_csv()
        self.assertEqual(tmp_loop.get_data_as_csv(), "_test.tag1,_test.tag2,_test.tag3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False), "tag1,tag2,tag3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(header=False), "1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False, header=False), "1,5,6\n2,8,9\n")

        # Test get_tag
        self.assertRaises(ValueError, tmp_loop.get_tag, "invalid.tag1")
        self.assertEqual(tmp_loop.get_tag("tag1"), [1, 2])
        self.assertEqual(tmp_loop.get_tag(["tag1", "tag2"]), [[1, 5], [2, 8]])
        self.assertEqual(tmp_loop.get_tag("tag1", whole_tag=True), [['_test.tag1', 1], ['_test.tag1', 2]])

        self.assertEqual(
            test_loop.get_tag(['_Entry_author.Ordinal', '_Entry_author.Middle_initials'], dict_result=True),
            [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
             {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
             {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
             {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
             {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

        self.assertEqual(
            test_loop.get_tag(['ORdinal', 'MIddle_initials'], dict_result=True),
            [{'MIddle_initials': 'C.', 'ORdinal': '1'},
             {'MIddle_initials': '.', 'ORdinal': '2'},
             {'MIddle_initials': 'B.', 'ORdinal': '3'},
             {'MIddle_initials': 'H.', 'ORdinal': '4'},
             {'MIddle_initials': 'L.', 'ORdinal': '5'}])

        self.assertEqual(
            test_loop.get_tag(['Ordinal', 'Middle_initials'], dict_result=True, whole_tag=True),
            [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
             {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
             {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
             {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
             {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

        self.assertEqual(test_loop.get_tag(['_Entry_author.Ordinal', '_Entry_author.Middle_initials'], dict_result=True,
                                           whole_tag=True),
                         [{'_Entry_author.Middle_initials': 'C.', '_Entry_author.Ordinal': '1'},
                          {'_Entry_author.Middle_initials': '.', '_Entry_author.Ordinal': '2'},
                          {'_Entry_author.Middle_initials': 'B.', '_Entry_author.Ordinal': '3'},
                          {'_Entry_author.Middle_initials': 'H.', '_Entry_author.Ordinal': '4'},
                          {'_Entry_author.Middle_initials': 'L.', '_Entry_author.Ordinal': '5'}])

        def simple_key(x):
            return -int(x[2])

        # Test sort_rows
        tmp_loop.sort_rows(["tag2"], key=simple_key)
        self.assertEqual(tmp_loop.data, [[2, 8, 9], [1, 5, 6]])
        tmp_loop.sort_rows(["tag2"])
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

        # Test clear data
        tmp_loop.clear_data()
        self.assertEqual(tmp_loop.data, [])

        # Test that the from_template method works
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
        my_schem = Schema()
        my_schem.add_tag("_Atom_chem_shift.New_Tag", "VARCHAR(100)", True, "assigned_chemical_shifts", True,
                         "_Atom_chem_shift.Atom_ID")
        self.assertEqual(Loop.from_template("atom_chem_shift", all_tags=True, schema=my_schem),
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

        # Make sure adding data with a tag works
        tmp_loop = Loop.from_string("loop_ _Atom_chem_shift.ID stop_")
        tmp_loop.data = [[1]]
        tmp_loop.add_tag("Assembly_atom_ID", update_data=True)
        self.assertEqual(tmp_loop.data, [[1, None]])
        self.assertEqual(tmp_loop.tags, ["ID", "Assembly_atom_ID"])

        # Make sure the add missing tags loop is working
        tmp_loop = Loop.from_string("loop_ _Atom_chem_shift.ID stop_")
        tmp_loop.add_missing_tags()
        self.assertEqual(tmp_loop, Loop.from_template("atom_chem_shift"))

    def test_loop_add_data(self):
        test1 = Loop.from_scratch('test')
        test1.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test1.add_data, None)
        self.assertRaises(ValueError, test1.add_data, [])
        self.assertRaises(ValueError, test1.add_data, {})
        self.assertRaises(ValueError, test1.add_data, {'not_present': 1})
        test1.add_data([{'name': 'Jeff', 'location': 'Connecticut'}, {'name': 'Chad', 'location': 'Madison'}])

        test2 = Loop.from_scratch('test')
        test2.add_tag(['Name', 'Location'])
        test2.add_data({'name': ['Jeff', 'Chad'], 'location': ['Connecticut', 'Madison']})

        test3 = Loop.from_scratch('test')
        test3.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test3.add_data, [['Jeff', 'Connecticut'], ['Chad']])
        test3.add_data([['Jeff', 'Connecticut'], ['Chad', 'Madison']])

        test4 = Loop.from_scratch('test')
        test4.add_tag(['Name', 'Location'])
        self.assertRaises(ValueError, test4.add_data, ['Jeff', 'Connecticut', 'Chad', 'Madison'])
        test4.add_data(['Jeff', 'Connecticut', 'Chad', 'Madison'], rearrange=True)

        self.assertEqual(test1, test2)
        self.assertEqual(test2, test3)
        self.assertEqual(test3, test4)

        # Now check the 'convert_data_types' argument and the raw data present in the loop
        test = Loop.from_scratch('_Atom_chem_shift')
        test.add_tag(['Val', 'Entry_ID', 'Details'])
        test.add_data([{'details': 'none', 'vAL': '1.2'}, {'val': 5, 'details': '.'}], convert_data_types=True)
        self.assertEqual(test.data, [[Decimal('1.2'), None, 'none'], [Decimal(5), None, None]])
        test.clear_data()
        test.add_data([{'details': 'none', 'vAL': '1.2'}, {'val': 5, 'details': '.'}])
        self.assertEqual(test.data, [['1.2', None, 'none'], [5, None, '.']])

    def test_syntax_outliers(self):
        """ Make sure the case of semi-colon delineated data in a data
        value is properly escaped. """

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
        # Check the data too - this should never fail (the previous test would
        # have already failed.)
        self.assertEqual(ml[0][0], Loop.from_string(str(ml))[0][0])
