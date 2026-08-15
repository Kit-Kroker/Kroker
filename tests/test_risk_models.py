# tests/test_risk_models.py
"""Contracts: structural completeness is what makes omission unrepresentable."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.risk.models import (
    CapabilityRisk, Composite, ControlCoverage, ControlFamily, ControlState,
    Criticality, CriticalityRating, RiskSource, Severity, StrideCategory,
    SystemRisk, ThreatAssessment, UnifiedRiskMap, Vulnerability,
    VulnerabilityClass,
)
from sdlc.measurement import Measurement

NO_SCORE = Composite(value=Measurement.not_collected("no factors"))


def _threats() -> tuple[ThreatAssessment, ...]:
    return tuple(
        ThreatAssessment(category=c, applicable=False,
                         rationale="no data flow of this shape")
        for c in StrideCategory)


def _controls() -> tuple[ControlCoverage, ...]:
    return tuple(
        ControlCoverage(family=f, collected=Measurement.not_collected("x"),
                        rule="r")
        for f in ControlFamily)


def _risk(bc_id: str = "BC-001", **kw) -> CapabilityRisk:
    base = dict(
        bc_id=bc_id,
        criticality=CriticalityRating(
            collected=Measurement.not_collected("SS4 did not collect")),
        threats=_threats(), controls=_controls(),
        security=NO_SCORE, qa=NO_SCORE, unified=NO_SCORE)
    base.update(kw)
    return CapabilityRisk(**base)


def test_all_six_stride_categories_are_required():
    """FR-916: a category with no applicable threat carries a rationale
    rather than being omitted -- so omission must be unrepresentable."""
    with pytest.raises(ValidationError, match="all six STRIDE"):
        _risk(threats=_threats()[:5])


def test_all_five_control_families_are_required():
    with pytest.raises(ValidationError, match="all five control families"):
        _risk(controls=_controls()[:4])


def test_a_threat_that_is_not_applicable_needs_a_rationale():
    with pytest.raises(ValidationError, match="rationale"):
        ThreatAssessment(category=StrideCategory.SPOOFING, applicable=False,
                         rationale="   ")


def test_a_control_state_has_no_unknown_member():
    """An UNKNOWN member would be a second way to say not_collected."""
    assert {s.value for s in ControlState} == {"present", "absent"}


def test_an_uncollected_control_carries_no_state():
    with pytest.raises(ValidationError, match="did not collect"):
        ControlCoverage(family=ControlFamily.MONITORING,
                        state=ControlState.PRESENT,
                        collected=Measurement.not_collected("no source"),
                        rule="r")


def test_an_uncollected_criticality_carries_no_level():
    with pytest.raises(ValidationError, match="did not collect"):
        CriticalityRating(level=Criticality.HIGH,
                          collected=Measurement.not_collected("no SS4"))


def test_counts_are_derived_not_assigned():
    m = UnifiedRiskMap(
        capabilities=(_risk("BC-001"), _risk("BC-002")),
        system=SystemRisk(), collected=Measurement.measured(1.0))
    assert m.counts["capabilities"] == 2


def test_capabilities_are_asserted_sorted():
    with pytest.raises(ValidationError, match="sorted"):
        UnifiedRiskMap(capabilities=(_risk("BC-002"), _risk("BC-001")),
                       system=SystemRisk(),
                       collected=Measurement.measured(1.0))


def test_an_uncollected_map_carries_no_capabilities():
    """_unmeasured_carries_no_payload."""
    with pytest.raises(ValidationError, match="did not collect"):
        UnifiedRiskMap(capabilities=(_risk(),), system=SystemRisk(),
                       collected=Measurement.not_collected("no discover"))


def test_a_vulnerability_keeps_the_scan_identity():
    v = Vulnerability(
        key="SS1:hardcoded-secret:src/a.py:", severity=Severity.HIGH,
        classification=VulnerabilityClass.POTENTIAL,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="src/a.py", source=RiskSource.BASELINE)
    assert v.key.startswith("SS1:")
