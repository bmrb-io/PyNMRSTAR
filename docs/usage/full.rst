Module documentation
======================================

Entry class
~~~~~~~~~~~

.. autoclass:: pynmrstar.Entry
   :special-members:
   :members:

Saveframe class
~~~~~~~~~~~~~~~

.. autoclass:: pynmrstar.Saveframe
   :special-members:
   :members:

Loop class
~~~~~~~~~~

.. autoclass:: pynmrstar.Loop
   :special-members:
   :members:

Schema class
~~~~~~~~~~~~

.. autoclass:: pynmrstar.Schema
   :special-members: __init__
   :members:
   :exclude-members: convert_tag, val_type, tag_key

Validation results
~~~~~~~~~~~~~~~~~~

:py:meth:`pynmrstar.Entry.validate_full` returns a list of these.

.. autoclass:: pynmrstar.ValidationIssue
   :members:

.. autoclass:: pynmrstar.Severity
   :members:
   :undoc-members:

Repairs
~~~~~~~

.. automodule:: pynmrstar.repair
   :members: insert_mandatory_tags

Exceptions
~~~~~~~~~~

.. autoclass:: pynmrstar.exceptions.ParsingError
.. autoclass:: pynmrstar.exceptions.InvalidStateError

Utilities
~~~~~~~~~

.. automodule:: pynmrstar.utils
   :members: diff, iter_entries, validate
