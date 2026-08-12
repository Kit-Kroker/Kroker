"""FR-912 (E-46): the scan phase artifact and its contracts.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py, capability/models.py and assessment/models.py must not: a
dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


class ScanSignalId(str, Enum):
    """BrownKit's scan signal ids, kept verbatim: they are the traceable
    contract with the source methodology, and renaming them would make every
    cross-reference to `scan.md` a translation step.

    Declaration order IS the order (see SCAN_ORDER) -- a hand-written tuple
    beside the enum is a second registry, exactly as PHASE_ORDER records.
    """
    S1 = "S1"       # package structure
    S2 = "S2"       # database schema clusters
    S3 = "S3"       # backend entry points
    S4 = "S4"       # frontend entry points
    S5 = "S5"       # cross-source merge and confidence
    SS1 = "SS1"     # static security
    SS2 = "SS2"     # dependency vulnerabilities
    SS3 = "SS3"     # configuration and infrastructure
    SS4 = "SS4"     # data sensitivity
    QS1 = "QS1"     # test inventory
    QS2 = "QS2"     # coverage
    QS3 = "QS3"     # testability
    QS4 = "QS4"     # environment and CI


SCAN_ORDER: tuple[ScanSignalId, ...] = tuple(ScanSignalId)


class SignalFamily(str, Enum):
    CAPABILITY = "capability"
    SECURITY = "security"
    QA = "qa"


def family_of(signal_id: ScanSignalId) -> SignalFamily:
    """Derived from the id prefix rather than declared per signal: the prefix
    IS the family in BrownKit's scheme, and a declaration could disagree."""
    if signal_id.value.startswith("QS"):
        return SignalFamily.QA
    if signal_id.value.startswith("SS"):
        return SignalFamily.SECURITY
    return SignalFamily.CAPABILITY


class SignalSource(str, Enum):
    """D2. INHERITED is narrow: the fact is already recorded in an artifact
    this assessment holds (Assessment.triage). Reusing a parser is code reuse,
    not inheritance."""
    COMPUTED = "computed"
    INHERITED = "inherited"
    EXTENDED = "extended"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence_from(signals: Iterable[ScanSignalId]) -> Confidence:
    """S5's rule (D8): 3+ distinct source SIGNALS high, 2 medium, else low.

    Distinct signals, not distinct candidates -- two S1 groupings are one
    source's opinion twice, which is FR-912's "never the depth of one source".
    Total by construction so it is never the thing that raises; a candidate
    with no sources is refused by ScanCandidate instead.
    """
    n = len(set(signals))
    if n >= 3:
        return Confidence.HIGH
    if n == 2:
        return Confidence.MEDIUM
    return Confidence.LOW
