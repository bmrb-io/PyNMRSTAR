#!/usr/bin/env python3
import unittest

from pynmrstar import Entry, Saveframe, Loop
from pynmrstar.exceptions import ParsingError


class TestParser(unittest.TestCase):

    def test__Parser(self):
        """ Test that the various parsing Errors that can be raised are raised. """

        # These checks match the order of the parser code at the time they were written.
        self.assertRaises(ParsingError, Entry.from_string, 'data_1\nsave_1\n"loop"_\n_tag.tag\ndata_\nstop_\nsave_\n')

        # STAR/file start checks
        self.assertRaises(ParsingError, Entry.from_string, "whatever test")
        self.assertRaises(ParsingError, Entry.from_string, "data_")
        self.assertRaises(ParsingError, Entry.from_string, "'data_1'\nsave_1\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")

        # Saveframe checks
        self.assertRaises(ParsingError, Entry.from_string, "data_frame invalid")
        self.assertRaises(ParsingError, Entry.from_string, "data_frame save_ invalid")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\n'save_1'\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n")

        # Loop checks
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n'loop_'\n_tag.tag\ndata_\nstop_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 loop_ _tag.one _tag2.one stop_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 loop_ _tag.one stop_ loop_ _tag.one stop_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 loop_ _tag.one 'stop_'")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ stop_ save_", raise_parse_warnings=True)
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ _tag.one stop_ save_", raise_parse_warnings=True)
        with self.assertLogs('pynmrstar', level='WARNING'):
            Entry.from_string("data_1 save_1 _saveframe.tag value loop_ stop_ save_", raise_parse_warnings=False)
        with self.assertLogs('pynmrstar', level='WARNING'):
            Entry.from_string("data_1 save_1 _saveframe.tag value loop_ _tag.one stop_ save_", raise_parse_warnings=False)
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data stop_ save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data _tag.three stop_ save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ data stop_ save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data data2 loop_ stop_ save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data data2")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value 'save_'")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 stop_")

        # Back to saveframes
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n'_tag.example' save_\nsave_\n")
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n_tag.example save_\nsave_\n")
        self.assertRaises(ParsingError, Loop.from_string, "d")
        self.assertRaises(ParsingError, Saveframe.from_string, "save_1\n_tag.1 _tag.2")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _savef.rame.tag value save_")
        self.assertRaises(ParsingError, Entry.from_string, "data_1 save_1 _saveframe.tag value")

    def test_parse_outliers(self):
        """ Make sure the parser handles edge cases. """

        test_string = """data_#pound
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
save_
"""
        #self.assertEqual(test_string, str(Entry.from_string(test_string)))
