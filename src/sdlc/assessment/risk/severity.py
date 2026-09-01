"""RD4: criticality derived, severity assigned from a table.

Pure by design -- see the package docstring in models.py.

SecurityObservation carries `severity_hint`, never `severity`, and its own
docstring names this module's job: "scan emits hints and /assess assigns
severity (E-49). A field called `severity` would invite a consumer to treat a
pattern match as a rating."
"""

from __future__ import annotations

from collections.abc import Iterable

from ...measurement import Measurement
from ..discover.map import Capability
from ..scan.models import Confidence, MemberKind, Sensitivity
from .models import Criticality, CriticalityRating, Severity
from .rules import LOW_CONFIDENCE_SHIFT, SEVERITY_TABLE

# Externally reachable member kinds. A DB table or an exported symbol is not
# an exposure surface on its own; a route is.
REACHABLE_KINDS: frozenset[MemberKind] = frozenset(
    {
        MemberKind.HTTP_ROUTE,
        MemberKind.FRONTEND_ROUTE,
        MemberKind.GRPC_METHOD,
    }
)

# Regulated classes outrank PII alone for impact purposes.
_REGULATED = frozenset({Sensitivity.HEALTH, Sensitivity.REGULATORY, Sensitivity.FINANCIAL})

_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def criticality(cap: Capability, *, sensitivity_collected: bool) -> CriticalityRating:
    """HIGH/MEDIUM/LOW from the data the capability handles and whether it is
    externally reachable.

    `sensitivity_collected` is a PARAMETER rather than inferred from an empty
    `cap.sensitivity`: SensitivityRecord.accessed_by's docstring warns that an
    empty list "must never be read as 'no entry point touches PII'", and a
    criticality derived from that emptiness would launder the warning into a
    rating (RD4).
    """
    if not sensitivity_collected:
        return CriticalityRating(
            collected=Measurement.not_collected(
                "criticality needs SS4, which did not collect -- an empty "
                "sensitivity set is not evidence that no entity is regulated"
            )
        )

    regulated = any(r.classification in _REGULATED for r in cap.sensitivity)
    sensitive = bool(cap.sensitivity)
    reachable = any(m.kind in REACHABLE_KINDS for m in cap.members)

    if sensitive and reachable:
        level = Criticality.HIGH
    elif regulated or (sensitive and reachable):
        level = Criticality.MEDIUM
    elif sensitive or reachable:
        level = Criticality.MEDIUM if reachable else Criticality.LOW
    else:
        level = Criticality.LOW
    return CriticalityRating(level=level, collected=Measurement.measured(1.0))


def severity(hint: str, rating: CriticalityRating, confidence: Confidence) -> Severity:
    """The table, then the confidence step. Confidence never RAISES."""
    # An unrated capability is scored at MEDIUM -- neither the benefit of the
    # doubt (LOW would understate) nor an unearned escalation (HIGH would
    # overstate a capability we could not rate).
    level = rating.level or Criticality.MEDIUM
    out = SEVERITY_TABLE[(hint, level)]
    if confidence is Confidence.LOW:
        i = _ORDER.index(out)
        out = _ORDER[max(0, i + LOW_CONFIDENCE_SHIFT)]
    return out


def max_severity(values: Iterable[Severity]) -> Severity:
    """The highest severity in `values`, INFO for an empty run.

    Over the ONE order the table is built from (_ORDER), so a caller cannot
    introduce a second ranking of the same five members.
    """
    out = Severity.INFO
    for value in values:
        if _ORDER.index(value) > _ORDER.index(out):
            out = value
    return out
