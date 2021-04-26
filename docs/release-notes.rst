Release notes
=============

3.1.1
~~~~~

Changes:

-  Significant extra detail added to most error messages.
-  A new exception called :py:exc:`pynmrstar.exceptions.InvalidStateError` is thrown when trying to
   perform actions which cannot be completed because the current state of the
   objects cannot be properly mapped to NMR-STAR. When using the appropriate setters and getters
   rather than directly modifying object attributes, it is somewhat hard to create such invalid states. The exception
   inherits from :py:exc:`ValueError` (which is the exception that used to be thrown in these circumstances) so no code changes
   should be necessary to catch these exceptions.
-  The parser now properly handles some ultra rare edge cases during loop parsing during which it previously either
   threw exceptions when it shouldn't have, or failed to throw an exception when it should have.
-  Deprecated :py:meth:`pynmrstar.Loop.add_data_by_tag`. This was originally used
   internally when parsing an entry, but it is recommended
   to use :py:meth:`pynmrstar.Loop.add_data` instead, or
   ``loop[['Number', 'Unit']] = [[1,2,3],['db', 'atm', 'bar']]`` style
   assignments. New methods to make tag assignment in a loop easier are also being considered.

Potentially breaking changes:

-  Saveframe tags no longer store the line number from which a tag was
   originally read. This was not always set anyway, since saveframes could also be created from
   scratch. This was also never advertised to calling code, so it's very unlikely this change will affect you.
-  Long deprecated methods :py:meth:`!pynmrstar.Loop.add_column`,
   :py:meth:`pynmrstar.Loop.add_data_by_column`, and :py:meth:`pynmrstar.Loop.get_columns` were removed.
   Also, the long deprecated root level reference to :py:func:`~pynmrstar.utils.iter_entries` was removed,
   but the function is still available in :py:mod:`pynmrstar.utils`.

3.1.0
~~~~~

Changes:

-  PyNMRSTAR automatically retries fetching an entry from the BMR API
   using an exponential backoff if rate limited.
-  PyNMRSTAR now lists the package :doc:`Requests <requests:index>` as a requirement, which
   allows it to significantly speed up fetching entries
   from the database. It will still work if requests is not installed
   though, as in the case where you have checked out
   the code locally and don't have requests installed - you just won't
   get the enhanced performance.

Breaking changes:

-  The default value of ``skip_empty_loops`` of the methods
   :py:meth:`pynmrstar.Entry.write_to_file` and :py:meth:`pynmrstar.Saveframe.write_to_file` has
   been changed to ``True`` to write out empty loops. Technically
   according to the NMR-STAR format, empty loops should
   be omitted. In practice, many libraries fail to treat a missing tag
   as equivalent to a present but null tag, and
   would be confused by the fact that reading in a file and writing it
   back out again would cause these empty loops to
   go missing. You can still manually specify ``skip_empty_loops=True``
   to maintain the previous behavior.

3.0.9
~~~~~

Changes:

-  The library now tolerates keywords (``save_``, ``stop_``, etc.) that are
   not entirely lowercase which is technically allowed according to the STAR
   specification.
-  Minor improvements to the c module

Breaking changes:

-  When calling :py:meth:`pynmrstar.Loop.filter` with ``ignore_missing_tags=False``,
   the Loop will now throw a :py:exc:`KeyError` rather than a :py:exc:`ValueError`.

3.0.8
~~~~~

Changes:

-  Extra validation of tag names in saveframes and loops to ensure that
   users do not create tag names which contain whitespace or are the empty string.
-  :py:attr:`pynmrstar.Saveframe.name` has been converted to a property from an attibute.
   This allows extra verification of the saveframe name, so that it can also be checked to
   ensure it does not contain whitespace or the empty string. This should generally not
   affect calling code.
-  Updated code to use new api.bmrb.io domain when fetching entries

Potentially breaking change:

-  When the name of a saveframe is reassigned, if the tag ``sf_framecode``,
   is present, it is automatically updated. Also, if the tag ``sf_framecode``
   is assigned, then the saveframe name is updated.

