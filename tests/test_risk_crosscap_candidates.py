# tests/test_risk_crosscap_candidates.py
"""RD10's two JUDGMENT families: code enumerates candidates, the proposer
dispositions them. Neither may invent an edge."""
from __future__ import annotations

import random

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.discover.models import (
    AttributionReport, FileBucket, ReferenceGraph,
)
from sdlc.assessment.risk.build import build
from sdlc.assessment.risk.crosscap import (
    boundary_candidates, escalation_candidates, project_edges,
)
from sdlc.assessment.risk.models import (
    BoundaryVerdict, ChainVerdict, RiskSource,
)
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, C_DATA_SENSITIVITY, CandidateMember, Confidence, MemberKind,
    ScanSignalId, SecurityObservation, Sensitivity, SensitivityRecord,
)
from sdlc.measurement import CollectionState, Measurement

from tests.helpers_risk import capability

ALL = frozenset({C_AUTHN_AUTHZ, C_DATA_SENSITIVITY})
OK = Measurement.measured(1.0)


def _weak_authn(path="a.py") -> SecurityObservation:
    """An authn_authz observation, which is what makes the AUTHENTICATION
    control row read ABSENT: an observation IS a weakness (controls.py)."""
    return SecurityObservation(
        signal=ScanSignalId.SS1, category=C_AUTHN_AUTHZ, rule="no-auth-guard",
        detail="d", severity_hint="high", path=path,
        confidence=Confidence.HIGH)


def _pii(entity="customer") -> SensitivityRecord:
    return SensitivityRecord(
        classification=Sensitivity.PII, entity=entity, origin="table",
        fields=["email"], rule="ss4_field_name", confidence=Confidence.HIGH)


def _route(value="GET /orders", path="a.py") -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value, path=path)


def _attribution(edges, parsed=("a.py", "b.py")) -> AttributionReport:
    return AttributionReport(
        files=(), counts={b: 0 for b in FileBucket},
        coverage=Measurement.measured(1.0), meets_floor=True,
        graph=ReferenceGraph(
            edges=tuple(edges), parsed=tuple(parsed),
            unresolved_relative_rate=Measurement.not_collected("no imports")))


def _cmap(caps, attribution=None) -> CapabilityMap:
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(capabilities=tuple(caps), by_action=actions,
                         attribution=attribution,
                         collected=Measurement.measured(1.0))


def _risks(caps, attribution, categories=ALL):
    return build(_cmap(caps, attribution),
                 collected_categories=categories).capabilities


def _pair():
    """A HIGH-criticality capability edging to a LOW-criticality one."""
    high = capability("BC-001", member_paths=("a.py",),
                      members=(_route(),), sensitivity=(_pii(),))
    low = capability("BC-002", member_paths=("b.py",))
    return [high, low], _attribution([("a.py", "b.py")])


def test_an_edge_across_a_criticality_difference_is_a_candidate():
    caps, attribution = _pair()
    out = boundary_candidates(_risks(caps, attribution), caps,
                              project_edges(caps, attribution.graph.edges),
                              sensitivity_collected=True, graph=OK)
    assert out.collected.state is CollectionState.MEASURED
    assert [(b.source_bc_id, b.target_bc_id) for b in out.rows] == [
        ("BC-001", "BC-002")]
    assert out.rows[0].rule == "criticality_differs"


def test_a_candidate_carries_no_verdict_of_its_own():
    """RD10: WEAK|SOUND|UNCLEAR is the proposer's. The baseline records that
    no judgment was applied -- not a finding of soundness."""
    caps, attribution = _pair()
    row = boundary_candidates(_risks(caps, attribution), caps,
                              project_edges(caps, attribution.graph.edges),
                              sensitivity_collected=True, graph=OK).rows[0]
    assert row.verdict is BoundaryVerdict.UNCLEAR
    assert row.source is RiskSource.BASELINE
    assert "no judgment" in row.rationale


def test_an_edge_between_alike_endpoints_is_not_a_candidate():
    caps = [capability("BC-001", member_paths=("a.py",)),
            capability("BC-002", member_paths=("b.py",))]
    attribution = _attribution([("a.py", "b.py")])
    out = boundary_candidates(_risks(caps, attribution), caps,
                              project_edges(caps, attribution.graph.edges),
                              sensitivity_collected=True, graph=OK)
    assert out.collected.state is CollectionState.MEASURED
    assert out.rows == ()


def test_a_sensitivity_difference_alone_makes_a_candidate():
    """Both LOW criticality (neither is reachable), but one handles PII."""
    caps = [capability("BC-001", member_paths=("a.py",), sensitivity=(_pii(),)),
            capability("BC-002", member_paths=("b.py",))]
    attribution = _attribution([("a.py", "b.py")])
    out = boundary_candidates(_risks(caps, attribution), caps,
                              project_edges(caps, attribution.graph.edges),
                              sensitivity_collected=True, graph=OK)
    assert out.rows[0].rule == "sensitivity_exposure_differs"


def test_neither_criticality_nor_sensitivity_collected_is_not_collected():
    caps, attribution = _pair()
    risks = _risks(caps, attribution, categories=frozenset())
    out = boundary_candidates(risks, caps,
                              project_edges(caps, attribution.graph.edges),
                              sensitivity_collected=False, graph=OK)
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert out.rows == ()


