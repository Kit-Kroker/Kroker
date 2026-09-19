# tests/graph/test_run_view_projections.py
"""E-75 spec §5.1-§5.3: node status, run outcome and stage marks are pure tables."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.graph import (
    ActivationFacts,
    Emitted,
    GraphRouter,
    GraphRunView,
    Halt,
    PendingFact,
    UnroutedFailure,
    close_marks,
    node_cost,
    node_status,
    run_outcome,
    stage_marks,
    validate,
)
from sdlc.graph.node_types import NodeTypeSpec
from tests.graph.fixtures.registries import (
    edge,
    gate,
    graph,
    node,
    port_in,
    port_out,
    registry,
    roles,
    stage,
)

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _staged(spec: NodeTypeSpec, canonical: str, role: str | None = None) -> NodeTypeSpec:
    return spec.model_copy(update={"canonical_stage": canonical, "role": role})


REG = registry(
    _staged(stage("start", port_out("ok", None), port_out("alt", None)), "intake"),
    _staged(
        stage(
            "work",
            port_in("trigger", None),
            port_in("guidance", "GateDecision", required=False),
            port_out("out", "P"),
            port_out("fail", "NodeFailure", terminal="failed"),
        ),
        "architecture",
        role="architect",
    ),
    _staged(gate("check", "P"), "architecture"),
    _staged(stage("side", port_in("trigger", None), port_out("done", None)), "context"),
    _staged(stage("sink", port_in("art", "P"), port_out("done", None)), "deploy"),
)

# start.ok -> w -> g (gate) -> s ; g.revise -> w.guidance (bound 1) ; start.alt -> x (side)
G = graph(
    [
        node("start", "start"),
        node("w", "work"),
        node("g", "check"),
        node("s", "sink"),
        node("x", "side"),
    ],
    [
        edge("start.ok", "w.trigger"),
        edge("start.alt", "x.trigger"),
        edge("w.out", "g.artifact"),
        edge("g.approve", "s.art"),
        edge("g.revise", "w.guidance", bound=1),
    ],
)
REPORT = validate(G, REG, roles=roles())
assert REPORT.topology is not None, REPORT.problems
T = REPORT.topology
ROUTER = GraphRouter(T)


def _emit(state, aid: str, port: str):
    return ROUTER.advance(state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}"))


def _at_gate():
    """start#1 ok -> w#1 out -> g#1 live; x is dead (start took ok)."""
    s = ROUTER.start().state
    s = _emit(s, "start#1", "ok").state
    return _emit(s, "w#1", "out").state


def _view(state, **kw) -> GraphRunView:
    return GraphRunView(graph_sha="sha", state=state, **kw)


def test_status_table_at_a_live_gate():
    v = _view(_at_gate())
    assert node_status("start", v, T) == "done"
    assert node_status("x", v, T) == "skipped"  # dead
    assert node_status("w", v, T) == "done"
    assert node_status("g", v, T) == "running"
    assert node_status("s", v, T) == "idle"


def test_a_pending_attributed_to_the_latest_activation_blocks():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert node_status("g", v, T) == "blocked"
    other = _view(_at_gate(), pending=(PendingFact(key="k", activation_id=None, kind="gate"),))
    assert node_status("g", other, T) == "running"


def test_a_back_edge_makes_the_region_stale():
    s = _emit(_at_gate(), "g#1", "revise").state  # w re-issued as w#2; g reset to pending
    v = _view(s)
    assert node_status("w", v, T) == "running"
    assert node_status("g", v, T) == "stale"  # pending with round 1


def test_a_rejecting_gate_is_done_and_the_run_rejected():
    s = _emit(_at_gate(), "g#1", "reject").state  # terminal rejected; g done
    v = _view(s)
    assert s.outcome == "rejected"
    assert node_status("g", v, T) == "done"  # a rejecting gate did its job


def test_escalating_emitter_renders_failed():
    s = _emit(_at_gate(), "g#1", "revise").state
    s = _emit(s, "w#2", "out").state  # g#2 issued with revise exhausted
    step = _emit(s, "g#2", "revise")
    assert step.outcome == "escalated"
    v = _view(step.state, escalated_by="g#2")
    assert node_status("g", v, T) == "failed"


