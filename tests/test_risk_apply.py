# tests/test_risk_apply.py
"""RD1/RD7: dispositions stamped onto rows code already produced."""

from __future__ import annotations

import random

import pytest

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.discover.models import (
    AttributionReport,
    FileBucket,
    ReferenceGraph,
)
from sdlc.assessment.risk.apply import apply_judgment, degraded
from sdlc.assessment.risk.build import build
from sdlc.assessment.risk.models import (
    BoundaryVerdict,
    ChainVerdict,
    ControlFamily,
    ControlState,
    ProposedBoundary,
    ProposedControl,
    ProposedEscalation,
    ProposedThreat,
    ProposedVulnerability,
    RiskProposal,
    RiskSource,
    StrideCategory,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_DATA_SENSITIVITY,
    C_DB_SECURITY,
    C_INPUT_VALIDATION,
    C_TLS,
    CandidateMember,
    Confidence,
    EvidenceRef,
    MemberKind,
    ScanSignalId,
    SecurityObservation,
    Sensitivity,
    SensitivityRecord,
)
from sdlc.measurement import CollectionState, Measurement
from tests.helpers_risk import capability

ALL = frozenset([C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY, C_DATA_SENSITIVITY])


def _obs(rule: str = "r1") -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1,
        category=C_AUTHN_AUTHZ,
        rule=rule,
        detail="d",
        severity_hint="high",
        path="a.py",
        line=3,
        confidence=Confidence.HIGH,
    )


def _baseline(*caps):
    """`by_action` is DERIVED and validated against the rows: CapabilityMap
    raises on "capabilities carry actions absent from by_action"."""
    actions: dict = {}
    for c in caps:
        a = c.disposition.action
        actions[a] = actions.get(a, 0) + 1
    cmap = CapabilityMap(
        capabilities=tuple(caps), by_action=actions, collected=Measurement.measured(1.0)
    )
    return build(cmap, collected_categories=ALL)


def _one():
    return _baseline(capability("BC-001", security=(_obs(),)))


def _vuln_key(m):
    return m.capabilities[0].vulnerabilities[0].key


# --- what the proposer may change -------------------------------------


def test_a_threat_disposition_replaces_applicability_and_rationale():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-001",
                    category=StrideCategory.SPOOFING,
                    applicable=True,
                    rationale="unauthenticated route",
                )
            ]
        ),
    )
    row = next(t for t in out.capabilities[0].threats if t.category is StrideCategory.SPOOFING)
    assert row.applicable is True
    assert row.rationale == "unauthenticated route"
    assert row.source is RiskSource.PROPOSER
    assert out.judgment.state is CollectionState.MEASURED


def test_untouched_threats_stay_baseline():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
                )
            ]
        ),
    )
    others = [t for t in out.capabilities[0].threats if t.category is not StrideCategory.SPOOFING]
    assert len(others) == 5
    assert all(t.source is RiskSource.BASELINE for t in others)


def test_a_vulnerability_disposition_replaces_class_and_stride_not_severity():
    """RD4: severity is a table, and no classification term feeds it."""
    b = _one()
    before = b.capabilities[0].vulnerabilities[0].severity
    out = apply_judgment(
        b,
        RiskProposal(
            vulnerabilities=[
                ProposedVulnerability(
                    key=_vuln_key(b),
                    classification=VulnerabilityClass.CONFIRMED,
                    stride_category=StrideCategory.SPOOFING,
                    rationale="reachable without a session",
                )
            ]
        ),
    )
    row = out.capabilities[0].vulnerabilities[0]
    assert row.classification is VulnerabilityClass.CONFIRMED
    assert row.stride_category is StrideCategory.SPOOFING
    assert row.severity is before
    assert row.source is RiskSource.PROPOSER


def test_verified_proposer_evidence_is_merged_with_the_baseline_evidence():
    b = _one()
    extra = EvidenceRef(path="b.py", lines="7")
    out = apply_judgment(
        b,
        RiskProposal(
            vulnerabilities=[
                ProposedVulnerability(
                    key=_vuln_key(b),
                    classification=VulnerabilityClass.PROBABLE,
                    stride_category=StrideCategory.TAMPERING,
                    rationale="r",
                    evidence=(extra,),
                )
            ]
        ),
    )
    paths = [e.path for e in out.capabilities[0].vulnerabilities[0].evidence]
    assert paths == ["a.py", "b.py"]


