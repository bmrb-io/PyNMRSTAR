#!/usr/bin/env python3
import os
import random
import unittest
from copy import deepcopy as copy
from pathlib import Path

from pynmrstar import Entry, Saveframe, Loop
from pynmrstar.exceptions import ParsingError

our_path = os.path.dirname(os.path.realpath(__file__))
database_entry = Entry.from_database(15000)
sample_file_location = os.path.join(our_path, "sample_files", "bmr15000_3.str")
sample_saveframe_location = os.path.join(our_path, "sample_files", "saveframe.txt")
sample_loop_location = os.path.join(our_path, "sample_files", "loop.txt")
file_entry = Entry.from_file(sample_file_location)


class TestEntry(unittest.TestCase):

    def setUp(self):
        self.file_entry = copy(file_entry)
        self.maxDiff = None

    def test_edge_cases(self):
        """ Make sure that the various types of edge cases are properly handled. """

        Entry.from_file(os.path.join(our_path, 'sample_files', 'edge_cases.str'))
        Entry.from_file(os.path.join(our_path, 'sample_files', 'dos.str'))
        Entry.from_file(os.path.join(our_path, 'sample_files', 'nonewlines.str'))
        Entry.from_file(os.path.join(our_path, 'sample_files', 'onlynewlines.str'))

    def test_entry_delitem(self):
        tmp_entry = copy(self.file_entry)
        tmp_entry.frame_list.pop(0)
        del self.file_entry[0]
        self.assertEqual(self.file_entry, tmp_entry)

    def test_duplicate_saveframe_errors(self):
        tmp_entry = copy(self.file_entry)
        self.assertRaises(ValueError, tmp_entry.add_saveframe, tmp_entry[0])
        tmp_entry.frame_list.append(tmp_entry[0])
        self.assertRaises(ValueError, tmp_entry.__getattribute__, 'frame_dict')

    def test_entry_eq(self):
        # Normalize them both first
        db_copy = copy(database_entry)
        db_copy.normalize()
        self.file_entry.normalize()
        self.assertEqual(self.file_entry, db_copy)

    def test_getitem(self):
        self.assertEqual(self.file_entry['entry_information'],
                         self.file_entry.get_saveframe_by_name("entry_information"))
        self.assertEqual(self.file_entry[0], self.file_entry.get_saveframe_by_name("entry_information"))

        # Slices, and anything else a list accepts as an index (such as numpy integers), work as for a list
        class Index:
            def __index__(self):
                return 1

        self.assertEqual(self.file_entry[0:2], list(self.file_entry.frame_list[0:2]))
        self.assertEqual(self.file_entry[Index()], self.file_entry.frame_list[1])

        self.assertRaises(KeyError, lambda: self.file_entry['no_such_saveframe'])
        self.assertRaises(IndexError, lambda: self.file_entry[10000])
        for invalid in (1.0, None, b'entry_information'):
            with self.subTest(invalid=invalid):
                self.assertRaises(ValueError, lambda: self.file_entry[invalid])

    def test_init(self):
        # Make sure the correct errors are raised
        self.assertRaises(ValueError, Entry)
        self.assertRaises(ParsingError, Entry, the_string="test", entry_num="test")
        # Make sure string parsing is correct
        self.assertEqual(self.file_entry, Entry.from_string(str(self.file_entry)))
        self.assertEqual(str(self.file_entry), str(Entry.from_string(str(self.file_entry))))
        self.assertRaises(IOError, Entry.from_database, 0)

        self.assertEqual(str(Entry.from_scratch(15000)), "data_15000\n\n")
        self.assertEqual(Entry.from_file(os.path.join(our_path, "sample_files", "bmr15000_3.str.gz")), self.file_entry)

    def test_from_file_path_support(self):
        """Test that from_file methods support pathlib.Path objects."""

        # Test Entry.from_file with Path object
        path_obj = Path(sample_file_location)
        entry_from_path = Entry.from_file(path_obj)
        self.assertEqual(entry_from_path, self.file_entry)

    def test___setitem(self):
        tmp_entry = copy(self.file_entry)
        tmp_entry[0] = tmp_entry.get_saveframe_by_name('entry_information')
        self.assertEqual(tmp_entry, self.file_entry)
        tmp_entry['entry_information'] = tmp_entry.get_saveframe_by_name('entry_information')
        self.assertEqual(tmp_entry, self.file_entry)

        self.assertRaises(ValueError, tmp_entry.__setitem__, 'entry_informations',
                          tmp_entry.get_saveframe_by_name('entry_information'))
        self.assertRaises(ValueError, tmp_entry.__setitem__, 'entry_information', 1)

    def test_compare(self):
        self.assertEqual(self.file_entry.compare(str(self.file_entry)), [])
        self.assertEqual(self.file_entry.compare(self.file_entry), [])

        mutated = copy(self.file_entry)
        mutated.frame_list.pop()
        self.assertEqual(self.file_entry.compare(mutated),
                         ["The number of saveframes in the entries are not equal: '25' vs '24'.",
                          "No saveframe with name 'assigned_chem_shift_list_1' in other entry."])

    def test_getmethods(self):
        self.assertEqual(5, len(self.file_entry.get_loops_by_category("_Vendor")))
        self.assertEqual(5, len(self.file_entry.get_loops_by_category("vendor")))

        self.assertEqual(self.file_entry.get_saveframe_by_name('assigned_chem_shift_list_1'), self.file_entry[-1])
        self.assertRaises(KeyError, self.file_entry.get_saveframe_by_name, 'no such saveframe')

        self.assertEqual(len(self.file_entry.get_saveframes_by_category("NMR_spectrometer")), 6)
        self.assertEqual(len(self.file_entry.get_saveframes_by_category("nmr_SPectrometer")), 0)
        self.assertEqual(self.file_entry.get_saveframes_by_category('no such category'), [])

        self.assertEqual(self.file_entry.get_saveframes_by_tag_and_value('Submission_date', '2006-09-07'),
                         [self.file_entry[0]])
        self.assertEqual(self.file_entry.get_saveframes_by_tag_and_value('submission_Date', '2006-09-07'),
                         [self.file_entry[0]])
        self.assertEqual(self.file_entry.get_saveframes_by_tag_and_value('test.submission_date', '2006-09-07'), [])

        self.assertRaises(ValueError, self.file_entry.get_tag, 'bad_tag')
        self.assertEqual(self.file_entry.get_tag("entry.Submission_date"), ['2006-09-07'])
        self.assertEqual(self.file_entry.get_tag("entry.Submission_date", whole_tag=True),
                         [[u'Submission_date', u'2006-09-07']])

    def test_validate(self):
        validation = []
        self.assertEqual(self.file_entry.validate(), [])
        self.file_entry[-1][-1][0][0] = 'a'
        validation.append(
            "Value does not match specification: '_Atom_chem_shift.ID':'a'.\n     "
            "Type specified: int\n     Regular expression for type: '^(?:-?[0-9]*)?$'")
        self.assertEqual(self.file_entry.validate(), validation)
        self.file_entry[-1][-1][0][0] = '1'

    def test_Entry___setitem__(self):
        """ Test the setting a tag functionality of an entry. """

        test_entry = Entry.from_scratch('test')
        test_saveframe = Saveframe.from_scratch('test', 'test')
        test_entry._frame_list = [test_saveframe, test_saveframe]
        with self.assertRaises(ValueError):
            test_entry['test'] = test_saveframe

    def test_category_list(self):
        """ Test the category list property. """

        tmp = copy(self.file_entry)
        self.assertEqual(tmp.category_list, ['entry_information', 'citations', 'assembly', 'entity', 'natural_source',
                                             'experimental_source', 'chem_comp', 'sample', 'sample_conditions',
                                             'software', 'NMR_spectrometer', 'NMR_spectrometer_list', 'experiment_list',
                                             'chem_shift_reference', 'assigned_chemical_shifts'])
        tmp.add_saveframe(Saveframe.from_scratch("test", None))
        self.assertEqual(tmp.category_list, ['entry_information', 'citations', 'assembly', 'entity', 'natural_source',
                                             'experimental_source', 'chem_comp', 'sample', 'sample_conditions',
                                             'software', 'NMR_spectrometer', 'NMR_spectrometer_list', 'experiment_list',
                                             'chem_shift_reference', 'assigned_chemical_shifts'])

    def test_rename_saveframe(self):
        tmp = copy(self.file_entry)
        tmp.rename_saveframe('F5-Phe-cVHP', 'jons_frame')
        tmp.rename_saveframe('jons_frame', 'F5-Phe-cVHP')
        self.assertEqual(tmp, self.file_entry)

    def test_normalize(self):

        db_tmp = copy(self.file_entry)
        denormalized = Entry.from_file(os.path.join(our_path, "sample_files", "bmr15000_3_denormalized.str"))
        denormalized.normalize()
        self.assertEqual(db_tmp.compare(denormalized), [])

        # Shuffle our local entry
        random.shuffle(db_tmp.frame_list)
        for frame in db_tmp:
            random.shuffle(frame.loops)
            random.shuffle(frame.tags)

        # Might as well test equality testing while shuffled:
        self.assertEqual(db_tmp.compare(self.file_entry), [])

        # Test that the frames are in a different order
        self.assertNotEqual(db_tmp.frame_list, self.file_entry.frame_list)
        db_tmp.normalize()

        self.assertEqual(db_tmp.frame_list, self.file_entry.frame_list)

        # Now test ordering of saveframes when tags may be missing
        b = Saveframe.from_scratch('not_real2')
        b.add_tag('_help.Sf_category', 'a')
        b.add_tag('_help.ID', 1)
        c = Saveframe.from_scratch('not_real')
        c.add_tag('_help.Sf_category', 'a')
        c.add_tag('_help.ID', 'a')
        d = Saveframe.from_scratch('not_real3')
        d.add_tag('_help.borg', 'a')

        db_tmp.add_saveframe(b)
        db_tmp.add_saveframe(c)
        db_tmp.add_saveframe(d)

        correct_order = db_tmp.frame_list[:]
        random.shuffle(db_tmp.frame_list)
        db_tmp.normalize()
        self.assertEqual(db_tmp.frame_list, correct_order)
