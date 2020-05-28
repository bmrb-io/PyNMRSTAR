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
refer to [this resource](http://www.bmrb.wisc.edu/bmrb/news/20200407.shtml) if you still have 2.1 files you 
need to convert.

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