def test_a_control_disposition_lands_on_a_family_that_collected():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            controls=[
                ProposedControl(
                    bc_id="BC-001",
                    family=ControlFamily.VALIDATION,
                    state=ControlState.ABSENT,
                    rationale="no schema on the write path",
                )
            ]
        ),
    )
    row = next(c for c in out.capabilities[0].controls if c.family is ControlFamily.VALIDATION)
    assert row.state is ControlState.ABSENT
    assert row.source is RiskSource.PROPOSER


# --- what the proposer may NOT change ---------------------------------


@pytest.mark.parametrize("family", [ControlFamily.AUTHORIZATION, ControlFamily.MONITORING])
def test_a_family_with_no_source_cannot_be_dispositioned(family):
    """P2-D4: flipping "we have no signal" into "present" is the most
    expensive over-claim the artifact admits."""
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            controls=[
                ProposedControl(
                    bc_id="BC-001",
                    family=family,
                    state=ControlState.PRESENT,
                    rationale="looks fine",
                )
            ]
        ),
    )
    row = next(c for c in out.capabilities[0].controls if c.family is family)
    assert row.state is None
    assert row.source is RiskSource.BASELINE
    assert row.collected.state is CollectionState.NOT_COLLECTED


def test_an_unknown_bc_id_is_dropped_never_created():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-999", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
                )
            ]
        ),
    )
    assert [c.bc_id for c in out.capabilities] == ["BC-001"]
    assert all(t.source is RiskSource.BASELINE for t in out.capabilities[0].threats)


def test_an_unknown_vulnerability_key_is_dropped_never_created():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            vulnerabilities=[
                ProposedVulnerability(
                    key="ss9:invented:z.py:",
                    classification=VulnerabilityClass.CONFIRMED,
                    stride_category=StrideCategory.SPOOFING,
                    rationale="r",
                )
            ]
        ),
    )
    assert len(out.capabilities[0].vulnerabilities) == 1
    assert out.capabilities[0].vulnerabilities[0].source is RiskSource.BASELINE


def test_a_threat_linking_an_unknown_vulnerability_key_is_refused():
    """FR-918's cross-reference integrity, enforced where the reference is
    made rather than discovered by E-51 in the bundle."""
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-001",
                    category=StrideCategory.SPOOFING,
                    applicable=True,
                    rationale="r",
                    vulnerability_keys=("ss9:invented:z.py:",),
                )
            ]
        ),
    )
    row = next(t for t in out.capabilities[0].threats if t.category is StrideCategory.SPOOFING)
    assert row.source is RiskSource.BASELINE


@pytest.mark.parametrize("rationale", ["", "   "])
def test_a_disposition_with_no_rationale_is_refused(rationale):
    """P2-D6: an unexplained verdict is unreviewable."""
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            vulnerabilities=[
                ProposedVulnerability(
                    key=_vuln_key(b),
                    classification=VulnerabilityClass.CONFIRMED,
                    stride_category=StrideCategory.SPOOFING,
                    rationale=rationale,
                )
            ]
        ),
    )
    assert out.capabilities[0].vulnerabilities[0].source is RiskSource.BASELINE


def test_a_key_dispositioned_twice_is_refused_not_resolved():
    """P2-D5: picking either is picking at random."""
    b = _one()
    key = _vuln_key(b)
    out = apply_judgment(
        b,
        RiskProposal(
            vulnerabilities=[
                ProposedVulnerability(
                    key=key,
                    classification=VulnerabilityClass.CONFIRMED,
                    stride_category=StrideCategory.SPOOFING,
                    rationale="a",
                ),
                ProposedVulnerability(
                    key=key,
                    classification=VulnerabilityClass.POTENTIAL,
                    stride_category=StrideCategory.TAMPERING,
                    rationale="b",
                ),
            ]
        ),
    )
    assert out.capabilities[0].vulnerabilities[0].source is RiskSource.BASELINE


