Module documentation
======================================

Entry class
~~~~~~~~~~~

.. autoclass:: pynmrstar.Entry
   :special-members: __delitem__
   :members:

Saveframe class
~~~~~~~~~~~~~~~

.. autoclass:: pynmrstar.Saveframe
   :members:

Loop class
~~~~~~~~~~

.. autoclass:: pynmrstar.Loop
   :members:

Schema class
~~~~~~~~~~~~

.. autoclass:: pynmrstar.Schema
   :special-members: __init__
   :members:
   :exclude-members: convert_tag, val_type, tag_key

Exceptions
~~~~~~~~~~

.. autoclass:: pynmrstar.exceptions.ParsingError
.. autoclass:: pynmrstar.exceptions.InvalidStateError

Utilities
~~~~~~~~~

.. automodule:: pynmrstar.utils
   :members: diff, iter_entries, validate
