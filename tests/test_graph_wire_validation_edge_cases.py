"""Edge cases for graph_wire's mapping of E-73 validate onto ValidationWire
(E-76 spec §5.5; handover 2026-09-14-e76-needs-from-e73-validate.md).

Pinned API: `graph_wire.validation(graph, registry=NODE_TYPES, *, roles)`,
the same signature as `sdlc.graph.validate`. It takes the graph and not a
bare report because a report with problems carries no Topology, while
`back_edges` must still reach the canvas for a broken draft.

Target precedence (most specific element the canvas can draw):
edge > port (node + port) > node > graph. UNKNOWN_PORT carries all three
and lands on its edge, because an unknown port has no handle to draw.
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

import sdlc.dashboard.graph_wire as graph_wire
from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.graph.validate import Problem, ProblemCode, validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles
from tests.graph.test_graph_validate_catalogue import ROWS

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"
_EDGE_FIELDS = ("source", "source_port", "target", "target_port")
_FIXTURE_BACK_EDGES = [
    ("architecture", "revise", "architect", "guidance"),
    ("plan", "revise", "planner", "guidance"),
    ("research", "revise", "researcher", "guidance"),
]


def _fixture():
    return from_yaml(FIXTURE.read_text(encoding="utf-8"))


def _wire(g, registry=NODE_TYPES, role_map=None):
    return graph_wire.validation(g, registry, roles=roles() if role_map is None else role_map)


def _refs(wire) -> list[tuple[str, str, str, str]]:
    return [tuple(getattr(r, f) for f in _EDGE_FIELDS) for r in wire.back_edges]


def _expected_target(p: Problem) -> dict:
    if p.edge is not None:
        return {"kind": "edge", "edge": dict(zip(_EDGE_FIELDS, p.edge, strict=True))}
    if p.port is not None:
        return {"kind": "port", "node": p.node, "port": p.port}
    if p.node is not None:
        return {"kind": "node", "id": p.node}
    return {"kind": "graph"}


# --- every ProblemCode through the wire ----------------------------------------


@pytest.mark.parametrize("code", sorted(ROWS, key=lambda c: c.value), ids=lambda c: c.value)
def test_each_issue_mirrors_its_problem_in_order(code):
    g, registry, role_map = ROWS[code]()
    report = validate(g, registry, roles=role_map)
    wire = graph_wire.validation(g, registry, roles=role_map)

    assert len(wire.issues) == len(report.problems)
    for issue, problem in zip(wire.issues, report.problems, strict=True):
        assert issue.code == problem.code.value
        assert type(issue.code) is str  # a plain string, never the StrEnum member
        assert issue.severity == "error"  # E-73 has no non-blocking finding
        assert issue.message == problem.message
        assert issue.target.model_dump(mode="json", exclude_none=True) == _expected_target(problem)


def test_unknown_port_lands_on_its_edge_not_on_the_missing_port():
    g, registry, role_map = ROWS[ProblemCode.UNKNOWN_PORT]()
    wire = graph_wire.validation(g, registry, roles=role_map)
    (issue,) = [i for i in wire.issues if i.code == "unknown_port"]
    assert issue.target.kind == "edge"
    assert issue.target.edge is not None
    assert (issue.target.edge.source, issue.target.edge.source_port) == ("start", "nope")
    assert issue.target.node is None and issue.target.port is None


def test_graph_wide_problems_target_the_graph():
    wire = _wire(graph([], []), GENERIC)
    assert [i.code for i in wire.issues] == ["entry_count"]
    assert wire.issues[0].target.model_dump(mode="json", exclude_none=True) == {"kind": "graph"}
    assert wire.back_edges == []


# --- back_edges ------------------------------------------------------------------


def test_clean_fixture_has_no_issues_and_its_three_loop_edges():
    wire = _wire(_fixture())
    assert wire.issues == []
    assert _refs(wire) == _FIXTURE_BACK_EDGES


def test_back_edges_survive_a_broken_graph_without_topology():
    """report.topology is None here; deriving back_edges from it would
    blank every loop curve the moment a draft has one error."""
    g = _fixture()
    broken = graph([*g.nodes, node("zz", "nope")], list(g.edges))
    assert validate(broken, roles=roles()).topology is None
    wire = _wire(broken)
    assert "unknown_node_type" in [i.code for i in wire.issues]
    assert _refs(wire) == _FIXTURE_BACK_EDGES


def test_back_edges_include_a_bounded_edge_with_a_dangling_endpoint():
    g = graph(
        [node("start", "start"), node("w", "work")],
        [edge("start.ok", "w.trigger"), edge("ghost.out", "w.guidance", bound=1)],
    )
    wire = _wire(g, GENERIC)
    assert "dangling_endpoint" in [i.code for i in wire.issues]
    assert _refs(wire) == [("ghost", "out", "w", "guidance")]


def test_duplicated_loop_edge_appears_once_in_back_edges():
    """Same 4-tuple twice with disagreeing bounds: an EdgeRef names the
    tuple, and the canvas maps one ref onto every duplicate."""
    g = graph(
        [node("start", "start"), node("w", "work"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revise", "w.guidance", bound=1),
            edge("g.revise", "w.guidance", bound=3),
        ],
    )
    wire = _wire(g, GENERIC)
    assert "duplicate_edge" in [i.code for i in wire.issues]
    assert _refs(wire) == [("g", "revise", "w", "guidance")]


def test_unbounded_edges_are_never_back_edges():
    g = graph(
        [node("start", "start"), node("r", "retry")],
        [edge("start.ok", "r.trigger"), edge("r.redo", "r.again")],
    )
    wire = _wire(g, GENERIC)
    assert "forward_cycle" in [i.code for i in wire.issues]
    assert wire.back_edges == []


# --- determinism, degenerate inputs, concurrency -----------------------------


def _messy_parts():
    g = _fixture()
    nodes = [*g.nodes, node("zz", "nope"), node("intake", "sink"), node("merge", "gate.plan")]
    edges = [*g.edges, edge("ghost.out", "planner.guidance", bound=1), edge("intake.ok", "zz.x")]
    return nodes, edges


def test_output_is_independent_of_author_order_and_roles_order():
    nodes, edges = _messy_parts()
    role_map = roles()
    baseline = graph_wire.validation(graph(nodes, edges), roles=role_map).model_dump_json()
    assert len(graph_wire.validation(graph(nodes, edges), roles=role_map).issues) > 3
    rng = random.Random(1202)
    for _ in range(20):
        n, e = list(nodes), list(edges)
        rng.shuffle(n)
        rng.shuffle(e)
        reversed_roles = dict(reversed(list(role_map.items())))
        got = graph_wire.validation(graph(n, e), roles=reversed_roles).model_dump_json()
        assert got == baseline


def test_empty_roles_mapping_maps_without_raising():
    wire = _wire(_fixture(), role_map={})
    assert "role_not_in_registry" in [i.code for i in wire.issues]
    assert {i.target.kind for i in wire.issues} <= {"node", "graph"}
    assert _refs(wire) == _FIXTURE_BACK_EDGES


def test_wire_json_round_trips():
    nodes, edges = _messy_parts()
    wire = _wire(graph(nodes, edges))
    assert graph_wire.ValidationWire.model_validate_json(wire.model_dump_json()) == wire


def test_concurrent_calls_agree():
    """E-75 serves this from a threadpool; validate's ADR-6 check imports
    lazily inside its body."""
    nodes, edges = _messy_parts()
    g = graph(nodes, edges)
    with ThreadPoolExecutor(max_workers=8) as pool:
        dumps = set(pool.map(lambda _: _wire(g).model_dump_json(), range(32)))
    assert len(dumps) == 1


# --- the wire model refuses a target the canvas would silently drop -------------

_REF = {"source": "a", "source_port": "o", "target": "b", "target_port": "i"}


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "graph", "id": "a"},
        {"kind": "graph", "edge": _REF},
        {"kind": "node"},
        {"kind": "node", "id": "a", "port": "p"},
        {"kind": "edge"},
        {"kind": "edge", "edge": _REF, "id": "a"},
        {"kind": "port", "node": "a"},
        {"kind": "port", "port": "p"},
        {"kind": "port", "node": "a", "port": "p", "edge": _REF},
    ],
    ids=lambda t: "+".join([t["kind"], *sorted(set(t) - {"kind"})]),
)
def test_issue_target_rejects_a_shape_outside_the_spec_union(target):
    """adapters/graph.ts drops `kind: 'port'` without `node` (and the like)
    to a '(not on canvas)' row: the model must refuse to build one."""
    with pytest.raises(ValidationError):
        graph_wire.IssueTarget.model_validate(target)
