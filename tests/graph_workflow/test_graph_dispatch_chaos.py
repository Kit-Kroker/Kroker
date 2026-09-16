"""Chaos + edge-case characterization for E-74 Task 15 (GraphDispatcher).

RED until ``sdlc.workflows.graph_dispatch`` exists: every test imports the
dispatch names IN-FUNCTION, so the file still collects and each test fails
on its own with ``ModuleNotFoundError: No module named
'sdlc.workflows.graph_dispatch'`` -- the plan's own expected RED reason.
Everything else (router state models, base contract, role_host's
_BudgetRejected, fixtures) exists and imports at module level; tests/conftest
stubs the API keys those imports need.

Pins the edge behaviour the task specifies:
- outcome_string: for a rejected run budget_halted wins over BOTH the
  terminal result and the reason; the reason is split at the FIRST dot
  ("architecture.reject" -> "rejected:architecture", no dots -> the whole
  reason, empty/None -> "rejected:"); a terminal_result is returned verbatim.
  A failed run returns the terminal_result verbatim, else the FULL reason
  (no dot split) -- and a None reason renders "failed:None" (the plan has no
  `or ''` here, unlike the rejected branch: asymmetry pinned on purpose).
  Escalated prefixes the reason. RouterState's Literal makes truly unknown
  outcomes unconstructible; any other real outcome ("running") falls through
  to last_sink_result, else the sorted edgeless-sink list ("completed:a,b");
  a done node whose taken port HAS edges is not a sink, a node that is not
  done is not a sink either, and no sinks at all yields "completed:".
- FAILURE_TYPES: exactly FailureError, UserError, PydanticUserError,
  AgentRunError -- no more, no fewer.
- DispatchOutcome: a plain dataclass whose five fields are all required.
- _is_boundary truth table: budget_after 'none' never boundary; 'exiting'
  always boundary unless one of the emitted edges is bounded; 'continuing'
  boundary only with unbounded edges (an edgeless emission is no boundary).
- _classify: NodeResult passes through; a cancelled exception re-raises
  immediately (both temporalio's and asyncio's); _BudgetRejected halts the
  budget (Halt rejected/'budget' advanced into the state) and returns None;
  a FAILURE_TYPES error on a node WITH a fail out-port becomes a NodeResult
  carrying a NodeFailure (stored only when the fail port is UNROUTED);
  anything else -- including a FAILURE_TYPES error on a node WITHOUT a fail
  port -- re-raises the original object.
"""

from __future__ import annotations

import asyncio
from dataclasses import fields as dc_fields

import pytest
from pydantic import PydanticUserError
from pydantic_ai.exceptions import AgentRunError, UserError
from temporalio.exceptions import CancelledError as TemporalCancelledError
from temporalio.exceptions import FailureError

from sdlc.core.models import NodeFailure, PipelineConfig
from sdlc.graph import validate
from sdlc.graph.router import GraphRouter, NodeState, RouterState
from sdlc.workflows.graph_nodes.base import NodeResult, RunFacts
from sdlc.workflows.role_host import _BudgetRejected
from tests.fakes.canned import greenfield_idea
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


def _budgeted(kind: str, *ports):
    return stage(kind, *ports).model_copy(update={"budget_after": kind})


REG = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "NodeFailure", terminal="failed"),
    ),
    _budgeted("continuing", port_in("trigger", None), port_out("out", "P")),
    _budgeted("exiting", port_in("trigger", None), port_out("out", "P")),
    stage("handler", port_in("failure", "NodeFailure"), port_out("done", None)),
    stage("sink", port_in("art", "P"), port_out("done", None)),
    # the loop/fixer pair is the plan's back-edge shape: loop.out -> fixer.trigger,
    # fixer.fix -> loop.guidance with bound=1 -- a real cycle, an exclusive bounded
    # port, GD -> GD payloads (validate: BACK_PORT_NOT_EXCLUSIVE /
    # BOUNDED_EDGE_NOT_A_LOOP / INCOMPATIBLE_PORTS otherwise)
    _budgeted(
        "exiting",
        port_in("trigger", None),
        port_in("guidance", "GD", required=False),
        port_out("out", "P"),
    ),
    stage("fixer", port_in("trigger", "P"), port_out("fix", "GD")),
)

