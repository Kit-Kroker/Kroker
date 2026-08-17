# tests/test_risk_crosscap.py
"""RD10: the capability->capability projection and the two computed families.

The projection is a re-index of data already on the CapabilityMap -- no blob
is read and nothing is executed (NFR-9).
"""
from __future__ import annotations

import random

import pytest

from sdlc.assessment.risk.crosscap import (
    cascades, graph_state, project_edges, shared_vulnerabilities,
    weakness_class,
)
from sdlc.assessment.risk.models import CapabilityEdge

from tests.helpers_risk import capability


def test_an_edge_between_two_capabilities_is_projected():
    caps = [capability("BC-001", member_paths=("a.py",)),
            capability("BC-002", member_paths=("b.py",))]
    edges = project_edges(caps, [("a.py", "b.py")])
    assert [(e.source_bc_id, e.target_bc_id) for e in edges] == [
        ("BC-001", "BC-002")]
    assert edges[0].weight == 1
    assert [r.path for r in edges[0].evidence] == ["a.py"]


def test_an_intra_capability_edge_is_dropped():
    """RD10: intra-capability edges are not cross-capability facts."""
    caps = [capability("BC-001", member_paths=("a.py", "b.py"))]
    assert project_edges(caps, [("a.py", "b.py")]) == ()


def test_an_edge_touching_an_unowned_file_is_dropped():
    caps = [capability("BC-001", member_paths=("a.py",))]
    assert project_edges(caps, [("a.py", "orphan.py")]) == ()


def test_a_file_owned_by_two_capabilities_projects_both_edges():
    """Attribution allows a file to belong to more than one capability, so
    the index is a set per path rather than a single owner."""
    caps = [capability("BC-001", member_paths=("a.py",)),
            capability("BC-002", member_paths=("a.py",)),
            capability("BC-003", member_paths=("b.py",))]
    edges = project_edges(caps, [("a.py", "b.py")])
    assert [(e.source_bc_id, e.target_bc_id) for e in edges] == [
        ("BC-001", "BC-003"), ("BC-002", "BC-003")]


def test_weight_counts_supporting_file_edges_and_evidence_is_capped():
    caps = [capability("BC-001", member_paths=("a.py", "b.py", "c.py", "d.py")),
            capability("BC-002", member_paths=("z.py",))]
    edges = project_edges(caps, [("a.py", "z.py"), ("b.py", "z.py"),
                                 ("c.py", "z.py"), ("d.py", "z.py")])
    assert edges[0].weight == 4
    assert len(edges[0].evidence) == 3
    assert [r.path for r in edges[0].evidence] == ["a.py", "b.py", "c.py"]


def test_a_self_edge_cannot_be_constructed():
    with pytest.raises(ValueError, match="edges to itself"):
        CapabilityEdge(source_bc_id="BC-001", target_bc_id="BC-001")


def test_project_edges_is_order_independent():
    """NFR-10."""
    caps = [capability("BC-001", member_paths=("a.py",)),
            capability("BC-002", member_paths=("b.py",)),
            capability("BC-003", member_paths=("c.py",))]
    file_edges = [("a.py", "b.py"), ("b.py", "c.py"), ("a.py", "c.py")]
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(file_edges)
        out = repr(project_edges(caps, file_edges))
        first = first if first is not None else out
        assert out == first


from sdlc.assessment.risk.models import Severity
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, Confidence, ScanSignalId, SecurityObservation,
    security_identity,
)
from sdlc.measurement import CollectionState


def _obs(rule="hardcoded-secret", path="src/a.py", key="",
         hint="high") -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1, category=C_AUTHN_AUTHZ, rule=rule,
        detail="d", severity_hint=hint, path=path, key=key,
        confidence=Confidence.HIGH)


def test_weakness_class_excludes_the_path_that_security_identity_carries():
    """The join key is deliberately coarser: security_identity includes the
    path, which is right for a per-instance identity and means two
    capabilities could never share one."""
    a, b = _obs(path="src/a.py"), _obs(path="src/b.py")
    assert security_identity(a) != security_identity(b)
    assert weakness_class(a) == weakness_class(b)


