
How to run the unit tests
=========================


Setup
-----

All the following commands should be made from a shell inside the
PyNMRStar distribution folder (PyNMRStar not PyNMRStar/pynmrstar).

Some parts of the unit test structure are in a sub-repo that needs to be
downloaded separately using git.

.. code:: bash

   git submodule init
   git submodule update

if you have downloaded PyNMR-Star as a git hub repo you may need

.. code:: shell

   export PYTHONPATH=<full-path-to-PyNMRStar-folder>

Using unit test
---------------

.. code:: bash

   python3 pynmrstar/unit_tests/test_pynmrstar.py

Using pytest
------------

.. code:: bash

   pytest pynmrstar/unit_tests