3.0.7
~~~~~

Yanked due to a packaging error.

3.0.6
~~~~~

Changes:

-  If there is an issue with the number of data elements in a loop
   during parsing, raise a :py:exc:`pynmrstar.exceptions.ParsingError` rather than the :py:exc:`ValueError` that
   would be raised normally.
-  :py:meth:`pynmrstar.Entry.write_to_file` had a default value of ``True`` for
   ``skip_empty_tags`` - this value has been changed to a default of ``False`` to match the
   default for :py:meth:`pynmrstar.Saveframe.write_to_file()`.

3.0.5
~~~~~

Changes:

-  Add new :py:exc:`pynmrstar.exceptions.FormattingException`, and throw it when formatting an entry with an
   empty string as a tag value with context information, rather than just allowing
   the :py:exc:`ValueError` from :py:func:`pynmrstar.utils.quote_value` to go uncaught. **Note** - This exception
   has since been renamed to :py:exc:`pynmrstar.exceptions.InvalidStateError`
-  :py:meth:`pynmrstar.Entry.__str__` and :py:meth:`pynmrstar.Saveframe.__str__`
   show empty loops to help development, but :py:meth:`pynmrstar.Entry.format`,
   :py:meth:`pynmrstar.Entry.write_to_file`, :py:meth:`pynmrstar.Saveframe.format`,
   and :py:meth:`pynmrstar.Saveframe.write_to_file` still do not
-  Update to :py:meth:`pynmrstar.Entry.normalize` to ensure that all tags have the proper
   capitalization.
-  Minor improvement in behavior of :py:meth:`pynmrstar.Loop.filter` to preserve the case
   of the existing tags if the filtered tags were the same but with different
   capitalization.

3.0.4
~~~~~

Changes:

-  Update packaging to mark that the 3.x branch is only for Python3.

3.0.2, 3.03
~~~~~~~~~~~

Changes:

-  Minor bug fixes to :py:meth:`pynmrstar.Entry.normalize`

3.0.1
~~~~~

Changes:

-  Added support for ``skip_empty_tags`` in :py:meth:`pynmrstar.Entry.write_to_file`
   and :py:meth:`pynmrstar.Saveframe.write_to_file`.
   Originally it was only available in :py:meth:`pynmrstar.Entry.format`

3.0
~~~

3.0 has been a long time coming! There are some major improvements,
specifically:

- Type annotations for all functions and classes
- Classes are broken out into their own files
- More consistent method naming in a few places
- A lot of minor improvements and cleanup

As much as possible, old method and functions have been preserved with
a :py:exc:`DeprecationWarning` to help you migrate to version 3. Using an editor like PyCharm will show where
your code using the PyNMR-STAR v2 library may be using deprecated methods/functions or have other
incompatibilities with version 3.

If you do not have the time to make the minor changes that may be
needed to start working with version 3, you can continue using the version 2 branch, which will no longer receive
updates, but will still have any major bugs fixed. To do that, either checkout the v2 branch
from GitHub, or if using PyPI, simply specify ``pynmrstar<=3`` rather than ``pynmrstar`` when using
``pip install`` or a ``requirements.txt`` file.

Breaking changes:

-  :py:meth:`pynmrstar.Saveframe.get_tag` now returns a list of values rather than a
   single value. This is to be consistent with :py:meth:`pynmrstar.Loop.get_tag`
   and :py:meth:`pynmrstar.Entry.get_tag`.

   Furthermore, calling :py:meth:`pynmrstar.Entry.get_tag`
   or :py:meth:`pynmrstar.Saveframe.get_tag` will return all values for that
   tag within any children objects. (For example, you can get the
   values of loop tags within a loop in a specific saveframe by calling
   :py:meth:`pynmrstar.Saveframe.get_tag` rather than
   first getting a reference to the Loop and then :py:meth:`pynmrstar.Loop.get_tag`.)
-  Global variables to control behavior have been removed, and
   definitions that under certain circumstances
   might be edited have been moved to the definitions submodule. Those
   previous module-level features have been
   preserved where possible:


