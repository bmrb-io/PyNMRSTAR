### 2.6.6

Updated URLs now that BMRB has moved to BMRB.io.

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