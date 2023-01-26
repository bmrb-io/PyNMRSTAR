#!/usr/bin/env python3
import unittest

from .test_pynmrstar import TestPyNMRSTAR

# Allow unit testing from other modules
def start_tests():
    unittest.main(module=__name__)
