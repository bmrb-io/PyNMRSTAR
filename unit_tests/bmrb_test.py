#!/usr/bin/env python

# Standard imports
import os
import sys
import random
import unittest
import subprocess
from copy import deepcopy as copy

# Determine if we are running in python3
PY3 = (sys.version_info[0] == 3)

if PY3:
    from io import StringIO
else:
    from cStringIO import StringIO

# Local imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
import bmrb

if bmrb.cnmrstar:
    print("Using C library...")

# We will use this for our tests
our_path = os.path.dirname(os.path.realpath(__file__))
database_entry = bmrb.Entry.from_database(15000)
sample_file_location = os.path.join(our_path, "sample_files", "bmr15000_3.str")
file_entry = bmrb.Entry.from_file(sample_file_location)

class TestPyNMRSTAR(unittest.TestCase):

    def setUp(self):
        self.entry = copy(database_entry)

    def test_enable_nef_defaults(self):
        bmrb.enable_nef_defaults()
        self.assertEqual(bmrb.STR_CONVERSION_DICT, {None:".", True:"true", False:"false"})
        self.assertEqual(bmrb.SKIP_EMPTY_LOOPS, True)

    def test_enable_bmrb_defaults(self):
        bmrb.enable_bmrb_defaults()
        self.assertEqual(bmrb.STR_CONVERSION_DICT, {None:"."})
        self.assertEqual(bmrb.SKIP_EMPTY_LOOPS, False)

    def test_clean_val(self):
        # Check tag cleaning
        self.assertEqual(bmrb.clean_value("single quote test"), "'single quote test'")
        self.assertEqual(bmrb.clean_value("double quote' test"), '"double quote\' test"')
        self.assertEqual(bmrb.clean_value("loop_"), "'loop_'")
        self.assertEqual(bmrb.clean_value("#comment"), "'#comment'")
        self.assertEqual(bmrb.clean_value("_tag"), "'_tag'")
        self.assertEqual(bmrb.clean_value("simple"), "simple")
        self.assertEqual(bmrb.clean_value("  "), "'  '")
        self.assertEqual(bmrb.clean_value("\nnewline\n"), "\nnewline\n")
        self.assertEqual(bmrb.clean_value(None), ".")
        self.assertRaises(ValueError, bmrb.clean_value, "")

        bmrb.STR_CONVERSION_DICT = {"loop_":"noloop_"}
        self.assertEqual(bmrb.clean_value("loop_"), "noloop_")
        bmrb.STR_CONVERSION_DICT = {None:"."}

    def test__format_category(self):
        self.assertEqual(bmrb._format_category("test"), "_test")
        self.assertEqual(bmrb._format_category("_test"), "_test")
        self.assertEqual(bmrb._format_category("test.test"), "_test")

    def test__format_tag(self):
        self.assertEqual(bmrb._format_tag("test"), "test")
        self.assertEqual(bmrb._format_tag("_test.test"), "test")
        self.assertEqual(bmrb._format_tag("test.test"), "test")

    def test__InterpretFile(self):
        with open(sample_file_location, "r") as local_file:
            local_version = local_file.read()

        # Test reading file from local locations
        self.assertEqual(bmrb._interpret_file(sample_file_location).read(), local_version)
        with open(sample_file_location, "rb") as tmp:
            self.assertEqual(bmrb._interpret_file(tmp).read(), local_version)
        with open(os.path.join(our_path, "sample_files", "bmr15000_3.str.gz"), "rb") as tmp:
            self.assertEqual(bmrb._interpret_file(tmp).read(), local_version)

        # Test reading from ftp and http
        self.assertEqual(bmrb._interpret_file("http://rest.bmrb.wisc.edu/bmrb/NMR-STAR3/15000").read(), local_version)
        self.assertEqual(bmrb._interpret_file("ftp://ftp.bmrb.wisc.edu/pub/bmrb/entry_directories/bmr15000/bmr15000_3.str").read(), local_version)

        # Test reading from https locations
        self.assertEqual(bmrb._interpret_file("http://svn.bmrb.wisc.edu/svn/sans/python/unit_tests/sample_files/bmr15000_3.str").read(), local_version)
        self.assertEqual(bmrb._interpret_file("http://svn.bmrb.wisc.edu/svn/sans/python/unit_tests/sample_files/bmr15000_3.str.gz").read(), local_version)

    # Test the parser
    def test___Parser(self):
        self.assertRaises(ValueError, bmrb._Parser)

        # Check for error when reserved token present in data value
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\n_tag.example loop_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\n_tag.example data_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\n_tag.example save_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nloop_\nstop_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nsave_\nstop_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nglobal_\nstop_\nsave_\n")

        # Check for error when reserved token quoted
        self.assertRaises(ValueError, bmrb.Entry.from_string, "'data_1'\nsave_1\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\n'save_1'\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")
        self.assertRaises(ValueError, bmrb.Entry.from_string, 'data_1\nsave_1\n"loop"_\n_tag.tag\ndata_\nstop_\nsave_\n')
        self.assertRaises(ValueError, bmrb.Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\ndata_\n;\nstop_\n;\nsave_\n")

    def test_Schema(self):
        default = bmrb.Schema()
        loaded = bmrb.Schema(bmrb._SCHEMA_URL)

        self.assertEqual(default.schema, loaded.schema)
        self.assertEqual(default.types, loaded.types)
        self.assertEqual(default.headers, loaded.headers)
        self.assertEqual(default.headers, ['Dictionary sequence', 'SFCategory', 'ADIT category mandatory', 'ADIT category view type', 'ADIT super category ID', 'ADIT super category', 'ADIT category group ID', 'ADIT category view name', 'Tag', 'BMRB current', 'Query prompt', 'Query interface', 'SG Mandatory', '', 'ADIT exists', 'User full view', 'User structure view', 'User non-structure view', 'User NMR param. View', 'Annotator full view', 'Item enumerated', 'Item enumeration closed', 'Enum parent SFcategory', 'Enum parent tag', 'Derived enumeration mantable', 'Derived enumeration', 'ADIT item view name', 'Data Type', 'Nullable', 'Non-public', 'ManDBTableName', 'ManDBColumnName', 'Row Index Key', 'Saveframe ID tag', 'Source Key', 'Table Primary Key', 'Foreign Key Group', 'Foreign Table', 'Foreign Column', 'Secondary index', 'Sub category', 'Units', 'Loopflag', 'Seq', 'Adit initial rows', 'Enumeration ties', 'Mandatory code overides', 'Overide value', 'Overide view value', 'ADIT auto insert', 'Example', 'Prompt', 'Interface', 'bmrbPdbMatchID', 'bmrbPdbTransFunc', 'STAR flag', 'DB flag', 'SfNamelFlg', 'Sf category flag', 'Sf pointer', 'Natural primary key', 'Natural foreign key', 'Redundant keys', 'Parent tag', 'public', 'internal', 'small molecule', 'small molecule', 'metabolomics', 'Entry completeness', 'Overide public', 'internal', 'small molecule', 'small molecule', 'metabolomic', 'metabolomic', 'default value', 'Adit form code', 'Tag category', 'Tag field', 'Local key', 'Datum count flag', 'pdbx D&A insertion flag', 'mmCIF equivalent', 'Meta data', 'Tag delete', 'BMRB data type', 'STAR vs Curated DB', 'Key group', 'Reference table', 'Reference column', 'Dictionary description', 'variableTypeMatch', 'entryIdFlg', 'outputMapExistsFlg', 'lclSfIdFlg', 'Met ADIT category view name', 'Met Example', 'Met Prompt', 'Met Description', 'SM Struct ADIT-NMR category view name', 'SM Struct Example', 'SM Struct Prompt', 'SM Struct Description', 'Met default value', 'SM default value'])

        self.assertEqual(default.val_type("_Entity.ID", 1), [])
        self.assertEqual(default.val_type("_Entity.ID", "test"), ["Value is not of type INTEGER.:'_Entity.ID':'test' on line 'None'."])
        self.assertEqual(default.val_type("_Atom_chem_shift.Val", float(1.2)), [])
        self.assertEqual(default.val_type("_Atom_chem_shift.Val", "invalid"), ["Value is not of type FLOAT.:'_Atom_chem_shift.Val':'invalid' on line 'None'."])

        self.assertEqual(default.val_type("_Entry.ID", "this should be far too long - much too long"), ["Length of value '43' is too long for CHAR(12): '_Entry.ID':'this should be far too long - much too long' on line 'None'."])
        self.assertEqual(default.val_type("_Assembly.Ambiguous_chem_comp_sites", "this should be far too long - much too long"), ["Length of value '43' is too long for VARCHAR(3): '_Assembly.Ambiguous_chem_comp_sites':'this should be far too long - much too long' on line 'None'."])

    def test_entry_delitem(self):
        del(self.entry[0])
        tmp_entry = copy(database_entry)
        tmp_entry.frame_list.pop(0)
        self.assertEqual(self.entry, tmp_entry)

    def test_entry_eq(self):
        self.assertEqual(file_entry, database_entry)

    def test_getitem(self):
        self.assertEqual(self.entry['entry_information'], self.entry.get_saveframe_by_name("entry_information"))
        self.assertEqual(self.entry[0], self.entry.get_saveframe_by_name("entry_information"))

    def test_init(self):
        # Make sure the correct errors are raised
        self.assertRaises(ValueError, bmrb.Entry)
        self.assertRaises(ValueError, bmrb.Entry, the_string="test", entry_num="test")
        # Make sure string parsing is correct
        self.assertEqual(self.entry, bmrb.Entry.from_string(str(self.entry)))
        self.assertEqual(str(self.entry), str(bmrb.Entry.from_string(str(self.entry))))
        self.assertRaises(IOError, bmrb.Entry.from_database, 0)
        self.assertEqual(str(bmrb.Entry.from_scratch(15000)), "data_15000\n\n")
        self.assertEqual(bmrb.Entry.from_file(os.path.join(our_path, "sample_files", "bmr15000_3.str.gz")), self.entry)

    def test___setitem(self):
        tmp_entry = copy(file_entry)
        tmp_entry[0] = tmp_entry.get_saveframe_by_name('entry_information')
        self.assertEqual(tmp_entry, self.entry)
        tmp_entry['entry_information'] = tmp_entry.get_saveframe_by_name('entry_information')
        self.assertEqual(tmp_entry, self.entry)

        self.assertRaises(KeyError, tmp_entry.__setitem__, 'entry_informations', tmp_entry.get_saveframe_by_name('entry_information'))
        self.assertRaises(ValueError, tmp_entry.__setitem__, 'entry_information', 1)

    def test_compare(self):
        self.assertEqual(self.entry.compare(str(self.entry)), [])
        self.assertEqual(self.entry.compare(self.entry), [])

        self.entry.entry_id = 14999
        self.entry.frame_list.pop()
        self.assertEqual(file_entry.compare(self.entry), ["Entry ID does not match between entries: '15000' vs '14999'.", "The number of saveframes in the entries are not equal: '25' vs '24'.", "No saveframe with name 'assigned_chem_shift_list_1' in other entry."])

    def test_getmethods(self):
        self.assertEqual(5, len(self.entry.get_loops_by_category("_Vendor")))
        self.assertEqual(5, len(self.entry.get_loops_by_category("vendor")))

        self.assertEqual(self.entry.get_saveframe_by_name('assigned_chem_shift_list_1'), self.entry[-1])
        self.assertRaises(KeyError, self.entry.get_saveframe_by_name, 'no such saveframe')

        self.assertEqual(len(self.entry.get_saveframes_by_category("NMR_spectrometer")), 6)
        self.assertEqual(len(self.entry.get_saveframes_by_category("nmr_SPectrometer")), 0)
        self.assertEqual(self.entry.get_saveframes_by_category('no such category'), [])

        self.assertEqual(self.entry.get_saveframes_by_tag_and_value('Submission_date', '2006-09-07'), [self.entry[0]])
        self.assertEqual(self.entry.get_saveframes_by_tag_and_value('submission_Date', '2006-09-07'), [self.entry[0]])
        self.assertEqual(self.entry.get_saveframes_by_tag_and_value('test.submission_date', '2006-09-07'), [])

        self.assertRaises(ValueError, self.entry.get_tag, 'bad_tag')
        self.assertEqual(self.entry.get_tag("entry.Submission_date"), ['2006-09-07'])
        self.assertEqual(self.entry.get_tag("entry.Submission_date", whole_tag=True), [[u'Submission_date', u'2006-09-07']])

    def test_validate(self):
        validation = [u"Value cannot be NULL but is: '_Chem_comp.Provenance':'.' on line 'None'."]
        self.assertEqual(self.entry.validate(), validation)

    def test_saveframe(self):
        frame = self.entry[0]

        # Check initial state before tests
        self.assertEqual(frame.tags, [[u'Sf_category', u'entry_information'], [u'Sf_framecode', u'entry_information'], [u'ID', u'15000'], [u'Title', u'Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n'], [u'Type', u'macromolecule'], [u'Version_type', u'original'], [u'Submission_date', u'2006-09-07'], [u'Accession_date', u'2006-09-07'], [u'Last_release_date', u'.'], [u'Original_release_date', u'.'], [u'Origination', u'author'], [u'NMR_STAR_version', u'3.1.1.61'], [u'Original_NMR_STAR_version', u'.'], [u'Experimental_method', u'NMR'], [u'Experimental_method_subtype', u'solution'], [u'Details', u'.'], [u'BMRB_internal_directory_name', u'.']])

        # Check __delitem__
        del frame['DEtails']
        self.assertEqual(frame.tags, [[u'Sf_category', u'entry_information'], [u'Sf_framecode', u'entry_information'], [u'ID', u'15000'], [u'Title', u'Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n'], [u'Type', u'macromolecule'], [u'Version_type', u'original'], [u'Submission_date', u'2006-09-07'], [u'Accession_date', u'2006-09-07'], [u'Last_release_date', u'.'], [u'Original_release_date', u'.'], [u'Origination', u'author'], [u'NMR_STAR_version', u'3.1.1.61'], [u'Original_NMR_STAR_version', u'.'], [u'Experimental_method', u'NMR'], [u'Experimental_method_subtype', u'solution'], [u'BMRB_internal_directory_name', u'.']])
        self.assertEqual(len(frame), 7)
        del frame[0]
        self.assertEqual(len(frame), 6)
        del frame[frame.get_loop_by_category('RElease')]
        self.assertEqual(len(frame), 5)
        self.assertRaises(KeyError, frame.get_loop_by_category, 'RElease')

        # Check __getitem__
        self.assertEqual(frame['NMR_STAR_version'], ['3.1.1.61'])
        self.assertEqual(frame[0], frame.loops[0])
        self.assertEqual(frame['_SG_project'], frame.loops[0])

        # Check __lt__
        self.assertEqual(frame[-3] > frame[-1], False)

        # Check __init__
        self.assertRaises(ValueError, bmrb.Saveframe)
        self.assertEqual(bmrb.Saveframe.from_string(str(frame)), frame)
        self.assertEqual(str(bmrb.Saveframe.from_scratch("test", tag_prefix="test")), "\nsave_test\n\nsave_\n")
        tmp = copy(frame)
        tmp.loops = []
        tmp.name = ""
        self.assertEqual(bmrb.Saveframe.from_string(frame.get_data_as_csv(frame), csv=True).compare(tmp), [])
        self.assertRaises(ValueError, bmrb.Saveframe.from_string, "test.1,test.2\n2,3,4", csv=True)

        # Check __repr__
        self.assertEqual(repr(frame), "<bmrb.Saveframe 'entry_information'>")

        # Check __setitem__
        frame['test'] = 1
        self.assertEqual(frame.tags[-1][1], 1)
        frame['tESt'] = 2
        self.assertEqual(frame.tags[-1][1], 2)
        frame[4] = frame[3]
        self.assertEqual(frame.loops[3], frame.loops[4])

        # Check add_loop
        self.assertRaises(ValueError, frame.add_loop, frame.loops[0])

        # Check add_tag
        self.assertRaises(ValueError, frame.add_tag, "test", 1)
        self.assertRaises(ValueError, frame.add_tag, "invalid test", 1)
        self.assertRaises(ValueError, frame.add_tag, "invalid.test.test", 1)
        self.assertRaises(ValueError, frame.add_tag, "invalid.test", 1, update=True)
        frame.add_tag("test", 3, update=True)
        self.assertEqual(frame['test'], [3])

        # Check add_tags
        frame.add_tags([['example1'], ['example2']])
        self.assertEqual(frame.tags[-2], ['example1', "."])
        frame.add_tags([['example1', 5], ['example2']], update=True)
        self.assertEqual(frame.tags[-2], ['example1', 5])

        # Check compare
        self.assertEqual(frame.compare(frame), [])
        self.assertEqual(frame.compare(self.entry[1]), ["\tSaveframe names do not match: 'entry_information' vs 'citation_1'."])
        tmp = copy(frame)
        tmp.tag_prefix = "test"
        self.assertEqual(frame.compare(tmp), ["\tTag prefix does not match: '_Entry' vs 'test'."])
        tmp = copy(frame)
        tmp.tags[0][0] = "broken"
        self.assertEqual(frame.compare(tmp), ["\tNo tag with name '_Entry.Sf_category' in compared entry."])

        # Test delete_tag
        self.assertRaises(KeyError, frame.delete_tag, "this_tag_will_not_exist")
        frame.delete_tag("test")
        self.assertEqual(frame.get_tag("test"), [])

        # Test get_data_as_csv
        self.assertEqual(frame.get_data_as_csv(), '_Entry.Sf_category,_Entry.Sf_framecode,_Entry.ID,_Entry.Title,_Entry.Type,_Entry.Version_type,_Entry.Submission_date,_Entry.Accession_date,_Entry.Last_release_date,_Entry.Original_release_date,_Entry.Origination,_Entry.NMR_STAR_version,_Entry.Original_NMR_STAR_version,_Entry.Experimental_method,_Entry.Experimental_method_subtype,_Entry.BMRB_internal_directory_name,_Entry.example1,_Entry.example2\nentry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n",macromolecule,original,2006-09-07,2006-09-07,.,.,author,3.1.1.61,.,NMR,solution,.,5,.\n')
        self.assertEqual(frame.get_data_as_csv(show_category=False), 'Sf_category,Sf_framecode,ID,Title,Type,Version_type,Submission_date,Accession_date,Last_release_date,Original_release_date,Origination,NMR_STAR_version,Original_NMR_STAR_version,Experimental_method,Experimental_method_subtype,BMRB_internal_directory_name,example1,example2\nentry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n",macromolecule,original,2006-09-07,2006-09-07,.,.,author,3.1.1.61,.,NMR,solution,.,5,.\n')
        self.assertEqual(frame.get_data_as_csv(header=False), 'entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n",macromolecule,original,2006-09-07,2006-09-07,.,.,author,3.1.1.61,.,NMR,solution,.,5,.\n')
        self.assertEqual(frame.get_data_as_csv(show_category=False, header=False), 'entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n",macromolecule,original,2006-09-07,2006-09-07,.,.,author,3.1.1.61,.,NMR,solution,.,5,.\n')

        # Test get_loop_by_category
        self.assertEqual(repr(frame.get_loop_by_category("_SG_projecT")), "<bmrb.Loop '_SG_project'>")
        self.assertRaises(KeyError, frame.get_loop_by_category, 'this_loop_wont_be_found')

        # Test get_tag - this is really already tested in the other tests here
        self.assertEqual(frame.get_tag("sf_category"), ['entry_information'])
        self.assertEqual(frame.get_tag("entry.sf_category"), ['entry_information'])
        self.assertEqual(frame.get_tag("entry.sf_category", whole_tag=True), [[u'Sf_category', u'entry_information']])

        # Test sort
        self.assertEqual(frame.tags, [[u'Sf_category', u'entry_information'], [u'Sf_framecode', u'entry_information'], [u'ID', u'15000'], [u'Title', u'Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n'], [u'Type', u'macromolecule'], [u'Version_type', u'original'], [u'Submission_date', u'2006-09-07'], [u'Accession_date', u'2006-09-07'], [u'Last_release_date', u'.'], [u'Original_release_date', u'.'], [u'Origination', u'author'], [u'NMR_STAR_version', u'3.1.1.61'], [u'Original_NMR_STAR_version', u'.'], [u'Experimental_method', u'NMR'], [u'Experimental_method_subtype', u'solution'], [u'BMRB_internal_directory_name', u'.'], [u'example1', 5], [u'example2', u'.']])

        frame.sort_tags
        del frame['example2'], frame['example1']
        frame.tags.append(frame.tags.pop(0))
        frame.sort_tags()
        self.assertEqual(frame.tags, [[u'Sf_category', u'entry_information'], [u'Sf_framecode', u'entry_information'], [u'ID', u'15000'], [u'Title', u'Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n'], [u'Type', u'macromolecule'], [u'Version_type', u'original'], [u'Submission_date', u'2006-09-07'], [u'Accession_date', u'2006-09-07'], [u'Last_release_date', u'.'], [u'Original_release_date', u'.'], [u'Origination', u'author'], [u'NMR_STAR_version', u'3.1.1.61'], [u'Original_NMR_STAR_version', u'.'], [u'Experimental_method', u'NMR'], [u'Experimental_method_subtype', u'solution'], [u'BMRB_internal_directory_name', u'.']])

        # Test validate
        self.assertEqual(self.entry['assigned_chem_shift_list_1'].validate(), [])

        # Test set_tag_prefix
        frame.set_tag_prefix("new_prefix")
        self.assertEqual(frame.tag_prefix, "_new_prefix")


    def test_loop(self):
        test_loop = self.entry[0][0]

        # Check eq
        self.assertEqual(test_loop == self.entry[0][0], True)
        self.assertEqual(test_loop != self.entry[0][1], True)
        # Check __getitem__
        self.assertEqual(test_loop['_Entry_author.Ordinal'], ['1', '2', '3', '4', '5'])
        self.assertEqual(test_loop[['_Entry_author.Ordinal', '_Entry_author.Middle_initials']], [['1', 'C.'], ['2', '.'], ['3', 'B.'], ['4', 'H.'], ['5', 'L.']])
        # Test __setitem__
        test_loop['_Entry_author.Ordinal'] = [1]*5
        self.assertEqual(test_loop['_Entry_author.Ordinal'], [1,1,1,1,1])
        test_loop['_Entry_author.Ordinal'] = ['1','2','3','4','5']
        self.assertRaises(ValueError, test_loop.__setitem__, '_Entry_author.Ordinal', [1])
        self.assertRaises(ValueError, test_loop.__setitem__, '_Wrong_loop.Ordinal', [1,2,3,4,5])
        # Check __init__
        self.assertRaises(ValueError, bmrb.Loop)
        test = bmrb.Loop.from_scratch(category="test")
        self.assertEqual(test.category, "_test")
        self.assertEqual(bmrb.Loop.from_string(str(test_loop)), test_loop)
        self.assertEqual(test_loop, bmrb.Loop.from_string(test_loop.get_data_as_csv(), csv=True))
        # Check len
        self.assertEqual(len(test_loop), len(test_loop.data))
        # Check lt
        self.assertEqual(test_loop < self.entry[0][1], True)
        # Check __str__
        bmrb.SKIP_EMPTY_LOOPS = False
        self.assertEqual(str(bmrb.Loop.from_scratch()), "\n   loop_\n\n   stop_\n")
        bmrb.SKIP_EMPTY_LOOPS = True
        self.assertEqual(str(bmrb.Loop.from_scratch()), "")
        tmp_loop = bmrb.Loop.from_scratch()
        tmp_loop.data = [[1, 2, 3]]
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.add_column("column1")
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.add_column("column2")
        tmp_loop.add_column("column3")
        self.assertRaises(ValueError, tmp_loop.__str__)
        tmp_loop.set_category("test")
        self.assertEqual(str(tmp_loop), "\n   loop_\n      _test.column1\n      _test.column2\n      _test.column3\n\n     1   2   3    \n   stop_\n")
        self.assertEqual(tmp_loop.category, "_test")
        # Check different category
        self.assertRaises(ValueError, tmp_loop.add_column, "invalid.column")
        # Check duplicate tag
        self.assertRaises(ValueError, tmp_loop.add_column, "test.column3")
        self.assertEqual(tmp_loop.add_column("test.column3", ignore_duplicates=True), None)
        # Check space and period in tag
        self.assertRaises(ValueError, tmp_loop.add_column, "test. column")
        self.assertRaises(ValueError, tmp_loop.add_column, "test.column.test")

        # Check add_data
        self.assertRaises(ValueError, tmp_loop.add_data, [1, 2, 3, 4])
        tmp_loop.add_data([4, 5, 6])
        self.assertEqual(tmp_loop.data, [[1, 2, 3], [4, 5, 6]])

        # Check add_data_by_column
        # Wrong column order
        self.assertRaises(ValueError, tmp_loop.add_data_by_column, "column2", "data")
        # Invalid tag_prefix
        self.assertRaises(ValueError, tmp_loop.add_data_by_column, "invalid.column2", "data")
        # Column doesn't exist
        self.assertRaises(ValueError, tmp_loop.add_data_by_column, "column4", "data")
        # Valid adds
        tmp_loop.add_data_by_column("column1", 7)
        tmp_loop.add_data_by_column("test.column2", 8)
        tmp_loop.add_data_by_column("COLumn3", 9)
        self.assertEqual(tmp_loop.data, [[1, 2, 3], [4, 5, 6], [7, 8, 9]])

        # Test delete_data_by_tag_value
        self.assertEqual(tmp_loop.delete_data_by_tag_value("COLUMn1", 1, index_tag=0), [[1, 2, 3]])
        self.assertRaises(ValueError, tmp_loop.delete_data_by_tag_value, "column4", "data")
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

        # Test get_data_as_csv()
        self.assertEqual(tmp_loop.get_data_as_csv(), "_test.column1,_test.column2,_test.column3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False), "column1,column2,column3\n1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(header=False), "1,5,6\n2,8,9\n")
        self.assertEqual(tmp_loop.get_data_as_csv(show_category=False, header=False), "1,5,6\n2,8,9\n")

        # Test get_tag
        self.assertEqual(tmp_loop.get_data_by_tag("COLUmN1"), [[1, 2]])
        self.assertRaises(ValueError, tmp_loop.get_tag, "invalid.COLUmN1")
        self.assertEqual(tmp_loop.get_tag("COLUmN1"), [1, 2])
        self.assertEqual(tmp_loop.get_tag(["COLUmN1", "Column2"]), [[1, 5], [2, 8]])
        self.assertEqual(tmp_loop.get_tag("COLUmN1", whole_tag=True), [['_test.column1', 1], ['_test.column1', 2]])

        def simple_key(x):
            return -int(x[2])

        # Test sort_rows
        tmp_loop.sort_rows(["Column2"], key=simple_key)
        self.assertEqual(tmp_loop.data, [[2, 8, 9], [1, 5, 6]])
        tmp_loop.sort_rows(["Column2"])
        self.assertEqual(tmp_loop.data, [[1, 5, 6], [2, 8, 9]])

        # Test clear data
        tmp_loop.clear_data()
        self.assertEqual(tmp_loop.data, [])

        bmrb.SKIP_EMPTY_LOOPS = False

    def test_rename_saveframe(self):
        tmp = copy(database_entry)
        tmp.rename_saveframe('F5-Phe-cVHP', 'jons_frame')
        tmp.rename_saveframe('jons_frame', 'F5-Phe-cVHP')
        self.assertEqual(tmp, database_entry)

    def test_normalize(self):

        tmp = copy(database_entry)
        tmp.normalize()
        # Make sure the frames are already in the right order
        self.assertEqual(tmp.frame_list, database_entry.frame_list)

        # Shuffle our local entry
        random.shuffle(tmp.frame_list)
        for frame in tmp:
            random.shuffle(frame.loops)
            random.shuffle(frame.tags)

        # Might as well test equality testing while shuffled:
        self.assertEqual(tmp, database_entry)

        # Test that the frames are in a different order
        self.assertNotEqual(tmp.frame_list, database_entry.frame_list)
        tmp.normalize()
        # And test they have been put back together
        self.assertEqual(tmp.frame_list, database_entry.frame_list)

    # Parse and re-print entries to check for divergences. Only use in-house.
    def test_reparse(self):

        # Use a different parsing implementation as a sanity check
        # (used within the BMRB only)
        if not os.path.exists("/bmrb/linux/bin/stardiff"):
            return

        start, end = 15000, 15500
        sys.stdout.write("\nEntry tests: %5s/%5s" % (start, end))
        for x in range(start, end):

            location = '/share/subedit/entries/bmr%d/clean/bmr%d_3.str' % (x, x)
            try:
                with open(location, "r") as tmp:
                    orig_str = tmp.read()
                sys.stdout.write('\b' * 11 + "%5s/%5s" % (x, end))
                sys.stdout.flush()
            except IOError:
                continue

            ent = bmrb.Entry.from_string(orig_str)
            ent_str = str(ent)

            # The multiple quoted values thing makes this infeasable
            reent = bmrb.Entry.from_string(ent_str)
            self.assertEqual(reent, ent_str)

            if PY3:
                ent_str = ent_str.encode()

            compare = subprocess.Popen(["/bmrb/linux/bin/stardiff",
                                        "-ignore-tag",
                                        "_Spectral_peak_list.Text_data",
                                        "-", location],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
            results = compare.communicate(input=ent_str)[0]

            if PY3:
                results = results.decode()

            self.assertEqual("<standard input>:%s: NO DIFFERENCES REPORTED\n" %
                             location, results,
                             msg="%d: Output inconsistent with original: %s" %
                             (x, results.strip()))

# Allow unit testing from other modules
def start_tests():
    unittest.main(module=__name__)

# Run unit tests if we are called directly
if __name__ == '__main__':
    unittest.main()
