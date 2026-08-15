"""Assemble the UnifiedRiskMap from the CapabilityMap (E-49 plan 1).

Pure by design -- see the package docstring in models.py.

The proposer's contributions (STRIDE applicability, vulnerability
classification, control disposition) land in plan 2. Until then the baseline
states what it does not know rather than guessing, exactly as E-48's DD6
baseline does.
"""
from __future__ import annotations

from ..discover.map import Capability, CapabilityMap
from ..scan.models import EvidenceRef, security_identity
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
    "STRIDE applicability is judgment and no proposer ran (E-49 plan 2); "
    "this is the deterministic baseline, not a finding of inapplicability")


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
            # The baseline cannot link a threat it did not judge. Plan 2
            # replaces this with the proposer's linkage.
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

    sensitivity_collected = any(
        c.sensitivity for c in cmap.capabilities) or False
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
            qa_factors(cap, coverage_collected=bool(cap.coverage),
                       testability_collected=True),
            label="qa")
        rows.append(CapabilityRisk(
            bc_id=cap.bc_id, criticality=rating, threats=_threats(),
            vulnerabilities=_vulnerabilities(cap, rating),
            controls=control_rows, security=sec, qa=qa,
            unified=unified(sec, qa)))

    return UnifiedRiskMap(capabilities=tuple(rows), system=SystemRisk(),
                          collected=Measurement.measured(1.0))
