# tests/test_risk_crosscap.py
"""RD10: the capability->capability projection and the two computed families.

The projection is a re-index of data already on the CapabilityMap -- no blob
is read and nothing is executed (NFR-9).
"""
from __future__ import annotations

import random

import pytest

from sdlc.assessment.risk.crosscap import (
    project_edges, shared_vulnerabilities, weakness_class,
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

