"""The structured validation model used by :meth:`pynmrstar.Entry.validate_full`.

The older ``validate()`` methods return a list of strings, which is enough to
show a user but not enough to act on: there is no way to filter by severity,
locate the offending tag, or recognise a finding across runs. Everything here
exists to give a finding an identity -- a machine-readable check name, a
severity, and the saveframe/loop/tag it came from -- so that a caller can route
it, suppress it, or render it in its own format.
"""

import enum
import re
from functools import lru_cache
from typing import Any, Dict, Iterator, List, NamedTuple, Optional

from pynmrstar import definitions
from pynmrstar._internal import _non_ascii_error
from pynmrstar.schema import _is_valid_date

__all__ = ['Severity', 'ValidationIssue']


class Severity(str, enum.Enum):
    """How much a validation finding matters.

    The first four mirror the severities BMRB's validator has always used.
    :attr:`STRICT` is the one addition, and it is about *provenance* rather than
    seriousness: it marks a genuine dictionary violation that BMRB's own
    validator does not report. Those findings are real -- a ``code``-typed tag
    holding spaces, say -- but surfacing them alongside the others would change
    what annotators see on entries that have always passed. Keeping them in
    their own band means a caller can present the historical result exactly and
    still offer the stricter one.
    """

    CRITICAL = 'critical'
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'info'
    STRICT = 'strict'

    def __str__(self) -> str:
        return self.value


class ValidationIssue:
    """One validation finding.

    Location is recorded as identity (which saveframe, which loop, which tag,
    which row) rather than as a line number, because pynmrstar's model does not
    carry line numbers -- a caller that needs them renders the entry and maps
    identity onto the render.
    """

    __slots__ = ['severity', 'check', 'message', 'saveframe', 'category', 'tag', 'loop', 'row', 'value']

    def __init__(self, severity: Severity, check: str, message: str, *,
                 saveframe: Optional[str] = None, category: Optional[str] = None,
                 tag: Optional[str] = None, loop: Optional[str] = None,
                 row: Optional[int] = None, value: Optional[Any] = None) -> None:
        self.severity: Severity = severity
        #: Machine-readable check name, e.g. ``saveframe.duplicate_name``.
        self.check: str = check
        self.message: str = message
        self.saveframe: Optional[str] = saveframe
        self.category: Optional[str] = category
        self.tag: Optional[str] = tag
        self.loop: Optional[str] = loop
        self.row: Optional[int] = row
        self.value: Optional[Any] = value

    def __repr__(self) -> str:
        return f"<ValidationIssue {self.severity} {self.check}: {self.message}>"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.message}"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ValidationIssue):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def _key(self) -> tuple:
        return (self.severity, self.check, self.message, self.saveframe,
                self.category, self.tag, self.loop, self.row)

    def to_dict(self) -> Dict[str, Any]:
        """The issue as a plain dictionary, for serialization."""

        return {
            'severity': str(self.severity),
            'check': self.check,
            'message': self.message,
            'saveframe': self.saveframe,
            'category': self.category,
            'tag': self.tag,
            'loop': self.loop,
            'row': self.row,
            'value': self.value,
        }


def _free_tag(saveframe, name: str) -> List[Any]:
    """The values of one of a saveframe's own tags, ignoring its loops.

    ``Saveframe.get_tag`` also searches the loops, and raises if a loop that
    could hold the tag does not -- which happens for a saveframe containing a
    loop of its own category. Here only the saveframe's own tags are wanted."""

    folded = name.lower()
    return [value for tag, value in saveframe.tags if tag.lower() == folded]


def _dereference(value: Any) -> Any:
    """A saveframe pointer's value without the ``$`` that marks it as one.

    STAR writes a reference to a saveframe as ``$name`` while the saveframe
    itself is named plainly, so the two only compare equal once the marker is
    removed. The marker is read off the value rather than off the dictionary
    because that is where it is unambiguous: a value written ``$x`` is a
    reference whatever the tag's flags say it should be."""

    if isinstance(value, str) and value.startswith('$'):
        return value[1:]
    return value


class _MetadataScope:
    """Which of an entry's tags describe it, as opposed to being its data.

    The dictionary flags each tag, and the distinction is the difference between
    the few hundred tags an annotator works with and the millions of numbers
    underneath them. The referential checks below only apply to the former --
    they are statements about how an entry's descriptions hang together, and
    running them over every chemical shift would cost far more and say nothing.

    The rule has one wrinkle worth stating: **a loop is in or out as a whole**.
    Its tags are judged by the category, not individually, so a category with
    even one data tag takes the whole loop out. Four of the dictionary's 354 loop
    categories are mixed in this way (``History``, ``Software_applied_methods``,
    ``Coupling_constant``, ``Peak_row_format``), and two of them are common in
    real entries -- so judging tag by tag there would check columns that are
    supposed to be out of scope. A category the dictionary does not know at all
    is in scope, so that an unrecognised loop is still examined rather than
    silently ignored.
    """

    def __init__(self, schema) -> None:
        self._schema = schema
        self._categories: Optional[Dict[str, bool]] = None

    def free(self, full_tag: str) -> bool:
        """Whether a saveframe's own tag is metadata. An unknown tag is."""

        tag_data = self._schema.schema.get(full_tag.lower())
        return tag_data is None or tag_data.get('Meta data') == 'Y'

    def loop(self, category: Optional[str]) -> bool:
        """Whether a loop of this category is metadata, judged over every tag
        the dictionary places in it."""

        if self._categories is None:
            self._categories = {}
            for tag, tag_data in self._schema.schema.items():
                folded = tag.rsplit('.', 1)[0]
                metadata = tag_data.get('Meta data') == 'Y'
                self._categories[folded] = self._categories.get(folded, True) and metadata
        if category is None:
            return True
        return self._categories.get(category.lower(), True)