# A live bystander: start.ok feeds both w and y, so y is running while g decides.
G2 = graph(
    [
        node("start", "start"),
        node("w", "work"),
        node("g", "check"),
        node("s", "sink"),
        node("y", "side"),
    ],
    [
        edge("start.ok", "w.trigger"),
        edge("start.ok", "y.trigger"),
        edge("w.out", "g.artifact"),
        edge("g.approve", "s.art"),
        edge("g.revise", "w.guidance", bound=1),
    ],
)
T2 = validate(G2, REG, roles=roles()).topology
assert T2 is not None
ROUTER2 = GraphRouter(T2)


def _bystander_states():
    def emit(state, aid, port):
        return ROUTER2.advance(
            state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")
        ).state

    s = emit(ROUTER2.start().state, "start#1", "ok")
    s = emit(s, "w#1", "out")  # g#1 and y#1 live
    rejected = emit(s, "g#1", "reject")
    s = emit(emit(s, "g#1", "revise"), "w#2", "out")
    escalated = emit(s, "g#2", "revise")
    return rejected, escalated


def test_bystanders_cancel_under_rejection_and_escalation():
    rejected, escalated = _bystander_states()
    assert rejected.outcome == "rejected" and escalated.outcome == "escalated"
    assert node_status("y", _view(rejected), T2) == "cancelled"
    v = _view(escalated, escalated_by="g#2")
    assert node_status("y", v, T2) == "cancelled"
    assert node_status("g", v, T2) == "failed"


def test_failed_terminal_and_fail_port_render_failed():
    s = ROUTER.start().state
    s = _emit(s, "start#1", "ok").state
    s = _emit(s, "w#1", "fail").state  # terminal failed
    v = _view(s, unrouted_failure=UnroutedFailure(activation_id="w#1", error_type="X"))
    assert node_status("w", v, T) == "failed"


def test_an_interrupted_execution_cancels_live_nodes_and_hides_blocking():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert node_status("g", v, T, execution_closed=True) == "cancelled"


def test_node_cost_rules():
    s = _at_gate()
    v = _view(
        s,
        activations={
            "w#1": ActivationFacts(started_at=AT, cost_usd=1.25),
            "g#1": ActivationFacts(started_at=AT),
        },
    )
    assert node_cost("w", v, REG["work"]) == 1.25
    assert node_cost("g", v, REG["check"]) is None  # no role
    assert node_cost("s", v, REG["sink"]) is None  # never ran
    unpriced = _view(s, activations={"w#1": ActivationFacts(started_at=AT, priced=False)})
    assert node_cost("w", unpriced, REG["work"]) is None
    zero = _view(s, activations={"w#1": ActivationFacts(started_at=AT)})
    assert node_cost("w", zero, REG["work"]) == 0.0
    assert node_cost("w", zero, None) is None


@pytest.mark.parametrize(
    ("view", "closed", "close_status", "expected"),
    [
        (None, False, None, ("running", None, None)),
        (None, True, "failed", ("failed", "not_started:failed", None)),
        ("live", False, None, ("running", None, None)),
        ("live", True, "terminated", ("failed", "interrupted:terminated", None)),
        ("rejected", True, "completed", ("rejected", "g.reject", "rejected:g")),
        ("retro", False, None, ("completed", None, None)),
        ("unrouted", True, "failed", ("failed", "w.fail: ApplicationError", None)),
        ("budget", True, "completed", ("rejected", "budget", "rejected:budget")),
    ],
)
def test_run_outcome_table(view, closed, close_status, expected):
    views = {
        None: None,
        "live": _view(_at_gate()),
        "rejected": _view(_emit(_at_gate(), "g#1", "reject").state, result="rejected:g"),
        "retro": _view(_emit(_emit(_at_gate(), "g#1", "approve").state, "s#1", "done").state),
        "unrouted": _view(
            _emit(_emit(ROUTER.start().state, "start#1", "ok").state, "w#1", "fail").state,
            unrouted_failure=UnroutedFailure(activation_id="w#1", error_type="ApplicationError"),
        ),
        "budget": _view(
            ROUTER.advance(_at_gate(), Halt(outcome="rejected", reason="budget")).state,
            result="rejected:budget",
        ),
    }
    out = run_outcome(views[view], execution_closed=closed, close_status=close_status)
    assert (out.state, out.reason, out.result) == expected


def test_stage_marks_precedence_and_skipped():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert stage_marks(v, T, G, REG) == {
        "architecture": "blocked",  # w done + g blocked
        "context": "skipped",  # only x, dead
        "deploy": "pending",
        "intake": "done",
    }