def test_boundary_candidates_need_the_graph():
    caps, attribution = _pair()
    out = boundary_candidates(_risks(caps, attribution), caps, (),
                              sensitivity_collected=True,
                              graph=Measurement.not_collected("no attribution"))
    assert out.collected.state is CollectionState.NOT_COLLECTED


def test_boundary_candidates_are_order_independent():
    caps, attribution = _pair()
    caps = caps + [capability("BC-003", member_paths=("c.py",),
                              sensitivity=(_pii("invoice"),))]
    file_edges = [("a.py", "b.py"), ("c.py", "b.py")]
    attribution = _attribution(file_edges, parsed=("a.py", "b.py", "c.py"))
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(file_edges)
        out = repr(boundary_candidates(_risks(caps, attribution), caps,
                                       project_edges(caps, file_edges),
                                       sensitivity_collected=True, graph=OK))
        first = first if first is not None else out
        assert out == first


def test_a_chain_runs_from_an_unauthenticated_entry_to_sensitive_data():
    entry = capability("BC-001", member_paths=("a.py",), members=(_route(),),
                       security=(_weak_authn(),))
    store = capability("BC-002", member_paths=("b.py",), sensitivity=(_pii(),))
    caps = [entry, store]
    attribution = _attribution([("a.py", "b.py")])
    out = escalation_candidates(_risks(caps, attribution), caps,
                                project_edges(caps, attribution.graph.edges),
                                sensitivity_collected=True, graph=OK)
    assert out.collected.state is CollectionState.MEASURED
    assert [p.path for p in out.rows] == [("BC-001", "BC-002")]
    assert out.rows[0].path_id == "BC-001->BC-002"
    assert out.rows[0].verdict is ChainVerdict.UNCLEAR
    assert out.rows[0].source is RiskSource.BASELINE


def test_an_entry_whose_authentication_is_present_is_not_a_candidate():
    """The AUTHENTICATION control row reads PRESENT when SS1 collected and
    found no weakness for that capability."""
    entry = capability("BC-001", member_paths=("a.py",), members=(_route(),))
    store = capability("BC-002", member_paths=("b.py",), sensitivity=(_pii(),))
    caps = [entry, store]
    attribution = _attribution([("a.py", "b.py")])
    risks = _risks(caps, attribution)
    auth = next(c for c in risks[0].controls
                if c.family.value == "authentication")
    assert auth.state is not None and auth.state.value == "present"
    out = escalation_candidates(risks, caps,
                                project_edges(caps, attribution.graph.edges),
                                sensitivity_collected=True, graph=OK)
    assert out.rows == ()


def test_a_chain_needs_an_externally_reachable_entry():
    # Authentication reads ABSENT, so reachability is the only thing keeping
    # this out of the candidate list.
    entry = capability("BC-001", member_paths=("a.py",),
                       security=(_weak_authn(),))   # no route member
    store = capability("BC-002", member_paths=("b.py",), sensitivity=(_pii(),))
    caps = [entry, store]
    attribution = _attribution([("a.py", "b.py")])
    out = escalation_candidates(_risks(caps, attribution), caps,
                                project_edges(caps, attribution.graph.edges),
                                sensitivity_collected=True, graph=OK)
    assert out.rows == ()


def test_uncollected_sensitivity_is_not_an_empty_chain_set():
    entry = capability("BC-001", member_paths=("a.py",), members=(_route(),))
    store = capability("BC-002", member_paths=("b.py",))
    caps = [entry, store]
    attribution = _attribution([("a.py", "b.py")])
    out = escalation_candidates(_risks(caps, attribution, frozenset()), caps,
                                project_edges(caps, attribution.graph.edges),
                                sensitivity_collected=False, graph=OK)
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "no chain has an end" in out.collected.reason


def test_the_known_limit_chains_are_authentication_gated_not_authorization():
    """RD10's written-down limit, pinned as a test rather than a caveat.

    RD5 leaves Authorization with no scan source, so a capability whose
    AUTHENTICATION control is PRESENT is excluded even though nothing in the
    scan can say whether it AUTHORIZES the caller for the entity it reaches.
    """
    entry = capability("BC-001", member_paths=("a.py",), members=(_route(),))
    store = capability("BC-002", member_paths=("b.py",), sensitivity=(_pii(),))
    caps = [entry, store]
    attribution = _attribution([("a.py", "b.py")])
    risks = _risks(caps, attribution)
    authz = next(c for c in risks[0].controls
                 if c.family.value == "authorization")
    assert authz.collected.state is CollectionState.NOT_COLLECTED
    out = escalation_candidates(risks, caps,
                                project_edges(caps, attribution.graph.edges),
                                sensitivity_collected=True, graph=OK)
    assert out.rows == (), (
        "an authenticated entry is excluded even though authorization was "
        "never collected -- the narrower claim, stated")


def test_escalation_candidates_are_order_independent():
    entry = capability("BC-001", member_paths=("a.py",), members=(_route(),),
                       security=())
    mid = capability("BC-002", member_paths=("b.py",))
    store = capability("BC-003", member_paths=("c.py",), sensitivity=(_pii(),))
    caps = [entry, mid, store]
    file_edges = [("a.py", "b.py"), ("b.py", "c.py")]
    attribution = _attribution(file_edges, parsed=("a.py", "b.py", "c.py"))
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(file_edges)
        out = repr(escalation_candidates(_risks(caps, attribution, frozenset(
            {C_DATA_SENSITIVITY})), caps, project_edges(caps, file_edges),
            sensitivity_collected=True, graph=OK))
        first = first if first is not None else out
        assert out == first

