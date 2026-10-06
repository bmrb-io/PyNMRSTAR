#!/usr/bin/env python3
import logging
import os
import tempfile
import unittest

logging.getLogger('pynmrstar').setLevel(logging.FATAL)

# Make dictionary loading hermetic for the test suite. The default schema is the
# packaged one regardless; this keeps the tests that ask for a download off the
# network (the "download" reads the packaged files) and out of the real cache.
import pynmrstar

os.environ['PYNMRSTAR_DICTIONARY_SOURCE'] = os.path.join(os.path.dirname(pynmrstar.__file__),
                                                         'reference_files')
os.environ['XDG_CACHE_HOME'] = tempfile.mkdtemp(prefix='pynmrstar-test-cache-')

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
