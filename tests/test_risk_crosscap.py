# tests/test_risk_crosscap.py
"""RD10: the capability->capability projection and the two computed families.

The projection is a re-index of data already on the CapabilityMap -- no blob
is read and nothing is executed (NFR-9).
"""
from __future__ import annotations

import random

import pytest

from sdlc.assessment.risk.crosscap import project_edges
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
