# tests/test_dashboard_graph_state_wire.py
"""E-75 spec §7.4: FINAL run-graph and run-state wire projections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.core.models import PipelineConfig
from sdlc.dashboard import graph_wire
from sdlc.graph import (
    ActivationFacts,
    Emitted,
    GraphRouter,
    GraphRunView,
    PendingFact,
    UnroutedFailure,
    from_yaml,
    validate,
)
from sdlc.graph.node_types import NODE_TYPES
from sdlc.workflows.graph_catalog import SHIPPED, executable, resolved_roles

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
GRAPH = SHIPPED["default"]
ROLES = resolved_roles(PipelineConfig())
TOPOLOGY = validate(GRAPH, NODE_TYPES, roles=ROLES).topology
assert TOPOLOGY is not None
ROUTER = GraphRouter(TOPOLOGY)


def _emit(state, aid, port):
    return ROUTER.advance(
        state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")
    ).state


def _at_architecture():
    s = ROUTER.start().state
    s = _emit(s, "intake#1", "ok")
    s = _emit(s, "clarify#1", "requirements")
    return _emit(s, "architect#1", "spec")


def test_graph_response_carries_sha_graph_and_sorted_back_edges():
    r = graph_wire.graph_response(GRAPH)
    assert r.kind == "graph" and r.sha == GRAPH.content_sha()
    assert [(e.source, e.source_port) for e in r.back_edges] == [
        ("architecture", "revise"),
        ("plan", "revise"),
    ]


def test_state_before_dispatch_is_all_idle_and_running():
    s = graph_wire.project_graph_state(None, GRAPH, TOPOLOGY, execution_closed=False)
    assert s.graph_sha == GRAPH.content_sha()
    assert {n.status for n in s.nodes.values()} == {"idle"}
    assert s.outcome.model_dump() == {"state": "running", "reason": None, "result": None}
    assert (s.edges, s.current_nodes, s.pending) == ([], [], [])


def test_state_at_a_blocked_gate():
    view = GraphRunView(
        graph_sha=GRAPH.content_sha(),
        state=_at_architecture(),
        activations={
            "architect#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.5),
            "architecture#1": ActivationFacts(started_at=AT),
        },
        pending=(
            PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),
            PendingFact(key="orphan#1", activation_id=None, kind="gate"),
        ),
    )
    s = graph_wire.project_graph_state(view, GRAPH, TOPOLOGY, execution_closed=False)
    assert s.nodes["architecture"].status == "blocked"
    assert s.nodes["architecture"].started_at == AT.isoformat()
    assert s.nodes["architecture"].ended_at is None
    assert s.nodes["architecture"].cost_usd is None  # gate: no role
    assert s.nodes["architect"].cost_usd == 1.5
    assert s.nodes["context"].status == "skipped"
    assert s.current_nodes == ["architecture"]
    assert [(p.node, p.key, p.kind) for p in s.pending] == [
        ("architecture", "architecture#1", "gate"),
        (None, "orphan#1", "gate"),
    ]


def test_traversed_back_edges_only_and_closed_runs_list_no_pendings():
    s = _emit(_at_architecture(), "architecture#1", "revise")
    view = GraphRunView(
        graph_sha="x",
        state=s,
        pending=(PendingFact(key="architecture#2", activation_id=None, kind="gate"),),
    )
    open_ = graph_wire.project_graph_state(view, GRAPH, TOPOLOGY, execution_closed=False)
    assert [(e.edge.source, e.edge.target, e.traversals) for e in open_.edges] == [
        ("architecture", "architect", 1)
    ]
    closed = graph_wire.project_graph_state(
        view, GRAPH, TOPOLOGY, execution_closed=True, close_status="terminated"
    )
    assert closed.pending == [] and closed.current_nodes == []
    assert closed.outcome.state == "failed" and closed.outcome.reason == "interrupted:terminated"
    assert closed.nodes["architect"].status == "cancelled"


def test_unrouted_failure_outcome_and_node():
    s = _emit(ROUTER.start().state, "intake#1", "fail")
    view = GraphRunView(
        graph_sha="x",
        state=s,
        unrouted_failure=UnroutedFailure(activation_id="intake#1", error_type="ApplicationError"),
    )
    out = graph_wire.project_graph_state(
        view, GRAPH, TOPOLOGY, execution_closed=True, close_status="failed"
    )
    assert out.nodes["intake"].status == "failed"
    assert out.outcome.model_dump() == {
        "state": "failed",
        "reason": "intake.fail: ApplicationError",
        "result": None,
    }


def test_wire_models_are_final_shapes():
    with pytest.raises(ValidationError):
        graph_wire.GraphState.model_validate(
            {
                "kind": "state",
                "graph_sha": "x",
                "nodes": {},
                "edges": [],
                "current_nodes": [],
                "pending": [],
                "terminal": None,
            }
        )
    assert "terminal" not in graph_wire.GraphState.model_fields


def test_executable_problems_get_their_own_severity():
    pre_code = from_yaml(
        (Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml").read_text(
            encoding="utf-8"
        )
    )
    problems = executable(pre_code)
    assert problems, "pre_code has a gate.research node, which is not executable"
    wire = graph_wire.with_executable(graph_wire.validation(pre_code, roles=ROLES), problems)
    extra = [i for i in wire.issues if i.severity == "not_executable"]
    assert [(i.code, i.target.kind, i.target.id) for i in extra] == [
        (p.code, "node", p.node) for p in problems
    ]
