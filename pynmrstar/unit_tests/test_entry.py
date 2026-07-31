#!/usr/bin/env python3
import os
import random
import unittest
import warnings
from copy import deepcopy as copy
from pathlib import Path

from pynmrstar import Entry, Saveframe, Loop, Severity
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

    def test_validate_full(self):
        def structural(entry, **kwargs):
            """Only the saveframe-structure findings. An archived entry is
            structurally clean but does not carry every tag the dictionary
            wants, so the mandatory-tag findings are a separate question."""
            return [_ for _ in entry.validate_full(**kwargs) if _.check.startswith('saveframe.')]

        # A real archived entry is structurally clean
        self.assertEqual(structural(self.file_entry), [])

        entry = copy(self.file_entry)

        # The Sf_framecode tag disagreeing with the saveframe's own name. Set it
        # through the tag rather than through .name, which keeps the two in step.
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.get_tag('Sf_framecode', whole_tag=True)[0][1] = 'something_else'
        issues = structural(entry)
        self.assertEqual([_.check for _ in issues], ['saveframe.framecode_mismatch'])
        self.assertEqual(issues[0].severity, Severity.ERROR)
        self.assertEqual(issues[0].saveframe, frame.name)
        self.assertEqual(issues[0].value, 'something_else')
        self.assertEqual(issues[0].tag, '_Entry.Sf_framecode')

        # An Sf_category value that disagrees with the dictionary. The category
        # a saveframe *is* comes from its tags, so this is a wrong value, not a
        # different category -- nothing else should be reported.
        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.get_tag('Sf_category', whole_tag=True)[0][1] = 'not_a_category'
        issues = structural(entry)
        self.assertEqual([_.check for _ in issues], ['saveframe.invalid_category'])
        self.assertEqual(issues[0].category, 'entry_information')

        # A missing mandatory saveframe category
        entry = copy(self.file_entry)
        entry.remove_saveframe(entry.get_saveframes_by_category('citations')[0])
        issues = structural(entry)
        self.assertIn('saveframe.missing_mandatory_category', [_.check for _ in issues])

        # Profiles differ, and an unknown one is rejected. The internal view is
        # stricter than the public one, so it wants strictly more tags.
        self.assertEqual(structural(self.file_entry, profile='internal'), [])
        self.assertGreater(len(self.file_entry.validate_full(profile='internal')),
                           len(self.file_entry.validate_full(profile='public')))
        self.assertRaises(ValueError, self.file_entry.validate_full, profile='nope')

        # Severity filtering
        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.get_tag('Sf_framecode', whole_tag=True)[0][1] = 'something_else'
        self.assertEqual(entry.validate_full(severities=['warning']), [])
        self.assertEqual(len(structural(entry, severities=['error'])), 1)

    def test_validate_full_mandatory(self):
        entry = copy(self.file_entry)
        checks = lambda: [_ for _ in entry.validate_full(profile='internal') if _.check.startswith('tag.')]

        # Emptying a value-mandatory tag is reported as a missing value, and
        # removing it outright as a missing tag -- two different findings.
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.get_tag('_Entry.Title', whole_tag=True)[0][1] = '.'
        found = [_ for _ in checks() if _.tag == '_Entry.Title']
        self.assertEqual([_.check for _ in found], ['tag.missing_value'])

        frame.remove_tag('Title')
        found = [_ for _ in checks() if _.tag == '_Entry.Title']
        self.assertEqual([_.check for _ in found], ['tag.missing'])
        self.assertEqual(found[0].saveframe, frame.name)
        self.assertEqual(found[0].category, 'entry_information')

    def test_validate_full_invalid_tags(self):
        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]

        def invalid():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check in ('tag.unknown', 'tag.miscapitalized', 'tag.free_in_loop',
                                   'tag.duplicate', 'tag.invalid')]

        # An archived entry uses no tag it should not
        self.assertEqual(invalid(), [])

        # A tag the dictionary has never heard of
        frame.add_tag('_Entry.Bogus_invented_tag', 'fnord')
        found = invalid()
        self.assertEqual([_.check for _ in found], ['tag.unknown'])
        self.assertEqual(found[0].tag, '_Entry.Bogus_invented_tag')
        self.assertEqual(found[0].saveframe, frame.name)
        frame.remove_tag('Bogus_invented_tag')

        # A real tag spelled with the wrong capitalization. pynmrstar's own
        # lookups ignore case, but the dictionary does not, so this is reported
        # -- with the spelling it should have had.
        submission_date = frame.get_tag('_Entry.Submission_date', whole_tag=True)[0]
        submission_date[0] = 'SUBMISSION_date'
        found = invalid()
        self.assertEqual([_.check for _ in found], ['tag.miscapitalized'])
        self.assertIn("Should be '_Entry.Submission_date'", found[0].message)
        submission_date[0] = 'Submission_date'

        # A tag the profile forbids outright. _Entry.Sf_ID is bookkeeping the
        # internal view does not accept in the file.
        frame.add_tag('_Entry.Sf_ID', '1')
        self.assertEqual([_.check for _ in invalid()], ['tag.invalid'])
        frame.remove_tag('Sf_ID')

        # A loop whose columns are all tags the dictionary marks as free. That
        # is one category, so it parses, but every column is misplaced -- and
        # both columns are already free tags of this saveframe, so each is also
        # reported as a duplicate, once per occurrence.
        loop = Loop.from_scratch(category='_Entry')
        loop.add_tag(['_Entry.Experimental_method', '_Entry.Origination'])
        loop.add_data(['NMR', 'author'])
        frame.add_loop(loop)
        found = invalid()
        self.assertEqual(sorted(_.check for _ in found),
                         ['tag.duplicate'] * 4 + ['tag.free_in_loop'] * 2)
        self.assertEqual({_.tag for _ in found},
                         {'_Entry.Experimental_method', '_Entry.Origination'})

    def test_validate_full_tag_order(self):
        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]

        def order():
            return [_ for _ in entry.validate_full(profile='internal') if _.check == 'tag.order']

        # An archived entry is written in dictionary order
        self.assertEqual(order(), [])

        # Move the fourth of four consecutive tags to the front of them, so the
        # run reads 10, 40, 20, 30. Exactly one finding is right: order is
        # compared against the tag immediately before, so only the tag that
        # actually goes backwards is reported. Comparing against the highest
        # sequence seen so far would report the two after it as well.
        tags = frame.tags
        start = next(i for i in range(len(tags) - 3)
                     if not any('.' in tags[i + n][0] for n in range(4)))
        run = tags[start:start + 4]
        tags[start:start + 4] = [run[0], run[3], run[1], run[2]]

        found = order()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].tag, f'{frame.tag_prefix}.{run[1][0]}')
        self.assertEqual(found[0].saveframe, frame.name)
        self.assertIsNone(found[0].loop)
        self.assertIn('should be before', found[0].message)

    def test_validate_full_conditional(self):
        # _Citation.Journal_abbrev is required only of a journal citation, so
        # changing the citation's type changes whether its absence is reported.
        entry = copy(self.file_entry)
        citation = entry.get_saveframes_by_category('citations')[0]
        citation.get_tag('_Citation.Class', whole_tag=True)[0][1] = 'entry citation'

        def abbrev_reported():
            return any(_.tag == '_Citation.Journal_abbrev'
                       for _ in entry.validate_full(profile='internal'))

        citation.get_tag('_Citation.Type', whole_tag=True)[0][1] = 'journal'
        citation.remove_tag('Journal_abbrev')
        self.assertTrue(abbrev_reported())

        citation.get_tag('_Citation.Type', whole_tag=True)[0][1] = 'thesis'
        self.assertFalse(abbrev_reported())

    def test_validate_deprecated(self):
        # validate() still works, but says it is on the way out
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.file_entry.validate()
        self.assertTrue(any(issubclass(_.category, DeprecationWarning) for _ in caught))

    def test_validate(self):
        warnings.simplefilter("ignore", DeprecationWarning)
        # The sample entry spells two enumeration values with different
        # capitalization than the dictionary does
        validation = ["Value 'non-polymer' of tag '_Chem_comp.Type' is improperly capitalized but otherwise "
                      "valid. Should be 'NON-POLYMER'.",
                      "Value 'PDBe' of tag '_Chem_comp.Processing_site' is improperly capitalized but otherwise "
                      "valid. Should be 'PDBE'."]
        self.assertEqual(self.file_entry.validate(), validation)
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