_PRE = [
    node("start", "start"),
    node("w", "work"),
    node("c", "continuing"),
    node("e", "exiting"),
    node("loop", "exiting"),
    node("fixer", "fixer"),
    node("sw", "sink"),
    node("sc", "sink"),
    node("se", "sink"),
]

G_UNROUTED = graph(
    _PRE,
    [
        edge("start.ok", "w.trigger"),
        edge("start.ok", "c.trigger"),
        edge("start.ok", "e.trigger"),
        edge("start.ok", "loop.trigger"),
        edge("w.out", "sw.art"),
        edge("c.out", "sc.art"),
        edge("e.out", "se.art"),
        edge("loop.out", "fixer.trigger"),
        edge("fixer.fix", "loop.guidance", bound=1),  # the one bounded edge
    ],
)

G_ROUTED = graph(
    [*_PRE, node("h", "handler")],
    [
        edge("start.ok", "w.trigger"),
        edge("start.ok", "c.trigger"),
        edge("start.ok", "e.trigger"),
        edge("start.ok", "loop.trigger"),
        edge("w.out", "sw.art"),
        edge("c.out", "sc.art"),
        edge("e.out", "se.art"),
        edge("loop.out", "fixer.trigger"),
        edge("fixer.fix", "loop.guidance", bound=1),
        edge("w.fail", "h.failure"),  # the routed failure path
    ],
)


def _facts():
    return RunFacts(
        idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=None, memory_watermark=None
    )


def _dispatcher(graph=G_UNROUTED):
    from sdlc.workflows.graph_dispatch import GraphDispatcher

    report = validate(graph, REG, roles=roles())
    assert report.topology is not None, report.problems
    dispatcher = GraphDispatcher(
        host=object(),
        services=None,
        router=GraphRouter(report.topology),
        graph=graph,
        registry=REG,
        handlers={},
        facts=_facts(),
        cfg=PipelineConfig(),
    )
    return dispatcher, report.topology


def _state(outcome="running", reason=None, nodes=None):
    return RouterState(nodes=nodes or {}, outcome=outcome, reason=reason)


def _o(state, *, terminal=None, sink=None, budget=False):
    from sdlc.workflows.graph_dispatch import DispatchOutcome

    return DispatchOutcome(
        state=state,
        terminal_result=terminal,
        last_sink_result=sink,
        budget_halted=budget,
        stored_failure=None,
    )


DONE = NodeState(round=1, status="done", taken_port="done")
WORKED = NodeState(round=1, status="done", taken_port="out")


# ---- outcome_string: the §5.6 wire contract ----------------------------------


@pytest.mark.parametrize(
    ("state", "terminal", "sink", "budget", "expected"),
    [
        # rejected: budget_halted beats BOTH the terminal result and the reason
        (_state("rejected", "architecture.reject"), "x", None, True, "rejected:budget"),
        (_state("rejected", None), None, None, True, "rejected:budget"),
        # rejected: a terminal result is verbatim, whatever it contains
        (
            _state("rejected", "merge.reject"),
            "rejected:intake (not a git repository)",
            None,
            False,
            "rejected:intake (not a git repository)",
        ),
        (
            _state("rejected", "merge.reject"),
            "rejected:merge:advisory",
            None,
            False,
            "rejected:merge:advisory",
        ),
        # rejected: the reason splits at the FIRST dot only
        (_state("rejected", "architecture.reject"), None, None, False, "rejected:architecture"),
        (_state("rejected", "a.b.c"), None, None, False, "rejected:a"),
        (_state("rejected", "halt"), None, None, False, "rejected:halt"),  # no dots: whole reason
        (_state("rejected", ""), None, None, False, "rejected:"),  # empty reason
        (_state("rejected", None), None, None, False, "rejected:"),  # None reason
        # failed: terminal verbatim, else the FULL reason (no dot split)
        (
            _state("failed", "plan_check.halt"),
            "failed:plan-validation:dependency cycle: a -> b -> a",
            None,
            False,
            "failed:plan-validation:dependency cycle: a -> b -> a",
        ),
        (_state("failed", "code.halt"), None, None, False, "failed:code.halt"),
        (_state("failed", None), None, None, False, "failed:None"),  # no `or ''` in this branch
        # escalated: reason verbatim after the prefix
        (
            _state("escalated", "architecture.revise: exhausted"),
            None,
            None,
            False,
            "escalated:architecture.revise: exhausted",
        ),
        # completed: a recorded sink result wins verbatim
        (
            _state("completed"),
            None,
            "deployed:https://example.test/pr/1",
            False,
            "deployed:https://example.test/pr/1",
        ),
        # completed: sorted edgeless sinks, comma-joined
        (
            _state("completed", nodes={"sc": DONE, "sw": DONE, "w": WORKED}),
            None,
            None,
            False,
            "completed:sc,sw",  # w's taken port has edges: not a sink
        ),
    ],
    ids=[
        "budget-beats-terminal",
        "budget-beats-reason",
        "terminal-verbatim-prose",
        "terminal-verbatim-colons",
        "reason-first-dot",
        "reason-multi-dot",
        "reason-no-dot",
        "reason-empty",
        "reason-none",
        "failed-terminal-verbatim",
        "failed-full-reason",
        "failed-none-reason",
        "escalated-verbatim",
        "sink-verbatim",
        "sinks-sorted",
    ],
)
def test_outcome_string_wire_table(state, terminal, sink, budget, expected):
    from sdlc.workflows.graph_dispatch import DispatchOutcome, outcome_string

    # built IN the test body: DispatchOutcome is a graph_dispatch name and the
    # parametrize table must evaluate at collection without importing it
    outcome = DispatchOutcome(
        state=state,
        terminal_result=terminal,
        last_sink_result=sink,
        budget_halted=budget,
        stored_failure=None,
    )

    _, topology = _dispatcher()
    assert outcome_string(outcome, topology) == expected


