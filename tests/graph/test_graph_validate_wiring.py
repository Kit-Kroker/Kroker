"""E-73 validate.py T4 wiring (spec §7.2): the preconditions the router's
readiness, invalidation and exclusive-merge semantics rely on."""

from __future__ import annotations

from sdlc.graph.validate import ProblemCode, ValidationReport, validate
from tests.graph.fixtures.registries import (
    FIX_LOOP,
    GENERIC,
    edge,
    fix_loop_graph,
    graph,
    node,
    roles,
)

C = ProblemCode


def _check(nodes, edges) -> ValidationReport:
    return validate(graph([node("start", "start"), *nodes], edges), GENERIC, roles=roles())


def _hits(report: ValidationReport, code: ProblemCode) -> list[tuple]:
    return [(p.node, p.port, p.edge) for p in report.problems if p.code is code]


def test_fix_loop_fixture_is_clean():
    report = validate(fix_loop_graph(2, 2), FIX_LOOP, roles=roles())
    assert report.problems == ()
    assert report.topology is not None
    wiring = report.topology.in_ports["coder"]["guidance"]
    assert wiring.back_edges == ("qa.fail->coder.guidance", "task.revise->coder.guidance")


def test_required_in_port_unconnected():
    report = _check([node("s", "sink")], [])
    assert _hits(report, C.REQUIRED_IN_PORT_UNCONNECTED) == [("s", "art", None)]


def test_required_in_port_fed_only_by_a_loop_edge_is_unconnected():
    """A back edge alone would deadlock at round 1 (spec §7.2 T4)."""
    report = _check(
        [node("w", "work"), node("r", "retry")],
        [edge("start.ok", "w.trigger"), edge("r.redo", "r.again", bound=2)],
    )
    assert ("r", "trigger", None) in _hits(report, C.REQUIRED_IN_PORT_UNCONNECTED)


def test_lone_gate_yields_exactly_one_problem():
    report = validate(graph([node("g", "gate.art")], []), GENERIC, roles=roles())
    assert [p.code for p in report.problems] == [C.REQUIRED_IN_PORT_UNCONNECTED]


def test_mixed_in_port():
    report = _check(
        [node("w", "work"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revise", "w.guidance", bound=2),
            edge("g.approve", "w.guidance"),  # incompatible AND forward: mixes with the loop
        ],
    )
    assert _hits(report, C.MIXED_IN_PORT) == [("w", "guidance", None)]


def test_back_port_not_exclusive():
    report = _check(
        [node("w", "work"), node("g", "gate.art"), node("x", "work")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revise", "w.guidance", bound=2),
            edge("g.revise", "x.guidance"),
            edge("start.ok", "x.trigger"),
        ],
    )
    assert _hits(report, C.BACK_PORT_NOT_EXCLUSIVE) == [("g", "revise", None)]


def test_back_edge_into_many():
    report = _check(
        [node("w", "work"), node("c", "collect"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "c.items"),
            edge("c.done", "g.artifact"),  # incompatible; irrelevant here
            edge("g.approve", "c.items", bound=1),
        ],
    )
    assert _hits(report, C.BACK_EDGE_INTO_MANY) == [(None, None, ("g", "approve", "c", "items"))]


def test_one_port_multiple_sources_rejects_two_nodes():
    report = _check(
        [node("a", "work"), node("b", "work"), node("s", "sink")],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "s.art"),
            edge("b.out", "s.art"),
        ],
    )
    assert _hits(report, C.ONE_PORT_MULTIPLE_SOURCES) == [("s", "art", None)]


def test_one_port_fed_by_distinct_ports_of_one_node_is_legal():
    """The §6.4 exclusive merge: mutually exclusive by one-port-per-activation."""
    report = _check(
        [node("br", "brancher"), node("m", "sink")],
        [edge("start.ok", "br.trigger"), edge("br.left", "m.art"), edge("br.right", "m.art")],
    )
    assert report.problems == ()


def test_many_port_accepts_several_sources():
    report = _check(
        [node("a", "work"), node("b", "work"), node("c", "collect")],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "c.items"),
            edge("b.out", "c.items"),
        ],
    )
    assert report.problems == ()


def test_duplicated_edge_is_reported_once():
    """Spec §7.1 (skeptic F6): a duplicate is skipped by T4, yet still counts
    as connecting its required in-port."""
    report = _check(
        [node("w", "work"), node("s", "sink")],
        [edge("start.ok", "w.trigger"), edge("w.out", "s.art"), edge("w.out", "s.art", bound=2)],
    )
    assert [p.code for p in report.problems] == [C.DUPLICATE_EDGE]


def test_unresolved_out_port_does_not_trip_back_port_exclusivity():
    report = _check(
        [node("w", "work"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revize", "w.guidance", bound=2),
            edge("g.revize", "g.artifact"),
        ],
    )
    assert _hits(report, C.BACK_PORT_NOT_EXCLUSIVE) == []
    assert C.UNKNOWN_PORT in [p.code for p in report.problems]