def test_a_weakness_recurring_across_two_capabilities_is_shared():
    caps = [capability("BC-001", security=(_obs(path="src/a.py"),)),
            capability("BC-002", security=(_obs(path="src/b.py"),))]
    sev = {security_identity(o): Severity.HIGH
           for c in caps for o in c.security}
    out = shared_vulnerabilities(caps, sev, security_collected=True)
    assert out.collected.state is CollectionState.MEASURED
    assert len(out.rows) == 1
    row = out.rows[0]
    assert row.bc_ids == ("BC-001", "BC-002")
    assert row.vulnerability_keys == tuple(sorted(sev))
    assert row.severity is Severity.HIGH


def test_a_weakness_in_one_capability_only_is_not_shared():
    caps = [capability("BC-001", security=(_obs(),)),
            capability("BC-002")]
    out = shared_vulnerabilities(caps, {}, security_collected=True)
    assert out.collected.state is CollectionState.MEASURED
    assert out.rows == ()


def test_one_weakness_on_overlapping_capabilities_is_not_shared():
    """Finding 2: a single observation in a shared file (len(keys)==1,
    len(bc_ids)==2) is one finding on two capabilities, not a recurring
    weakness class."""
    shared_obs = _obs(path="src/shared.py")
    caps = [capability("BC-001", member_paths=("src/shared.py",), security=(shared_obs,)),
            capability("BC-002", member_paths=("src/shared.py",), security=(shared_obs,))]
    sev = {security_identity(shared_obs): Severity.HIGH}
    out = shared_vulnerabilities(caps, sev, security_collected=True)
    assert out.collected.state is CollectionState.MEASURED
    assert out.rows == ()



def test_shared_severity_is_the_highest_of_its_member_rows():
    caps = [capability("BC-001", security=(_obs(path="src/a.py"),)),
            capability("BC-002", security=(_obs(path="src/b.py"),))]
    sev = {security_identity(caps[0].security[0]): Severity.LOW,
           security_identity(caps[1].security[0]): Severity.CRITICAL}
    out = shared_vulnerabilities(caps, sev, security_collected=True)
    assert out.rows[0].severity is Severity.CRITICAL


def test_no_security_category_collected_is_not_an_empty_shared_set():
    """FR-915: zero shared weaknesses from a scan that never ran reads as
    'no shared weakness', which is the malformed-SARIF hole again."""
    out = shared_vulnerabilities([capability()], {}, security_collected=False)
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert out.rows == ()
    assert "no security category collected" in out.collected.reason


def test_shared_vulnerabilities_are_order_independent():
    caps = [capability("BC-003", security=(_obs(path="src/c.py"),)),
            capability("BC-001", security=(_obs(path="src/a.py"),)),
            capability("BC-002", security=(_obs(path="src/b.py"),))]
    sev = {security_identity(o): Severity.HIGH
           for c in caps for o in c.security}
    first = None
    for _ in range(5):
        random.shuffle(caps)
        out = repr(shared_vulnerabilities(caps, sev, security_collected=True))
        first = first if first is not None else out
        assert out == first


from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.discover.models import (
    AttributionReport, FileBucket, ReferenceGraph,
)
from sdlc.assessment.risk.build import build
from sdlc.assessment.risk.rules import CASCADE_MAX_DEPTH
from sdlc.assessment.scan.models import (
    C_DATA_SENSITIVITY, CandidateMember, MemberKind, Sensitivity,
    SensitivityRecord,
)
from sdlc.measurement import Measurement

# C_DATA_SENSITIVITY is REQUIRED here, not incidental: without it criticality
# does not collect, so `impact` does not collect, so no security composite is
# MEASURED and cascades correctly report not_collected. The threshold test
# needs a measured composite to exceed.
SEC = frozenset({C_AUTHN_AUTHZ, C_DATA_SENSITIVITY})