def check_saveframes(entry, schema, profile: str) -> List[ValidationIssue]:
    """Structural checks over an entry's saveframes.

    Ported from the BMRB validator's ``CheckSaveFrames`` (function 0), which is
    the one check that is entry-wide by nature: duplicate names and categories,
    missing mandatory categories and saveframe ordering are all statements about
    the entry as a whole rather than about any one saveframe.
    """

    issues: List[ValidationIssue] = []
    categories = schema.validation_profile(profile)['categories']

    seen_names: Dict[str, str] = {}
    seen_categories: Dict[str, str] = {}
    present: set = set()
    previous_category: Optional[str] = None
    previous_ordinal: Optional[int] = None

    for saveframe in entry:
        name = saveframe.name

        # A saveframe's category is the one the dictionary gives its tags, not
        # whatever its Sf_category tag happens to say -- those are separate
        # facts, and 0-6 below exists precisely to compare them. Everything that
        # asks "which categories does this entry contain" uses the dictionary's
        # answer, so that a saveframe with a missing or wrong Sf_category value
        # still counts as the category it structurally is.
        category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        # Read the tag rather than Saveframe.category, which caches the value
        # seen at parse time and so would not notice a later edit -- and an
        # edited-in-place value is exactly what this check exists to catch.
        # Scan the saveframe's own tags rather than calling get_tag(), which
        # searches the loops as well: a saveframe can hold a loop of its own
        # category (broken, and reported by check_invalid_tags), and asking that
        # loop for a tag it does not have raises rather than returning nothing.
        declared = _free_tag(saveframe, 'Sf_category')

        # 0-0: the dictionary does not recognise this saveframe's tags at all.
        if not category:
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.missing_category',
                f"Invalid saveframe category for saveframe {name} (missing saveframe label tag?)",
                saveframe=name))
        else:
            present.add(category)

            # 0-6: the Sf_category value disagrees with the dictionary. Only
            # meaningful when the tag is actually there; a saveframe with no
            # Sf_category at all is a mandatory-tag finding, not this one.
            if declared and declared[0] != category:
                issues.append(ValidationIssue(
                    Severity.ERROR, 'saveframe.invalid_category',
                    f"Invalid saveframe category value for saveframe {name}",
                    saveframe=name, category=category,
                    tag=f'{saveframe.tag_prefix}.Sf_category', value=declared[0]))

            # 0-3: a category ADIT may not replicate, appearing more than once.
            if schema.saveframe_categories.get(category, {}).get('unique'):
                if category in seen_categories:
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'saveframe.duplicate_category',
                        f"Duplicate saveframe category: {category} ({name}, previously defined in "
                        f"saveframe {seen_categories[category]})",
                        saveframe=name, category=category))
                else:
                    seen_categories[category] = name

            # 0-5: saveframes out of the dictionary's category order.
            ordinal = schema.saveframe_categories.get(category, {}).get('id')
            if ordinal is not None:
                if previous_ordinal is not None and previous_ordinal > ordinal:
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'saveframe.order',
                        f"Saveframe order error: {category} ({ordinal}) after "
                        f"{previous_category} ({previous_ordinal})",
                        saveframe=name, category=category))
                previous_ordinal, previous_category = ordinal, category

        # 0-1: duplicate saveframe names, compared without regard to case.
        folded = name.lower()
        if folded in seen_names:
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.duplicate_name',
                f"Duplicate saveframe name: {name}", saveframe=name, category=category))
        else:
            seen_names[folded] = name

        # 0-2: the Sf_framecode tag disagrees with the saveframe's own name. The
        # parser keeps both strings rather than reconciling them, which is what
        # makes this checkable at all.
        framecode = _free_tag(saveframe, 'Sf_framecode')
        if framecode and framecode[0] not in definitions.NULL_VALUES and framecode[0] != name:
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.framecode_mismatch',
                f"Saveframe name does not match label: {name} ({framecode[0]})",
                saveframe=name, category=category,
                tag=f'{saveframe.tag_prefix}.Sf_framecode', value=framecode[0]))

    # 0-4: a mandatory saveframe category missing from the entry entirely.
    for category in sorted(_ for _, code in categories.items() if code == 'M'):
        if category not in present:
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.missing_mandatory_category',
                f"Missing mandatory saveframe category {category}", category=category))

    return issues


@lru_cache(maxsize=None)
def _control_pattern(value: str) -> Optional['re.Pattern']:
    """Compile a conditional rule's control value into a pattern.

    The dictionary writes these four ways, distinguished by shape: a bracketed
    character class is implicitly repeated (``[YN]`` means one or more of those
    characters), a parenthesised alternation is already a regular expression,
    a bare ``*`` is a wildcard meaning "any value at all", and anything else is
    matched literally. Patterns are anchored -- the whole value has to match.

    ``None`` means the wildcard: any non-null value satisfies the rule. The
    historical validator hands every control value straight to the regex engine,
    which throws on the 16 rules whose value is ``*``; reading it as the wildcard
    it plainly is keeps those rules working instead.
    """

    if value == '*':
        return None
    if re.fullmatch(r'\[.+]', value):
        pattern = value + '+'
    else:
        pattern = value
    try:
        return re.compile(pattern)
    except re.error:
        # Not a regular expression after all -- compare it as written.
        return re.compile(re.escape(value))


def _matches(pattern: Optional['re.Pattern'], values: List[Any]) -> bool:
    """Whether any non-null value matches the pattern in full.

    A ``None`` pattern is the ``*`` wildcard: any non-null value matches."""

    for value in values:
        if value in definitions.NULL_VALUES:
            continue
        text = str(value).strip()
        if not text or text in ('?', '.'):
            continue
        if pattern is None or pattern.fullmatch(text):
            return True
    return False


def _tag_values(saveframe, full_tag: str) -> List[Any]:
    """The values of a fully qualified tag within one saveframe, or an empty
    list if it is absent.

    ``Loop.get_tag`` raises when a tag is missing from a loop that would
    otherwise hold it -- which here is not an error but the very thing being
    tested for."""

    try:
        return saveframe.get_tag(full_tag)
    except KeyError:
        return []


