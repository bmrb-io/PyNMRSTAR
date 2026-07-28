"""The structured validation model used by :meth:`pynmrstar.Entry.validate_full`.

The older ``validate()`` methods return a list of strings, which is enough to
show a user but not enough to act on: there is no way to filter by severity,
locate the offending tag, or recognise a finding across runs. Everything here
exists to give a finding an identity -- a machine-readable check name, a
severity, and the saveframe/loop/tag it came from -- so that a caller can route
it, suppress it, or render it in its own format.
"""

import enum
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
        declared = saveframe.get_tag('Sf_category')

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
        framecode = saveframe.get_tag('Sf_framecode')
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
