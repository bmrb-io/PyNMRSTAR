#!/usr/bin/env python3
import logging
import unittest

logging.getLogger('pynmrstar').setLevel(logging.FATAL)

# Import all test classes
from .test_entry import TestEntry
from .test_saveframe import TestSaveframe
from .test_loop import TestLoop
from .test_parser import TestParser
from .test_parser_fast_path import TestParserFastPath
from .test_utils import TestUtils
from .test_schema import TestSchema


# Allow unit testing from other modules
def start_tests():
    unittest.main(module=__name__)
