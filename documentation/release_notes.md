### 3.2

Changes:
* Significant extra detail added to most error messages.
* A new exception called InvalidStateError is thrown when trying to perform actions which cannot be completed because
  the current state of the objects cannot be properly mapped to NMR-STAR. When using the appropriate setters and getters
  rather than directly modifying object attributes, it is somewhat hard to create such invalid states. The exception
  inherits from ValueError (which is the exception that used to be thrown in these circumstances) so no code changes
  should be necessary to catch these exceptions.
* The parser now properly handles some ultra rare edge cases during loop parsing during which it previously either 
  threw exceptions when it shouldn't have, or failed to throw an exception when it should have.
* Deprecated Loop.add_data_by_tag(). This was originally used internally when parsing an entry, but it is recommended
  to use Loop.add_data() instead, or `loop[['Number', 'Unit']] = [[1,2,3],['db', 'atm', 'bar']]` style assignments.
  New methods to make tag assignment in a loop easier are also being considered.

Potentially breaking changes:
* Saveframe tags no longer store the line number from which a tag was originally read. This was not
  always set anyway, since saveframes could also be created from scratch. This was also never advertised to calling
  code, so it's very unlikely this change will affect you.
* Long deprecated methods Loop.add_column(), Loop.add_data_by_column(), and Loop.get_columns() were removed.


### 3.1.0

Changes:
* PyNMRSTAR automatically retries fetching an entry from the BMR API using an exponential backoff if rate limited.
* PyNMRSTAR now lists the package `requests` as a requirement, which allows it to significantly speed up fetching entries
  from the database. It will still work if requests is not installed though, as in the case where you have checked out
  the code locally and don't have requests installed - you just won't get the enhanced performance.

Breaking changes:
* The default value of `skip_empty_loops` of the method `write_to_file()` for both `Entry` and `Saveframe` has 
  been changed to `True` to write out empty loops. Technically according to the NMR-STAR format, empty loops should
  be omitted. In practice, many libraries fail to treat a missing tag as equivalent to a present but null tag, and 
  would be confused by the fact that reading in a file and writing it back out again would cause these empty loops to
  go missing. You can still manually specify `skip_empty_loops=True` to maintain the previous behavior.
  

### 3.0.9

Changes:
* The library now tolerates keywords (save_, stop_, etc.) that are not entirely lowercase which
is technically allowed according to the STAR specification.
* Minor improvements to the c module

Breaking changes:
* When calling .filter() on a Loop with ignore_missing_tags=False, the Loop will now throw a KeyError
rather than a ValueError.

### 3.0.8

Changes:

* Extra validation of tag names in saveframes and loops to ensure that users do not
create tag names which contain whitespace or are the empty string.
* Saveframe.name has been converted to a property. This allows extra verification of the
saveframe name, so that it can also be checked to ensure it does not contain whitespace or
the empty string. This should generally not affect calling code.
* Updated code to use new api.bmrb.io domain when fetching entries

Potentially breaking change: When the name of a saveframe is reassigned, if the tag
`sf_framecode`, if present, it is automatically updated. Also, if the tag `sf_framecode`
is assigned, then the saveframe name is updated.

### 3.0.7

Yanked due to a packaging error.

### 3.0.6

Changes:

* If there is an issue with the number of data elements in a loop during
parsing, raise a `ParsingError` rather than the `ValueError` that would be raised
normally.
* Entry.write_to_file() had a default value of `True` for `skip_empty_tags` - 
this value has been changed to a default of `False` to match the default for
Saveframe.write_to_file().

### 3.0.5

Changes:
* Add new FormattingException, and throw it when formatting an entry with an empty string
 as a tag value with context information, rather than just allowing the ValueError from
  quote_value to go uncaught.
* \_\_str__ shows empty loops to help development, but  format() and write_to_file() still do not
* Update to Entry.normalize() to ensure that all tags have the proper capitalization.
* Minor improvement in behavior of Loop.filter() to preserve the case of the
existing tags if the filtered tags were the same but with different capitalization.

### 3.0.4

Changes:
* Update packaging to mark that the 3.x branch is only for Python3.

### 3.0.2, 3.03

Changes:
* Minor bug fixes to normalize()

### 3.0.1

