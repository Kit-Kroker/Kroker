"""E-73 GraphRouter forward semantics (spec §6.1-§6.4, §6.6): branching,
static fan-out/collect, exclusive merge, readiness, sinks, REJECTED and the
activation-check taxonomy. Loops live in test_graph_router_loops.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.node_types import NODE_TYPES
from sdlc.graph.router import (
    Emitted,
    GraphRouter,
    NodeState,
    RouterError,
    RouterState,
    Token,
)
from tests.graph.fixtures.registries import GENERIC, edge, graph, node
from tests.graph.fixtures.routing import Run

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _chain() -> Run:
    return Run(
        graph(
            [node("start", "start"), node("w", "work"), node("s", "sink")],
            [edge("start.ok", "w.trigger"), edge("w.out", "s.art")],
        ),
        GENERIC,
    )


# ---- (1) happy paths -----------------------------------------------------------


def test_start_issues_the_entry_at_round_one():
    run = _chain()
    step = run.last
    assert [a.activation_id for a in step.activations] == ["start#1"]
    assert step.activations[0].round == 1
    assert step.activations[0].inputs == {}
    assert step.outcome == "running"


def test_chain_runs_to_completed_and_passes_payload_refs():
    run = _chain()
    run.emit("start#1", "ok", "r0")
    assert run.activation("w#1").inputs == {"trigger": "r0"}
    run.emit("w#1", "out", "art1")
    assert run.activation("s#1").inputs == {"art": "art1"}
    step = run.emit("s#1", "done")  # edgeless out-port: a sink
    assert step.activations == ()
    assert step.outcome == "completed"
    assert run.issued() == ["start#1", "w#1", "s#1"]


def test_e72_fixture_happy_path():
    from tests.graph.fixtures.registries import roles

    run = Run(from_yaml(FIXTURE.read_text(encoding="utf-8")), NODE_TYPES, roles())
    run.emit("intake#1", "ok")
    run.emit("researcher#1", "brief")
    assert run.live() == ["research#1"]
    assert run.activation("research#1").unavailable_ports == {}
    run.emit("research#1", "approve")
    run.emit("clarifier#1", "requirements", "reqs")
    assert run.activation("architect#1").inputs == {"requirements": "reqs"}
    run.emit("architect#1", "spec", "spec1")
    run.emit("architecture#1", "approve", "spec1")
    assert run.activation("planner#1").inputs == {"requirements": "reqs", "spec": "spec1"}
    run.emit("planner#1", "plan")
    step = run.emit("plan#1", "approve")  # plan.approve is a sink in the fixture
    assert step.outcome == "completed"


def test_state_is_json_round_trippable():
    run = _chain()
    run.emit("start#1", "ok")
    state = run.state
    assert RouterState.model_validate_json(state.model_dump_json()) == state


# ---- branching: one out-port per activation --------------------------------------


def _branch() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("br", "brancher"),
                node("l", "sink"),
                node("r", "sink"),
                node("after", "opt2"),
            ],
            [
                edge("start.ok", "br.trigger"),
                edge("br.left", "l.art"),
                edge("br.right", "r.art"),
                edge("br.left", "after.a"),
                edge("br.right", "after.b"),
            ],
        ),
        GENERIC,
    )


def test_untaken_branch_dies_and_optional_ports_do_not_wait_for_dead_edges():
    run = _branch()
    run.emit("start#1", "ok")
    step = run.emit("br#1", "left", "L")
    assert [a.activation_id for a in step.activations] == ["after#1", "l#1"]
    assert run.state.nodes["r"].status == "dead"
    assert run.activation("after#1").inputs == {"a": "L"}  # port b is DEAD, not waited for


def test_optional_ports_wait_for_every_live_edge():
    """Spec §6.3: optional means 'may be absent', not 'don't wait'."""
    run = Run(
        graph(
            [node("start", "start"), node("a", "work"), node("b", "work"), node("j", "opt2")],
            [
                edge("start.ok", "a.trigger"),
                edge("start.ok", "b.trigger"),
                edge("a.out", "j.a"),
                edge("b.out", "j.b"),
            ],
        ),
        GENERIC,
    )
    step = run.emit("start#1", "ok")
    assert [a.activation_id for a in step.activations] == ["a#1", "b#1"]  # static fan-out
    assert run.emit("a#1", "out", "A").activations == ()
    step = run.emit("b#1", "out", "B")
    assert [a.activation_id for a in step.activations] == ["j#1"]
    assert run.activation("j#1").inputs == {"a": "A", "b": "B"}


