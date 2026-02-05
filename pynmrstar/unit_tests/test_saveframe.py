#!/usr/bin/env python3
import json
import os
import unittest
from copy import deepcopy as copy
from pathlib import Path

from pynmrstar import Saveframe, Loop, definitions, Entry
from pynmrstar.exceptions import ParsingError

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

    def test_saveframe(self):
        frame = self.file_entry[0]

        # Check __delitem__
        frame.remove_tag('DEtails')
        self.assertEqual([[x[0], x[1]] for x in frame.tags],
                         [['Sf_category', 'entry_information'],
                          ['Sf_framecode', 'entry_information'],
                          ['ID', '15000'],
                          ['Title',
                           'Solution structure of chicken villin headpiece subdomain containing a '
                           'fluorinated side chain in the core\n'],
                          ['Type', 'macromolecule'],
                          ['Version_type', 'original'],
                          ['Submission_date', '2006-09-07'],
                          ['Accession_date', '2006-09-07'],
                          ['Last_release_date', '2006-09-07'],
                          ['Original_release_date', '2006-09-07'],
                          ['Origination', 'author'],
                          ['Format_name', '.'],
                          ['NMR_STAR_version', '3.2.6.0'],
                          ['NMR_STAR_dict_location', '.'],
                          ['Original_NMR_STAR_version', '3.2.6.0'],
                          ['Experimental_method', 'NMR'],
                          ['Experimental_method_subtype', 'solution'],
                          ['Source_data_format', '.'],
                          ['Source_data_format_version', '.'],
                          ['Generated_software_name', '.'],
                          ['Generated_software_version', '.'],
                          ['Generated_software_ID', '.'],
                          ['Generated_software_label', '.'],
                          ['Generated_date', '.'],
                          ['DOI', '.'],
                          ['UUID', '.'],
                          ['Related_coordinate_file_name', '.'],
                          ['BMRB_internal_directory_name', '.']])
        self.assertEqual(len(frame), 7)
        del frame[0]
        self.assertEqual(len(frame), 6)
        del frame[frame.get_loop('RElease')]
        self.assertEqual(len(frame), 5)
        self.assertRaises(KeyError, frame.get_loop, 'RElease')

        # Check __getitem__
        self.assertEqual(frame.get_tag('NMR_STAR_version'), ['3.2.6.0'])
        self.assertEqual(frame[0], frame.loops[0])
        self.assertEqual(frame.get_loop('_SG_project'), frame.loops[0])

        # Check __lt__
        self.assertEqual(frame[-3] > frame[-1], False)

        # Check __init__
        self.assertRaises(ValueError, Saveframe)
        self.assertEqual(Saveframe.from_string(str(frame)), frame)
        self.assertEqual(str(Saveframe.from_scratch("test", tag_prefix="test")), "save_test\n\nsave_\n")
        tmp = copy(frame)
        tmp._loops = []
        self.assertEqual(Saveframe.from_string(frame.get_data_as_csv(frame), csv=True).compare(tmp), [])
        self.assertRaises(ValueError, Saveframe.from_string, "test.1,test.2\n2,3,4", csv=True)

        # Check __repr__
        self.assertEqual(repr(frame), "<pynmrstar.Saveframe 'entry_information'>")

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
        self.assertEqual(frame.get_tag('test'), [3])

        # Check add_tags
        frame.add_tags([['example1'], ['example2']])
        self.assertEqual(frame.tags[-2], ['example1', "."])
        frame.add_tags([['example1', 5], ['example2']], update=True)
        self.assertEqual(frame.tags[-2], ['example1', 5])

        # Check compare
        self.assertEqual(frame.compare(frame), [])
        self.assertEqual(frame.compare(self.file_entry[1]),
                         ["\tSaveframe names do not match: 'entry_information' vs 'citation_1'."])
        tmp = copy(frame)
        tmp.tag_prefix = "test"
        self.assertEqual(frame.compare(tmp), ["\tTag prefix does not match: '_Entry' vs 'test'."])
        tmp = copy(frame)
        tmp.tags[0][0] = "broken"
        self.assertEqual(frame.compare(tmp), ["\tNo tag with name '_Entry.Sf_category' in compared entry."])

        # Test remove_tag
        self.assertRaises(KeyError, frame.remove_tag, "this_tag_will_not_exist")
        frame.remove_tag("test")
        self.assertEqual(frame.get_tag("test"), [])

        # Test get_data_as_csv
        self.assertEqual(frame.get_data_as_csv(),
                         '''_Entry.Sf_category,_Entry.Sf_framecode,_Entry.ID,_Entry.Title,_Entry.Type,_Entry.Version_type,_Entry.Submission_date,_Entry.Accession_date,_Entry.Last_release_date,_Entry.Original_release_date,_Entry.Origination,_Entry.Format_name,_Entry.NMR_STAR_version,_Entry.NMR_STAR_dict_location,_Entry.Original_NMR_STAR_version,_Entry.Experimental_method,_Entry.Experimental_method_subtype,_Entry.Source_data_format,_Entry.Source_data_format_version,_Entry.Generated_software_name,_Entry.Generated_software_version,_Entry.Generated_software_ID,_Entry.Generated_software_label,_Entry.Generated_date,_Entry.DOI,_Entry.UUID,_Entry.Related_coordinate_file_name,_Entry.BMRB_internal_directory_name,_Entry.example1,_Entry.example2
entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core
",macromolecule,original,2006-09-07,2006-09-07,2006-09-07,2006-09-07,author,.,3.2.6.0,.,3.2.6.0,NMR,solution,.,.,.,.,.,.,.,.,.,.,.,5,.
''')
        self.assertEqual(frame.get_data_as_csv(show_category=False),
                         '''Sf_category,Sf_framecode,ID,Title,Type,Version_type,Submission_date,Accession_date,Last_release_date,Original_release_date,Origination,Format_name,NMR_STAR_version,NMR_STAR_dict_location,Original_NMR_STAR_version,Experimental_method,Experimental_method_subtype,Source_data_format,Source_data_format_version,Generated_software_name,Generated_software_version,Generated_software_ID,Generated_software_label,Generated_date,DOI,UUID,Related_coordinate_file_name,BMRB_internal_directory_name,example1,example2
entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core
",macromolecule,original,2006-09-07,2006-09-07,2006-09-07,2006-09-07,author,.,3.2.6.0,.,3.2.6.0,NMR,solution,.,.,.,.,.,.,.,.,.,.,.,5,.
''')
        self.assertEqual(frame.get_data_as_csv(header=False),
                         '''entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core
",macromolecule,original,2006-09-07,2006-09-07,2006-09-07,2006-09-07,author,.,3.2.6.0,.,3.2.6.0,NMR,solution,.,.,.,.,.,.,.,.,.,.,.,5,.
''')
        self.assertEqual(frame.get_data_as_csv(show_category=False, header=False),
                         '''entry_information,entry_information,15000,"Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core
",macromolecule,original,2006-09-07,2006-09-07,2006-09-07,2006-09-07,author,.,3.2.6.0,.,3.2.6.0,NMR,solution,.,.,.,.,.,.,.,.,.,.,.,5,.
''')

        # Test get_loop
        self.assertEqual(repr(frame.get_loop("_SG_projecT")), "<pynmrstar.Loop '_SG_project'>")
        self.assertRaises(KeyError, frame.get_loop, 'this_loop_wont_be_found')

        # Test get_tag - this is really already tested in the other tests here
        self.assertEqual(frame.get_tag("sf_category"), ['entry_information'])
        self.assertEqual(frame.get_tag("entry.sf_category"), ['entry_information'])
        self.assertEqual(frame.get_tag("entry.sf_category", whole_tag=True), [['Sf_category', 'entry_information']])

        # Test sort
        self.assertEqual([[x[0], x[1]] for x in frame.tags], [['Sf_category', 'entry_information'],
                                                              ['Sf_framecode', 'entry_information'],
                                                              ['ID', '15000'],
                                                              ['Title',
                                                               'Solution structure of chicken villin headpiece subdomain containing a '
                                                               'fluorinated side chain in the core\n'],
                                                              ['Type', 'macromolecule'],
                                                              ['Version_type', 'original'],
                                                              ['Submission_date', '2006-09-07'],
                                                              ['Accession_date', '2006-09-07'],
                                                              ['Last_release_date', '2006-09-07'],
                                                              ['Original_release_date', '2006-09-07'],
                                                              ['Origination', 'author'],
                                                              ['Format_name', '.'],
                                                              ['NMR_STAR_version', '3.2.6.0'],
                                                              ['NMR_STAR_dict_location', '.'],
                                                              ['Original_NMR_STAR_version', '3.2.6.0'],
                                                              ['Experimental_method', 'NMR'],
                                                              ['Experimental_method_subtype', 'solution'],
                                                              ['Source_data_format', '.'],
                                                              ['Source_data_format_version', '.'],
                                                              ['Generated_software_name', '.'],
                                                              ['Generated_software_version', '.'],
                                                              ['Generated_software_ID', '.'],
                                                              ['Generated_software_label', '.'],
                                                              ['Generated_date', '.'],
                                                              ['DOI', '.'],
                                                              ['UUID', '.'],
                                                              ['Related_coordinate_file_name', '.'],
                                                              ['BMRB_internal_directory_name', '.'],
                                                              ['example1', 5],
                                                              ['example2', '.']])

        frame.remove_tag(['example2', 'example1'])
        frame.tags.append(frame.tags.pop(0))
        frame.sort_tags()
        self.assertEqual([[x[0], x[1]] for x in frame.tags], [['Sf_category', 'entry_information'],
                                                              ['Sf_framecode', 'entry_information'],
                                                              ['ID', '15000'],
                                                              ['Title',
                                                               'Solution structure of chicken villin headpiece subdomain containing a '
                                                               'fluorinated side chain in the core\n'],
                                                              ['Type', 'macromolecule'],
                                                              ['Version_type', 'original'],
                                                              ['Submission_date', '2006-09-07'],
                                                              ['Accession_date', '2006-09-07'],
                                                              ['Last_release_date', '2006-09-07'],
                                                              ['Original_release_date', '2006-09-07'],
                                                              ['Origination', 'author'],
                                                              ['Format_name', '.'],
                                                              ['NMR_STAR_version', '3.2.6.0'],
                                                              ['NMR_STAR_dict_location', '.'],
                                                              ['Original_NMR_STAR_version', '3.2.6.0'],
                                                              ['Experimental_method', 'NMR'],
                                                              ['Experimental_method_subtype', 'solution'],
                                                              ['Source_data_format', '.'],
                                                              ['Source_data_format_version', '.'],
                                                              ['Generated_software_name', '.'],
                                                              ['Generated_software_version', '.'],
                                                              ['Generated_software_ID', '.'],
                                                              ['Generated_software_label', '.'],
                                                              ['Generated_date', '.'],
                                                              ['DOI', '.'],
                                                              ['UUID', '.'],
                                                              ['Related_coordinate_file_name', '.'],
                                                              ['BMRB_internal_directory_name', '.']])

        # Test validate
        self.assertEqual(self.file_entry['assigned_chem_shift_list_1'].validate(), [])

        # Test set_tag_prefix
        frame.set_tag_prefix("new_prefix")
        self.assertEqual(frame.tag_prefix, "_new_prefix")

    def test_Saveframe_add_tag(self):
        """ Test the add_tag functionality of a saveframe. """

        # Test that you cannot set the framecode to a null value
        test_sf = Saveframe.from_scratch('test')

        # Test that the initial setter can't set a null value
        with self.assertRaises(ValueError):
            test_sf.add_tag('sf_framecode', None)
        test_sf.add_tag('sf_framecode', 'test')

        # Test that updating both via add_tag(update=True) and .name= don't
        # allow for setting a null value
        for val in definitions.NULL_VALUES:
            with self.assertRaises(ValueError):
                test_sf.add_tag('sf_framecode', val)
            with self.assertRaises(ValueError):
                test_sf.name = val

        # Test that adding an sf_framecode with a different value than the
        #  saveframe name throws an exception
        with self.assertRaises(ValueError):
            test_sf_two = Saveframe.from_scratch('test')
            test_sf_two.add_tag('sf_framecode', 'different')

    def test_duplicate_loop_detection(self):
        one = Loop.from_scratch(category="duplicate")
        two = Loop.from_scratch(category="duplicate")
        frame = Saveframe.from_scratch('1')
        frame.add_loop(one)
        self.assertRaises(ValueError, frame.add_loop, two)
