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
from typing import Any, Dict, List, Optional

from pynmrstar import definitions

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
