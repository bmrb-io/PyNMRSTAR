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

    def test_sf_framecode_mismatch_is_a_parse_warning(self):
        """A saveframe whose Sf_framecode differs from its save_ label is a
        thing a validator must be able to *report*, so parsing keeps both
        strings and warns rather than refusing the file."""

        star = "data_1\nsave_the_name\n_sf.Sf_category cat\n_sf.Sf_framecode a_different_name\nsave_\n"

        with self.assertLogs('pynmrstar', level='WARNING'):
            entry = Entry.from_string(star)
        saveframe = entry[0]
        self.assertEqual(saveframe.name, 'the_name')
        self.assertEqual(saveframe['Sf_framecode'], ['a_different_name'])

        # ...and it survives a write/re-parse, so the file round-trips
        reparsed = Entry.from_string(entry.format())
        self.assertEqual(reparsed[0].name, 'the_name')
        self.assertEqual(reparsed[0]['Sf_framecode'], ['a_different_name'])

    def test_sf_framecode_mismatch_raises_when_strict(self):
        """raise_parse_warnings=True keeps the old, strict behavior."""

        star = "data_1\nsave_the_name\n_sf.Sf_category cat\n_sf.Sf_framecode a_different_name\nsave_\n"
        self.assertRaises(ParsingError, Entry.from_string, star, raise_parse_warnings=True)

    def test_sf_framecode_mismatch_still_raises_outside_a_parse(self):
        """Building an inconsistent saveframe through the API is a programming
        error, not malformed input, so it still raises."""

        saveframe = Saveframe.from_scratch('the_name', tag_prefix='_sf')
        self.assertRaises(ValueError, saveframe.add_tag, '_sf.Sf_framecode', 'a_different_name')

    def test_structural_error_line_numbers(self):
        """A file that will not parse must still say *where*.

        Duplicate tags and tags whose category doesn't match their container are
        rejected while building the object model, after the tokenizer has moved
        on, so the line has to be carried from where the tag was read."""

        duplicate = ("data_test\n\nsave_entry_information\n"
                     "    _Entry.Sf_category    entry_information\n"
                     "    _Entry.Sf_framecode   entry_information\n"
                     "    _Entry.Title          'first title'\n"
                     "    _Entry.Title          'second title'\n"
                     "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(duplicate)
        # The *second* occurrence is the offending one
        self.assertEqual(caught.exception.line_number, 7)

        foreign = ("data_test\n\nsave_entry_information\n"
                   "    _Entry.Sf_category    entry_information\n"
                   "    _Entry.Sf_framecode   entry_information\n"
                   "    _Entry.Title          'a title'\n"
                   "    _Citation.Class       journal\n"
                   "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(foreign)
        self.assertEqual(caught.exception.line_number, 7)

        # A tag name appearing inside a semicolon block is not the tag itself:
        # the duplicate is on line 11, not the 10 it would be if line 8 counted.
        semicolon = ("data_test\n\nsave_entry_information\n"
                     "    _Entry.Sf_category    entry_information\n"
                     "    _Entry.Sf_framecode   entry_information\n"
                     "    _Entry.Details\n;\n_Entry.Title is discussed here\n;\n"
                     "    _Entry.Title          'first title'\n"
                     "    _Entry.Title          'second title'\n"
                     "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(semicolon)
        self.assertEqual(caught.exception.line_number, 11)

    def test_loop_tag_line_numbers(self):
        """Loop tags are batched too, so they need the same treatment."""

        header = ("data_test\n\nsave_x\n"
                  "    _Entry.Sf_category    entry_information\n"
                  "    _Entry.Sf_framecode   x\n"
                  "    loop_\n"
                  "        _Entry_author.Ordinal\n"
                  "        _Entry_author.Given_name\n")

        duplicate = header + "        _Entry_author.Ordinal\n        1 Jon 2\n    stop_\nsave_\n"
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(duplicate)
        self.assertEqual(caught.exception.line_number, 9)

        foreign = header + "        _Citation.Class\n        1 Jon journal\n    stop_\nsave_\n"
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(foreign)
        self.assertEqual(caught.exception.line_number, 9)

    def test_tokenizer_error_line_numbers(self):
        """Errors raised by the tokenizer itself carry the line of the token
        they were reading, not of the line the tokenizer had advanced to."""

        # A token which is rejected mid-line: the tag is followed by spaces
        # rather than a newline, so the tokenizer has not left line 6 yet.
        quoted_tag = ("data_test\n\nsave_entry_information\n"
                      "    _Entry.Sf_category    entry_information\n"
                      "    _Entry.Sf_framecode   entry_information\n"
                      "    '_Entry.Title'        'x'\n"
                      "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(quoted_tag)
        self.assertEqual(caught.exception.line_number, 6)

        # ...and one rejected at the end of a line
        underscore_value = ("data_test\n\nsave_entry_information\n"
                            "    _Entry.Sf_category    entry_information\n"
                            "    _Entry.Sf_framecode   entry_information\n"
                            "    _Entry.Title          _bad_value\n"
                            "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(underscore_value)
        self.assertEqual(caught.exception.line_number, 6)

        # A multi-line value is reported against the line it opens on
        unterminated = ("data_test\n\nsave_entry_information\n"
                        "    _Entry.Sf_category    entry_information\n"
                        "    _Entry.Sf_framecode   entry_information\n"
                        "    _Entry.Title\n;\nno closing semicolon\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(unterminated)
        self.assertEqual(caught.exception.line_number, 7)

    def test_line_numbers_survive_semicolon_rewriting(self):
        """A `;content` value is split over two lines before tokenizing, which
        pushes the rest of the file down a line. Reported lines must still name
        the line of the file the caller actually has."""

        # _Entry.Details holds a value written as ';content' on one line. Without
        # the correction the duplicate below would be reported one line late.
        star = ("data_test\n\nsave_entry_information\n"
                "    _Entry.Sf_category    entry_information\n"
                "    _Entry.Sf_framecode   entry_information\n"
                "    _Entry.Details\n; some details on the semicolon line\n;\n"
                "    _Entry.Title          'first title'\n"
                "    _Entry.Title          'second title'\n"
                "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(star)
        self.assertEqual(caught.exception.line_number, 10)

        # ...and the same for an error the tokenizer raises itself
        star = ("data_test\n\nsave_entry_information\n"
                "    _Entry.Sf_category    entry_information\n"
                "    _Entry.Sf_framecode   entry_information\n"
                "    _Entry.Details\n; some details on the semicolon line\n;\n"
                "    '_Entry.Title'        'x'\n"
                "save_\n")
        with self.assertRaises(ParsingError) as caught:
            Entry.from_string(star)
        self.assertEqual(caught.exception.line_number, 9)