def test_node_with_all_fed_ports_dead_is_dead_and_run_completes():
    run = _branch()
    run.emit("start#1", "ok")
    run.emit("br#1", "left")
    run.emit("l#1", "done")
    step = run.emit("after#1", "done")
    assert step.outcome == "completed"
    assert run.state.nodes["r"].status == "dead"


# ---- (7)/(11) static fan-out and many-collect -------------------------------------


def _collect() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("fast", "work"),
                node("slow", "work"),
                node("br", "brancher"),
                node("c", "collect"),
            ],
            [
                edge("start.ok", "fast.trigger"),
                edge("start.ok", "slow.trigger"),
                edge("start.ok", "br.trigger"),
                edge("fast.out", "c.items"),
                edge("slow.out", "c.items"),
                edge("br.left", "c.items"),
            ],
        ),
        GENERIC,
    )


def test_many_collector_waits_for_the_slow_branch():
    """Skeptic F2: FILLED on a many port needs EVERY forward in-edge resolved."""
    run = _collect()
    run.emit("start#1", "ok")
    assert run.emit("fast#1", "out", "F").activations == ()
    assert run.emit("br#1", "left", "L").activations == ()
    step = run.emit("slow#1", "out", "S")
    assert [a.activation_id for a in step.activations] == ["c#1"]


def test_many_inputs_are_ordered_by_edge_id_not_arrival():
    run = _collect()
    run.emit("start#1", "ok")
    run.emit("slow#1", "out", "S")
    run.emit("br#1", "left", "L")
    run.emit("fast#1", "out", "F")
    # br.left->c.items < fast.out->c.items < slow.out->c.items
    assert run.activation("c#1").inputs == {"items": ("L", "F", "S")}


def test_many_collector_skips_a_dead_branch():
    run = _collect()
    run.emit("start#1", "ok")
    run.emit("br#1", "right")  # br.left edge is dead
    run.emit("fast#1", "out", "F")
    run.emit("slow#1", "out", "S")
    assert run.activation("c#1").inputs == {"items": ("F", "S")}


def test_many_collector_with_every_edge_dead_is_dead():
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("c", "collect")],
            [edge("start.ok", "br.trigger"), edge("br.left", "c.items")],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    step = run.emit("br#1", "right")
    assert run.state.nodes["c"].status == "dead"
    assert step.outcome == "completed"


# ---- (17) exclusive merge into a one port (reviewer R1) ---------------------------


@pytest.mark.parametrize(("taken", "other"), [("left", "right"), ("right", "left")])
def test_exclusive_merge_into_a_one_port(taken, other):
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("m", "sink")],
            [edge("start.ok", "br.trigger"), edge("br.left", "m.art"), edge("br.right", "m.art")],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    step = run.emit("br#1", taken, "T")
    assert [a.activation_id for a in step.activations] == ["m#1"]
    assert run.activation("m#1").inputs == {"art": "T"}
    assert f"br.{taken}->m.art" in run.state.slots
    assert f"br.{other}->m.art" not in run.state.slots
    assert run.state.nodes["br"].taken_port == taken  # the sibling edge is dead via taken_port
    assert step.outcome == "running"
    assert run.emit("m#1", "done").outcome == "completed"  # no backstop fired


# ---- REJECTED: an emission on a gate's unconnected reject -------------------------


def _gated() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("w", "work"),
                node("x", "work"),
                node("g", "gate.art"),
                node("s", "sink"),
            ],
            [
                edge("start.ok", "w.trigger"),
                edge("start.ok", "x.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.approve", "s.art"),
            ],
        ),
        GENERIC,
    )