class _MandatoryResolver:
    """Resolves a tag's mandatory code for one entry, conditional rules included.

    The dictionary gives every tag a code per validation profile, but a
    conditional rule can replace it when some *other* tag holds a particular
    value -- and that control tag is frequently in a different saveframe. So the
    resolution needs the whole entry, and both the mandatory check and the
    invalid-tag check need the same answer for the same tag.

    Control values found outside the tag's own saveframe are cached, since a
    handful of control tags govern many tags across the entry.
    """

    def __init__(self, entry, schema, profile: str) -> None:
        self._entry = entry
        self._schema = schema
        self._codes = schema.validation_profile(profile)['tags']
        self._index = schema._profile_index(profile)
        self._entry_values: Dict[str, List[Any]] = {}

    def _control_values(self, control_tag: str, saveframe, same_category: bool) -> List[Any]:
        """The values a rule's control tag has: looked up within the saveframe
        when the rule is about this category, and across the whole entry
        otherwise."""

        if same_category:
            return _tag_values(saveframe, control_tag)
        if control_tag not in self._entry_values:
            try:
                self._entry_values[control_tag] = self._entry.get_tag(control_tag)
            except ValueError:
                self._entry_values[control_tag] = []
        return self._entry_values[control_tag]

    def code(self, tag: str, saveframe, category: Optional[str]) -> str:
        """The mandatory code that applies to ``tag`` in this saveframe.

        ``tag`` is the lowercase schema key. The first rule whose control value
        matches wins; the historical validator reads only the first rule at all,
        which silently ignores any later one that applies.
        """

        code = self._codes.get(tag, 'O')
        for rule in self._schema.conditional_rules.get(tag, []):
            values = self._control_values(rule['control_tag'], saveframe,
                                          rule['control_category'] == category)
            if _matches(_control_pattern(rule['value']), values):
                return rule['flags'][self._index:self._index + 1].strip().upper() or code
        return code


def check_mandatory_tags(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report tags the dictionary requires but the entry does not supply.

    Ported from the BMRB validator's ``CheckMandatoryTags`` (function 2). Only
    tags flagged as metadata are checked, and a tag's requirement can be
    overridden by a conditional rule keyed on another tag's value -- which is
    why this cannot be done one saveframe at a time: a rule's control tag
    frequently lives in a different saveframe.
    """

    issues: List[ValidationIssue] = []
    resolver = _MandatoryResolver(entry, schema, profile)

    # Tags to check, grouped by the saveframe category they belong to.
    by_category: Dict[str, List[str]] = {}
    for tag, tag_data in schema.schema.items():
        if tag_data.get('Meta data') != 'Y':
            continue
        # The Sf_ID tag is bookkeeping the tools maintain, not something an
        # author supplies, so its absence is never reported.
        if tag_data.get('Saveframe ID tag') == 'Y':
            continue
        category = (tag_data.get('SFCategory') or '').strip()
        if category:
            by_category.setdefault(category, []).append(tag)
    for tags in by_category.values():
        tags.sort(key=lambda _: int(schema.schema[_].get('Dictionary sequence') or 0))

    for saveframe in entry:
        category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        if not category:
            continue

        for tag in by_category.get(category, []):
            # A conditional rule fires when its control tag holds a matching
            # value, and replaces the tag's usual requirement.
            code = resolver.code(tag, saveframe, category)

            if code in ('O', 'I'):
                # Optional needs nothing; an invalid tag that is present is
                # CheckInvalidTags' finding to report, not this one's.
                continue

            # Query with the fully qualified tag: a bare name would resolve
            # against the saveframe's own prefix, which silently misses every
            # tag that lives in one of its loops (and can match the wrong tag
            # of the same name on the saveframe itself).
            full_tag = schema.schema[tag]['Tag']
            values = _tag_values(saveframe, full_tag)

            if code in ('M', 'C'):
                if not values:
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'tag.missing',
                        f"Missing tag: {full_tag}",
                        saveframe=saveframe.name, category=category, tag=full_tag))
            elif code in ('V', 'R'):
                if not values:
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'tag.missing',
                        f"Missing tag that requires a value: {full_tag}",
                        saveframe=saveframe.name, category=category, tag=full_tag))
                elif all(_ in definitions.NULL_VALUES or str(_).strip() in ('?', '.') for _ in values):
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'tag.missing_value',
                        f"Missing value for tag: {full_tag}",
                        saveframe=saveframe.name, category=category, tag=full_tag))

    return issues


def check_invalid_tags(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report tags that do not belong where they are used.

    Ported from the BMRB validator's ``CheckInvalidTags`` (function 1). Four of
    its six sub-checks survive the move to pynmrstar's model, plus part of a
    fifth:

    ==== =========================================================================
    1-0  the tag is unknown *here* -- not in the dictionary at all, or defined
         for a different saveframe category than the one it is used in. A tag
         whose spelling differs from the dictionary's only in capitalization
         belongs here too: pynmrstar's lookups ignore case but the dictionary
         does not
    1-1  a loop tag used as a free saveframe tag
    1-2  a free tag used inside a loop
    1-5  the same tag used twice within one saveframe
    1-6  the dictionary marks the tag invalid for this profile (``I``), possibly
         by way of a conditional rule
    ==== =========================================================================

    1-3 (tag without a category) and 1-4 (tag category changes within a loop)
    cannot arise: pynmrstar requires a ``_Category.Tag`` name and gives a loop
    exactly one category, so such a file fails to parse.

    Two of the surviving five are narrower than they look, because a saveframe
    has one tag prefix and a loop has one category:

    * **1-1 cannot currently fire.** Writing a loop tag freely means writing a
      tag whose prefix differs from the saveframe's, which the parser rejects --
      unless the prefix carries free tags too, and in this dictionary no prefix
      carries both. The check is kept because that is a property of the
      dictionary, not of the format.
    * **1-5 only fires on one arrangement.** Two free tags of the same name, a
      repeated column in a loop, and two loops of one category all raise while
      parsing. What survives is a tag that is both a free tag and a column of a
      loop whose category is the saveframe's own prefix.

    Note that the historical check identifies a tag by ``{saveframe category,
    tag name}``, so every tag of a saveframe whose category is unrecognised is
    reported as unknown. That is deliberate there and kept here: the alternative
    is to report nothing until the saveframe is fixed and the check re-run.
    """

    issues: List[ValidationIssue] = []
    resolver = _MandatoryResolver(entry, schema, profile)

    def examine(full_tag: str, saveframe, category: Optional[str],
                loop: Optional[str]) -> None:
        """Check one tag, used either freely (``loop`` is None) or in a loop."""

        tag_data = schema.schema.get(full_tag.lower())
        if tag_data is None or (tag_data.get('SFCategory') or '').strip() != category:
            issues.append(ValidationIssue(
                Severity.ERROR, 'tag.unknown', f"Unknown tag {full_tag}",
                saveframe=saveframe.name, category=category, tag=full_tag, loop=loop))
            return

        # A tag spelled with the wrong capitalization. pynmrstar's own lookups
        # are case-insensitive, but the dictionary is not: the historical
        # validator matches the name exactly and so reports this as an unknown
        # tag. It is the same finding, and naming the correct spelling makes it
        # actionable -- the same treatment closed-enumeration values get. Like an
        # unknown tag, it stops the checks below, which would otherwise repeat
        # the complaint in less useful words.
        if full_tag != tag_data['Tag']:
            issues.append(ValidationIssue(
                Severity.ERROR, 'tag.miscapitalized',
                f"The tag '{full_tag}' is improperly capitalized but otherwise valid. "
                f"Should be '{tag_data['Tag']}'.",
                saveframe=saveframe.name, category=category, tag=full_tag, loop=loop))
            return

        # Placement. The dictionary's Loopflag says which side of a loop a tag
        # belongs on; either mismatch is a structural error even though the tag
        # itself is a real one.
        if loop is None and tag_data.get('Loopflag') == 'Y':
            issues.append(ValidationIssue(
                Severity.ERROR, 'tag.not_in_loop', f"Tag not in loop: {full_tag}",
                saveframe=saveframe.name, category=category, tag=full_tag))
        elif loop is not None and tag_data.get('Loopflag') == 'N':
            issues.append(ValidationIssue(
                Severity.ERROR, 'tag.free_in_loop', f"Free tag in loop: {full_tag}",
                saveframe=saveframe.name, category=category, tag=full_tag, loop=loop))

        # A tag the profile forbids outright. Resolved through the conditional
        # rules, so a tag can be invalid only for entries of a certain kind.
        #
        # Only metadata tags are asked. A profile's flags describe one view of
        # the dictionary, and a view that annotates metadata marks the bulk
        # experimental tags 'I' simply because they are outside it -- the
        # ``internal`` view does that to 93% of the non-metadata tags. That is a
        # statement about the view's scope, not about the file, and reporting it
        # would bury the real findings under thousands of entries' worth of
        # perfectly good data. (The historical validator reaches the same place
        # by a different route: its loader never puts data tags in the database,
        # so this check never sees them.)
        if tag_data.get('Meta data') != 'Y':
            return
        if resolver.code(full_tag.lower(), saveframe, category) == 'I':
            issues.append(ValidationIssue(
                Severity.ERROR, 'tag.invalid', f"Invalid tag: {full_tag}",
                saveframe=saveframe.name, category=category, tag=full_tag, loop=loop))

    for saveframe in entry:
        category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        if category is not None:
            category = category.strip() or None

        # 1-5: the same tag twice in one saveframe. Most ways of writing that do
        # not survive parsing -- two free tags of the same name, a repeated
        # column within a loop, and two loops of the same category all raise --
        # so what reaches here is the one arrangement pynmrstar accepts: a tag
        # that is both a free tag and a column of a loop whose category is the
        # saveframe's own prefix. Each occurrence is reported, which is what the
        # historical check does (its self-join yields a row per occurrence).
        places: Dict[str, List[Optional[str]]] = {}

        for tag in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag[0]}'
            places.setdefault(full_tag.lower(), []).append(None)
            examine(full_tag, saveframe, category, None)

        for loop in saveframe:
            for tag in loop.tags:
                full_tag = f'{loop.category}.{tag}'
                places.setdefault(full_tag.lower(), []).append(loop.category)
                examine(full_tag, saveframe, category, loop.category)

        for full_tag, found in places.items():
            if len(found) < 2:
                continue
            display = schema.schema.get(full_tag, {}).get('Tag', full_tag)
            for loop in found:
                issues.append(ValidationIssue(
                    Severity.ERROR, 'tag.duplicate', f"Duplicate tag: {display}",
                    saveframe=saveframe.name, category=category, tag=display, loop=loop))

    return issues


