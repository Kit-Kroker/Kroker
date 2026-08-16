"""Assemble the UnifiedRiskMap from the CapabilityMap (E-49 plan 1).

Pure by design -- see the package docstring in models.py.

The proposer's contributions (STRIDE applicability, vulnerability
classification, control disposition) land in plan 2. Until then the baseline
states what it does not know rather than guessing, exactly as E-48's DD6
baseline does.
"""
from __future__ import annotations

import hashlib

from ..discover.map import Capability, CapabilityMap
from ..scan.models import (
    C_COVERAGE, C_DATA_SENSITIVITY, C_TESTABILITY, EvidenceRef,
    security_identity,
)
from ...measurement import CollectionState, Measurement
from .composites import compose, unified
from .controls import controls
from .factors import qa_factors, security_factors
from .models import (
    CapabilityRisk, RiskSource, StrideCategory, SystemRisk, ThreatAssessment,
    UnifiedRiskMap, Vulnerability, VulnerabilityClass,
)
from .severity import criticality, severity

_NO_JUDGMENT = (
    "deterministic baseline: STRIDE applicability is the risk proposer's "
    "judgment, and this row records that no judgment was applied -- not a "
    "finding of inapplicability. See UnifiedRiskMap.judgment for why")


def no_risk(reason: str) -> UnifiedRiskMap:
    """RD8: the phase produced no map, and says why.

    Never an empty map with a measured `collected` -- zero vulnerabilities
    over zero capabilities renders as a clean risk map, which is byte-for-byte
    the hole E-40 closed on the absolute floor.
    """
    return UnifiedRiskMap(collected=Measurement.not_collected(reason))


def _threats() -> tuple[ThreatAssessment, ...]:
    return tuple(ThreatAssessment(category=c, applicable=False,
                                  rationale=_NO_JUDGMENT)
                 for c in StrideCategory)


def _vulnerabilities(cap: Capability, rating) -> tuple[Vulnerability, ...]:
    rows = sorted(cap.security,
                  key=lambda o: (o.signal.value, o.rule, o.path, o.line or 0))
    return tuple(
        Vulnerability(
            key=security_identity(o),
            # POTENTIAL, never CONFIRMED: classification is the proposer's
            # disposition, and a pattern match is not a confirmation.
            classification=VulnerabilityClass.POTENTIAL,
            severity=severity(o.severity_hint, rating, o.confidence),
            # The baseline cannot link a threat it did not judge; the
            # proposer's linkage replaces this in apply_judgment.
            stride_category=StrideCategory.INFORMATION_DISCLOSURE,
            path=o.path, line=o.line,
            evidence=(EvidenceRef(path=o.path,
                                  lines=str(o.line) if o.line else ""),),
            source=RiskSource.BASELINE)
        for o in rows)


def build(cmap: CapabilityMap, *,
          collected_categories: frozenset[str]) -> UnifiedRiskMap:
    """One CapabilityRisk per capability, sorted by bc_id."""
    if cmap.collected.state is not CollectionState.MEASURED:
        return no_risk(
            f"discover did not collect ({cmap.collected.reason}), so there "
            f"is no capability set to assess")
    if not cmap.capabilities:
        return no_risk(
            "discover collected but identified no capabilities, so there is "
            "nothing to score -- a map over zero capabilities would read as "
            "a clean risk map")

    sensitivity_collected = C_DATA_SENSITIVITY in collected_categories
    rows: list[CapabilityRisk] = []
    for cap in sorted(cmap.capabilities, key=lambda c: c.bc_id):
        rating = criticality(cap, sensitivity_collected=sensitivity_collected)
        control_rows = controls(cap,
                                collected_categories=collected_categories)
        sec = compose(
            security_factors(cap, rating=rating, controls_rows=control_rows,
                             collected_categories=collected_categories),
            label="security")
        qa = compose(
            qa_factors(cap,
                       coverage_collected=C_COVERAGE in collected_categories,
                       testability_collected=C_TESTABILITY in collected_categories),
            label="qa")
        rows.append(CapabilityRisk(
            bc_id=cap.bc_id, criticality=rating, threats=_threats(),
            vulnerabilities=_vulnerabilities(cap, rating),
            controls=control_rows, security=sec, qa=qa,
            unified=unified(sec, qa)))

    return UnifiedRiskMap(capabilities=tuple(rows), system=SystemRisk(),
                          collected=Measurement.measured(1.0))


def map_digest(cmap: CapabilityMap) -> str:
    """A content hash over the serialized CapabilityMap (the assess memo's
    third key term).

    Lives here rather than in memo.py (P2-D8): the workflow needs the digest
    to build the memo key before any activity runs, and memo.py does
    filesystem I/O. build.py is pure and already in RULE_MODULES, which is
    where a digest function belongs -- changing it must invalidate what it
    keyed.

    Pydantic emits fields in declaration order, so this does not depend on
    construction order (NFR-10).
    """
    return hashlib.sha256(cmap.model_dump_json().encode("utf-8")).hexdigest()