def test_gate_reject_unconnected_rejects_and_cancels_live_work():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("w#1", "out")
    step = run.emit("g#1", "reject")
    assert step.outcome == "rejected"
    assert step.reason == "g.reject"
    assert step.cancelled == ("x#1",)
    assert run.state.retired == ("x#1",)
    assert run.state.live == ()
    assert run.state.nodes["g"].status == "done"  # the rejecting emission was applied


def test_unconnected_non_reject_port_is_a_sink():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("x#1", "out")  # x.out has no edges
    assert run.last.outcome == "running"


# ---- (9)/(12) the activation-check taxonomy (skeptic F3, F9) ----------------------


def test_never_issued_ids_raise():
    run = _chain()
    for bad in ["w#1", "start#2", "start#0", "start", "ghost#1", "start#x"]:
        with pytest.raises(RouterError, match="never issued"):
            run.emit(bad, "ok")


def test_port_not_on_the_type_raises():
    run = _chain()
    with pytest.raises(RouterError, match="not an out-port"):
        run.emit("start#1", "nope")


def test_identical_duplicate_is_dropped():
    run = _chain()
    run.emit("start#1", "ok", "r0")
    step = run.emit("start#1", "ok", "r0")
    assert step.activations == ()
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("start#1", "duplicate")]
    assert run.live() == ["w#1"]


def test_conflicting_second_emission_raises():
    run = _branch()
    run.emit("start#1", "ok")
    run.emit("br#1", "left", "L")
    with pytest.raises(RouterError, match="conflicting"):
        run.emit("br#1", "right", "L")
    with pytest.raises(RouterError, match="conflicting"):
        run.emit("br#1", "left", "other-ref")


def test_late_emission_after_rejected_is_post_terminal():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("w#1", "out")
    run.emit("g#1", "reject")
    step = run.emit("x#1", "out")
    assert step.outcome == "rejected"
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("x#1", "post_terminal")]
    run.emit("g#1", "reject")
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [
        ("g#1", "duplicate"),  # dropped is sorted by activation id, not arrival
        ("x#1", "post_terminal"),
    ]


def test_unsupported_event_raises():
    run = _chain()
    with pytest.raises(RouterError, match="unsupported event"):
        run.router.advance(run.state, object())  # type: ignore[arg-type]


# ---- (9a)/(9b) router_invariant backstops on hand-built illegal states -------------


def test_backstop_delivery_into_an_occupied_slot():
    run = _chain()
    run.emit("start#1", "ok")
    illegal = run.state.model_copy(
        update={"slots": {"w.out->s.art": Token(payload_ref="ghost", producer="w#1")}}
    )
    step = run.router.advance(illegal, Emitted(activation_id="w#1", port="out", payload_ref="x"))
    assert step.outcome == "escalated"
    assert step.reason == "router_invariant: delivery into occupied slot w.out->s.art"


def test_backstop_two_tokens_on_a_one_port():
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("m", "sink"), node("x", "work")],
            [
                edge("start.ok", "br.trigger"),
                edge("start.ok", "x.trigger"),
                edge("br.left", "m.art"),
                edge("br.right", "m.art"),
            ],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    illegal = run.state.model_copy(
        update={
            "nodes": {
                **run.state.nodes,
                "br": NodeState(round=1, status="done", taken_port="left"),
            },
            "live": tuple(a for a in run.state.live if a.node_id != "br"),
            "slots": {
                "br.left->m.art": Token(payload_ref="L", producer="br#1"),
                "br.right->m.art": Token(payload_ref="R", producer="br#1"),
            },
        }
    )
    step = run.router.advance(illegal, Emitted(activation_id="x#1", port="out", payload_ref="x"))
    assert step.outcome == "escalated"
    assert step.reason == "router_invariant: m holds two tokens on a one port"
    assert step.activations == ()


def test_router_is_pure_same_input_same_step():
    run = _chain()
    event = Emitted(activation_id="start#1", port="ok", payload_ref="r")
    a = run.router.advance(run.state, event)
    b = GraphRouter(run.router.topology).advance(run.state, event)
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()
