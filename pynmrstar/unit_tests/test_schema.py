#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest

from io import StringIO

from pynmrstar import Schema, definitions
from pynmrstar._internal import load_dictionary, packaged_dictionary_version

reference = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "reference_files")


class TestSchema(unittest.TestCase):

    def test_Schema(self):
        default = Schema()

        self.assertEqual(default.headers,
                         ['Dictionary sequence', 'SFCategory', 'ADIT category mandatory', 'ADIT category view type',
                          'ADIT super category ID', 'ADIT super category', 'ADIT category group ID',
                          'ADIT category view name', 'Tag', 'BMRB current', 'Query prompt', 'Query interface',
                          'SG Mandatory', '', 'ADIT exists', 'User full view', 'Metabolomics', 'Metabolites', 'SENCI',
                          'Fragment library', 'Item enumerated', 'Item enumeration closed', 'Enum parent SFcategory',
                          'Enum parent tag', 'Derived enumeration mantable', 'Derived enumeration',
                          'ADIT item view name', 'Data Type', 'Nullable', 'Non-public', 'ManDBTableName',
                          'ManDBColumnName', 'Row Index Key', 'Saveframe ID tag', 'Source Key', 'Table Primary Key',
                          'Foreign Key Group', 'Foreign Table', 'Foreign Column', 'Secondary index', 'Sub category',
                          'Units', 'Loopflag', 'Seq', 'Adit initial rows', 'Enumeration ties',
                          'Mandatory code overides', 'Overide value', 'Overide view value', 'ADIT auto insert',
                          'Example', 'Prompt', 'Interface', 'bmrbPdbMatchID', 'bmrbPdbTransFunc', 'STAR flag',
                          'DB flag', 'SfNamelFlg', 'Sf category flag', 'Sf pointer', 'Natural primary key',
                          'Natural foreign key', 'obsolete tag', 'Parent tag', 'public', 'internal', 'small molecule',
                          'small molecule', 'metabolomics', 'Entry completeness', 'Overide public', 'internal',
                          'small molecule', 'small molecule', 'metabolomic', 'metabolomic', 'default value',
                          'Adit form code', 'Tag category', 'Tag field', 'Local key', 'Datum count flag',
                          'NEF equivalent', 'mmCIF equivalent', 'Meta data', 'Tag delete', 'BMRB data type',
                          'STAR vs Curated DB', 'Key group', 'Reference table', 'Reference column',
                          'Dictionary description', 'variableTypeMatch', 'entryIdFlg', 'outputMapExistsFlg',
                          'lclSfIdFlg', 'Met ADIT category view name', 'Met Example', 'Met Prompt', 'Met Description',
                          'SM Struct ADIT-NMR category view name', 'SM Struct Example', 'SM Struct Prompt',
                          'SM Struct Description', 'Met default value', 'SM default value'])

        self.assertEqual(default.val_type("_Entity.ID", 1), [])
        self.assertEqual(default.val_type("_Entity.ID", "test"), [
            "Value does not match specification: '_Entity.ID':'test'.\n     Type specified: int\n     "
            "Regular expression for type: '^(?:-?[0-9]*)?$'"])
        self.assertEqual(default.val_type("_Atom_chem_shift.Val", float(1.2)), [])
        self.assertEqual(default.val_type("_Atom_chem_shift.Val", "invalid"), [
            "Value does not match specification: '_Atom_chem_shift.Val':'invalid'.\n     Type "
            "specified: float\n     Regular expression for type: '^(?:-?[0-9]*\\.?[0-9]+(?:[eE][-+]?[0-9]+)?)?$'"])

        self.assertEqual(default.val_type("_Entry.ID", "this should be far too long - much too long"), [
            "Length of '43' is too long for 'CHAR(12)': '_Entry.ID':'this should be far too long - much too long'."])

    def test_dates(self):
        default = Schema()

        self.assertEqual(default.val_type("_Release.Date", "2006-09-07"), [])

        # The type pattern allows these, but they are not dates: a two digit
        # year, an impossible month and day, and a day that month never has
        for bad_date in ("10-11-67", "1066-13-32", "2023-02-31"):
            self.assertEqual(default.val_type("_Release.Date", bad_date),
                             [f"Value is not a valid date: '_Release.Date':'{bad_date}'."])

    def test_enumerations(self):
        default = Schema()

        # The enumeration value lists built from the dictionary's adit_enum files
        self.assertTrue(len(default.enumerations) > 0)

        # A known closed enumeration, spelled as the dictionary spells it
        subtype = default.enumerations["_entry.experimental_method_subtype"]
        self.assertTrue(subtype["closed"])
        self.assertIn("solution", subtype["values"])

        # A value in a closed enumeration passes
        self.assertEqual(default.val_type("_Entry.Experimental_method_subtype", "solution"), [])

        # A value that differs only in capitalization is reported as such
        self.assertEqual(default.val_type("_Entry.Experimental_method_subtype", "SOLUTION"), [
            "Value 'SOLUTION' of tag '_Entry.Experimental_method_subtype' is improperly capitalized but "
            "otherwise valid. Should be 'solution'."])

        # A value that is genuinely not in a closed enumeration fails
        self.assertEqual(default.val_type("_Entry.Experimental_method_subtype", "not_a_real_subtype"), [
            "Value 'not_a_real_subtype' is not in the closed enumeration for tag "
            "'_Entry.Experimental_method_subtype'."])

        # Open (non-closed) enumerations are advisory only: a non-member value is
        # not flagged as an error.
        db_code = default.enumerations["_assembly_db_link.database_code"]
        self.assertFalse(db_code["closed"])
        self.assertEqual(default.val_type("_Assembly_db_link.Database_code", "NOT_A_REAL_DATABASE"), [])

        # The distribution CSVs encode a comma inside a value as '$'
        comp_type = default.enumerations["_chem_comp.type"]
        self.assertIn("D-SACCHARIDE 1,4 AND 1,4 LINKING", comp_type["values"])
        self.assertFalse(any("$" in _ for _ in comp_type["values"]))
        self.assertEqual(default.val_type("_Chem_comp.Type", "D-SACCHARIDE 1,4 AND 1,4 LINKING"), [])

    def test_validation_profiles(self):
        default = Schema()

        # The saveframe category table, from adit_cat_grp_o.csv
        self.assertTrue(len(default.saveframe_categories) > 0)
        self.assertIn('entry_information', default.saveframe_categories)

        internal = default.validation_profile('internal')
        public = default.validation_profile('public')

        # Every tag and every category resolves to a code
        self.assertEqual(len(internal['tags']), len(default.schema))
        self.assertEqual(len(internal['categories']), len(default.saveframe_categories))
        self.assertTrue(set(internal['tags'].values()) <= set('IOMVCR'))
        self.assertTrue(set(internal['categories'].values()) <= set('IOMVCR'))

        # entry_information is mandatory; a tag in it is value-mandatory
        self.assertEqual(internal['categories']['entry_information'], 'M')
        self.assertEqual(internal['tags']['_entry.sf_category'], 'V')

        # The views genuinely differ -- this is why the profile has to be
        # selectable rather than baked in.
        self.assertNotEqual(internal['tags'], public['tags'])

        # Demotion for tags in an optional saveframe category: 'study_list' is
        # optional, so a mandatory tag there can only be conditionally mandatory
        # (fix_loopmandatory in the dictionary build does the same). Neither M
        # nor V may survive in such a category.
        self.assertEqual(internal['categories']['study_list'], 'O')
        study_codes = {internal['tags'][t] for t, d in default.schema.items()
                       if d.get('SFCategory') == 'study_list'}
        self.assertIn('C', study_codes)
        self.assertFalse(study_codes & {'M', 'V'})

        # Only real categories are loaded -- the file's rule-off row of dashes
        # between header and data is not one.
        self.assertFalse([_ for _ in default.saveframe_categories if not _[0].isalpha()])

        # The profile is memoized, and unknown profiles are rejected
        self.assertIs(default.validation_profile('internal'), internal)
        self.assertRaises(ValueError, default.validation_profile, 'no_such_profile')

    def test_conditional_rules(self):
        default = Schema()

        # The conditional mandatory rules, from adit_tag_validation.csv
        self.assertTrue(len(default.conditional_rules) > 0)

        # _Citation.Journal_abbrev is mandatory only for a journal citation
        rules = default.conditional_rules['_citation.journal_abbrev']
        journal = [_ for _ in rules if _['value'] == 'journal']
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]['control_tag'], '_Citation.Type')
        self.assertEqual(journal[0]['control_category'], 'citations')

        # Rules carry one flag per view, like every other dictionary flag string
        self.assertTrue(all(_['flags'] for _ in rules))

    def test_relationships(self):
        default = Schema()

        # Ties, resolved from the tag table's Foreign Table/Foreign Column pair
        self.assertEqual(default.parent_tags['_sample_component.entity_label'],
                         '_Entity.Sf_framecode')
        # Ties chain: a loop's Entry_ID answers to its saveframe's, which
        # answers to the entry's own ID.
        self.assertEqual(default.parent_tags['_entity_comp_index.entry_id'], '_Entity.Entry_ID')
        self.assertEqual(default.parent_tags['_entity.entry_id'], '_Entry.ID')

        # Both sides of a tie are real tags, spelled as the dictionary spells
        # them -- a reference to a category that does not exist is dropped
        # rather than kept as an unresolvable pair.
        self.assertTrue(all(_ in default.schema for _ in default.parent_tags))
        self.assertTrue(all(_.lower() in default.schema for _ in default.parent_tags.values()))

        # Local IDs: the tag that numbers a saveframe within its category, and
        # the loop columns that repeat it
        self.assertIn('_sample.id', default.local_id_tags)
        self.assertIn('_sample_component.sample_id', default.local_id_tags)

        # The entry's own ID is not a local ID: it identifies the entry, which
        # is the same in every saveframe.
        self.assertNotIn('_entry.id', default.local_id_tags)
        self.assertNotIn('_sample.entry_id', default.local_id_tags)

    def _isolated(self, source: str) -> str:
        """Point the dictionary source and cache at throwaway locations for the
        rest of the test, and return the cache root."""

        saved = {k: os.environ.get(k) for k in ("XDG_CACHE_HOME", "PYNMRSTAR_DICTIONARY_SOURCE")}
        cache = tempfile.mkdtemp(prefix="pynmrstar-cache-test-")

        def restore():
            shutil.rmtree(cache, ignore_errors=True)
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)
        os.environ["XDG_CACHE_HOME"] = cache
        os.environ["PYNMRSTAR_DICTIONARY_SOURCE"] = source
        return os.path.join(cache, "pynmrstar")

    def test_default_dictionary_is_packaged(self):
        # The default never touches the network or the cache, even with an
        # unreachable source.
        cache = self._isolated("http://invalid.invalid/none")
        files, version = load_dictionary()
        self.assertEqual(version, packaged_dictionary_version())
        self.assertEqual(sorted(files), sorted(definitions.DICTIONARY_FILES))
        self.assertFalse(os.path.exists(cache))

        schema = Schema()
        self.assertEqual(schema.version, packaged_dictionary_version())
        self.assertTrue(schema.enumerations)
        self.assertEqual(repr(schema), f"pynmrstar.Schema(version='{schema.version}')")
        self.assertFalse(os.path.exists(cache))

        # Asking for the packaged version by number does not go anywhere either
        self.assertEqual(Schema(version=schema.version).version, schema.version)

    def test_latest_dictionary_is_downloaded_and_cached(self):
        cache = self._isolated(reference)
        files, version = load_dictionary('latest')
        self.assertEqual(version, packaged_dictionary_version())
        # Cached complete, with nothing left over from writing it
        self.assertEqual(sorted(os.listdir(cache)), [version])
        self.assertEqual(sorted(os.listdir(os.path.join(cache, version))),
                         sorted(definitions.DICTIONARY_FILES))
        for name, text in files.items():
            with open(os.path.join(cache, version, name), encoding='utf-8', newline='') as handle:
                self.assertEqual(handle.read(), text)

        # Asking for the newest release when it cannot be fetched is an error,
        # not a silent fallback to something older.
        os.environ["PYNMRSTAR_DICTIONARY_SOURCE"] = "http://invalid.invalid/none"
        self.assertRaises(ValueError, load_dictionary, 'latest')

    def test_specific_dictionary_version(self):
        cache = self._isolated("http://invalid.invalid/none")

        # Neither packaged, cached nor downloadable
        self.assertRaises(ValueError, Schema, version='3.2.15.0')

        # Found in the cache without the network
        os.makedirs(os.path.join(cache, '3.2.15.0'))
        for name in definitions.DICTIONARY_FILES:
            shutil.copy(os.path.join(reference, name), os.path.join(cache, '3.2.15.0', name))
        files, version = load_dictionary('3.2.15.0')
        self.assertEqual(version, '3.2.15.0')

        # Only the newest release can be downloaded
        shutil.rmtree(os.path.join(cache, '3.2.15.0'))
        os.environ["PYNMRSTAR_DICTIONARY_SOURCE"] = reference
        self.assertRaises(ValueError, load_dictionary, '3.2.15.0')

    def _release(self, directory: str, version: str) -> None:
        """Write a copy of the packaged distribution, relabelled as ``version``,
        to ``directory``."""

        os.makedirs(directory)
        for name in definitions.DICTIONARY_FILES:
            with open(os.path.join(reference, name), encoding='utf-8', newline='') as handle:
                text = handle.read()
            if name == 'xlschem_ann.csv':
                text = text.replace(f'TBL_BEGIN,,new,{packaged_dictionary_version()},',
                                    f'TBL_BEGIN,,new,{version},', 1)
            with open(os.path.join(directory, name), 'w', encoding='utf-8', newline='') as handle:
                handle.write(text)

    def test_tagged_dictionary_release(self):
        cache = self._isolated("unused")
        del os.environ["PYNMRSTAR_DICTIONARY_SOURCE"]

        # Stand-ins for the dictionary repository: one directory per tag, and
        # one for the production branch
        releases = tempfile.mkdtemp(prefix="pynmrstar-releases-test-")
        self.addCleanup(shutil.rmtree, releases, True)
        for name, value in (('DICTIONARY_RELEASE_URL', os.path.join(releases, 'nmr-star-v{version}')),
                            ('DICTIONARY_URL', os.path.join(releases, 'production'))):
            self.addCleanup(setattr, definitions, name, getattr(definitions, name))
            setattr(definitions, name, value)
        self._release(os.path.join(releases, 'nmr-star-v3.2.15.0'), '3.2.15.0')
        self._release(os.path.join(releases, 'production'), '3.2.16.0')

        # An older release is downloaded by its tag, and cached
        files, version = load_dictionary('3.2.15.0')
        self.assertEqual(version, '3.2.15.0')
        self.assertEqual(sorted(os.listdir(os.path.join(cache, '3.2.15.0'))),
                         sorted(definitions.DICTIONARY_FILES))
        self.assertEqual(Schema(version='3.2.15.0').version, '3.2.15.0')

        # The newest release is found even before it is tagged
        self.assertEqual(load_dictionary('3.2.16.0')[1], '3.2.16.0')

        # Neither tagged nor the newest
        self.assertRaises(ValueError, load_dictionary, '3.2.17.0')

        # A tag that holds some other version is an error, not that version
        self._release(os.path.join(releases, 'nmr-star-v3.2.18.0'), '3.2.15.1')
        self.assertRaises(ValueError, load_dictionary, '3.2.18.0')

        # An explicit source is the only place looked
        self._release(os.path.join(releases, 'nmr-star-v3.2.19.0'), '3.2.19.0')
        self.assertRaises(ValueError, load_dictionary, '3.2.19.0', os.path.join(releases, 'production'))
        self.assertEqual(load_dictionary('3.2.19.0')[1], '3.2.19.0')

    def test_schema_file(self):
        self._isolated("http://invalid.invalid/none")

        # A directory holding a whole distribution
        schema = Schema(schema_file=reference)
        self.assertEqual(schema.version, packaged_dictionary_version())
        self.assertTrue(schema.enumerations)
        self.assertTrue(schema.saveframe_categories)
        self.assertRaises(ValueError, Schema, schema_file=reference, version='latest')

        # A single tag table brings the rest of its own version along, from the
        # packaged copy rather than the network
        schema = Schema(schema_file=os.path.join(reference, 'xlschem_ann.csv'))
        self.assertTrue(schema.enumerations)
        self.assertTrue(schema.conditional_rules)

        # A tag table of a version that is not available stands alone
        with open(os.path.join(reference, 'xlschem_ann.csv'), encoding='utf-8') as handle:
            text = handle.read().replace(f',{packaged_dictionary_version()},', ',9.9.9.9,', 1)
        with self.assertLogs('pynmrstar', level='WARNING'):
            schema = Schema(schema_file=StringIO(text))
        self.assertEqual(schema.version, '9.9.9.9')
        self.assertTrue(schema.schema)
        self.assertFalse(schema.enumerations)
        self.assertFalse(schema.saveframe_categories)
