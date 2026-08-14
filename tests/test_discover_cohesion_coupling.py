"""FR-913 (E-48 DD1): clause D1 as arithmetic, not opinion."""
from __future__ import annotations

import random

from sdlc.assessment.discover.context import cohesion, coupling
from sdlc.measurement import CollectionState

PARSED = {"a.py", "b.py", "c.py", "d.py"}


def test_cohesion_is_the_share_of_touching_edges_that_stay_inside():
    edges = (("a.py", "b.py"), ("a.py", "c.py"))
    m = cohesion({"a.py", "b.py"}, edges, PARSED)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.5


def test_a_fully_internal_candidate_scores_one():
    edges = (("a.py", "b.py"),)
    assert cohesion({"a.py", "b.py"}, edges, PARSED).value == 1.0


def test_cohesion_is_not_collected_when_no_edge_touches_the_candidate():
    """measured(0.0) would claim the files are mutually unreferenced. They
    may simply be leaves."""
    m = cohesion({"a.py"}, (("b.py", "c.py"),), PARSED)
    assert m.state is CollectionState.NOT_COLLECTED
    assert "no reference-graph edge" in m.reason


def test_cohesion_is_not_collected_when_the_files_were_never_parsed():
    """FR-915: an unparsed file yields no edges, and an absence of edges from
    an absence of parsing is not evidence of anything."""
    m = cohesion({"x.rb"}, (("a.py", "b.py"),), PARSED)
    assert m.state is CollectionState.NOT_COLLECTED
    assert "not parsed" in m.reason


def test_coupling_counts_distinct_partner_capabilities():
    edges = (("a.py", "c.py"), ("a.py", "d.py"), ("b.py", "c.py"))
    owner_of = {"c.py": {"C-02"}, "d.py": {"C-03"}}
    m = coupling("C-01", {"a.py", "b.py"}, edges, owner_of, PARSED)
    assert m.value == 2.0


def test_coupling_never_counts_the_candidate_itself():
    edges = (("a.py", "b.py"),)
    owner_of = {"a.py": {"C-01"}, "b.py": {"C-01"}}
    assert coupling("C-01", {"a.py", "b.py"}, edges, owner_of, PARSED).value == 0.0


def test_zero_coupling_is_a_real_measurement_when_the_files_parsed():
    """The counterpart to the guard above: a parsed, edge-having tree in
    which this capability reaches nobody is a measured zero."""
    m = coupling("C-01", {"a.py"}, (("b.py", "c.py"),), {}, PARSED)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0


def test_coupling_is_not_collected_when_the_files_were_never_parsed():
    m = coupling("C-01", {"x.rb"}, (("a.py", "b.py"),), {}, PARSED)
    assert m.state is CollectionState.NOT_COLLECTED


def test_both_are_order_independent():
    """NFR-10."""
    edges = [("a.py", "b.py"), ("a.py", "c.py"), ("b.py", "d.py")]
    owner_of = {"c.py": {"C-02"}, "d.py": {"C-03"}}
    first = (cohesion({"a.py", "b.py"}, tuple(edges), PARSED),
             coupling("C-01", {"a.py", "b.py"}, tuple(edges), owner_of, PARSED))
    for _ in range(5):
        shuffled = edges[:]
        random.shuffle(shuffled)
        assert (cohesion({"a.py", "b.py"}, tuple(shuffled), PARSED),
                coupling("C-01", {"a.py", "b.py"}, tuple(shuffled), owner_of,
                         PARSED)) == first
