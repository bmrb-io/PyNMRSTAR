#!/usr/bin/env python3
import unittest

from pynmrstar import Entry, Saveframe, _Parser
from pynmrstar.exceptions import ParsingError


class TestParser(unittest.TestCase):

    def test___Parser(self):

        # Check for error when reserved token present in data value
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n_tag.example loop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n_tag.example data_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n_tag.example save_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nloop_\nstop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nsave_\nstop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\nloop_\n_tag.tag\nglobal_\nstop_\nsave_\n")

        # Check for error when reserved token quoted
        self.assertRaises(ParsingError, Entry.from_string, "'data_1'\nsave_1\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\n'save_1'\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, 'data_1\nsave_1\n"loop"_\n_tag.tag\ndata_\nstop_\nsave_\n')
        self.assertRaises(ParsingError, Entry.from_string,
                          "data_1\nsave_1\nloop_\n_tag.tag\ndata_\n;\nstop_\n;\nsave_\n")
        self.assertRaises(ParsingError, Saveframe.from_string, "save_1\n_tag.1 _tag.2")

    def test_parse_outliers(self):
        """ Make sure the parser handles edge cases. """

        parser = _Parser()
        parser.load_data("""data_#pound
save_entry_information  _Entry.Sf_category entry_information _Entry.Sf_framecode entry_information
_Entry.sameline_comment value #ignore this all
_Entry.ID    \".-!?\"
_Entry.Invalid_tag            "This tag doesn't exist."
_Entry.Title
; Solution structure of chicken villin headpiece subdomain contain;ing a fluorinated side chain in the cores;
;
_Entry.Submi#ssion_date                "check inn"er "quoted vals"
_Entry.Accession_date                 'check inner quoted vals'
_Entry.Original_NMR_STAR_version      '_.'
   _Entry.Experimental_method            $
   _Entry.Details                        "1#"
   _Entry.Experimental_method_subtype    solution
   _Entry.BMRB_internal_directory_name   ;data;
_Entry.pointer $it
_Entry.multi
;

   nothing
   to shift
;
_Entry.multi2
;

   ;
   something
   to shift
;
""")
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('data_#pound', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('save_entry_information', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Sf_category', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('entry_information', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Sf_framecode', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('entry_information', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.sameline_comment', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('value', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.ID', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('.-!?', '"'))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Invalid_tag', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ("This tag doesn't exist.", '"'))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Title', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), (" Solution structure of chicken villin headpiece subdomain"
                                                            " contain;ing a fluorinated side chain in the cores;\n",
                                                            ';'))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Submi#ssion_date', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('check inn"er "quoted vals', '"'))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Accession_date', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('check inner quoted vals', '\''))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Original_NMR_STAR_version', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_.', '\''))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Experimental_method', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('$', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Details', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('1#', '"'))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.Experimental_method_subtype', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('solution', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.BMRB_internal_directory_name', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), (';data;', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('_Entry.pointer', ' '))
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ('$it', '$'))
        parser.get_token()
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ("\n   nothing\n   to shift\n", ';'))
        parser.get_token()
        parser.get_token()
        self.assertEqual((parser.token, parser.delimiter), ("\n;\nsomething\nto shift", ';'))
