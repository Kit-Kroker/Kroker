# tests/test_risk_system_view.py
"""RD10 assembled: the four families on one artifact, and build()'s wiring."""

from __future__ import annotations

import random

import pytest

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.discover.models import (
    AttributionReport,
    FileBucket,
    ReferenceGraph,
)
from sdlc.assessment.risk.build import build
from sdlc.assessment.risk.crosscap import system_view
from sdlc.assessment.risk.models import (
    FAM_CASCADES,
    SYSTEM_FAMILIES,
    Cascade,
    SystemRisk,
)
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_DATA_SENSITIVITY,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    SecurityObservation,
    Sensitivity,
    SensitivityRecord,
)
from sdlc.measurement import CollectionState, Measurement
from tests.helpers_risk import capability

ALL = frozenset({C_AUTHN_AUTHZ, C_DATA_SENSITIVITY})


def _obs(path="a.py", rule="hardcoded-secret") -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1,
        category=C_AUTHN_AUTHZ,
        rule=rule,
        detail="d",
        severity_hint="high",
        path=path,
        confidence=Confidence.HIGH,
    )


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


def _cmap(caps, attribution=None) -> CapabilityMap:
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(
        capabilities=tuple(caps),
        by_action=actions,
        attribution=attribution,
        collected=Measurement.measured(1.0),
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


def test_a_default_system_risk_still_constructs():
    """Plan 1 and 2 artifacts and tests build SystemRisk() with no
    arguments; every family reports not_collected."""
    s = SystemRisk()
    assert s.shared_vulnerabilities == ()
    for family in SYSTEM_FAMILIES:
        state = getattr(s, f"{family}_collected").state
        assert state is CollectionState.NOT_COLLECTED


def test_an_uncollected_family_may_not_carry_rows():
    with pytest.raises(ValueError, match="carries 1 row"):
        SystemRisk(cascades=(Cascade(origin="BC-001", path=("BC-001", "BC-002")),))


def test_truncated_must_name_a_collected_family():
    with pytest.raises(ValueError, match="did not collect"):
        SystemRisk(truncated=(FAM_CASCADES,))


def test_system_view_populates_every_family():
    caps, attribution = _world()
    cmap = _cmap(caps, attribution)
    risks = build(cmap, collected_categories=ALL).capabilities
    s = system_view(cmap, risks, collected_categories=ALL)
    for family in SYSTEM_FAMILIES:
        assert getattr(s, f"{family}_collected").state is (CollectionState.MEASURED), family
    assert [b.source_bc_id for b in s.trust_boundaries] == ["BC-001"]
    assert [p.path_id for p in s.escalation_paths] == ["BC-001->BC-002"]
    assert [r.weakness_class for r in s.shared_vulnerabilities] == ["SS1:hardcoded-secret:"]


def test_build_carries_the_system_view_onto_the_map():
    caps, attribution = _world()
    m = build(_cmap(caps, attribution), collected_categories=ALL)
    assert m.system.trust_boundaries, "build() must populate SystemRisk"
    assert m.counts["trust_boundaries"] == len(m.system.trust_boundaries)


def test_a_map_without_attribution_reports_the_graph_families_uncollected():
    caps, _ = _world()
    m = build(_cmap(caps), collected_categories=ALL)
    assert m.collected.state is CollectionState.MEASURED
    assert m.system.cascades_collected.state is CollectionState.NOT_COLLECTED
    assert m.system.trust_boundaries == ()
    # The one family that needs no graph still computes.
    assert m.system.shared_vulnerabilities_collected.state is (CollectionState.MEASURED)


def test_build_with_the_system_view_is_order_independent():
    """NFR-10, end to end through the family assembly."""
    caps, attribution = _world()
    caps = list(caps) + [capability("BC-003", member_paths=("c.py",), security=(_obs("c.py"),))]
    attribution = _attribution(
        [("a.py", "b.py"), ("c.py", "b.py")], parsed=("a.py", "b.py", "c.py")
    )
    first = None
    for _ in range(5):
        random.shuffle(caps)
        out = build(_cmap(caps, attribution), collected_categories=ALL).model_dump_json()
        first = first if first is not None else out
        assert out == first


def test_build_degrades_system_view_gracefully_on_unexpected_exception(monkeypatch):
    """Finding 1: a crosscap failure in system_view degrades the four families
    without discarding the deterministic per-capability score."""
    import sdlc.assessment.risk.build as build_module

    def _exploding_system_view(*args, **kwargs):
        raise RuntimeError("simulated crosscap explosion")

    monkeypatch.setattr(build_module, "system_view", _exploding_system_view)

    caps, attribution = _world()
    m = build(_cmap(caps, attribution), collected_categories=ALL)
    assert m.collected.state is CollectionState.MEASURED
    assert len(m.capabilities) == 2
    for family in SYSTEM_FAMILIES:
        state = getattr(m.system, f"{family}_collected")
        assert state.state is CollectionState.NOT_COLLECTED
        assert "simulated crosscap explosion" in state.reason