def _ordered_tags(saveframe, schema, category: Optional[str]):
    """Every tag of a saveframe in the order it is written, with its dictionary
    sequence number.

    Yields ``(full tag, sequence, loop category or None)``, skipping tags the
    dictionary does not place in this saveframe's category -- those have no
    sequence to compare, and are ``check_invalid_tags``' business anyway.

    "The order it is written" is the order pynmrstar renders: a saveframe's own
    tags, then each loop's declarations. The model does not record an original
    interleaving of free tags and loops, which costs nothing here because the
    validator normalizes the buffer before validating -- the render *is* the file
    the line numbers refer to.
    """

    def sequence(full_tag: str) -> Optional[int]:
        tag_data = schema.schema.get(full_tag.lower())
        if tag_data is None or (tag_data.get('SFCategory') or '').strip() != category:
            return None
        raw = (tag_data.get('Dictionary sequence') or '').strip()
        return int(raw) if raw.isdigit() else None

    for tag in saveframe.tags:
        full_tag = f'{saveframe.tag_prefix}.{tag[0]}'
        found = sequence(full_tag)
        if found is not None:
            yield full_tag, found, None

    for loop in saveframe:
        for tag in loop.tags:
            full_tag = f'{loop.category}.{tag}'
            found = sequence(full_tag)
            if found is not None:
                yield full_tag, found, loop.category


def _row_index_tag(loop, schema) -> Optional[str]:
    """The tag that numbers a loop's rows, or ``None`` if it has none.

    The dictionary marks one tag per loop category as its row index. A loop
    whose category it does not recognise has no index to check."""

    for tag in loop.tags:
        tag_data = schema.schema.get(f'{loop.category}.{tag}'.lower())
        if tag_data is not None and (tag_data.get('Row Index Key') or '').strip() == 'Y':
            return tag
    return None


