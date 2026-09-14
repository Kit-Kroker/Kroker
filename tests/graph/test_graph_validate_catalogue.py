"""E-73 ProblemCode catalogue (spec §7.2, §8): ONE table row per code, plus a
meta-test that the table covers the whole closed enum. A new code without a
row fails here, so E-76 never renders a code no test can produce."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sdlc.graph import NODE_TYPES
from sdlc.graph.model import PipelineGraph
from sdlc.graph.validate import ProblemCode, validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

C = ProblemCode
_START = node("start", "start")


def _g(*nodes, edges=()) -> PipelineGraph:
    return graph([_START, *nodes], list(edges))


def _builder(id_: str, model: str):
    return node(id_, "builder", role={"kind": "harness", "harness": "opencode", "model": model})


# code -> (graph, registry, roles)
ROWS: dict[ProblemCode, Callable[[], tuple]] = {
    C.DUPLICATE_NODE_ID: lambda: (_g(node("start", "sink")), GENERIC, roles()),
    C.DUPLICATE_EDGE: lambda: (
        _g(node("w", "work"), edges=[edge("start.ok", "w.trigger")] * 2),
        GENERIC,
        roles(),
    ),
    C.DANGLING_ENDPOINT: lambda: (_g(edges=[edge("start.ok", "ghost.trigger")]), GENERIC, roles()),
    C.UNKNOWN_NODE_TYPE: lambda: (_g(node("x", "nope")), GENERIC, roles()),
    C.UNKNOWN_PORT: lambda: (
        _g(node("w", "work"), edges=[edge("start.nope", "w.trigger")]),
        GENERIC,
        roles(),
    ),
    C.INCOMPATIBLE_PORTS: lambda: (
        _g(node("s", "sink"), edges=[edge("start.ok", "s.art")]),
        GENERIC,
        roles(),
    ),
    C.ROLE_ON_ROLELESS_TYPE: lambda: (
        _g(node("w", "work", role={"kind": "proposer"})),
        GENERIC,
        roles(),
    ),
    C.GATE_ON_NON_GATE: lambda: (_g(node("w", "work", gate={})), GENERIC, roles()),
    C.LOADER_OWNED_FIELD: lambda: (
        _g(
            node(
                "b",
                "builder",
                role={"kind": "harness", "harness": "opencode", "tool_files": ["t.py"]},
            )
        ),
        GENERIC,
        roles(),
    ),
    C.ROLE_NOT_IN_REGISTRY: lambda: (
        graph([node("intake", "intake"), node("r", "research")], []),
        NODE_TYPES,
        roles(research=None),
    ),
    C.ROLE_KIND_MISMATCH: lambda: (
        graph([node("intake", "intake"), node("a", "architect", role={})], []),
        NODE_TYPES,
        roles(),
    ),
    C.ROLE_HARNESS_MISSING: lambda: (_g(node("b", "builder", role={})), GENERIC, roles()),
    C.RESEARCH_PROVIDER_MISSING: lambda: (
        graph([node("intake", "intake"), node("r", "research", role={"kind": "research"})], []),
        NODE_TYPES,
        roles(),
    ),
    C.ADR6_VIOLATION: lambda: (_g(_builder("b", "anthropic:x")), GENERIC, roles()),
    C.ADR6_COMBINATIONS_EXCEEDED: lambda: (
        _g(*(_builder(f"b{i}", f"f{i}:m") for i in range(300))),
        GENERIC,
        roles(),
    ),
    C.RESERVED_GATE_NAME: lambda: (_g(node("merge", "gate.art")), GENERIC, roles()),
    C.REQUIRED_IN_PORT_UNCONNECTED: lambda: (_g(node("s", "sink")), GENERIC, roles()),
    C.MIXED_IN_PORT: lambda: (
        _g(
            node("w", "work"),
            node("g", "gate.art"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.revise", "w.guidance", bound=1),
                edge("g.approve", "w.guidance"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.BACK_PORT_NOT_EXCLUSIVE: lambda: (
        _g(
            node("w", "work"),
            node("g", "gate.art"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.revise", "w.guidance", bound=1),
                edge("g.revise", "g.artifact"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.BACK_EDGE_INTO_MANY: lambda: (
        _g(
            node("w", "work"),
            node("c", "collect"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "c.items"),
                edge("c.done", "c.items", bound=1),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.ONE_PORT_MULTIPLE_SOURCES: lambda: (
        _g(
            node("a", "work"),
            node("b", "work"),
            node("s", "sink"),
            edges=[
                edge("start.ok", "a.trigger"),
                edge("start.ok", "b.trigger"),
                edge("a.out", "s.art"),
                edge("b.out", "s.art"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.FORWARD_CYCLE: lambda: (
        _g(node("r", "retry"), edges=[edge("start.ok", "r.trigger"), edge("r.redo", "r.again")]),
        GENERIC,
        roles(),
    ),
    C.BOUNDED_EDGE_NOT_A_LOOP: lambda: (
        _g(node("w", "work"), edges=[edge("start.ok", "w.trigger", bound=1)]),
        GENERIC,
        roles(),
    ),
    C.ENTRY_COUNT: lambda: (graph([], []), GENERIC, roles()),
    C.UNREACHABLE_NODE: lambda: (
        _g(
            node("a", "work"),
            node("b", "sink"),
            edges=[edge("a.out", "b.art"), edge("b.done", "a.trigger")],
        ),
        GENERIC,
        roles(),
    ),
}


def test_every_problem_code_has_a_row():
    assert set(ROWS) == set(ProblemCode)


@pytest.mark.parametrize("code", sorted(ROWS, key=lambda c: c.value), ids=lambda c: c.value)
def test_row_produces_its_code(code):
    g, registry, role_map = ROWS[code]()
    report = validate(g, registry, roles=role_map)
    assert code in {p.code for p in report.problems}
    assert report.topology is None


def test_codes_are_stable_snake_case_strings():
    """E-76 generates its TypeScript union from these values."""
    for code in ProblemCode:
        assert code.value == code.name.lower()
