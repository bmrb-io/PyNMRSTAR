#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest

from pynmrstar import Schema
from pynmrstar._internal import load_dictionary


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

    def test_dictionary_cache(self):
        # load_dictionary() reads the distribution, caches it under
        # $XDG_CACHE_HOME/pynmrstar/<version>, and reuses the cache next time
        # (so a subsequent load works even with an unreachable source).
        reference = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                                 "reference_files")
        cache = tempfile.mkdtemp(prefix="pynmrstar-cache-test-")
        saved = {k: os.environ.get(k) for k in ("XDG_CACHE_HOME", "PYNMRSTAR_DICTIONARY_SOURCE")}
        try:
            os.environ["XDG_CACHE_HOME"] = cache
            os.environ["PYNMRSTAR_DICTIONARY_SOURCE"] = reference

            files, version = load_dictionary()
            self.assertNotEqual(version, "unknown")
            for name in ("xlschem_ann.csv", "adit_enum_hdr.csv", "adit_enum_dtl.csv"):
                self.assertIn(name, files)
            self.assertTrue(os.path.isdir(os.path.join(cache, "pynmrstar", version)))

            # With the source now unreachable, it still resolves from the cache.
            os.environ["PYNMRSTAR_DICTIONARY_SOURCE"] = "http://invalid.invalid/none"
            _, cached_version = load_dictionary()
            self.assertEqual(cached_version, version)
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