-  ``pynmrstar.VERBOSE`` has been replaced with setting the log level using
   the standard logging module
-  ``pynmrstar.RAISE_PARSE_WARNINGS`` has been moved to the
   ``raise_parse_warnings`` argument of the parse() function
   in the parser module
-  ``pynmrstar.SKIP_EMPTY_LOOPS`` is now the default behavior, but empty
   loops can be printed by specifying ``skip_empty_loops=False`` as an argument
   to :py:meth:`pynmrstar.Entry.format`, :py:meth:`pynmrstar.Entry.write_to_file`,
   :py:meth:`pynmrstar.Saveframe.format`, :py:meth:`pynmrstar.Saveframe.write_to_file`,
   :py:meth:`pynmrstar.Loop.format`
-  NMR-STAR 2.1 files are no longer supported. NMR-STAR 2.1 is no longer
   officially supported by the BMRB. Please
   refer to `this resource <https://bmrb.io/bmrb/news/20200407.shtml>`__
   if you still have 2.1 files you need to convert.

Other changes:

-  :py:class:`pynmrstar.Entry`, :py:class:`pynmrstar.Saveframe`, and
   :py:class:`pynmrstar.Loop` have a ``format()`` method to customize how
   the entry is formatted. Use this if you want to only show tags with values,
   hide comments, etc. The ``skip_empty_tags`` argument will only print tags
   with non-null values.
-  :py:attr:`pynmrstar.Entry.entry_id` is now a property rather than a variable. When set,
   it will update the ``Entry_ID`` tags throughout the entry automatically
-  The :py:meth:`pynmrstar.Entry.normalize` method has been made more robust and fully
   featured than in v2.

2.6.5
~~~~~

Releases from this point forward will only fix bugs, no new features
will be added on the 2.x branch. Please prepare to migrate your code to the 3.x
branch once you are running in a Python3 environment.

Changes:

-  Fix a bug in :py:meth:`pynmrstar.Entry.normalize` which sorted loop and saveframe tags
   according to the default schema rather than provided schema.
-  Added :py:exc:`DeprecationWarning` to methods and functions that are removed in
   v3.x releases or will be removed in the future.
-  Fix a bug in :py:meth:`pynmrstar.Loop.filter` triggered when a loop only has one tag.

2.6.4
~~~~~

Changes:

-  Fixed a bug in the c tokenizer which would incorrectly throw a parse
   exception if a file had a comment prior to the ``data_ENTRY_ID`` token.
-  Fixed a bug in :py:meth:`pynmrstar.Loop.add_data` that would replace the
   existing data rather than appending to it.

2.6.3
~~~~~

Changes:

-  Improvements to :py:meth:`pynmrstar.Entry.from_template`
-  Added new :py:attr:`pynmrstar.Saveframe.empty` and :py:attr:`pynmrstar.Loop.empty`
   properties which will indicate if the saveframe or loop has any tag values set.
-  Added option ``default_values`` to :py:meth:`pynmrstar.Entry.from_template`,
   :py:meth:`pynmrstar.Saveframe.from_template` and :py:meth:`pynmrstar.Loop.from_template`
   classmethods which will set tags to the schema defined default value if present.
-  Fix a bug in :py:meth:`pynmrstar.Entry.write_to_file` and :py:meth:`pynmrstar.Saveframe.write_to_file`
   which would write an empty output file if an exception occurred during string formatting.
   Instead the output file is not touched if an error occurs.
-  Updated built-in schema to 3.2.1.5

2.6.2
~~~~~

Changes:

-  Added :py:func:`pynmrstar.utils.iter_entries` generator for retrieving all BMRB entries.
-  Added :py:meth:`pynmrstar.Entry.from_template` method
-  Only print saveframe descriptions once per category
-  Code linting

Breaking changes:

-  Converted ``frame_dict`` and ``category_list`` methods of ``Entry``
   class into properties (:py:attr:`pynmrstar.Entry.frame_dict` and :py:attr:`pynmrstar.Entry.category_list`).
   You will need to remove the () from your code if you use those methods.