def test_outcome_string_excludes_untaken_untakenless_and_not_done_nodes():
    from sdlc.workflows.graph_dispatch import outcome_string

    _, topology = _dispatcher()
    nodes = {
        "sw": DONE,  # a real sink
        "sc": NodeState(round=1, status="done"),  # done but took nothing: not a sink
        "se": NodeState(round=1, status="pending", taken_port="done"),  # not done: not a sink
    }

    assert outcome_string(_o(_state("completed", nodes=nodes)), topology) == "completed:sw"


def test_outcome_string_with_no_qualifying_sinks_yields_the_empty_suffix():
    from sdlc.workflows.graph_dispatch import outcome_string

    _, topology = _dispatcher()

    assert outcome_string(_o(_state("completed", nodes={"w": WORKED})), topology) == "completed:"


def test_outcome_string_unknown_outcomes_are_unconstructible_and_running_falls_through():
    from pydantic import ValidationError

    from sdlc.workflows.graph_dispatch import outcome_string

    _, topology = _dispatcher()

    # a truly unknown outcome string cannot reach outcome_string: RouterState's
    # Literal rejects it at construction, so the fallthrough is only reachable
    # for real-but-non-terminal outcomes like "running"
    with pytest.raises(
        ValidationError,
        match="Input should be 'running', 'completed', 'rejected', 'escalated' or 'failed'",
    ):
        _state("banana")

    assert outcome_string(_o(_state("running"), sink="partial:x"), topology) == "partial:x"
    assert outcome_string(_o(_state("running", nodes={"w": WORKED})), topology) == "completed:"


# ---- FAILURE_TYPES pin --------------------------------------------------------


def test_failure_types_is_exactly_the_temporal_and_plugin_set():
    from sdlc.workflows.graph_dispatch import FAILURE_TYPES

    assert set(FAILURE_TYPES) == {FailureError, UserError, PydanticUserError, AgentRunError}
    assert len(FAILURE_TYPES) == 4  # no extras beyond the four
    assert all(isinstance(t, type) and issubclass(t, BaseException) for t in FAILURE_TYPES)


# ---- DispatchOutcome structure -------------------------------------------------


def test_dispatch_outcome_is_a_dataclass_with_five_required_fields():
    import dataclasses

    from sdlc.workflows.graph_dispatch import DispatchOutcome

    assert dataclasses.is_dataclass(DispatchOutcome)
    assert [f.name for f in dc_fields(DispatchOutcome)] == [
        "state",
        "terminal_result",
        "last_sink_result",
        "budget_halted",
        "stored_failure",
    ]
    with pytest.raises(TypeError):
        DispatchOutcome(state=_state())