def check_row_indexes(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report loops whose row-index column does not count 1, 2, 3, ...

    Ported from the BMRB validator's ``CheckRowIndexes`` (function 18) -- the
    one check the original runs over the file directly rather than over the
    database, which here makes no difference at all.

    After a wrong index the expectation resyncs to *that* value plus one, so a
    loop numbered from zero, or one with a row inserted, reports its first bad
    row and not every row after it. A lone outlier consequently costs two
    findings -- itself, and the row after it that goes back to counting where it
    left off. Both behaviours are the original's, verified against it.

    A negative index is neither "not a number" nor compared: the original
    guards its comparison with ``index >= 0``, so a negative value only
    advances the count. Reproduced rather than tidied -- it is the difference
    between reporting a row and not, and quietly diverging on a real entry is
    worse than an odd-looking branch.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []

    for saveframe in entry:
        category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        if category is not None:
            category = category.strip() or None

        for loop in saveframe:
            index_tag = _row_index_tag(loop, schema)
            if index_tag is None:
                continue

            full_tag = f'{loop.category}.{index_tag}'
            position = loop.tags.index(index_tag)
            expected = 1

            for number, row in enumerate(loop.data):
                value = row[position] if position < len(row) else None
                try:
                    index = int(str(value))
                except (TypeError, ValueError):
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'row.index_not_a_number',
                        f"Not a number: {value}({full_tag})",
                        saveframe=saveframe.name, category=category, tag=full_tag,
                        loop=loop.category, row=number, value=value))
                    expected += 1
                    continue

                if index < 0:
                    expected += 1
                    continue
                if index != expected:
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'row.index_wrong',
                        f"Incorrect row index, expected {expected}({full_tag})",
                        saveframe=saveframe.name, category=category, tag=full_tag,
                        loop=loop.category, row=number, value=value))
                expected = index + 1

    return issues


def check_tag_order(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report tags written out of the dictionary's order.

    Ported from the BMRB validator's ``CheckTagOrder`` (function 5). Order is
    only ever compared *within* a saveframe, and only against the tag
    immediately before -- so a single misplaced tag is reported once, where
    comparing against the highest sequence seen so far would report every tag
    after it as well.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []

    for saveframe in entry:
        category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
        if category is not None:
            category = category.strip() or None

        previous_tag: Optional[str] = None
        previous_sequence: Optional[int] = None
        for full_tag, sequence, loop in _ordered_tags(saveframe, schema, category):
            if previous_sequence is not None and sequence < previous_sequence:
                issues.append(ValidationIssue(
                    Severity.ERROR, 'tag.order',
                    f"Invalid tag order: {full_tag} ({sequence}) should be before "
                    f"{previous_tag} ({previous_sequence})",
                    saveframe=saveframe.name, category=category, tag=full_tag, loop=loop))
            previous_tag, previous_sequence = full_tag, sequence

    return issues


def _saveframe_category(schema, saveframe) -> Optional[str]:
    """A saveframe's category according to the dictionary, or ``None``."""

    category = schema.schema.get(f'{saveframe.tag_prefix.lower()}.sf_category', {}).get('SFCategory')
    if category is not None:
        category = category.strip() or None
    return category


def _parent_values(entry, schema, scope: _MetadataScope) -> Dict[str, set]:
    """Every value each parent tag holds in this entry, indexed by tag.

    Only tags that something refers to are collected -- a few hundred of the
    dictionary's 6 760 -- so this is one cheap pass rather than an index of the
    whole entry. Values are dereferenced, since a reference is written ``$name``
    and the definition it points at is not.
    """

    wanted = {parent.lower() for parent in schema.parent_tags.values()}
    values: Dict[str, set] = {}

    def record(full_tag: str, value: Any) -> None:
        folded = full_tag.lower()
        if folded not in wanted or value in definitions.NULL_VALUES:
            return
        values.setdefault(folded, set()).add(_dereference(value))

    for saveframe in entry:
        for tag, value in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag}'
            if scope.free(full_tag):
                record(full_tag, value)
        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for position, tag in enumerate(loop.tags):
                full_tag = f'{loop.category}.{tag}'
                if full_tag.lower() not in wanted:
                    continue
                for row in loop.data:
                    if position < len(row):
                        record(full_tag, row[position])

    return values


def check_related_tags(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report values that refer to something the entry does not define.

    Ported from the BMRB validator's ``CheckRelatedTags`` (function 13). The
    dictionary ties many tags to a parent -- ``_Experiment.Sample_label`` to
    ``_Sample.Sf_framecode``, every ``Comp_index_ID`` to ``_Entity_comp_index.ID``
    -- and a child's value has to be one the parent actually holds somewhere in
    the entry. It is the check that catches a reference to a deleted saveframe or
    a renumbered residue.

    Ties whose parent is a saveframe's *local* ID are left to
    :func:`check_local_ids`, which knows that such a value has to match the
    saveframe it is written in rather than merely existing somewhere.

    **A missing parent tag is reported for a free tag and not for a loop
    column.** The original resolves the two cases by different routes -- a query
    per free value, a cached list of the parent's values per loop -- and the
    cached list cannot tell "the parent has no values" from "the tag has no
    parent", so it stays silent. Reproduced rather than tidied: the asymmetry is
    the difference between reporting a finding and not, and every real entry that
    reaches this check has already been through the mandatory-tag one, which is
    what reports a missing parent tag properly.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []
    scope = _MetadataScope(schema)
    values = _parent_values(entry, schema, scope)

    def parent_of(full_tag: str) -> Optional[str]:
        parent = schema.parent_tags.get(full_tag.lower())
        if parent is None or parent.lower() in schema.local_id_tags:
            return None
        return parent

    for saveframe in entry:
        category = _saveframe_category(schema, saveframe)

        for tag, value in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag}'
            parent = parent_of(full_tag)
            if parent is None or value in definitions.NULL_VALUES or not scope.free(full_tag):
                continue
            if _dereference(value) not in values.get(parent.lower(), set()):
                issues.append(ValidationIssue(
                    Severity.ERROR, 'tag.parent_value_missing',
                    f"Cannot find parent tag {parent} with value {_dereference(value)} ({full_tag})",
                    saveframe=saveframe.name, category=category, tag=full_tag, value=value))

        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for position, tag in enumerate(loop.tags):
                full_tag = f'{loop.category}.{tag}'
                parent = parent_of(full_tag)
                if parent is None:
                    continue
                known = values.get(parent.lower())
                if not known:
                    continue
                for number, row in enumerate(loop.data):
                    value = row[position] if position < len(row) else None
                    if value in definitions.NULL_VALUES:
                        continue
                    if _dereference(value) not in known:
                        issues.append(ValidationIssue(
                            Severity.ERROR, 'tag.parent_value_missing',
                            f"Cannot find parent tag {parent} with value {_dereference(value)} ({full_tag})",
                            saveframe=saveframe.name, category=category, tag=full_tag,
                            loop=loop.category, row=number, value=value))

    return issues


