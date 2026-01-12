#!/usr/bin/env python3
import os
import unittest

from pynmrstar import utils, definitions, Entry
from pynmrstar._internal import _interpret_file

our_path = os.path.dirname(os.path.realpath(__file__))
database_entry = Entry.from_database(15000)
sample_file_location = os.path.join(our_path, "sample_files", "bmr15000_3.str")


class TestUtils(unittest.TestCase):

    def test_clean_val(self):
        # Check tag cleaning
        self.assertEqual(utils.quote_value("single quote test"), "'single quote test'")
        self.assertEqual(utils.quote_value("double quote' test"), '"double quote\' test"')
        self.assertEqual(utils.quote_value("loop_"), "'loop_'")
        self.assertEqual(utils.quote_value("#comment"), "'#comment'")
        self.assertEqual(utils.quote_value("_tag"), "'_tag'")
        self.assertEqual(utils.quote_value("simple"), "simple")
        self.assertEqual(utils.quote_value("  "), "'  '")
        self.assertEqual(utils.quote_value("\nnewline\n"), "\nnewline\n")
        self.assertEqual(utils.quote_value(None), ".")
        self.assertRaises(ValueError, utils.quote_value, "")

        definitions.STR_CONVERSION_DICT = {"loop_": "noloop_"}
        utils.quote_value.cache_clear()
        self.assertEqual(utils.quote_value("loop_"), "noloop_")
        definitions.STR_CONVERSION_DICT = {None: "."}

    def test__format_category(self):
        self.assertEqual(utils.format_category("test"), "_test")
        self.assertEqual(utils.format_category("_test"), "_test")
        self.assertEqual(utils.format_category("test.test"), "_test")

    def test__format_tag(self):
        self.assertEqual(utils.format_tag("test"), "test")
        self.assertEqual(utils.format_tag("_test.test"), "test")
        self.assertEqual(utils.format_tag("test.test"), "test")

    def test__InterpretFile(self):
        with open(sample_file_location, "r") as local_file:
            local_version = local_file.read()

        # Test reading file from local locations
        self.assertEqual(_interpret_file(sample_file_location).read(), local_version)
        with open(sample_file_location, "rb") as tmp:
            self.assertEqual(_interpret_file(tmp).read(), local_version)
        with open(os.path.join(our_path, "sample_files", "bmr15000_3.str.gz"), "rb") as tmp:
            self.assertEqual(_interpret_file(tmp).read(), local_version)

        # Test reading from http (ftp doesn't work on TravisCI)
        entry_url = 'https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr15000/bmr15000_3.str'
        self.assertEqual(Entry.from_string(_interpret_file(entry_url).read()), database_entry)

        # Test reading from https locations
        raw_api_url = "https://api.bmrb.io/v2/entry/15000?format=rawnmrstar"
        self.assertEqual(Entry.from_string(_interpret_file(raw_api_url).read()), database_entry)