def test_stage_marks_cancelled_is_failed_and_stale_is_pending():
    rejected = _view(_emit(_at_gate(), "g#1", "reject").state)
    assert stage_marks(rejected, T, G, REG)["architecture"] == "done"
    revising = _view(_emit(_at_gate(), "g#1", "revise").state)
    assert stage_marks(revising, T, G, REG)["architecture"] == "active"  # w#2 running, g stale
    interrupted = stage_marks(_view(_at_gate()), T, G, REG, execution_closed=True)
    assert interrupted["architecture"] == "failed"
    halted = _view(ROUTER.advance(_at_gate(), Halt(outcome="rejected", reason="budget")).state)
    assert node_status("g", halted, T) == "cancelled"
    assert stage_marks(halted, T, G, REG)["architecture"] == "failed"  # F11


def test_nodes_without_a_canonical_stage_contribute_nothing():
    bare = registry(*(spec.model_copy(update={"canonical_stage": None}) for spec in REG.values()))
    assert stage_marks(_view(_at_gate()), T, G, bare) == {}


@pytest.mark.parametrize("which", ["rejected", "escalated"])
def test_close_marks_equivalence_with_a_cancelled_bystander(which):
    rejected, escalated = _bystander_states()
    v = _view({"rejected": rejected, "escalated": escalated}[which], escalated_by="g#2")
    assert close_marks(stage_marks(v, T2, G2, REG)) == stage_marks(
        v, T2, G2, REG, execution_closed=True
    )


@pytest.mark.parametrize("which", ["gate", "revise", "reject", "start"])
def test_close_marks_equals_recomputing_with_execution_closed(which):
    states = {
        "gate": _at_gate(),
        "revise": _emit(_at_gate(), "g#1", "revise").state,
        "reject": _emit(_at_gate(), "g#1", "reject").state,
        "start": ROUTER.start().state,
    }
    v = _view(states[which], pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert close_marks(stage_marks(v, T, G, REG)) == stage_marks(
        v, T, G, REG, execution_closed=True
    )


# --- E-77 T026 (RED): unmapped/unregistered nodes land on 'unknown' (FR-005) --

# Like REG, but 'side' is registered with canonical_stage=None (unmapped) and
# 'sink' is absent from the registry entirely (unregistered).
MIXED = registry(
    REG["start"],
    REG["work"],
    REG["check"],
    REG["side"].model_copy(update={"canonical_stage": None}),
)


def test_unregistered_and_unmapped_nodes_contribute_under_unknown():
    from sdlc.graph import UNKNOWN_STAGE

    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    marks = stage_marks(v, T, G, MIXED)
    assert marks == {
        "architecture": "blocked",  # w done + g blocked: the usual merge
        "intake": "done",
        # x (side, unmapped) is dead -> skipped dot; s (sink, unregistered) is
        # idle -> pending dot; same precedence rule drops the skipped one.
        UNKNOWN_STAGE: "pending",
    }


def test_unmapped_nodes_never_change_canonical_stage_marks():
    from sdlc.graph import UNKNOWN_STAGE

    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    base = stage_marks(v, T, G, REG)
    mixed = stage_marks(v, T, G, MIXED)
    assert {k: mixed[k] for k in ("intake", "architecture")} == {
        "intake": base["intake"],
        "architecture": base["architecture"],
    }
    assert mixed[UNKNOWN_STAGE] == "pending"  # their only footprint is 'unknown'


def test_default_graph_marks_are_pinned_literal():
    """Computed on the pre-T027 code (== main: every shipped type is mapped,
    so the resolve_stage change moves nothing) at the start state. Any later
    change to the default graph's stage set or marks trips this literal."""
    from sdlc.agents.roles import REGISTRY as AGENT_ROLES
    from sdlc.graph.node_types import NODE_TYPES
    from sdlc.workflows.graph_catalog import build_run_input
    from sdlc.workflows.graph_nodes import HANDLERS
    from tests.fakes.canned import e2e_config, greenfield_idea

    run_input = build_run_input(
        greenfield_idea(), e2e_config(), None, registry_roles=AGENT_ROLES, handler_types=HANDLERS
    )
    report = validate(run_input.graph, NODE_TYPES, roles=run_input.roles)
    assert report.topology is not None, report.problems
    router = GraphRouter(report.topology)
    marks = stage_marks(_view(router.start().state), report.topology, run_input.graph, NODE_TYPES)
    assert marks == {
        "analyze": "pending",
        "architecture": "pending",
        "clarify": "pending",
        "code": "pending",
        "context": "pending",
        "deploy": "pending",
        "intake": "active",
        "planning": "pending",
        "quality_gate": "pending",
    }