def check_local_ids(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report loop rows that claim to belong to a different saveframe.

    Ported from the BMRB validator's ``CheckLocalIds`` (function 14). Every
    saveframe has an ID of its own, and each of its loops repeats that ID in a
    column, so that the loop's rows can be stored in a table shared with every
    other saveframe of the category. The two have to agree, and a mismatch means
    rows that will be filed under the wrong saveframe.

    A saveframe with no ID tag at all is reported as well -- twice, as the
    original does, once for the missing tag and once for the missing value. The
    entry information saveframe is exempt: its ID is the entry's accession
    number, which is global rather than local, and the dictionary marks it so.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []
    scope = _MetadataScope(schema)

    def is_local_id(full_tag: str, in_loop: bool) -> bool:
        tag_data = schema.schema.get(full_tag.lower())
        if tag_data is None or full_tag.lower() not in schema.local_id_tags:
            return False
        return tag_data.get('Loopflag') == ('Y' if in_loop else 'N')

    for saveframe in entry:
        category = _saveframe_category(schema, saveframe)

        local_id = None
        for tag, value in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag}'
            if is_local_id(full_tag, in_loop=False) and scope.free(full_tag):
                local_id = value
                break

        if local_id is None:
            # No ID tag at all. The entry information saveframe legitimately has
            # none; anywhere else the dictionary has one and the entry is
            # missing it, which is two findings rather than one because the
            # original reports the tag and the value separately.
            if category == 'entry_information':
                continue
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.no_local_id_tag',
                "Invalid saveframe: no local ID tag in dictionary",
                saveframe=saveframe.name, category=category))

        if local_id in definitions.NULL_VALUES:
            issues.append(ValidationIssue(
                Severity.ERROR, 'saveframe.invalid_local_id', "Invalid local ID",
                saveframe=saveframe.name, category=category))
            continue

        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for position, tag in enumerate(loop.tags):
                full_tag = f'{loop.category}.{tag}'
                if not is_local_id(full_tag, in_loop=True):
                    continue
                for number, row in enumerate(loop.data):
                    value = row[position] if position < len(row) else None
                    # Null is not excused here: a row that does not say which
                    # saveframe it belongs to is exactly as unusable as one that
                    # names the wrong saveframe.
                    if value != local_id:
                        issues.append(ValidationIssue(
                            Severity.ERROR, 'row.invalid_local_id',
                            f"Invalid local ID {value}, should be {local_id}",
                            saveframe=saveframe.name, category=category, tag=full_tag,
                            loop=loop.category, row=number, value=value))

    return issues


def check_frame_codes(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report references to saveframes the entry does not contain.

    Ported from the BMRB validator's ``CheckFrameCodes`` (function 10). A value
    written ``$name`` points at the saveframe called ``name``; if there is no
    such saveframe the reference dangles.

    This overlaps :func:`check_related_tags`, which reaches most of the same
    values through the dictionary's ties to ``Sf_framecode``. It is not
    redundant: this one reads the reference off the value itself, so it also
    covers a pointer the dictionary does not tie to anything, and it says plainly
    that a saveframe is missing rather than that a parent value is.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []
    scope = _MetadataScope(schema)
    names = {saveframe.name for saveframe in entry}

    def examine(value: Any, **location) -> None:
        if not isinstance(value, str) or not value.startswith('$'):
            return
        if value[1:] not in names:
            issues.append(ValidationIssue(
                Severity.ERROR, 'value.dangling_framecode',
                f"Saveframe not found: {value[1:]}", value=value, **location))

    for saveframe in entry:
        category = _saveframe_category(schema, saveframe)

        for tag, value in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag}'
            if scope.free(full_tag):
                examine(value, saveframe=saveframe.name, category=category, tag=full_tag)

        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for position, tag in enumerate(loop.tags):
                full_tag = f'{loop.category}.{tag}'
                for number, row in enumerate(loop.data):
                    if position < len(row):
                        examine(row[position], saveframe=saveframe.name, category=category,
                                tag=full_tag, loop=loop.category, row=number)

    return issues


def check_sample_saveframe(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report sample components that do not say what they are or how much.

    Ported from the BMRB validator's ``CheckSampleSaveframe`` (function 35). A
    sample's components are the one place where the dictionary's per-tag
    requirements cannot express the requirement: any *one* of ``Mol_common_name``
    and ``Entity_label`` identifies a component, and a concentration may be given
    either exactly or as a range, so no single tag is individually mandatory
    while a row with none of them is useless.

    Both rules are only applied where they can be: a loop that does not carry
    the columns at all is left to the mandatory-tag check, which is what knows
    whether they were required in the first place.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []

    def null(row, position: Optional[int]) -> bool:
        return position is None or position >= len(row) or row[position] in definitions.NULL_VALUES

    for saveframe in entry:
        if _saveframe_category(schema, saveframe) != 'sample':
            continue

        for loop in saveframe:
            if loop.category != '_Sample_component':
                continue

            columns = {tag.lower(): position for position, tag in enumerate(loop.tags)}
            name, entity = columns.get('mol_common_name'), columns.get('entity_label')
            value = columns.get('concentration_val')
            minimum, maximum = columns.get('concentration_val_min'), columns.get('concentration_val_max')

            for number, row in enumerate(loop.data):
                if name is not None and entity is not None and null(row, name) and null(row, entity):
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'row.unidentified_sample_component',
                        "Mol_common_name or Entity_label must have a value",
                        saveframe=saveframe.name, category='sample',
                        tag='_Sample_component.Mol_common_name', loop=loop.category, row=number))

                if (value is not None and minimum is not None and maximum is not None
                        and null(row, value) and null(row, minimum) and null(row, maximum)):
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'row.missing_concentration',
                        "Either Concentration_val or both Concentration_min_val and _max_val "
                        "must have a value",
                        saveframe=saveframe.name, category='sample',
                        tag='_Sample_component.Concentration_val', loop=loop.category, row=number))

    return issues


