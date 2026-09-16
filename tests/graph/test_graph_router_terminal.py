"""E-74 §4.4 / D6: a terminal port with no edges ends the run; with edges it routes."""

from __future__ import annotations

from tests.graph.fixtures.registries import edge, graph, node, port_in, port_out, registry, stage
from tests.graph.fixtures.routing import Run

TERM = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "F", terminal="failed"),
    ),
    stage("handler", port_in("failure", "F"), port_out("done", None)),
    stage("sink", port_in("art", "P"), port_out("done", None)),
)


def _two_workers(*extra_edges):
    return graph(
        [
            node("start", "start"),
            node("a", "work"),
            node("b", "work"),
            node("s", "sink"),
            *([node("h", "handler")] if extra_edges else []),
        ],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "s.art"),
            *extra_edges,
        ],
    )


def test_unrouted_failed_terminal_ends_the_run_and_cancels_live():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    assert run.live() == ["a#1", "b#1"]
    step = run.emit("a#1", "fail")
    assert (step.outcome, step.reason) == ("failed", "a.fail")
    assert step.cancelled == ("b#1",)
    assert run.state.live == ()


def test_routed_failed_terminal_routes_like_any_port():
    run = Run(_two_workers(edge("a.fail", "h.failure")), TERM)
    run.emit("start#1", "ok")
    step = run.emit("a#1", "fail", "boom-ref")
    assert step.outcome == "running"
    assert run.activation("h#1").inputs == {"failure": "boom-ref"}


def test_emission_after_failed_is_dropped_post_terminal():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    run.emit("a#1", "fail")
    step = run.emit("b#1", "out")
    assert step.outcome == "failed"
    assert [(d.activation_id, d.reason) for d in step.state.dropped] == [("b#1", "post_terminal")]


def test_topology_lists_only_terminal_ports():
    run = Run(_two_workers(), TERM)
    t = run.router.topology
    assert dict(t.terminal_ports["a"]) == {"fail": "failed"}
    assert dict(t.terminal_ports["start"]) == {}
