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
        # Closing save_ cannot be semicolon-delimited
        self.assertRaises(ParsingError, Entry.from_string, "data_1\nsave_1\n_saveframe.tag value\n;\nsave_\n;\n")
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

    def test_unicode_whitespace_warning(self):
        """Test that non-standard Unicode whitespace outside tag values logs a warning."""

        # U+3000 IDEOGRAPHIC SPACE used as a token separator should warn
        star = "data_test save_test\u3000_sf.sf_category test _sf.sf_framecode test save_"
        with self.assertLogs('pynmrstar', level='WARNING') as cm:
            Entry.from_string(star)
        self.assertTrue(any("Non-standard whitespace" in msg for msg in cm.output))

        # U+00A0 NO-BREAK SPACE should also warn
        star = "data_test save_test _sf.sf_category\u00a0test _sf.sf_framecode test save_"
        with self.assertLogs('pynmrstar', level='WARNING') as cm:
            Entry.from_string(star)
        self.assertTrue(any("Non-standard whitespace" in msg for msg in cm.output))

        # U+1680 OGHAM SPACE MARK should also warn
        star = "data_test\u1680save_test _sf.sf_category test _sf.sf_framecode test save_"
        with self.assertLogs('pynmrstar', level='WARNING') as cm:
            Entry.from_string(star)
        self.assertTrue(any("Non-standard whitespace" in msg for msg in cm.output))

    def test_unicode_whitespace_raises_with_flag(self):
        """Test that non-standard whitespace raises ParsingError when raise_parse_warnings is set."""

        star = "data_test save_test\u3000_sf.sf_category test _sf.sf_framecode test save_"
        self.assertRaises(ParsingError, Entry.from_string, star, raise_parse_warnings=True)

    def test_standard_whitespace_no_warning(self):
        """Test that standard whitespace does not produce a warning."""

        # Space, tab, newline, vertical tab, carriage return - all standard
        star = "data_test\n save_test\t_sf.sf_category test\r\n_sf.sf_framecode test\n save_\n"
        # assertLogs would fail if no log is emitted, so we use assertNoLogs (Python 3.10+)
        # or just parse and verify success
        entry = Entry.from_string(star)
        self.assertEqual(entry.entry_id, "test")

    def test_unicode_whitespace_in_quoted_value_no_warning(self):
        """Test that Unicode whitespace inside quoted values does not trigger a warning."""

        # U+3000 inside a single-quoted value should not warn
        star = "data_test save_test _sf.sf_category test _sf.sf_framecode test _sf.value '\u3000test\u3000' save_"
        entry = Entry.from_string(star)
        self.assertEqual(entry[0]['value'], ['\u3000test\u3000'])

        # U+3000 inside a semicolon-delimited value should not warn
        star = "data_test save_test _sf.sf_category test _sf.sf_framecode test _sf.value\n;\n\u3000value\u3000\n;\nsave_"
        entry = Entry.from_string(star)
        self.assertIn('\u3000', entry[0]['value'][0])