class _Value(NamedTuple):
    """One value of an entry, with everything a finding needs to locate it."""

    saveframe: str
    category: Optional[str]
    tag: str
    loop: Optional[str]
    row: Optional[int]
    value: Any


def _values(entry, schema, scope: '_MetadataScope') -> Iterator[_Value]:
    """Every metadata value in an entry, saveframe tags and loop values alike.

    The three per-value checks below all want the same walk, and all want it
    over the same subset: what the historical validator loads into its database
    is metadata only, so a check reading that database never sees a chemical
    shift. Iterating in one place keeps the three in step, and keeps the cost of
    a check proportional to the metadata rather than to the file.
    """

    for saveframe in entry:
        category = _saveframe_category(schema, saveframe)

        for tag, value in saveframe.tags:
            full_tag = f'{saveframe.tag_prefix}.{tag}'
            if scope.free(full_tag):
                yield _Value(saveframe.name, category, full_tag, None, None, value)

        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for position, tag in enumerate(loop.tags):
                full_tag = f'{loop.category}.{tag}'
                for number, row in enumerate(loop.data):
                    if position < len(row):
                        yield _Value(saveframe.name, category, full_tag,
                                     loop.category, number, row[position])


def _measured(value: str) -> str:
    """A value without the newline that closed its ``;`` block.

    A semicolon-delimited value ends ``...text\\n;``, and the parser keeps that
    final newline. It is the delimiter rather than data -- the historical
    validator's lexer drops it -- so a value that exactly fills its column would
    otherwise look one character too long, and one that exactly matches an
    enumeration would not match it.
    """

    return value[:-1] if value.endswith('\n') else value


def _shown(value: str) -> str:
    """A value as it can appear in a one-line message.

    Findings are consumed a line at a time, so an embedded newline would split
    one finding into two. The original mangles them (its replacement string is
    read as an escape, so a newline becomes the letter ``n``); they are escaped
    here instead."""

    return _measured(value).replace('\n', '\\n').replace('\r', '\\r')


