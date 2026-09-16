"""Chaos + edge-case characterization for E-74 Task 7 (terminal ports, D6).

RED until ``src/sdlc/graph`` grows the terminal contract: pre-landing,
``NodePort(terminal=...)`` raises ValidationError (extra_forbidden), so the
router tests below ERROR at registry construction and the model tests fail
on their own assertions.

Pins the edge behaviour the plan specifies:
- NodePort.terminal accepts exactly "rejected"/"failed"/None on out-ports;
  any other literal is a ValidationError; an in-port can never be terminal
- an edgeless terminal emission ends the run with that outcome, cancelling
  every other live worker (state.live empties; the emitter itself finished,
  only the cancelled workers retire)
- a "rejected"-kind terminal on a plain (non-gate) stage port ends the run
  too -- the gate-reject special case becomes data
- emissions arriving after a terminal are dropped with reason="post_terminal"
  and never applied
- a terminal port WITH edges routes like any port (no termination), while
  the same port emitted edgeless later still ends the run
- Topology.terminal_ports lists only terminal ports per node, maps nodes
  without them to {}, and unknown lookups via get() yield {}
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sdlc.graph.model import NodePort
from tests.graph.fixtures.registries import edge, graph, node, port_in, port_out, registry, stage
from tests.graph.fixtures.routing import Run


def term_out(name: str, payload: str | None, terminal: str) -> NodePort:
    """A terminal out-port built locally: the shared fixture helper must not
    grow `terminal=` until Task 7 lands it (fixtures stay untouched here)."""
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)


def term3():
    """One 'work3' type carrying both terminal kinds: fail -> "failed",
    stop -> "rejected" -- plus the routed-failure handler and a sink."""
    return registry(
        stage("start", port_out("ok", None)),
        stage(
            "work3",
            port_in("trigger", None),
            port_out("out", "P"),
            term_out("fail", "F", "failed"),
            term_out("stop", None, "rejected"),
        ),
        stage("handler", port_in("failure", "F"), port_out("done", None)),
        stage("sink", port_in("art", "P"), port_out("done", None)),
    )


def _three_workers(*extra_edges):
    """start fans out to THREE concurrent workers; a.out feeds the sink.
    Extra edges pull in the failure handler."""
    nodes = [
        node("start", "start"),
        node("a", "work3"),
        node("b", "work3"),
        node("c", "work3"),
        node("s", "sink"),
    ]
    edges = [
        edge("start.ok", "a.trigger"),
        edge("start.ok", "b.trigger"),
        edge("start.ok", "c.trigger"),
        edge("a.out", "s.art"),
        *extra_edges,
    ]
    if extra_edges:
        nodes.append(node("h", "handler"))
    return graph(nodes, edges)


# ---- NodePort.terminal validation (model layer) ----------------------------


def test_terminal_literal_accepts_rejected_failed_and_defaults_none():
    rejected = NodePort(name="reject", direction="out", payload=None, terminal="rejected")
    failed = NodePort(name="fail", direction="out", payload="F", terminal="failed")
    plain = NodePort(name="ok", direction="out", payload=None)

    assert rejected.terminal == "rejected"
    assert failed.terminal == "failed"
    assert plain.terminal is None


def test_terminal_rejects_invalid_literal():
    # match the Literal error itself: pre-landing the field does not exist
    # and pydantic says extra_forbidden, which must NOT satisfy this test
    with pytest.raises(ValidationError, match="Input should be 'rejected' or 'failed'"):
        NodePort(name="oops", direction="out", payload="F", terminal="invalid")


def test_in_port_cannot_be_terminal():
    with pytest.raises(ValidationError, match="cannot be terminal"):
        NodePort(name="x", direction="in", payload=None, terminal="rejected")


# ---- unrouted terminal emissions end the run -------------------------------


def test_unrouted_failed_terminal_ends_run_and_cancels_other_live():
    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    assert run.live() == ["a#1", "b#1", "c#1"]

    step = run.emit("a#1", "fail")

    assert (step.outcome, step.reason) == ("failed", "a.fail")
    assert step.cancelled == ("b#1", "c#1")
    assert step.activations == ()
    assert step.state.live == ()
    # the emitter finished cleanly; only the cancelled workers retire
    assert set(step.state.retired) == {"b#1", "c#1"}
    # applied emissions: the emitter's, plus start#1's kickoff -- the state
    # stores them sorted by activation id
    assert [(e.activation_id, e.port) for e in step.state.emissions] == [
        ("a#1", "fail"),
        ("start#1", "ok"),
    ]


def test_unrouted_rejected_terminal_from_plain_stage_ends_run_rejected():
    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")

    # middle worker, non-gate node, port not named "reject": the E-73
    # special case did not fire here -- terminal="rejected" data does.
    step = run.emit("b#1", "stop")

    assert (step.outcome, step.reason) == ("rejected", "b.stop")
    assert step.cancelled == ("a#1", "c#1")
    assert step.state.live == ()


# ---- post-terminal drops ----------------------------------------------------


def test_emissions_after_terminal_are_all_dropped_post_terminal():
    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    run.emit("a#1", "fail")

    b_step = run.emit("b#1", "out")
    c_step = run.emit("c#1", "out")

    assert (b_step.outcome, c_step.outcome) == ("failed", "failed")
    assert [(d.activation_id, d.port, d.reason) for d in c_step.state.dropped] == [
        ("b#1", "out", "post_terminal"),
        ("c#1", "out", "post_terminal"),
    ]
    # dropped emissions never apply: only start#1's kickoff and a#1's
    # terminal emission were applied (stored sorted by activation id)
    assert [(e.activation_id, e.port) for e in c_step.state.emissions] == [
        ("a#1", "fail"),
        ("start#1", "ok"),
    ]


# ---- routed terminal ports behave like any port -----------------------------


def test_routed_failed_terminal_routes_without_terminating():
    run = Run(_three_workers(edge("a.fail", "h.failure")), term3())
    run.emit("start#1", "ok")

    step = run.emit("a#1", "fail", "boom-ref")

    assert step.outcome == "running"
    assert step.cancelled == ()
    assert run.activation("h#1").inputs == {"failure": "boom-ref"}
    assert run.live() == ["b#1", "c#1", "h#1"]


def test_terminal_port_edges_do_not_disable_later_unrouted_termination():
    run = Run(_three_workers(edge("a.fail", "h.failure")), term3())
    run.emit("start#1", "ok")
    run.emit("a#1", "fail", "boom-ref")
    assert run.live() == ["b#1", "c#1", "h#1"]

    step = run.emit("b#1", "stop")

    assert (step.outcome, step.reason) == ("rejected", "b.stop")
    assert step.cancelled == ("c#1", "h#1")
    assert step.state.live == ()


# ---- Topology.terminal_ports edges ------------------------------------------


def test_topology_terminal_ports_shape_and_unknown_node():
    run = Run(_three_workers(), term3())
    topology = run.router.topology

    # only terminal ports are listed, both kinds on one node
    assert dict(topology.terminal_ports["a"]) == {"fail": "failed", "stop": "rejected"}
    # nodes without terminal ports are PRESENT, mapped to an empty dict
    assert topology.terminal_ports["start"] == {}
    assert topology.terminal_ports["s"] == {}
    assert set(topology.terminal_ports) == {"start", "a", "b", "c", "s"}
    # unknown node lookups yield {}
    assert topology.terminal_ports.get("nope", {}) == {}


# ---- the Halt event (E-74 Task 8, D7) ---------------------------------------
#
# Halt is imported inside each test: before Task 8 lands sdlc.graph does not
# export it, and a per-test ImportError keeps the Task 7 rows above green
# instead of collapsing the whole file into one collection error.


def test_halt_schema_default_kind_and_valid_outcomes():
    from sdlc.graph import Halt

    halt = Halt(outcome="failed", reason="x")
    assert halt.kind == "halt"
    assert halt.outcome == "failed"
    assert halt.reason == "x"
    # reason is an unconstrained str: the empty string is a valid post-mortem
    assert Halt(outcome="rejected", reason="").reason == ""


@pytest.mark.parametrize("outcome", ["running", "completed"])
def test_halt_rejects_non_terminal_outcomes(outcome):
    from sdlc.graph import Halt

    with pytest.raises(ValidationError, match="Input should be 'rejected' or 'failed'"):
        Halt(outcome=outcome, reason="x")


def test_halt_rejects_extra_fields():
    from sdlc.graph import Halt

    with pytest.raises(ValidationError, match="extra_forbidden"):
        Halt(outcome="failed", reason="x", bolt_on=True)


def test_advance_rejects_unsupported_events_but_takes_halt():
    from sdlc.graph import Halt, RouterError

    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")

    with pytest.raises(RouterError, match="unsupported event str"):
        run.router.advance(run.state, "bad")
    # a Halt-lookalike that is not a Halt must not slip through the union
    lookalike = SimpleNamespace(kind="halt", outcome="failed", reason="x")
    with pytest.raises(RouterError, match="unsupported event SimpleNamespace"):
        run.router.advance(run.state, lookalike)
    # the real event is accepted on the untouched running state
    step = run.router.advance(run.state, Halt(outcome="rejected", reason="dispatch stop"))
    assert (step.outcome, step.reason) == ("rejected", "dispatch stop")


@pytest.mark.parametrize("outcome", ["rejected", "failed"])
def test_halt_terminates_running_state_and_cancels_every_live(outcome):
    from sdlc.graph import Halt

    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")

    step = run.router.advance(run.state, Halt(outcome=outcome, reason="budget exhausted"))

    assert (step.outcome, step.reason) == (outcome, "budget exhausted")
    assert step.cancelled == ("a#1", "b#1", "c#1")
    assert step.state.retired == ("a#1", "b#1", "c#1")
    assert step.activations == ()
    assert step.state.live == ()
    # a halt is not an emission: the applied record is untouched
    assert [(e.activation_id, e.port) for e in step.state.emissions] == [("start#1", "ok")]


def _completed_run():
    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    run.emit("a#1", "out")  # fills s.art, issues s#1
    run.emit("s#1", "done")
    run.emit("b#1", "out")  # edgeless sink
    run.emit("c#1", "out")
    return run


def _escalated_run():
    # validate() rejects a one port fanned in from two sources, so the
    # illegal state is fabricated directly: inject a token into the slot,
    # then let a real emission collide with it (occupied-slot invariant).
    from sdlc.graph.router import Emitted, Token

    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    illegal = run.state.model_copy(
        update={"slots": {"a.out->s.art": Token(payload_ref="ghost", producer="a#1")}}
    )
    step = run.router.advance(illegal, Emitted(activation_id="a#1", port="out", payload_ref="x"))
    assert step.outcome == "escalated"
    return SimpleNamespace(router=run.router, state=step.state)


def test_halt_after_a_completed_state_is_an_interpreter_bug():
    from sdlc.graph import Halt, RouterError

    run = _completed_run()
    assert run.state.outcome == "completed"

    with pytest.raises(RouterError, match="halt after terminal outcome 'completed'"):
        run.router.advance(run.state, Halt(outcome="failed", reason="late stop"))


def test_halt_after_an_escalated_state_is_an_interpreter_bug():
    from sdlc.graph import Halt, RouterError

    run = _escalated_run()

    with pytest.raises(RouterError, match="halt after terminal outcome 'escalated'"):
        run.router.advance(run.state, Halt(outcome="rejected", reason="late stop"))


def test_halt_on_an_already_halted_state_is_an_interpreter_bug():
    from sdlc.graph import Halt, RouterError

    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    halted = run.router.advance(run.state, Halt(outcome="rejected", reason="first stop"))
    assert halted.outcome == "rejected"

    with pytest.raises(RouterError, match="halt after terminal outcome 'rejected'"):
        run.router.advance(halted.state, Halt(outcome="failed", reason="second stop"))


def test_emissions_after_a_halt_are_dropped_post_terminal():
    from sdlc.graph import Halt
    from sdlc.graph.router import Emitted

    run = Run(_three_workers(), term3())
    run.emit("start#1", "ok")
    halted = run.router.advance(run.state, Halt(outcome="failed", reason="budget exhausted"))

    step = run.router.advance(
        halted.state, Emitted(activation_id="b#1", port="out", payload_ref="b#1:out")
    )

    assert step.outcome == "failed"
    assert [(d.activation_id, d.port, d.reason) for d in step.state.dropped] == [
        ("b#1", "out", "post_terminal")
    ]
    assert [(e.activation_id, e.port) for e in step.state.emissions] == [("start#1", "ok")]
