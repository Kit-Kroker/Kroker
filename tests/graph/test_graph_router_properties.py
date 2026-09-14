"""E-73 router property tier (spec §6.7, §8, D4): EXHAUSTIVE exploration of
every reachable RouterState of small graphs -- stdlib only, no hypothesis.

From each state the explorer applies every out-port of every live activation
(unavailable ports included, so ESCALATED paths are explored too), with a
deterministic payload ref per (activation, port) so equal states converge.
After every transition it checks the invariants and theorems below.

Two statements are narrowed from the spec's wording (plan deviations 1-2):
- Invariant I is checked on FORWARD slots. A back-edge slot's producer is
  reset to pending by its own traversal (step 5b before 5c), so for back
  slots the checked property is I-back: the producer lies in REGION(target)
  and a port never holds two tokens.
- T2 compares states with live-activation snapshots projected out: a
  `target_dead` snapshot legitimately depends on arrival order (§6.5).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from pathlib import Path

import pytest

from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.graph.model import PipelineGraph
from sdlc.graph.router import (
    Emitted,
    GraphRouter,
    LiveActivation,
    RouterState,
    Step,
    _Work,
)
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import FIX_LOOP, GENERIC, fix_loop_graph, roles
from tests.graph.fixtures.routing import (
    collect_graph,
    disjoint_loops_graph,
    nested_loops_graph,
    running_target_graph,
    self_loop_graph,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"

GRAPHS: dict[str, Callable[[], tuple[PipelineGraph, object]]] = {
    "pre_code": lambda: (from_yaml(FIXTURE.read_text(encoding="utf-8")), NODE_TYPES),
    "fix_loop": lambda: (fix_loop_graph(2, 2), FIX_LOOP),
    "nested": lambda: (nested_loops_graph(), GENERIC),
    "disjoint": lambda: (disjoint_loops_graph(), GENERIC),
    "collect": lambda: (collect_graph(), GENERIC),
    "running_target": lambda: (running_target_graph(), GENERIC),
    "self_loop": lambda: (self_loop_graph(), GENERIC),
    "dead_target": lambda: (running_target_graph(dead_target_variant=True), GENERIC),
}
MAX_STATES = 5000


def _router(name: str) -> GraphRouter:
    g, registry = GRAPHS[name]()
    report = validate(g, registry, roles=roles())  # type: ignore[arg-type]
    assert report.topology is not None
    return GraphRouter(report.topology)


def _event(live: LiveActivation, port: str) -> Emitted:
    return Emitted(
        activation_id=live.activation_id, port=port, payload_ref=f"{live.activation_id}:{port}"
    )


def _check_invariant_i(router: GraphRouter, state: RouterState) -> None:
    t = router.topology
    for slot, token in state.slots.items():
        source, source_port, target, _ = t.edges[slot]
        producer_node, _, k = token.producer.rpartition("#")
        assert producer_node == source, slot
        if slot in t.bounds:  # I-back
            assert source in t.regions[target], slot
        else:  # Invariant I
            ns = state.nodes[source]
            assert ns.status == "done", slot
            assert ns.taken_port == source_port, slot
            assert ns.round == int(k), slot
    for node_id, ports in t.in_ports.items():
        for wiring in ports.values():
            if wiring.multiplicity == "one":
                occupied = [
                    e for e in (*wiring.forward_edges, *wiring.back_edges) if e in state.slots
                ]
                assert len(occupied) <= 1, (node_id, occupied)


def _check_transition(
    router: GraphRouter, before: RouterState, live: LiveActivation, port: str, step: Step
) -> None:
    t = router.topology
    assert not (step.reason or "").startswith("router_invariant"), step.reason
    # T5: never ESCALATED on a snapshot-available port.
    if step.outcome == "escalated" and before.outcome == "running":
        assert port in live.unavailable_ports, (live.activation_id, port, step.reason)
    # T1 (revised): a back token into a live target retires that activation.
    edges = t.out_ports[live.node_id][port]
    if port not in live.unavailable_ports and edges and edges[0] in t.bounds:
        target = t.edges[edges[0]][2]
        for other in before.live:
            if other.node_id == target and other.activation_id != live.activation_id:
                assert other.activation_id in step.cancelled
                assert other.activation_id in step.state.retired
    # A back traversal that was applied leaves the emitted token in its slot
    # (5b before 5c).
    if step.outcome == "running" and edges and edges[0] in t.bounds:
        token = step.state.slots.get(edges[0])
        assert token is not None and token.producer == live.activation_id, edges[0]
    # At issue: every forward in-edge of the node is resolved (FILLED or dead),
    # and the unavailable-ports snapshot matches the post-step state.
    work = _Work.of(step.state)
    for activation in step.activations:
        for wiring in t.in_ports[activation.node_id].values():
            for e in wiring.forward_edges:
                assert e in step.state.slots or router._edge_dead(work, e), (activation, e)
        assert activation.unavailable_ports == _expected_unavailable(t, step, activation)
    # Issued activations are exactly the new live ones, sorted by node id.
    new_live = {a.activation_id for a in step.state.live} - {a.activation_id for a in before.live}
    assert {a.activation_id for a in step.activations} == new_live
    assert [a.node_id for a in step.activations] == sorted(a.node_id for a in step.activations)


def _expected_unavailable(t, step: Step, activation) -> dict[str, str]:
    """Spec §6.5, recomputed independently of the router: a port carrying a
    back edge is `exhausted` at its bound, else `target_dead` if the target
    is dead in the state the activation was issued into."""
    expected: dict[str, str] = {}
    for port, eids in sorted(t.out_ports[activation.node_id].items()):
        if len(eids) == 1 and eids[0] in t.bounds:
            target = t.edges[eids[0]][2]
            if step.state.traversals.get(eids[0], 0) >= t.bounds[eids[0]]:
                expected[port] = "exhausted"
            elif step.state.nodes[target].status == "dead":
                expected[port] = "target_dead"
    return expected


def _check_redelivery(router: GraphRouter, state: RouterState) -> None:
    """Async races (skeptic F3): re-delivering a retired id or an applied
    emission is dropped -- never raised -- and changes nothing but `dropped`."""
    replays = [
        Emitted(
            activation_id=aid,
            port=sorted(router.topology.out_ports[aid.rpartition("#")[0]])[0],
            payload_ref="late",
        )
        for aid in state.retired
    ] + [
        Emitted(activation_id=e.activation_id, port=e.port, payload_ref=e.payload_ref)
        for e in state.emissions
    ]
    for event in replays:
        step = router.advance(state, event)
        assert step.activations == () and step.cancelled == ()
        assert step.state.model_copy(update={"dropped": state.dropped}) == state
        assert len(step.state.dropped) == len(state.dropped) + 1


def _ends_run(t, live: LiveActivation, port: str) -> bool:
    return port == "reject" and live.node_id in t.gate_nodes


def _explore(router: GraphRouter) -> dict[str, RouterState]:
    seen: dict[str, RouterState] = {}
    frontier = [router.start().state]
    while frontier:
        state = frontier.pop()
        key = state.model_dump_json()
        if key in seen:
            continue
        seen[key] = state
        assert len(seen) <= MAX_STATES, "state space larger than expected"
        _check_invariant_i(router, state)
        # T4 (quiescence): no live activation means a final outcome, and a
        # COMPLETED run leaves no node pending (nothing starved).
        if not state.live:
            assert state.outcome != "running"
        if state.outcome == "completed":
            assert all(ns.status in ("done", "dead") for ns in state.nodes.values())
        _check_redelivery(router, state)
        for live in state.live:
            for port in sorted(router.topology.out_ports[live.node_id]):
                step = router.advance(state, _event(live, port))
                _check_transition(router, state, live, port, step)
                frontier.append(step.state)
    return seen


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_exhaustive_exploration_terminates_and_holds_invariants(name):
    """T4: the reachable state space is finite (the explorer terminates) and
    every quiescent state is final; Invariant I / I-back, T1, T5 on every
    transition; router_invariant never fires on a legal graph."""
    states = _explore(_router(name))
    assert any(s.outcome != "running" for s in states.values())


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_forward_emissions_are_confluent(name):
    """T2: two live activations whose emissions touch no back edge and end
    nothing, applied in either order, reach equal states (modulo issue-time
    snapshots) and issue the same activation set."""
    router = _router(name)
    t = router.topology
    checked = 0
    for state in _explore(router).values():
        candidates = [
            (live, port)
            for live in state.live
            for port, edges in sorted(t.out_ports[live.node_id].items())
            if port not in live.unavailable_ports
            and (edges[0] not in t.bounds if edges else not _ends_run(t, live, port))
        ]
        for (l1, p1), (l2, p2) in itertools.combinations(candidates, 2):
            if l1.activation_id == l2.activation_id:
                continue
            e1, e2 = _event(l1, p1), _event(l2, p2)
            a = router.advance(state, e1)
            ab = router.advance(a.state, e2)
            b = router.advance(state, e2)
            ba = router.advance(b.state, e1)
            strip = {
                "live": tuple(x.model_copy(update={"unavailable_ports": {}}) for x in ab.state.live)
            }
            strip_ba = {
                "live": tuple(x.model_copy(update={"unavailable_ports": {}}) for x in ba.state.live)
            }
            assert ab.state.model_copy(update=strip) == ba.state.model_copy(update=strip_ba)
            issued_ab = {x.activation_id for x in (*a.activations, *ab.activations)}
            issued_ba = {x.activation_id for x in (*b.activations, *ba.activations)}
            assert issued_ab == issued_ba
            checked += 1
    if name in {"collect", "disjoint", "nested", "dead_target"}:
        assert checked > 0  # the property is exercised, not vacuous


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_same_script_same_bytes(name):
    """T3: determinism -- replaying one event script yields byte-identical
    state JSON at every step."""

    def replay() -> list[str]:
        router = _router(name)
        step = router.start()
        out = [step.state.model_dump_json()]
        for _ in range(40):
            if not step.state.live:
                break
            live = step.state.live[-1]
            port = sorted(router.topology.out_ports[live.node_id])[0]
            step = router.advance(step.state, _event(live, port))
            out.append(step.state.model_dump_json())
        return out

    assert replay() == replay()
