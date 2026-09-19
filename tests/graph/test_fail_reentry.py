# tests/graph/test_fail_reentry.py
"""E-77 T029 (RED): the R-5 fail-edge re-entry indicator (FR-015..FR-018).

fail_reentry(activation, state, topology) belongs in sdlc.graph.run_view
(not implemented yet): None = the node has no inbound fail back edge,
1 = an input ref '<aid>.fail' arrived over the fail back edge, 0 otherwise.
The fixture registry is the shipped NODE_TYPES plus an injected 'fixer'
whose 'failure' in-port (payload NodeFailure) is the only legal fail-edge
target in any graph buildable today (G4: no shipped in-port accepts
NodeFailure). Imports of fail_reentry stay function-local so the ref-format
pin below keeps running green until the function lands.
"""

from __future__ import annotations

import inspect

from sdlc.graph import Emitted, GraphRouter, validate
from sdlc.graph.node_types import NODE_TYPES
from tests.graph.fixtures.registries import (
    edge,
    graph,
    node,
    port_in,
    port_out,
    registry,
    roles,
    stage,
)

# The injected fixer; 'failure' mirrors node_types._in("failure", "NodeFailure").
FIXER = stage(
    "fixer",
    port_in("trigger", None),
    port_in("failure", "NodeFailure", required=False),
    port_in("guidance", "GateDecision", required=False),
    port_out("fixed", "ImplementationPlan"),
)
REG = registry(*list(NODE_TYPES.values()), FIXER)

# intake.ok -> fixer; fixer.fixed fans out to code.plan and the plan gate.
# code.fail -> fixer.failure (bound 3) is the fail back edge;
# gate.revise -> fixer.guidance (bound 2) re-enters fixer over a NON-fail
# back edge. Both close real cycles (a bound edge must close a cycle).
G = graph(
    [
        node("intake", "intake"),
        node("fixer", "fixer"),
        node("code", "code"),
        node("gate", "gate.plan"),
    ],
    [
        edge("intake.ok", "fixer.trigger"),
        edge("fixer.fixed", "code.plan"),
        edge("fixer.fixed", "gate.artifact"),
        edge("code.fail", "fixer.failure", bound=3),
        edge("gate.revise", "fixer.guidance", bound=2),
    ],
)
REPORT = validate(G, REG, roles=roles())
assert REPORT.topology is not None, REPORT.problems
T = REPORT.topology
ROUTER = GraphRouter(T)


def _emit(state, aid: str, port: str):
    return ROUTER.advance(state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}"))


def _drive():
    """intake#1 ok issues fixer#1; fixer#1 fixed issues code#1 and gate#1."""
    ok = _emit(ROUTER.start().state, "intake#1", "ok")
    fixed = _emit(ok.state, "fixer#1", "fixed")
    return ok, fixed


def test_dispatch_ref_format_is_pinned():
    """R-5 ref uniqueness: the dispatcher mints ref = f"{aid}.{result.port}"
    (graph_dispatch.py). Pinned on the dispatcher's own source -- a future
    change to ref minting breaks loudly -- and the format is checked against
    the emissions recorded in real router state."""
    from sdlc.workflows import graph_dispatch

    assert 'ref = f"{aid}.{result.port}"' in inspect.getsource(graph_dispatch)
    _, fixed = _drive()
    step = _emit(fixed.state, "code#1", "fail")
    for e in step.state.emissions:
        assert e.payload_ref == f"{e.activation_id}.{e.port}"
    assert step.state.traversals["code.fail->fixer.failure"] == 1


def test_shipped_default_graph_has_no_fail_reentry_anywhere():
    """G4: no shipped in-port accepts NodeFailure, so no legal default-graph
    activation can carry a fail-edge input -- the axis is absent (None)."""
    from sdlc.agents.roles import REGISTRY as AGENT_ROLES
    from sdlc.graph.run_view import fail_reentry  # E-77: does not exist yet
    from sdlc.workflows.graph_catalog import build_run_input
    from sdlc.workflows.graph_nodes import HANDLERS
    from tests.fakes.canned import e2e_config, greenfield_idea

    run_input = build_run_input(
        greenfield_idea(), e2e_config(), None, registry_roles=AGENT_ROLES, handler_types=HANDLERS
    )
    report = validate(run_input.graph, NODE_TYPES, roles=run_input.roles)
    assert report.topology is not None, report.problems
    router = GraphRouter(report.topology)
    step = router.start()
    seen = list(step.activations)
    entry = seen[0]
    port = next(p for p, eids in sorted(report.topology.out_ports[entry.node_id].items()) if eids)
    step = router.advance(
        step.state,
        Emitted(
            activation_id=entry.activation_id,
            port=port,
            payload_ref=f"{entry.activation_id}.{port}",
        ),
    )
    seen += list(step.activations)
    assert seen
    for activation in seen:
        assert fail_reentry(activation, step.state, report.topology) is None


def test_first_activation_of_a_fail_edge_target_is_zero():
    from sdlc.graph.run_view import fail_reentry  # E-77: does not exist yet

    ok, _ = _drive()
    first = ok.activations[0]
    assert first.activation_id == "fixer#1"
    assert first.inputs == {"trigger": "intake#1.ok"}  # arrived forward, no fail ref
    assert fail_reentry(first, ok.state, T) == 0


def test_fail_edge_reentry_is_one():
    from sdlc.graph.run_view import fail_reentry  # E-77: does not exist yet

    _, fixed = _drive()
    step = _emit(fixed.state, "code#1", "fail")
    re = step.activations[0]
    assert re.activation_id == "fixer#2"
    assert re.inputs["failure"] == "code#1.fail"  # the fail back edge delivered
    assert fail_reentry(re, step.state, T) == 1


def test_non_fail_back_edge_reentry_is_zero():
    from sdlc.graph.run_view import fail_reentry  # E-77: does not exist yet

    _, fixed = _drive()
    step = _emit(fixed.state, "gate#1", "revise")
    re = step.activations[0]
    assert re.activation_id == "fixer#2"
    assert re.inputs["guidance"] == "gate#1.revise"
    assert "failure" not in re.inputs  # re-entered, but not over the fail edge
    assert fail_reentry(re, step.state, T) == 0
