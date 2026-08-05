#!/usr/bin/env python3
import os
import random
import unittest
import warnings
from copy import deepcopy as copy
from pathlib import Path

from pynmrstar import Entry, Saveframe, Loop, Severity, utils
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

    def test_validate_full_mandatory_first_value_only(self):
        """A value-mandatory tag in a loop is judged on its *first* value.

        This is what the BMRB validator does -- CheckMandatoryTags reads one row
        of its result set and never loops -- and it is not what testing every
        value would do. Pinned in both directions because getting it wrong in
        either is silent: `all(...)` under-reports (which it did, missing two
        findings the Java tool makes on bmr7154) and `any(...)` would
        over-report.
        """

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('sample_conditions')[0]
        loop = frame['_Sample_condition_variable']
        column = loop.tags.index('Val')
        self.assertGreater(len(loop.data), 1, 'the fixture needs a multi-row loop')

        def missing_value():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check == 'tag.missing_value' and _.tag == '_Sample_condition_variable.Val']

        # Every row populated: nothing to report.
        self.assertEqual(missing_value(), [])

        # Null in a row that is not the first: the original never looks at it.
        original = loop.data[-1][column]
        loop.data[-1][column] = '.'
        self.assertEqual(missing_value(), [])
        loop.data[-1][column] = original

        # Null in the first row: reported, even though every other row has one.
        original = loop.data[0][column]
        loop.data[0][column] = '.'
        found = missing_value()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].saveframe, frame.name)
        loop.data[0][column] = original

    def test_fix_framecodes(self):
        """Both halves of the BMRB validator's FixFramecodes (75)."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]

        # Half one: Sf_framecode is set to the saveframe's own name. Written
        # through the tag pair rather than the name setter, because the setter
        # keeps the two in step and the inconsistency only ever arrives from a
        # parsed file.
        frame.get_tag('Sf_framecode', whole_tag=True)[0][1] = 'something_else'
        entry.fix_framecodes()
        self.assertEqual(frame.get_tag('Sf_framecode')[0], frame.name)

        # Half two: whitespace inside a saveframe-pointer value collapses to a
        # single underscore -- a framecode with a space cannot be written as a
        # $reference.
        shifts = entry.get_saveframes_by_category('assigned_chemical_shifts')[0]
        shifts.get_tag('Sample_condition_list_label', whole_tag=True)[0][1] = '$a b\tc'
        entry.fix_framecodes()
        self.assertEqual(shifts.get_tag('Sample_condition_list_label')[0], '$a_b_c')

    def test_fix_framecodes_leaves_nulls_alone(self):
        """The original's query excludes NULL, '.' and '?' explicitly: a missing
        reference is not a misspelt one."""

        entry = copy(self.file_entry)
        shifts = entry.get_saveframes_by_category('assigned_chemical_shifts')[0]
        for null in ('.', '?'):
            shifts.get_tag('Sample_condition_list_label', whole_tag=True)[0][1] = null
            entry.fix_framecodes()
            self.assertEqual(shifts.get_tag('Sample_condition_list_label')[0], null)

    def test_mark_framecode_values(self):
        """MarkFramecodeValues (73): every saveframe pointer carries its $.

        A no-op on an entry read from a well-formed file, since pynmrstar keeps
        the marker in the value -- so the test has to take one off first, which
        is the state an entry assembled through the API arrives in."""

        entry = copy(self.file_entry)
        shifts = entry.get_saveframes_by_category('assigned_chemical_shifts')[0]
        pointer = shifts.get_tag('Sample_condition_list_label', whole_tag=True)[0]
        self.assertTrue(pointer[1].startswith('$'))

        pointer[1] = pointer[1].lstrip('$')
        entry.mark_framecode_values()
        self.assertEqual(pointer[1], f'${shifts.get_tag("Sample_condition_list_label")[0].lstrip("$")}')
        self.assertTrue(pointer[1].startswith('$'))

        # Idempotent: running it again must not stack markers.
        entry.mark_framecode_values()
        self.assertFalse(pointer[1].startswith('$$'))

    def test_normalize_repairs_framecodes(self):
        """normalize() includes the framecode repairs, deliberately.

        It means normalizing can remove a validation finding: validate_full()
        reports a Sf_framecode that disagrees with its saveframe's name, and
        this fixes exactly that. BMRB's call -- there is no harm in repairing it
        without warning first -- but it is worth a test saying so out loud, so
        that nobody 'fixes' the interaction later by accident."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.get_tag('Sf_framecode', whole_tag=True)[0][1] = 'something_else'

        # The mismatch is a finding before normalizing ...
        mismatches = [_ for _ in entry.validate_full(profile='internal')
                      if _.check == 'saveframe.framecode_mismatch']
        self.assertEqual(len(mismatches), 1)

        # ... and normalize() repairs it, so it is not one afterwards.
        entry.normalize()
        self.assertEqual(frame.get_tag('Sf_framecode')[0], frame.name)
        self.assertEqual([_ for _ in entry.validate_full(profile='internal')
                          if _.check == 'saveframe.framecode_mismatch'], [])

    def test_insert_local_ids(self):
        """InsertLocalIDs (100): a per-category counter, in document order."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entity')[0]
        frame.get_tag('ID', whole_tag=True)[0][1] = '99'

        entry.insert_local_ids()
        self.assertEqual(frame.get_tag('ID')[0], '1')

        # The counter is per category and follows document order.
        for position, each in enumerate(entry.get_saveframes_by_category('entity'), start=1):
            self.assertEqual(each.get_tag('ID')[0], str(position))

    def test_insert_local_ids_leaves_entry_id_alone(self):
        """Entry_ID tags carry the accession number, not a per-category counter.

        They have lclSfIdFlg set, so a port that keys on that flag alone
        overwrites every one of them with '1'. Schema.local_id_tags already
        excludes _Entry.ID and the *.Entry_ID tags; this checks it stays that
        way."""

        entry = copy(self.file_entry)
        before = entry.get_saveframes_by_category('entity')[0].get_tag('Entry_ID')[0]
        entry.insert_local_ids()
        self.assertEqual(entry.get_saveframes_by_category('entity')[0].get_tag('Entry_ID')[0], before)

    def test_add_row_indexes(self):
        """AddRowIndexes (85), including the part that is easy to get wrong."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        loop = frame['_Entry_author']
        position = loop.tags.index('Ordinal')

        # A gap is filled, and the whole column is renumbered from 1.
        loop.data[1][position] = '.'
        entry.add_row_indexes()
        self.assertEqual([_[position] for _ in loop.data],
                         [str(_) for _ in range(1, len(loop.data) + 1)])

    def test_add_row_indexes_leaves_a_complete_column_alone(self):
        """A loop whose index column has no gap is not touched at all -- even
        when the numbering is wrong.

        That is the original's behaviour and it is load-bearing: its query looks
        for a row-index tag having at least one null value and returns without
        touching the loop if it finds none. Renumbering unconditionally, which
        is the natural thing to write, would silently repair what
        CheckRowIndexes (18) exists to report."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        loop = frame['_Entry_author']
        position = loop.tags.index('Ordinal')

        wrong = [str(_ * 10) for _ in range(1, len(loop.data) + 1)]
        for row, value in zip(loop.data, wrong):
            row[position] = value
        entry.add_row_indexes()
        self.assertEqual([_[position] for _ in loop.data], wrong)

    def test_insert_mandatory_tags(self):
        """InsertMandatoryTags (105): a missing required free tag arrives as '?'."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        self.assertEqual(frame.get_tag('Title'), file_entry.get_tag('_Entry.Title'))
        frame.remove_tag('Title')

        entry.insert_mandatory_tags(profile='internal')
        self.assertEqual(frame.get_tag('Title'), ['?'])

    def test_insert_mandatory_tags_skips_optional_and_auto(self):
        """Two kinds of tag it must not add, for two different reasons.

        An optional tag is nobody's to add. An *auto-inserted* one is the
        depositing tool's -- and since every tag carrying a dictionary default
        value is in that set, this is also what makes the value written by this
        method always '?'. Judged on what the method *adds*, since an entry read
        from a file already carries plenty of both, and on the free tags alone,
        since a loop it has to create deliberately arrives whole."""

        entry = copy(self.file_entry)
        schema = utils.get_schema()
        frame = entry.get_saveframes_by_category('entry_information')[0]
        codes = schema.validation_profile('internal')['tags']

        def entry_tags(kind) -> set:
            return {_ for _ in schema.schema
                    if schema.schema[_].get('SFCategory') == 'entry_information'
                    and (schema.schema[_].get('Loopflag') or '').strip() != 'Y'
                    and (kind(codes.get(_), _ in schema.auto_inserted_tags))}

        optional = entry_tags(lambda code, auto: code == 'O' and not auto)
        auto = entry_tags(lambda code, auto: code in ('M', 'V') and auto)
        self.assertTrue(optional and auto)

        def present() -> set:
            return {f'{frame.tag_prefix}.{name}'.lower() for name, _ in frame.tags}

        before = present()
        entry.insert_mandatory_tags(profile='internal')
        added = present() - before
        self.assertTrue(added)
        self.assertEqual(added.intersection(optional | auto), set())

    def test_insert_mandatory_tags_creates_a_missing_loop(self):
        """A required tag whose whole loop is missing brings the loop with it --
        every column of the category, one row, the row index numbered 0."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame.remove_loop(frame['_Entry_author'])

        entry.insert_mandatory_tags(profile='internal', entry_id='NEED_ACC_NUM')
        loop = frame['_Entry_author']

        self.assertEqual(len(loop.data), 1)
        self.assertEqual(loop.data[0][loop.tag_index('Ordinal')], '0')
        self.assertEqual(loop.data[0][loop.tag_index('Entry_ID')], 'NEED_ACC_NUM')
        self.assertEqual(loop.data[0][loop.tag_index('Family_name')], '?')
        # Optional columns come along too: the loop is a form to fill in.
        self.assertIn('middle_initials', [_.lower() for _ in loop.tags])
        # Sf_ID is bookkeeping, not a column for anyone to fill in.
        self.assertNotIn('sf_id', [_.lower() for _ in loop.tags])

    def test_insert_mandatory_tags_fills_an_existing_loop(self):
        """A loop that exists gets the missing column, valued in every row."""

        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]
        loop = frame['_Entry_author']
        self.assertGreater(len(loop.data), 1)
        position = loop.tag_index('Family_name')
        for row in loop.data:
            del row[position]
        del loop.tags[position]
        loop._lc_tags_cache = None

        entry.insert_mandatory_tags(profile='internal')
        loop = frame['_Entry_author']
        self.assertEqual([_[loop.tag_index('Family_name')] for _ in loop.data],
                         ['?'] * len(loop.data))

    def test_insert_mandatory_tags_honours_a_conditional_rule(self):
        """A conditional rule decides it, and it is scoped to the saveframe.

        _Entity.Nstd_monomer is value-mandatory, except in an entity whose Type
        is 'non-polymer', where the dictionary demotes it to optional. Two
        entities differing only in that tag must therefore come out
        differently."""

        entry = copy(self.file_entry)
        polymer, non_polymer = entry.get_saveframes_by_category('entity')[0], None
        non_polymer = copy(polymer)
        non_polymer.name = 'entity_non_polymer'
        for frame in (polymer, non_polymer):
            frame.remove_tag('Nstd_monomer')
        polymer.add_tag('Type', 'polymer', update=True)
        non_polymer.add_tag('Type', 'non-polymer', update=True)
        entry.add_saveframe(non_polymer)

        entry.insert_mandatory_tags(profile='internal')
        self.assertEqual(polymer.get_tag('Nstd_monomer'), ['?'])
        self.assertEqual(non_polymer.get_tag('Nstd_monomer'), [])

    def _pointer_entry(self, chem_comps=('LIG',)) -> Entry:
        """An entry with one entity pointing at nothing in particular, and as
        many chem_comp saveframes as asked for."""

        entry = Entry.from_scratch('related')
        for name in chem_comps:
            frame = Saveframe.from_scratch(f'chem_comp_{name}', tag_prefix='_Chem_comp')
            frame.add_tags([['Sf_category', 'chem_comp'], ['Sf_framecode', f'chem_comp_{name}'],
                            ['ID', name]])
            entry.add_saveframe(frame)

        entity = Saveframe.from_scratch('entity_1', tag_prefix='_Entity')
        entity.add_tags([['Sf_category', 'entity'], ['Sf_framecode', 'entity_1'], ['ID', '1'],
                         ['Parent_entity_ID', '7'],
                         ['Nonpolymer_comp_ID', '.'], ['Nonpolymer_comp_label', '.']])
        entry.add_saveframe(entity)
        return entry

    def test_update_related_tags_fills_a_lone_pointer(self):
        """UpdateRelatedTags (101), passes 1 and 2: an empty pointer is filled in
        when the entry holds exactly one saveframe it could mean, and the ID
        beside it is then resolved from it."""

        entry = self._pointer_entry()
        entry.update_related_tags()
        entity = entry.get_saveframe_by_name('entity_1')

        self.assertEqual(entity.get_tag('Nonpolymer_comp_label'), ['$chem_comp_LIG'])
        self.assertEqual(entity.get_tag('Nonpolymer_comp_ID'), ['LIG'])

    def test_update_related_tags_will_not_guess_between_two(self):
        """With two candidates there is nothing to choose between them, so the
        pointer is left empty -- and the ID with it."""

        entry = self._pointer_entry(chem_comps=('LIG', 'HEM'))
        entry.update_related_tags()
        entity = entry.get_saveframe_by_name('entity_1')

        self.assertEqual(entity.get_tag('Nonpolymer_comp_label'), ['.'])
        self.assertEqual(entity.get_tag('Nonpolymer_comp_ID'), ['.'])

    def test_update_related_tags_overwrites_a_child(self):
        """Pass 3 pushes a parent's value down over whatever the child held.

        The original's test for "these already agree" guards a debug print
        rather than the update, so the update is unconditional -- and writing
        the parent's value over a different one is the point of the function.
        _Entity.Parent_entity_ID starts at 7 here and must come out as the
        entity's own ID."""

        entry = self._pointer_entry()
        entry.update_related_tags()
        self.assertEqual(entry.get_saveframe_by_name('entity_1').get_tag('Parent_entity_ID'), ['1'])

    def test_update_related_tags_reports_an_empty_label(self):
        """An empty pointer that pass 1 would not guess at is reported instead --
        unless the row names a standard residue, in which case the reference can
        be reconstructed and the original stays quiet.

        Reported against the ID tag rather than the row, which is the original's
        own choice: it reports the line the tag was read from, so several empty
        rows of one column collapse to a single finding once the validator's
        error list has deduplicated them."""

        entry = copy(self.file_entry)
        entity = entry.get_saveframes_by_category('entity')[0]
        loop = entity['_Entity_comp_index']
        label, comp = loop.tag_index('Comp_label'), loop.tag_index('Comp_ID')
        for row in loop.data:
            row[label] = '.'
        loop.data[0][comp] = 'XYZ'

        issues = [_ for _ in entry.update_related_tags()
                  if _.tag == '_Entity_comp_index.Comp_ID']
        self.assertTrue(issues)
        self.assertEqual(issues[0].check, 'tag.missing_saveframe_label')
        self.assertIsNone(issues[0].row)

        # ... and with every residue standard, nothing is reported.
        for row in loop.data:
            row[comp] = 'ALA'
        self.assertEqual([_ for _ in entry.update_related_tags()
                          if _.tag == '_Entity_comp_index.Comp_ID'], [])

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

    def test_validate_full_row_indexes(self):
        entry = copy(self.file_entry)
        loop = entry.get_saveframes_by_category('entity')[0]['_Entity_comp_index']
        column = loop.tag_index('ID')

        def indexes():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check.startswith('row.')]

        # An archived entry numbers its rows 1, 2, 3, ...
        self.assertEqual(indexes(), [])

        # A non-numeric index
        loop.data[2][column] = '.'
        found = indexes()
        self.assertEqual([_.check for _ in found], ['row.index_not_a_number'])
        self.assertEqual(found[0].row, 2)
        self.assertEqual(found[0].tag, '_Entity_comp_index.ID')
        self.assertEqual(found[0].loop, '_Entity_comp_index')
        loop.data[2][column] = '3'

        # A lone wrong index costs two findings: the row itself, and the row
        # after it, which goes back to counting from where it left off.
        loop.data[2][column] = '99'
        found = indexes()
        self.assertEqual([_.check for _ in found], ['row.index_wrong'] * 2)
        self.assertIn('expected 3', found[0].message)
        self.assertIn('expected 100', found[1].message)
        loop.data[2][column] = '3'

        # A whole loop numbered from zero is reported once, not once per row:
        # the count resyncs to the value actually found, and every row after
        # the first is consistent with it.
        for number, row in enumerate(loop.data):
            row[column] = str(number)
        found = indexes()
        self.assertEqual([_.check for _ in found], ['row.index_wrong'])
        self.assertIn('expected 1', found[0].message)
        for number, row in enumerate(loop.data):
            row[column] = str(number + 1)

        # A negative index is neither "not a number" nor compared -- it only
        # advances the count, which is what the original does.
        loop.data[2][column] = '-1'
        self.assertEqual(indexes(), [])

    def test_validate_full_related_tags(self):
        entry = copy(self.file_entry)
        sample = entry.get_saveframes_by_category('sample')[0]
        components = sample['_Sample_component']

        def related():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check == 'tag.parent_value_missing']

        # Every reference in an archived entry resolves
        self.assertEqual(related(), [])

        # A loop value pointing at a saveframe that is not there. The reference
        # is written '$name' and the saveframe is named plainly, so the two only
        # compare once the marker is stripped -- if they did not, this would be
        # reported even when correct.
        column = components.tag_index('Entity_label')
        components.data[0][column] = '$no_such_entity'
        found = related()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].tag, '_Sample_component.Entity_label')
        self.assertEqual(found[0].loop, '_Sample_component')
        self.assertEqual(found[0].row, 0)
        self.assertIn('parent tag _Entity.Sf_framecode with value no_such_entity',
                      found[0].message)
        components.data[0][column] = '$F5-Phe-cVHP'
        self.assertEqual(related(), [])

        # ... and the same mistake in a saveframe's own tag
        shifts = entry.get_saveframes_by_category('assigned_chemical_shifts')[0]
        shifts['Sample_condition_list_label'] = '$no_such_conditions'
        found = related()
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0].loop)
        self.assertEqual(found[0].tag, '_Assigned_chem_shift_list.Sample_condition_list_label')

    def test_validate_full_local_ids(self):
        entry = copy(self.file_entry)
        sample = entry.get_saveframes_by_category('sample')[0]
        components = sample['_Sample_component']
        column = components.tag_index('Sample_ID')

        def local_ids():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check.endswith('local_id') or _.check.endswith('local_id_tag')]

        self.assertEqual(local_ids(), [])

        # A row filed under a different saveframe of the same category
        components.data[0][column] = '2'
        found = local_ids()
        self.assertEqual([_.check for _ in found], ['row.invalid_local_id'])
        self.assertEqual(found[0].row, 0)
        self.assertEqual(found[0].tag, '_Sample_component.Sample_ID')
        self.assertIn('should be 1', found[0].message)

        # A null is not excused: a row that does not say which saveframe it
        # belongs to is as unusable as one naming the wrong saveframe.
        components.data[0][column] = '.'
        self.assertEqual([_.check for _ in local_ids()], ['row.invalid_local_id'])
        components.data[0][column] = '1'

        # A saveframe whose own ID is null cannot be compared against at all,
        # and its loops are not reported -- one finding, not one per row.
        sample['ID'] = '.'
        self.assertEqual([_.check for _ in local_ids()], ['saveframe.invalid_local_id'])

        # No ID tag at all is two findings: the missing tag and the missing
        # value. The entry information saveframe is exempt -- its ID is the
        # entry's accession number, which is not local to it.
        sample.remove_tag('ID')
        self.assertEqual([_.check for _ in local_ids()],
                         ['saveframe.no_local_id_tag', 'saveframe.invalid_local_id'])

    def test_validate_full_frame_codes(self):
        entry = copy(self.file_entry)

        def dangling():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check == 'value.dangling_framecode']

        self.assertEqual(dangling(), [])

        # Renaming a saveframe without updating the references to it -- which
        # is what rename_saveframe() exists to avoid -- leaves them dangling
        entry.get_saveframe_by_name('sample_conditions').name = 'sample_conditions_1'
        found = dangling()
        self.assertTrue(found)
        self.assertTrue(all(_.message == 'Saveframe not found: sample_conditions' for _ in found))
        self.assertTrue(any(_.loop == '_Experiment' for _ in found))

    def test_validate_full_data_types(self):
        entry = copy(self.file_entry)
        frame = entry.get_saveframes_by_category('entry_information')[0]

        def typed(severities=None):
            return [_ for _ in entry.validate_full(profile='internal', severities=severities)
                    if _.check.startswith('value.') and _.check != 'value.miscapitalized']

        # An archived entry holds the types it declares
        self.assertEqual(typed(), [])

        # A saveframe pointer written without the '$' that makes it one, and
        # with a space in it, which is two findings rather than one
        sample = entry.get_saveframes_by_category('sample')[0]['_Sample_component']
        column = sample.tag_index('Entity_label')
        sample.data[0][column] = 'F5 Phe cVHP'
        self.assertEqual([_.check for _ in typed()],
                         ['value.not_a_framecode', 'value.framecode_whitespace'])
        sample.data[0][column] = '$F5-Phe-cVHP'

        # An integer, a float and a date that are none of those things
        datum = frame['_Datum']
        count = datum.tag_index('Count')
        datum.data[0][count] = 'six hundred'
        found = typed()
        self.assertEqual([_.check for _ in found], ['value.not_an_integer'])
        self.assertEqual((found[0].loop, found[0].row), ('_Datum', 0))
        datum.data[0][count] = '602'

        entity = entry.get_saveframes_by_category('entity')[0]
        entity['Formula_weight'] = '1.2.3'
        self.assertEqual([_.check for _ in typed()], ['value.not_a_float'])
        entity['Formula_weight'] = '3958.3'

        submission = frame.get_tag('_Entry.Submission_date', whole_tag=True)[0]
        submission[1] = '2010-13-01'
        self.assertEqual([_.check for _ in typed()], ['value.not_a_date'])

        # A date of the right shape naming a day that does not exist. The
        # original's test knows only that a month is 1-12 and a day 1-31, so
        # this is ours alone and is filed under STRICT.
        submission[1] = '2010-02-31'
        self.assertEqual(typed(), [])
        strict = typed(severities=['strict'])
        self.assertEqual([_.check for _ in strict], ['value.impossible_date'])
        self.assertEqual(strict[0].tag, '_Entry.Submission_date')
        submission[1] = '2010-02-19'

        # A value longer than its column. The size comes from the dictionary's
        # SQL type; _Entry.Title is TEXT and so has none at all.
        version = frame.get_tag('_Entry.NMR_STAR_version', whole_tag=True)[0]
        version[1] = 'v' * 40
        found = typed()
        self.assertEqual([_.check for _ in found], ['value.too_long'])
        self.assertIn('maxlength = 31', found[0].message)
        version[1] = '3.1.1.61'

        frame.get_tag('_Entry.Title', whole_tag=True)[0][1] = 't' * 5000
        self.assertEqual(typed(), [])

    def test_validate_full_data_values(self):
        entry = copy(self.file_entry)
        chem_comp = entry.get_saveframes_by_category('chem_comp')[0]

        def enumerated():
            return [_ for _ in entry.validate_full(profile='internal')
                    if _.check in ('value.not_in_enumeration', 'value.miscapitalized')]

        # The sample entry writes two closed-enumeration values in the wrong
        # case. They are findings -- the original compares case-sensitively --
        # but they get the message that names the spelling to use.
        found = enumerated()
        self.assertEqual([_.check for _ in found], ['value.miscapitalized'] * 2)
        self.assertEqual([_.tag for _ in found],
                         ['_Chem_comp.Type', '_Chem_comp.Processing_site'])
        self.assertIn('should be NON-POLYMER', found[0].message)

        # A value that is not in the list at any capitalization
        chem_comp.get_tag('_Chem_comp.Type', whole_tag=True)[0][1] = 'gaseous'
        found = [_ for _ in enumerated() if _.tag == '_Chem_comp.Type']
        self.assertEqual([_.check for _ in found], ['value.not_in_enumeration'])
        self.assertEqual(found[0].message,
                         'Enumerated value is not in the list: gaseous (_Chem_comp.Type)')

        # An open enumeration lists what has been seen, not what is allowed, so
        # a value outside it is not a finding
        self.assertFalse(utils.get_schema().enumerations['_software.name']['closed'])
        software = entry.get_saveframes_by_category('software')[0]
        software['Name'] = 'A program nobody has used before'
        self.assertFalse([_ for _ in enumerated() if _.tag == '_Software.Name'])

    def test_validate_full_empty_rows_and_charset(self):
        entry = copy(self.file_entry)
        loop = entry.get_saveframes_by_category('entity')[0]['_Entity_comp_index']

        def found(check):
            return [_ for _ in entry.validate_full(profile='internal') if _.check == check]

        self.assertEqual(found('row.empty'), [])
        self.assertEqual(found('value.non_ascii'), [])

        # A row of nothing but nulls, in all the spellings of null
        loop.data.append(['.', '?', '', None] + ['.'] * (len(loop.tags) - 4))
        empty = found('row.empty')
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0].row, len(loop.data) - 1)
        self.assertEqual(empty[0].loop, '_Entity_comp_index')

        # One non-null value is enough to make a row worth keeping, however
        # little it says
        loop.data[-1][0] = 'x'
        self.assertEqual(found('row.empty'), [])
        loop.data.pop()

        # NMR-STAR is ASCII. The message names the characters and their code
        # points, because they are usually invisible in the file.
        frame = entry.get_saveframes_by_category('entry_information')[0]
        frame['Title'] = 'Solution structure of a ubiquitin–like protein'
        non_ascii = found('value.non_ascii')
        self.assertEqual([_.tag for _ in non_ascii], ['_Entry.Title'])
        self.assertIn("'–' (U+2013)", non_ascii[0].message)

        # A finding is consumed one line at a time, so a multi-line value must
        # not put a newline in the message
        frame['Title'] = 'Two\nlines–long\n'
        non_ascii = found('value.non_ascii')
        self.assertEqual(len(non_ascii), 1)
        self.assertNotIn('\n', non_ascii[0].message)

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
