How to run the unit tests
=========================

Setup
-----

All the following commands should be executed from a shell inside the
PyNMRSTAR distribution folder (``PyNMRSTAR`` not ``PyNMRSTAR/pynmrstar``).

Some parts of the unit test structure are in a git submodule that needs to be
downloaded separately.

.. code:: bash

   git submodule init
   git submodule update

Using unit test
---------------

.. code:: bash

   python3 -m pynmrstar.unit_tests

Using pytest
------------

.. code:: bash

   pytest