def _origin(bc_id: str, path: str):
    """A capability whose security composite clears
    CASCADE_SOURCE_MIN_SECURITY: HIGH criticality (sensitive AND externally
    reachable) gives impact 1.0, and five or more observations saturate
    likelihood.
    """
    return capability(
        bc_id, member_paths=(path,),
        members=(CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="GET /orders", path=path),),
        sensitivity=(SensitivityRecord(
            classification=Sensitivity.PII, entity="customer", origin="table",
            fields=["email"], rule="ss4_field_name",
            confidence=Confidence.HIGH),),
        security=tuple(_obs(path=path, rule=f"r{i}") for i in range(5)))


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


def _risks(caps, attribution=None):
    """The deterministic per-capability rows, straight from plan 1's build."""
    return build(_cmap(caps, attribution), collected_categories=SEC).capabilities


def test_a_missing_attribution_report_means_no_reference_graph():
    state = graph_state(_cmap([capability()]))
    assert state.state is CollectionState.NOT_COLLECTED
    assert "AttributionReport" in state.reason


def test_a_graph_that_parsed_nothing_is_not_evidence_of_independence():
    """Zero edges from an extractor that ran on no file is not a finding."""
    state = graph_state(_cmap([capability()], _attribution([], parsed=())))
    assert state.state is CollectionState.NOT_COLLECTED
    assert "parsed no file" in state.reason


def test_a_cascade_follows_the_projected_edges_from_a_high_origin():
    caps = [_origin("BC-001", "a.py"),
            capability("BC-002", member_paths=("b.py",))]
    attribution = _attribution([("a.py", "b.py")])
    edges = project_edges(caps, attribution.graph.edges)
    out = cascades(_risks(caps, attribution), edges,
                   graph=Measurement.measured(1.0))
    assert out.collected.state is CollectionState.MEASURED
    assert [(c.origin, c.path) for c in out.rows] == [
        ("BC-001", ("BC-001", "BC-002"))]
    assert out.rows[0].impacted == "BC-002"
    assert out.rows[0].depth == 1


def test_cascades_need_the_graph():
    out = cascades((), (), graph=Measurement.not_collected("no attribution"))
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert out.rows == ()


def test_no_measured_security_composite_is_not_an_empty_cascade_set():
    """FR-915: 'nothing propagates' and 'we could not tell' are different."""
    caps = [capability("BC-001", member_paths=("a.py",)),
            capability("BC-002", member_paths=("b.py",))]
    attribution = _attribution([("a.py", "b.py")])
    # No scan category collected -> no capability carries a measured security
    # composite (likelihood and impact both fail to collect).
    risks = build(_cmap(caps, attribution),
                  collected_categories=frozenset()).capabilities
    out = cascades(risks, project_edges(caps, attribution.graph.edges),
                   graph=Measurement.measured(1.0))
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "cascade origin" in out.collected.reason


def test_traversal_stops_at_the_depth_cap():
    chain = [_origin("BC-001", "f1.py")] + [
        capability(f"BC-{i:03d}", member_paths=(f"f{i}.py",))
        for i in range(2, CASCADE_MAX_DEPTH + 3)]
    file_edges = [(f"f{i}.py", f"f{i + 1}.py")
                  for i in range(1, CASCADE_MAX_DEPTH + 2)]
    attribution = _attribution(file_edges,
                               parsed=tuple(f"f{i}.py" for i in
                                            range(1, CASCADE_MAX_DEPTH + 3)))
    out = cascades(_risks(chain, attribution),
                   project_edges(chain, attribution.graph.edges),
                   graph=Measurement.measured(1.0))
    assert out.rows, "the chain's origin must produce cascades"
    assert max(c.depth for c in out.rows) == CASCADE_MAX_DEPTH


def test_cascades_are_order_independent():
    caps = [capability("BC-003", member_paths=("c.py",)),
            _origin("BC-001", "a.py"),
            capability("BC-002", member_paths=("b.py",))]
    file_edges = [("a.py", "b.py"), ("b.py", "c.py")]
    attribution = _attribution(file_edges, parsed=("a.py", "b.py", "c.py"))
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(file_edges)
        out = repr(cascades(_risks(caps, attribution),
                            project_edges(caps, file_edges),
                            graph=Measurement.measured(1.0)))
        first = first if first is not None else out
        assert out == first


