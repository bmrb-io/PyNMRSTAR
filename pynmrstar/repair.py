"""Repairs that change an entry, and that a caller has to ask for.

:meth:`pynmrstar.Entry.normalize` already applies every repair that is safe to
run unconditionally -- sorting, framecode fixing, ID assignment, reference
updating. What lives here is the other kind: a change large or opinionated
enough that it should be a caller's explicit decision, not a side effect of
tidying an entry up.

They are functions taking an entry rather than methods on it, deliberately.
:class:`pynmrstar.Entry` is a model of an NMR-STAR file; dictionary-driven
surgery on one is a separate concern, and keeping it out of the class means the
model's API stays small enough to hold in your head.
"""

from typing import Dict, List, Optional

from pynmrstar import definitions, loop as loop_mod, utils
from pynmrstar.schema import Schema
from pynmrstar.validation import _MandatoryResolver

__all__ = ['insert_mandatory_tags']


def insert_mandatory_tags(entry, schema: Optional[Schema] = None,
                          profile: Optional[str] = None,
                          add_missing_loops: bool = True,
                          entry_id: Optional[str] = None) -> None:
    """Add the tags the dictionary requires but the entry does not supply, each
    with its dictionary default or ``?``.

    The counterpart of ``check_mandatory_tags``: it adds exactly the tags that
    check reports as absent. A tag is added when all of the following hold:

    * the dictionary places it in this saveframe's category;
    * it is **metadata** -- annotation, not measurement. A missing chemical
      shift is not something to conjure a column for;
    * it is **not auto-inserted**. A tag a deposition tool fills in by itself is
      that tool's to write, and every tag carrying a default value is in that
      set (see :attr:`pynmrstar.Schema.auto_inserted_tags`), which is why in
      practice the value written here is always ``?``;
    * its mandatory code, once any conditional rule is applied, is neither
      optional nor invalid -- so ``M``, ``V``, ``C`` and ``R`` alike are added.
      Conditional means "required once this saveframe exists", and the saveframe
      does exist.

    **A required tag whose whole loop is missing brings the loop with it**,
    unless ``add_missing_loops`` is false. The new loop gets every column the
    dictionary gives its category -- not only the required ones, since a loop is
    a form to be filled in -- and a single row: the row-index column numbered
    ``0``, ``*.Entry_ID`` set to ``entry_id``, every other column its default or
    ``?``. ``Sf_ID`` columns are left out; they are bookkeeping a tool
    maintains, not something to fill in.

    Note that this is a much narrower operation than
    :meth:`pynmrstar.Saveframe.add_missing_tags`, which adds every tag of a
    saveframe's own prefix that is not marked invalid. This adds only what is
    required, judged against a named profile and with the conditional rules
    resolved, and it reaches the saveframe's whole category rather than its own
    prefix -- which is what lets it notice a missing loop at all.

    :param entry: the entry to add tags to, modified in place
    :param schema: the dictionary to read; the cached current one by default
    :param profile: which view of the dictionary's mandatory flags to apply.
        Defaults to ``public``; a tool working on entries before release wants
        ``internal``, which requires more
    :param add_missing_loops: whether a required tag may bring a whole new loop
        with it. Set false to add free tags and columns of existing loops only
    :param entry_id: the value for ``*.Entry_ID`` columns of any loop this
        creates. Defaults to the entry's own ``_Entry.ID``, or ``?`` when that
        is absent or null
    """

    my_schema: Schema = utils.get_schema(schema)
    resolver = _MandatoryResolver(entry, my_schema, profile)

    if entry_id is None:
        entry_id = '?'
        for value in entry.get_tag('_Entry.ID'):
            if value is not None and str(value).strip() not in definitions.NULL_VALUES:
                entry_id = value
            break

    def default_for(tag: str) -> str:
        """What to write into a tag being created empty."""

        if tag.endswith('.entry_id'):
            return entry_id
        return my_schema.default_values.get(tag, '?')

    # The tags worth considering, grouped by the saveframe category they belong
    # to and ordered as the dictionary orders them. Auto-inserted tags are
    # dropped here rather than per saveframe: they are never added, whatever
    # their mandatory code says.
    by_category: Dict[str, List[str]] = {}
    for tag, tag_data in my_schema.schema.items():
        if tag_data.get('Meta data') != 'Y' or tag in my_schema.auto_inserted_tags:
            continue
        category = (tag_data.get('SFCategory') or '').strip()
        if category:
            by_category.setdefault(category, []).append(tag)
    for tags in by_category.values():
        tags.sort(key=lambda _: int(my_schema.schema[_].get('Dictionary sequence') or 0))

    # Every loop column the dictionary gives a category, in dictionary order,
    # for the loops this may have to create.
    columns: Dict[str, List[str]] = {}
    for tag, tag_data in my_schema.schema.items():
        if (tag_data.get('Loopflag') or '').strip() != 'Y':
            continue
        if (tag_data.get('Saveframe ID tag') or '').strip() == 'Y':
            continue
        columns.setdefault(f"{(tag_data.get('SFCategory') or '').strip()}|"
                           f"{tag.rsplit('.', 1)[0]}", []).append(tag)
    for tags in columns.values():
        tags.sort(key=lambda _: int(my_schema.schema[_].get('Dictionary sequence') or 0))

    for saveframe in entry:
        category = my_schema.schema.get(
            f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        if not category:
            continue

        present = {f'{saveframe.tag_prefix}.{name}'.lower() for name, _ in saveframe.tags}
        for loop in saveframe.loops:
            present.update(f'{loop.category}.{name}'.lower() for name in loop.tags)

        for tag in by_category.get(category, []):
            if tag in present:
                continue
            code = resolver.code(tag, saveframe, category)
            if code in ('O', 'I'):
                continue

            full_tag = my_schema.schema[tag]['Tag']
            if (my_schema.schema[tag].get('Loopflag') or '').strip() != 'Y':
                saveframe.add_tag(full_tag, default_for(tag))
                present.add(tag)
                continue

            loop_category = full_tag.rsplit('.', 1)[0]
            loop = None
            for candidate in saveframe.loops:
                if (candidate.category or '').lower() == loop_category.lower():
                    loop = candidate
                    break

            if loop is not None:
                loop.add_tag(full_tag, update_data=True)
                position = loop.tag_index(full_tag)
                for row in loop.data:
                    row[position] = default_for(tag)
                present.add(tag)
                continue

            if not add_missing_loops:
                continue

            new_columns = columns.get(f'{category}|{loop_category.lower()}', [tag])
            loop = loop_mod.Loop.from_scratch(category=loop_category)
            row = []
            for column in new_columns:
                loop.add_tag(my_schema.schema[column]['Tag'])
                index_key = (my_schema.schema[column].get('Row Index Key') or '').strip()
                row.append('0' if index_key == 'Y' else default_for(column))
            loop.data.append(row)
            saveframe.add_loop(loop)
            present.update(new_columns)
