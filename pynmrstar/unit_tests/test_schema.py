#!/usr/bin/env python3
import unittest

from pynmrstar import Schema


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
                          'Natural foreign key', 'Redundant keys', 'Parent tag', 'public', 'internal', 'small molecule',
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