def test_the_composites_are_never_touched():
    """RD1: the number is code's, and the proposer is downstream of it."""
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
                )
            ]
        ),
    )
    for name in ("security", "qa", "unified"):
        assert (
            getattr(out.capabilities[0], name).model_dump_json()
            == getattr(b.capabilities[0], name).model_dump_json()
        )


# --- degradation ------------------------------------------------------


def test_degraded_keeps_the_composites_and_names_the_reason():
    """RD7: the judgment layer only."""
    b = _one()
    out = degraded(b, "the risk proposer ran and failed: TimeoutError")
    assert out.collected.state is CollectionState.MEASURED
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert "TimeoutError" in out.judgment.reason
    assert (
        out.capabilities[0].unified.model_dump_json() == b.capabilities[0].unified.model_dump_json()
    )


def test_an_uncollected_baseline_is_returned_untouched():
    """RD8: no empty map is ever constructed here either."""
    from sdlc.assessment.risk.build import no_risk

    m = no_risk("discover did not collect")
    assert apply_judgment(m, RiskProposal()).model_dump_json() == m.model_dump_json()


def test_apply_judgment_with_surviving_rows_is_measured():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-001",
                    category=StrideCategory.SPOOFING,
                    applicable=True,
                    rationale="unauthenticated route",
                )
            ]
        ),
    )
    assert out.judgment.state is CollectionState.MEASURED


def test_apply_judgment_with_empty_proposal_is_degraded():
    b = _one()
    out = apply_judgment(b, RiskProposal())
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert out.judgment.reason == "the proposer returned no dispositions"


def test_apply_judgment_with_refused_rows_is_degraded():
    b = _one()
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-999", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
                )
            ]
        ),
    )
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert out.judgment.reason == ("the proposer returned 1 row(s) and none survived verification")

    out2 = apply_judgment(b, RiskProposal(), total_proposed=3)
    assert out2.judgment.state is CollectionState.NOT_COLLECTED
    assert out2.judgment.reason == ("the proposer returned 3 row(s) and none survived verification")


# --- NFR-10 -----------------------------------------------------------


def test_apply_judgment_is_order_independent():
    b = _baseline(
        capability("BC-001", security=(_obs("a"),)), capability("BC-002", security=(_obs("b"),))
    )
    rows = [
        ProposedThreat(
            bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True, rationale="r1"
        ),
        ProposedThreat(
            bc_id="BC-002", category=StrideCategory.TAMPERING, applicable=True, rationale="r2"
        ),
        ProposedControl(
            bc_id="BC-001",
            family=ControlFamily.VALIDATION,
            state=ControlState.ABSENT,
            rationale="r3",
        ),
    ]
    first = None
    for _ in range(5):
        random.shuffle(rows)
        p = RiskProposal(
            threats=[r for r in rows if isinstance(r, ProposedThreat)],
            controls=[r for r in rows if isinstance(r, ProposedControl)],
        )
        out = apply_judgment(b, p).model_dump_json()
        first = first if first is not None else out
        assert out == first


def _attribution(edges, parsed=("a.py", "b.py")) -> AttributionReport:
    return AttributionReport(
        files=(),
        counts={b: 0 for b in FileBucket},
        coverage=Measurement.measured(1.0),
        meets_floor=True,
        graph=ReferenceGraph(
            edges=tuple(edges),
            parsed=tuple(parsed),
            unresolved_relative_rate=Measurement.not_collected("no imports"),
        ),
    )


