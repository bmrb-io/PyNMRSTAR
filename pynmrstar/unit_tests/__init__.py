#!/usr/bin/env python3
import logging
import os
import tempfile
import unittest

logging.getLogger('pynmrstar').setLevel(logging.FATAL)

# Make dictionary loading hermetic for the test suite: read the packaged
# distribution files directly (no live network) and use a throwaway cache
# directory so a stale or newer real cache can't shadow the pinned version.
import pynmrstar

os.environ['PYNMRSTAR_DICTIONARY_SOURCE'] = os.path.join(os.path.dirname(pynmrstar.__file__),
                                                         'reference_files')
os.environ['XDG_CACHE_HOME'] = tempfile.mkdtemp(prefix='pynmrstar-test-cache-')

# Import all test classes
from .test_entry import TestEntry
from .test_saveframe import TestSaveframe
from .test_loop import TestLoop
from .test_parser import TestParser
from .test_utils import TestUtils
from .test_schema import TestSchema


# Allow unit testing from other modules
def start_tests():
    unittest.main(module=__name__)
