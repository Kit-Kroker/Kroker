# tests/test_risk_proposal_models.py
"""ADR-22 at the type: the proposer may name rows, never author them."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.risk.models import (
    CapabilityRisk,
    Composite,
    ControlCoverage,
    ControlFamily,
    ControlState,
    CriticalityRating,
    ProposedControl,
    ProposedThreat,
    ProposedVulnerability,
    RiskProposal,
    RiskSource,
    RiskVerification,
    Severity,
    StrideCategory,
    ThreatAssessment,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.measurement import CollectionState, Measurement


def _threats(source=RiskSource.BASELINE):
    return tuple(
        ThreatAssessment(category=c, applicable=False, rationale="baseline", source=source)
        for c in StrideCategory
    )


def _controls():
    return tuple(
        ControlCoverage(
            family=f, state=ControlState.PRESENT, collected=Measurement.measured(1.0), rule="r"
        )
        for f in ControlFamily
    )


def _empty() -> Composite:
    return Composite(value=Measurement.not_collected("no factors"))


def _cap(bc_id="BC-001", **kw) -> CapabilityRisk:
    base = dict(
        bc_id=bc_id,
        criticality=CriticalityRating(collected=Measurement.not_collected("no SS4")),
        threats=_threats(),
        controls=_controls(),
        security=_empty(),
        qa=_empty(),
        unified=_empty(),
    )
    base.update(kw)
    return CapabilityRisk(**base)


def _vuln(source=RiskSource.BASELINE, **kw) -> Vulnerability:
    base = dict(
        key="ss1:r:a.py:",
        classification=VulnerabilityClass.POTENTIAL,
        severity=Severity.MEDIUM,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="a.py",
        source=source,
    )
    base.update(kw)
    return Vulnerability(**base)


# --- the proposer authors nothing -------------------------------------


@pytest.mark.parametrize("model", [ProposedThreat, ProposedVulnerability, ProposedControl])
def test_no_proposer_row_can_stamp_its_own_provenance(model):
    """E-48 DD1: a model able to set `source` could label a hallucinated
    judgment as a code-computed baseline."""
    assert "source" not in model.model_fields


@pytest.mark.parametrize("model", [ProposedThreat, ProposedVulnerability, ProposedControl])
def test_no_proposer_row_can_author_a_number(model):
    """RD4: severity is a table, and a model field would overrule it."""
    forbidden = {
        "severity",
        "criticality",
        "security",
        "qa",
        "unified",
        "factors",
        "drivers",
        "value",
        "weight",
    }
    assert not (set(model.model_fields) & forbidden)


def test_the_proposal_carries_only_the_five_disposition_families():
    assert set(RiskProposal.model_fields) == {
        "threats",
        "vulnerabilities",
        "controls",
        "boundaries",
        "escalations",
    }


def test_row_ids_are_distinct_across_the_three_families():
    """One flat verification pass over heterogeneous rows needs ids that
    cannot collide."""
    t = ProposedThreat(
        bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
    )
    v = ProposedVulnerability(
        key="BC-001",
        classification=VulnerabilityClass.CONFIRMED,
        stride_category=StrideCategory.SPOOFING,
        rationale="r",
    )
    c = ProposedControl(
        bc_id="BC-001",
        family=ControlFamily.AUTHENTICATION,
        state=ControlState.ABSENT,
        rationale="r",
    )
    assert len({t.row_id, v.row_id, c.row_id}) == 3


def test_rows_returns_every_family_in_declaration_order():
    p = RiskProposal(
        threats=[
            ProposedThreat(
                bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
            )
        ],
        controls=[
            ProposedControl(
                bc_id="BC-001",
                family=ControlFamily.VALIDATION,
                state=ControlState.ABSENT,
                rationale="r",
            )
        ],
    )
    assert [r.row_id for r in p.rows] == ["threat:BC-001:spoofing", "control:BC-001:validation"]


# --- the judgment layer's state ---------------------------------------


def test_a_new_map_reports_no_judgment_rather_than_claiming_one():
    m = UnifiedRiskMap(collected=Measurement.not_collected("no discover"))
    assert m.judgment.state is CollectionState.NOT_COLLECTED


def test_an_unjudged_map_may_not_carry_a_proposer_threat():
    with pytest.raises(ValidationError, match="stamped PROPOSER"):
        UnifiedRiskMap(
            capabilities=(_cap(threats=_threats(RiskSource.PROPOSER)),),
            collected=Measurement.measured(1.0),
        )


def test_an_unjudged_map_may_not_carry_a_proposer_vulnerability():
    with pytest.raises(ValidationError, match="stamped PROPOSER"):
        UnifiedRiskMap(
            capabilities=(_cap(vulnerabilities=(_vuln(RiskSource.PROPOSER),)),),
            collected=Measurement.measured(1.0),
        )


def test_a_judged_map_may_carry_proposer_rows():
    m = UnifiedRiskMap(
        capabilities=(_cap(threats=_threats(RiskSource.PROPOSER)),),
        collected=Measurement.measured(1.0),
        judgment=Measurement.measured(1.0),
    )
    assert m.capabilities[0].threats[0].source is RiskSource.PROPOSER


# --- the verification wrapper -----------------------------------------


def test_zero_references_is_a_zero_rate():
    assert RiskVerification().fabrication_rate == 0.0


def test_the_rate_is_unresolved_over_total():
    v = RiskVerification(total_references=4, unresolved_references=1)
    assert v.fabrication_rate == 0.25


def test_proposed_system_rows_carry_prefixed_ids():
    """One flat verification pass over five families cannot collide a bc_id
    pair with a vulnerability key."""
    from sdlc.assessment.risk.models import (
        BoundaryVerdict,
        ChainVerdict,
        ProposedBoundary,
        ProposedEscalation,
        RiskProposal,
    )

    b = ProposedBoundary(
        source_bc_id="BC-001", target_bc_id="BC-002", verdict=BoundaryVerdict.WEAK, rationale="r"
    )
    e = ProposedEscalation(path_id="BC-001->BC-002", verdict=ChainVerdict.PLAUSIBLE, rationale="r")
    assert b.row_id == "boundary:BC-001->BC-002"
    assert e.row_id == "escalation:BC-001->BC-002"
    assert set(RiskProposal(boundaries=[b], escalations=[e]).rows) == {b, e}


def test_proposed_models_ignore_extra_fields():
    """Finding 4: LLM outputs with stray extra fields (e.g. severity, extra
    annotations) must be ignored, not fail the entire RiskProposal."""
    from sdlc.assessment.risk.models import (
        BoundaryVerdict,
        ChainVerdict,
        ProposedBoundary,
        ProposedEscalation,
    )

    t = ProposedThreat(
        bc_id="BC-001",
        category=StrideCategory.SPOOFING,
        applicable=True,
        rationale="r",
        severity="high",
    )
    v = ProposedVulnerability(
        key="ss1:r:a.py:",
        classification=VulnerabilityClass.CONFIRMED,
        stride_category=StrideCategory.SPOOFING,
        rationale="r",
        extra_field=123,
    )
    c = ProposedControl(
        bc_id="BC-001",
        family=ControlFamily.AUTHENTICATION,
        state=ControlState.ABSENT,
        rationale="r",
        unknown_tag=True,
    )
    b = ProposedBoundary(
        source_bc_id="BC-001",
        target_bc_id="BC-002",
        verdict=BoundaryVerdict.WEAK,
        rationale="r",
        severity="medium",
    )
    e = ProposedEscalation(
        path_id="BC-001->BC-002", verdict=ChainVerdict.PLAUSIBLE, rationale="r", confidence=0.9
    )
    assert t.bc_id == "BC-001"
    assert v.key == "ss1:r:a.py:"
    assert c.state is ControlState.ABSENT
    assert b.verdict is BoundaryVerdict.WEAK
    assert e.verdict is ChainVerdict.PLAUSIBLE