def _world():
    entry = capability(
        "BC-001",
        member_paths=("a.py",),
        members=(CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /orders", path="a.py"),),
        security=(_obs("a.py"),),
    )
    store = capability(
        "BC-002",
        member_paths=("b.py",),
        security=(_obs("b.py"),),
        sensitivity=(
            SensitivityRecord(
                classification=Sensitivity.PII,
                entity="customer",
                origin="table",
                fields=["email"],
                rule="ss4_field_name",
                confidence=Confidence.HIGH,
            ),
        ),
    )
    return [entry, store], _attribution([("a.py", "b.py")])


def _cmap_world(caps, attribution=None) -> CapabilityMap:
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(
        capabilities=tuple(caps),
        by_action=actions,
        attribution=attribution,
        collected=Measurement.measured(1.0),
    )


def test_a_boundary_verdict_replaces_verdict_and_rationale():
    caps, attribution = _world()
    cmap = _cmap_world(caps, attribution)
    b = build(cmap, collected_categories=ALL)
    out = apply_judgment(
        b,
        RiskProposal(
            boundaries=[
                ProposedBoundary(
                    source_bc_id="BC-001",
                    target_bc_id="BC-002",
                    verdict=BoundaryVerdict.SOUND,
                    rationale="mTLS configured across the hop",
                )
            ]
        ),
    )
    row = out.system.trust_boundaries[0]
    assert row.verdict is BoundaryVerdict.SOUND
    assert row.rationale == "mTLS configured across the hop"
    assert row.source is RiskSource.PROPOSER


def test_an_escalation_verdict_replaces_verdict_and_rationale():
    caps, attribution = _world()
    cmap = _cmap_world(caps, attribution)
    b = build(cmap, collected_categories=ALL)
    out = apply_judgment(
        b,
        RiskProposal(
            escalations=[
                ProposedEscalation(
                    path_id="BC-001->BC-002",
                    verdict=ChainVerdict.REFUTED,
                    rationale="caller has a signed claim",
                )
            ]
        ),
    )
    row = out.system.escalation_paths[0]
    assert row.verdict is ChainVerdict.REFUTED
    assert row.source is RiskSource.PROPOSER


def test_an_unknown_boundary_or_escalation_is_refused():
    """ADR-22 at the boundary: the proposer cannot inject an edge the
    graph did not project."""
    caps, attribution = _world()
    cmap = _cmap_world(caps, attribution)
    b = build(cmap, collected_categories=ALL)
    out = apply_judgment(
        b,
        RiskProposal(
            boundaries=[
                ProposedBoundary(
                    source_bc_id="BC-001",
                    target_bc_id="BC-999",
                    verdict=BoundaryVerdict.SOUND,
                    rationale="r",
                )
            ],
            escalations=[
                ProposedEscalation(
                    path_id="BC-001->BC-999", verdict=ChainVerdict.PLAUSIBLE, rationale="r"
                )
            ],
        ),
    )
    assert all(row.source is RiskSource.BASELINE for row in out.system.trust_boundaries)
    assert all(row.source is RiskSource.BASELINE for row in out.system.escalation_paths)


def test_path_id_matching_is_whitespace_tolerant():
    """Finding 7: path_id matching normalizes whitespace around '->'."""
    caps, attribution = _world()
    cmap = _cmap_world(caps, attribution)
    b = build(cmap, collected_categories=ALL)
    out = apply_judgment(
        b,
        RiskProposal(
            escalations=[
                ProposedEscalation(
                    path_id="BC-001 -> BC-002",
                    verdict=ChainVerdict.REFUTED,
                    rationale="caller has a signed claim",
                )
            ]
        ),
    )
    row = out.system.escalation_paths[0]
    assert row.verdict is ChainVerdict.REFUTED
    assert row.source is RiskSource.PROPOSER


def test_system_proposer_judgment_refused_when_escalation_family_not_collected():
    """Finding 3: when escalation paths did not collect (e.g. no SS4), proposer
    verdicts cannot land."""
    caps, attribution = _world()
    cmap = _cmap_world(caps, attribution)
    # frozenset() means SS4 did not collect -> escalation_paths is not_collected
    b = build(cmap, collected_categories=frozenset({C_AUTHN_AUTHZ}))
    assert b.system.escalation_paths_collected.state is CollectionState.NOT_COLLECTED
    out = apply_judgment(
        b,
        RiskProposal(
            escalations=[
                ProposedEscalation(
                    path_id="BC-001->BC-002", verdict=ChainVerdict.REFUTED, rationale="r"
                )
            ]
        ),
    )
    assert out.system.escalation_paths == ()
    assert out.system.escalation_paths_collected.state is CollectionState.NOT_COLLECTED
    assert out.judgment.state is CollectionState.NOT_COLLECTED