def test_dispatch_outcome_instances_compare_by_value():
    from sdlc.workflows.graph_dispatch import DispatchOutcome

    state = _state("rejected", "a.b")
    boom = RuntimeError("boom")
    first = DispatchOutcome(
        state=state,
        terminal_result="t",
        last_sink_result="s",
        budget_halted=True,
        stored_failure=boom,
    )
    second = DispatchOutcome(
        state=state,
        terminal_result="t",
        last_sink_result="s",
        budget_halted=True,
        stored_failure=boom,
    )

    assert first == second
    assert (first.terminal_result, first.budget_halted, first.stored_failure) == ("t", True, boom)


# ---- _is_boundary truth table --------------------------------------------------


@pytest.mark.parametrize(
    ("node_id", "port", "selector", "expected"),
    [
        ("w", "out", "ports", False),  # budget 'none': never a boundary
        ("c", "out", "ports", True),  # 'continuing' with unbounded edges
        ("e", "out", "ports", True),  # 'exiting' with only unbounded edges
        ("loop", "out", "ports", True),  # 'exiting', its own out-edge is unbounded
        ("loop", "out", "with_bounded", False),  # a bounded edge anywhere suppresses it
        ("c", "out", "empty", False),  # 'continuing' edgeless: not a boundary
        ("e", "out", "empty", True),  # 'exiting' is a boundary even edgeless
        ("sw", "done", "empty", False),  # 'none' edgeless (a sink): not a boundary
    ],
    ids=[
        "none-with-edges",
        "continuing-with-edges",
        "exiting-unbounded",
        "exiting-own-unbounded",
        "bounded-edge-suppresses",
        "continuing-edgeless",
        "exiting-edgeless",
        "none-edgeless",
    ],
)
def test_is_boundary_truth_table(node_id, port, selector, expected):
    dispatcher, topology = _dispatcher()

    out_edges = list(topology.out_ports[node_id][port])
    plain = [eid for eid in out_edges if eid not in topology.bounds]
    edges = {
        "ports": out_edges,
        "with_bounded": plain + list(topology.bounds.keys()),
        "empty": [],
    }[selector]

    assert dispatcher._is_boundary(node_id, port, edges) is expected


# ---- _classify behaviour -------------------------------------------------------


def test_classify_passes_a_node_result_through_untouched():
    dispatcher, _ = _dispatcher()
    result = NodeResult(port="out")

    assert dispatcher._classify("w#1", "w", result) is result


@pytest.mark.parametrize(
    "cancelled",
    [TemporalCancelledError("stop"), asyncio.CancelledError()],
    ids=["temporalio", "asyncio"],
)
def test_classify_reraises_cancellation_immediately(cancelled):
    dispatcher, _ = _dispatcher()

    with pytest.raises(type(cancelled)):
        dispatcher._classify("w#1", "w", cancelled)


def test_classify_budget_rejection_halts_and_returns_none():
    dispatcher, _ = _dispatcher()

    result = dispatcher._classify("w#1", "w", _BudgetRejected())

    assert result is None
    assert dispatcher._budget_halted is True
    assert (dispatcher._state.outcome, dispatcher._state.reason) == ("rejected", "budget")


def test_classify_routes_a_failure_over_an_unrouted_fail_port_and_stores_it():
    dispatcher, _ = _dispatcher()
    boom = FailureError("boom")

    result = dispatcher._classify("w#1", "w", boom)

    assert isinstance(result, NodeResult)
    assert result.port == "fail"
    assert result.payload == NodeFailure(
        activation_id="w#1", error_type="FailureError", message="boom"
    )
    # the fail port has no edges: the original exception is stored for run()
    assert dispatcher._stored_failure is boom


def test_classify_a_routed_failure_is_not_stored():
    dispatcher, _ = _dispatcher(G_ROUTED)
    boom = FailureError("boom")

    result = dispatcher._classify("w#1", "w", boom)

    assert result is not None and result.port == "fail"
    assert dispatcher._stored_failure is None  # the topology handles it


def test_classify_reraises_an_interpreter_bug_despite_the_fail_port():
    dispatcher, _ = _dispatcher()
    crash = RuntimeError("interpreter bug")

    with pytest.raises(RuntimeError) as err:
        dispatcher._classify("w#1", "w", crash)

    assert err.value is crash


def test_classify_reraises_a_failure_on_a_node_without_a_fail_port():
    dispatcher, _ = _dispatcher()
    boom = FailureError("boom")

    with pytest.raises(FailureError) as err:
        dispatcher._classify("c#1", "c", boom)

    assert err.value is boom
