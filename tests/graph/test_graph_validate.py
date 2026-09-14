"""E-73 validate.py (spec §7): one table row per ProblemCode, suppression,
degenerate graphs, and the Topology a clean graph yields."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.validate import Problem, ProblemCode, ValidationReport, validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"
C = ProblemCode


def _codes(report: ValidationReport) -> list[str]:
    return [p.code.value for p in report.problems]


def _check(g, registry=GENERIC, **role_overrides) -> ValidationReport:
    return validate(g, registry, roles=roles(**role_overrides))


def _chain(*extra_edges, extra_nodes=()):
    """start -> w (work) -> s (sink): the smallest clean GENERIC graph."""
    return graph(
        [node("start", "start"), node("w", "work"), node("s", "sink"), *extra_nodes],
        [edge("start.ok", "w.trigger"), edge("w.out", "s.art"), *extra_edges],
    )


# ---- clean graphs and the Topology they carry ------------------------------


def test_clean_chain_has_no_problems_and_a_topology():
    report = _check(_chain())
    assert report.problems == ()
    assert report.ok
    topo = report.topology
    assert topo is not None
    assert topo.entry == "start"
    assert topo.node_ids == ("s", "start", "w")
    assert topo.gate_nodes == ()
    assert topo.bounds == {}
    assert topo.regions == {}
    assert topo.out_ports["w"] == {"out": ("w.out->s.art",)}
    assert topo.out_ports["s"] == {"done": ()}  # unconnected out-ports are listed
    assert set(topo.in_ports["w"]) == {"trigger"}  # unconnected `guidance` is not


def test_e72_fixture_is_clean_against_the_seed_registry():
    report = validate(from_yaml(FIXTURE.read_text(encoding="utf-8")), roles=roles())
    assert report.problems == ()
    topo = report.topology
    assert topo is not None
    assert topo.entry == "intake"
    assert topo.gate_nodes == ("architecture", "plan", "research")
    assert topo.bounds == {
        "architecture.revise->architect.guidance": 2,
        "plan.revise->planner.guidance": 2,
        "research.revise->researcher.guidance": 2,
    }
    # REGION(v) = v plus its forward reach (spec D2).
    assert topo.regions["architect"] == ("architect", "architecture", "plan", "planner")
    assert topo.regions["planner"] == ("plan", "planner")
    wiring = topo.in_ports["architect"]["guidance"]
    assert wiring.forward_edges == ()
    assert wiring.back_edges == ("architecture.revise->architect.guidance",)


def test_plan_revise_to_architect_is_legal():
    """Dominance would reject this edge (spec U3); the marker rule accepts it."""
    g = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    extra = edge("plan.revise", "architect.guidance", bound=1)
    g2 = graph(list(g.nodes), [e for e in g.edges if e.source != "plan"] + [extra])
    report = validate(g2, roles=roles())
    assert report.problems == ()
    assert report.topology is not None
    assert "plan.revise->architect.guidance" in report.topology.bounds


def test_report_json_excludes_topology():
    report = _check(_chain())
    assert report.model_dump(mode="json") == {"problems": []}


# ---- T1 identity ------------------------------------------------------------


def test_duplicate_node_id():
    g = _chain(extra_nodes=(node("w", "sink"),))
    assert C.DUPLICATE_NODE_ID in _codes(_check(g))
    [p] = [p for p in _check(g).problems if p.code is C.DUPLICATE_NODE_ID]
    assert p.node == "w"


def test_duplicate_edge_even_when_bounds_disagree():
    g = _chain(edge("w.out", "s.art", bound=2))
    report = _check(g)
    [p] = [p for p in report.problems if p.code is C.DUPLICATE_EDGE]
    assert p.edge == ("w", "out", "s", "art")
    assert report.topology is None


# ---- T2 references ------------------------------------------------------------


def test_dangling_endpoint_names_each_missing_side():
    g = _chain(edge("ghost.out", "phantom.art"))
    dangling = [p for p in _check(g).problems if p.code is C.DANGLING_ENDPOINT]
    assert [p.message.split(": ")[1] for p in dangling] == [
        "source 'ghost' names no node",
        "target 'phantom' names no node",
    ]


def test_unknown_node_type():
    g = _chain(extra_nodes=(node("x", "nope"),))
    [p] = [p for p in _check(g).problems if p.code is C.UNKNOWN_NODE_TYPE]
    assert p.node == "x"


@pytest.mark.parametrize(
    ("bad", "node_id", "port"),
    [
        (edge("w.nope", "s.art"), "w", "nope"),  # no such out-port
        (edge("w.out", "s.nope"), "s", "nope"),  # no such in-port
        (edge("w.guidance", "s.art"), "w", "guidance"),  # an in-port used as a source
        (edge("w.out", "s.done"), "s", "done"),  # an out-port used as a target
    ],
)
def test_unknown_port_including_wrong_direction(bad, node_id, port):
    g = graph(
        [node("start", "start"), node("w", "work"), node("s", "sink")],
        [edge("start.ok", "w.trigger"), bad],
    )
    unknown = [p for p in _check(g).problems if p.code is C.UNKNOWN_PORT]
    assert [(p.node, p.port) for p in unknown] == [(node_id, port)]


def test_incompatible_ports_on_forward_and_back_edges():
    g = graph(
        [node("start", "start"), node("w", "work"), node("g", "gate.art"), node("s", "sink")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.approve", "s.art"),
            edge("start.ok", "s.art"),  # None -> Art
            edge("g.reject", "w.guidance", bound=1),  # back edge: None -> GateDecision
        ],
    )
    bad = [p.edge for p in _check(g).problems if p.code is C.INCOMPATIBLE_PORTS]
    assert bad == [("g", "reject", "w", "guidance"), ("start", "ok", "s", "art")]


# ---- T5 topology ----------------------------------------------------------------


def test_forward_cycle_reported_once_per_scc():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.trigger"), edge("a.redo", "a.again")],  # unbounded self loop
    )
    [p] = [p for p in _check(g).problems if p.code is C.FORWARD_CYCLE]
    assert p.node == "a"


def test_bounded_edge_not_a_loop():
    g = _chain(extra_nodes=(node("x", "work"),))
    g = graph(list(g.nodes), [*g.edges, edge("start.ok", "x.trigger", bound=2)])
    report = _check(g)
    assert [p.edge for p in report.problems if p.code is C.BOUNDED_EDGE_NOT_A_LOOP] == [
        ("start", "ok", "x", "trigger")
    ]


def test_bounded_self_loop_is_legal():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.trigger"), edge("a.redo", "a.again", bound=3)],
    )
    report = _check(g)
    assert report.problems == ()
    assert report.topology is not None
    assert report.topology.regions == {"a": ("a",)}


def test_zero_nodes_is_entry_count_zero():
    assert _codes(_check(graph([], []))) == [C.ENTRY_COUNT]


def test_two_roots_report_entry_count_and_no_unreachable_node():
    """Spec §7.2 T5 (reviewer R3): no arbitrary anchor when entries != 1."""
    g = _chain(extra_nodes=(node("start2", "start"),))
    report = _check(g)
    assert C.ENTRY_COUNT in _codes(report)
    assert C.UNREACHABLE_NODE not in _codes(report)
    [p] = [p for p in report.problems if p.code is C.ENTRY_COUNT]
    assert "'start', 'start2'" in p.message


def test_unreachable_node():
    """With exactly one entry, a node is unreachable only inside a forward
    cycle the entry never enters: both members have forward in-edges."""
    g = _chain(
        edge("a.out", "b.art"),
        edge("b.done", "a.trigger"),
        extra_nodes=(node("a", "work"), node("b", "sink")),
    )
    report = _check(g)
    assert [p.node for p in report.problems if p.code is C.UNREACHABLE_NODE] == ["a", "b"]
    assert C.FORWARD_CYCLE in _codes(report)
    assert C.ENTRY_COUNT not in _codes(report)


# ---- suppression (spec §7.1) ----------------------------------------------------


def test_port_typo_does_not_hide_a_forward_cycle():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.triggr"), edge("a.redo", "a.again")],
    )
    codes = _codes(_check(g))
    assert C.UNKNOWN_PORT in codes
    assert C.FORWARD_CYCLE in codes


@pytest.mark.parametrize(
    "g",
    [
        _chain(edge("ghost.out", "s.art")),  # dangling endpoint
        _chain(edge("w.out", "s.art")),  # duplicate edge
        _chain(extra_nodes=(node("s", "work"),)),  # duplicate node id
    ],
)
def test_ambiguous_node_or_edge_sets_suppress_the_topology_tier(g):
    g = graph(list(g.nodes), [*g.edges, edge("s.done", "s.done")])  # would be a forward cycle
    codes = _codes(_check(g))
    assert C.FORWARD_CYCLE not in codes
    assert C.ENTRY_COUNT not in codes


# ---- degenerate graphs ----------------------------------------------------------


def test_lone_start_node_is_legal():
    report = _check(graph([node("start", "start")], []))
    assert report.problems == ()


def test_problems_are_sorted_and_none_safe():
    g = graph(
        [node("start", "start"), node("x", "nope"), node("y", "nope")],
        [edge("ghost.ok", "x.in"), edge("start.ok", "phantom.in")],
    )
    problems = _check(g).problems
    assert list(problems) == sorted(problems, key=Problem.sort_key)
    assert len(problems) >= 4
