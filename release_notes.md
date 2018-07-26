### 2.6.2

Changes:

* Added iter_entries() generator for retrieving all BMRB entries.
* Added from_template() for Entry
* Only print saveframe descriptions once per category
* Code linting

<b>Breaking change</b>:

Converted `frame_dict` and `category_list` methods of `Entry` class into properties. You will
need to remove the () from your code if you use those methods.