Changes:
* Added support for skip_empty_tags in `write_to_file()`. Originally it was only available
in `format()`.

### 3.0

3.0 has been a long time coming! There are some major improvements, specifically:

1. Type annotations for all functions and classes
2. Classes are broken out into their own files
3. More consistent method naming in a few places
4. A lot of minor improvements and cleanup

As much as possible, old method and functions have been preserved with a DeprecationWarning to help
you migrate to version 3. Using an editor like PyCharm will show where your code using the PyNMR-STAR
v2 library may be using deprecated methods/functions or have other incompatibilities with version 3.

If you do not have the time to make the minor changes that may be needed to start working with version 3, you
can continue using the version 2 branch, which will no longer receive updates, but will still 
have any major bugs fixed. To do that, either checkout the v2 branch from GitHub, or if using PyPI,
simply specify `pynmrstar<=3` rather than `pynmrstar` when using `pip install` or a `requirements.txt`
file.

Breaking changes:

1. Saveframe.get_tag() now returns a list of values rather than a single value. This
is to be consistent with Loop.get_tag() and Entry.get_tag(). Furthermore, calling get_tag() on an Entry
or Saveframe will return all values for that tag within any children objects. (For example, you can get the
values of loop tags within a loop in a specific saveframe by calling get_tag() on the Saveframe rather than
first getting a reference to the Loop and then calling get_tag().)
2. Global variables to control behavior have been removed, and definitions that under certain circumstances
might be edited have been moved to the definitions submodule. Those previous module-level features have been
preserved where possible:
   * pynmrstar.VERBOSE has been replaced with setting the log level using the standard logging module
   * pynmrstar.RAISE_PARSE_WARNINGS has been moved to the raise_parse_warnings argument of the parse() function
   in the parser module
   * pynmrstar.SKIP_EMPTY_LOOPS is now the default behavior, but empty loops can be printed by specifying 
   skip_empty_loops=True as an argument to Entry.format(), Entry.write_to_file(), Saveframe.format(),
   Saveframe.write_to_file(), or Loop.format()
3. NMR-STAR 2.1 files are no longer supported. NMR-STAR 2.1 is no longer officially supported by the BMRB. Please
refer to [this resource](https://bmrb.io/bmrb/news/20200407.shtml) if you still have 2.1 files you 
need to convert.

Other changes:
* Entry, Saveframe, and Loop have a .format() method to customize how the entry is formatted. Use this if you
want to only show tags with values, hide comments, etc. The `skip_empty_tags` argument will only print
tags with non-null values.
* Entry.entry_id is now a property rather than a variable. When set, it will update the "Entry_ID" tags
throughout the entry automatically
* The `normalize` function has been made more robust and fully featured than in v2.

### 2.6.5

Releases from this point forward will only fix bugs, no new features will be added
on the 2.x branch. Please prepare to migrate your code to the 3.x branch once you
are running in a Python3 environment.

Changes:

* Fix a bug in normalize() which sorted loop and saveframe tags according to the default schema
rather than provided schema.
* Added DeprecationWarning to methods and functions that are removed in v3.x releases or will
be removed in the future.
* Fix a bug in Loop.filter() triggered when a loop only has one tag.

### 2.6.4

Changes:

* Fixed a bug in the c tokenizer which would incorrectly throw a parse exception if a file had
a comment prior to the `data_ENTRY_ID` token.
* Fixed a bug in add_data that would replace the existing data rather than appending to it.

### 2.6.3

Changes:

* Improvements to Entry.from_template()
* Added new `empty` property to saveframes and loops which will indicate if the saveframe or loop
has any tag values set.
* Added option `default_values` to `from_template()` classmethods which will set tags to the
schema defined default value if present. 
* Fix a bug in `write_to_file` which would write an empty output file if an exception occurred
during string formatting of an entry/saveframe. Instead the output file is not touched if an error
occurs.
* Updated built in schema to 3.2.1.5


### 2.6.2

Changes:

* Added iter_entries() generator for retrieving all BMRB entries.
* Added from_template() for Entry
* Only print saveframe descriptions once per category
* Code linting

<b>Breaking changes</b>:

Converted `frame_dict` and `category_list` methods of `Entry` class into properties. You will
need to remove the () from your code if you use those methods.