def check_charset(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report values containing characters NMR-STAR cannot carry.

    Ported from the BMRB validator's ``CheckCharset`` (function 19). The format
    is ASCII, so anything outside ``0x00``-``0x7f`` is a finding -- most often a
    typographic quote or a dash pasted in from a word processor.

    The message names the offending characters and their code points, which the
    original does not: they are frequently invisible in the file, and "there is
    a non-ASCII character somewhere in this paragraph" is not actionable.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []

    for item in _values(entry, schema, _MetadataScope(schema)):
        if item.value is None:
            continue
        text = str(item.value)
        if text.isascii():
            continue
        issues.append(ValidationIssue(
            Severity.ERROR, 'value.non_ascii', _non_ascii_error(item.tag, _shown(text)),
            saveframe=item.saveframe, category=item.category, tag=item.tag,
            loop=item.loop, row=item.row, value=item.value))

    return issues


def check_empty_rows(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report loop rows in which every value is null.

    Ported from the BMRB validator's ``CheckEmptyRows`` (function 15). Such a
    row carries no information and is almost always the residue of a deletion.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []
    scope = _MetadataScope(schema)

    for saveframe in entry:
        category = _saveframe_category(schema, saveframe)
        for loop in saveframe:
            if not scope.loop(loop.category):
                continue
            for number, row in enumerate(loop.data):
                if row and all(value in definitions.NULL_VALUES for value in row):
                    issues.append(ValidationIssue(
                        Severity.ERROR, 'row.empty', "Empty loop row",
                        saveframe=saveframe.name, category=category, loop=loop.category,
                        row=number))

    return issues


def check_data_values(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report values outside the closed enumeration their tag allows.

    Ported from the BMRB validator's ``CheckDataValues`` (function 12). Only
    *closed* enumerations are enforced; an open one lists the values seen so far
    and is advisory.

    Matching is case-sensitive, as the original's is, but a value that is right
    apart from its capitalization gets its own message naming the spelling to
    use -- the same finding, with the fix in it. That case is not rare: a
    quarter of archived entries contain at least one.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []

    for item in _values(entry, schema, _MetadataScope(schema)):
        if item.value in definitions.NULL_VALUES:
            continue
        enumeration = schema.enumerations.get(item.tag.lower())
        if enumeration is None or not enumeration['closed']:
            continue
        value = _measured(str(item.value))
        if value in enumeration['values']:
            continue

        capitalized = enumeration['folded'].get(value.lower())
        if capitalized is not None:
            check = 'value.miscapitalized'
            message = (f"Enumerated value is improperly capitalized: {_shown(value)}, should be "
                       f"{capitalized} ({item.tag})")
        else:
            check = 'value.not_in_enumeration'
            message = f"Enumerated value is not in the list: {_shown(value)} ({item.tag})"

        issues.append(ValidationIssue(
            Severity.ERROR, check, message, saveframe=item.saveframe, category=item.category,
            tag=item.tag, loop=item.loop, row=item.row, value=item.value))

    return issues


#: The ISO date shape the historical validator's ``TypeChecker`` insists on.
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
_DIGITS = frozenset('0123456789')
#: A SQL type of the ``VARCHAR(n)`` family, whose ``n`` is a length limit.
_SIZED_TYPE = re.compile(r'char(?:\((\d+)\))?$', re.IGNORECASE)
_WHITESPACE = re.compile(r'\s')


def _is_int(value: str) -> bool:
    """Whether a value is an integer, by the historical validator's rule.

    ``TypeChecker.isInt``: optional leading sign, then digits. It is written by
    hand rather than with :func:`int` because the two disagree at the edges --
    a bare ``+`` passes here, and ``int()`` accepts underscores and non-Latin
    digits -- and a check that reports a value the original accepts is a false
    positive on data that has always been considered clean.
    """

    for position, character in enumerate(value.strip()):
        if character in '+-':
            if position > 0:
                return False
        elif character not in _DIGITS:
            return False
    return True


def _is_float(value: str) -> bool:
    """Whether a value is a floating-point number, by the historical
    validator's rule.

    ``TypeChecker.isFloat``, transliterated: digits with at most one decimal
    point and at most one exponent, a sign only at the start or straight after
    the ``e``, and ``+inf``/``-inf``. Two of its quirks are load-bearing and are
    kept -- a bare ``inf`` is *not* accepted (the sign is required), and the
    ``i`` branch falls through to the decimal-point branch when the letters
    after it are not ``nf``.
    """

    text = value.strip()
    digit, exponent, dot, sign = 0, 1, 2, 3
    seen_dot = seen_exponent = has_exponent = need_digit = False
    previous = -1

    for position, character in enumerate(text):
        if character in '+-':
            if need_digit:
                return False
            if position != 0 and text[position - 1] not in 'eE':
                return False
            previous = sign
        elif character in 'eE':
            if seen_exponent or need_digit:
                return False
            seen_exponent = True
            previous = exponent
        elif character in 'iI.':
            if character in 'iI':
                if position > 1 or previous != sign or position + 2 >= len(text):
                    return False
                if text[position + 1] in 'nN' and text[position + 2] in 'fF':
                    return True
                # Not "inf" after all; the original falls through to the '.' case.
            if seen_dot:
                return False
            if previous != digit:
                # "1." and "-.1" are fine, "-." is not: something has to follow.
                if position + 1 >= len(text):
                    return False
                need_digit = True
            seen_dot = True
            previous = dot
        elif character in _DIGITS:
            if seen_exponent:
                has_exponent = True
            need_digit = False
            previous = digit
        else:
            return False

    return not (seen_exponent and not has_exponent)


def _is_iso_date(value: str) -> bool:
    """Whether a value is a date, by the historical validator's rule.

    ``TypeChecker.isIsoDate``: ``yyyy-mm-dd`` with a month of 1-12 and a day of
    1-31. It does not know how long a month is, so ``2024-02-31`` passes -- see
    :func:`_is_real_date` for the finding that catches it."""

    text = value.strip()
    if not _ISO_DATE.fullmatch(text):
        return False
    return 1 <= int(text[5:7]) <= 12 and 1 <= int(text[8:]) <= 31


def _value_type(tag_data: Dict[str, Any]) -> tuple:
    """A tag's value type and length limit, as the validator dictionary derives
    them.

    The dictionary states a SQL column type; the validator turns that into one
    of ``FRAMECODE``, ``INTEGER``, ``FLOAT``, ``DATE`` or ``STRING`` plus a
    size, and checks values against *that*
    (``nmr-star-dictionary-scripts/scripts/validator.py: load_tags``). A tag
    flagged as a saveframe pointer is a framecode whatever its column type says,
    which is why that test comes first.
    """

    if (tag_data.get('Sf pointer') or '').strip().upper().startswith('Y'):
        return 'FRAMECODE', None

    sql_type = (tag_data.get('Data Type') or '').strip().lower()
    sized = _SIZED_TYPE.search(sql_type)
    if sized:
        return 'STRING', int(sized.group(1)) if sized.group(1) else None
    if 'text' in sql_type:
        return 'STRING', None
    if 'integer' in sql_type:
        return 'INTEGER', None
    if 'float' in sql_type or 'real' in sql_type:
        return 'FLOAT', None
    if 'date' in sql_type:
        return 'DATE', None
    return 'STRING', None


def check_data_types(entry, schema, profile: str) -> List[ValidationIssue]:
    """Report values that are not of the type their tag is declared to hold.

    Ported from the BMRB validator's ``CheckDataTypes`` (function 11): numbers
    that are not numbers, dates that are not dates, values longer than their
    column, and saveframe pointers written without the ``$`` that makes them
    pointers.

    One finding is added that the original cannot make. Its date test knows only
    that a month is 1-12 and a day 1-31, so ``2024-02-31`` passes it; a day that
    does not exist is reported at :attr:`Severity.STRICT`, keeping the
    Java-equivalent band exactly what it always was.

    ``profile`` is unused; it is accepted so that every entry-level check has
    the same signature.
    """

    issues: List[ValidationIssue] = []
    types: Dict[str, tuple] = {}

    for item in _values(entry, schema, _MetadataScope(schema)):
        if item.value in definitions.NULL_VALUES:
            continue

        folded = item.tag.lower()
        if folded not in types:
            tag_data = schema.schema.get(folded)
            types[folded] = _value_type(tag_data) if tag_data is not None else (None, None)
        kind, size = types[folded]
        if kind is None:
            continue

        value = _measured(str(item.value))
        shown = _shown(value)
        found: List[tuple] = []

        if kind == 'FRAMECODE':
            # A pointer is written "$name". The original reads the delimiter the
            # lexer recorded; here the marker is still on the value.
            if not value.startswith('$'):
                found.append((Severity.ERROR, 'value.not_a_framecode',
                              f"Not a framecode value: {shown} ({item.tag})"))
                if _WHITESPACE.search(value):
                    found.append((Severity.ERROR, 'value.framecode_whitespace',
                                  f"Whitespace in framecode value: {shown} ({item.tag})"))
        elif kind == 'INTEGER':
            if not _is_int(value):
                found.append((Severity.ERROR, 'value.not_an_integer',
                              f"Not an integer value: {shown} ({item.tag})"))
        elif kind == 'FLOAT':
            if not _is_float(value):
                found.append((Severity.ERROR, 'value.not_a_float',
                              f"Not a floating-point value: {shown} ({item.tag})"))
        elif kind == 'DATE':
            if not _is_iso_date(value):
                found.append((Severity.ERROR, 'value.not_a_date',
                              f"Not a valid date: {shown} ({item.tag})"))
            elif not _is_valid_date(value.strip()):
                found.append((Severity.STRICT, 'value.impossible_date',
                              f"No such date: {shown} ({item.tag})"))
        elif size is not None and len(value) > size:
            found.append((Severity.ERROR, 'value.too_long',
                          f"Value too long: {shown} ({item.tag} maxlength = {size})"))

        for severity, check, message in found:
            issues.append(ValidationIssue(
                severity, check, message, saveframe=item.saveframe, category=item.category,
                tag=item.tag, loop=item.loop, row=item.row, value=item.value))

    return issues
