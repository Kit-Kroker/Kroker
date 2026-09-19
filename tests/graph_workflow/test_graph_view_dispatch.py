# tests/graph_workflow/test_graph_view_dispatch.py
"""E-75 spec §4.2: the dispatcher's per-activation facts and view()."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import (
    ACTIVATION,
    NODE_TYPES,
    UNKNOWN_STAGE,
    GraphRouter,
    GraphRunView,
    from_yaml,
    resolve_stage,
    validate,
)
from sdlc.workflows.graph_dispatch import GraphDispatcher
from sdlc.workflows.graph_nodes.base import NodeResult, RunFacts
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

pytestmark = pytest.mark.temporal
TQ = "e75-view-dispatch"

REG = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "NodeFailure", terminal="failed"),
    ),
    stage("sink", port_in("art", "P"), port_out("done", None)),
    stage(
        "loop",
        port_in("trigger", None),
        port_in("guidance", "GD", required=False),
        port_out("out", "P"),
    ),
    stage("fixer", port_in("trigger", "P"), port_out("fix", "GD"), port_out("done", None)),
)


@workflow.defn(sandboxed=False)
class ViewProbe:
    def __init__(self) -> None:
        self.seen: list[str] = []
        self.released = False
        self.dispatcher: GraphDispatcher | None = None

    @workflow.signal
    def release(self) -> None:
        self.released = True

    @workflow.query
    def view_json(self) -> str | None:
        d = self.dispatcher
        return None if d is None else _view(d).model_dump_json()

    @workflow.query
    def attributions(self) -> list[str]:
        return list(self.seen)

    @workflow.run
    async def run(self, scenario: str) -> str:
        host = self

        async def start(nc, act, cfg):
            return NodeResult(port="ok")

        async def sink(nc, act, cfg):
            return NodeResult(port="done", result="done")

        async def work_wait(nc, act, cfg):
            async def sub() -> None:
                host.seen.append(f"{act.activation_id}:{ACTIVATION.get()}")

            await asyncio.gather(sub(), sub())
            await workflow.wait_condition(lambda: host.released)
            return NodeResult(port="out")

        async def boom(nc, act, cfg):
            raise ApplicationError("boom", type="X", non_retryable=True)

        async def loop_ok(nc, act, cfg):
            return NodeResult(port="out")

        async def always_fix(nc, act, cfg):
            return NodeResult(port="fix")

        table = {
            "parallel": (
                graph(
                    [
                        node("start", "start"),
                        node("a", "work"),
                        node("b", "work"),
                        node("sa", "sink"),
                        node("sb", "sink"),
                    ],
                    [
                        edge("start.ok", "a.trigger"),
                        edge("start.ok", "b.trigger"),
                        edge("a.out", "sa.art"),
                        edge("b.out", "sb.art"),
                    ],
                ),
                {"start": start, "work": work_wait, "sink": sink},
            ),
            "unrouted": (
                graph(
                    [node("start", "start"), node("w", "work"), node("s", "sink")],
                    [edge("start.ok", "w.trigger"), edge("w.out", "s.art")],
                ),
                {"start": start, "work": boom, "sink": sink},
            ),
            "escalation": (
                graph(
                    [node("start", "start"), node("v", "loop"), node("u", "fixer")],
                    [
                        edge("start.ok", "v.trigger"),
                        edge("v.out", "u.trigger"),
                        edge("u.fix", "v.guidance", bound=1),
                    ],
                ),
                {"start": start, "loop": loop_ok, "fixer": always_fix},
            ),
        }
        g, handlers = table[scenario]
        report = validate(g, REG, roles=roles())
        assert report.topology is not None, report.problems
        router = GraphRouter(report.topology)
        facts = RunFacts(
            idea=greenfield_idea(),
            repo_path="/r",
            run_id=workflow.info().workflow_id,
            seeded=None,
            memory_watermark=None,
        )
        self.dispatcher = GraphDispatcher(
            host=self,
            services=None,
            router=router,
            graph=g,
            registry=REG,
            handlers=handlers,
            facts=facts,
            cfg=PipelineConfig(),
        )
        await self.dispatcher.run()
        self.seen.append(f"run:{ACTIVATION.get()}")
        return _view(self.dispatcher).model_dump_json()


def _view(d: GraphDispatcher) -> GraphRunView:
    return d.view(graph_sha="sha", result=None, pending=(), spend={"a#1": (0.5, True)})


async def _run(scenario: str, drive=None):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TQ,
                workflows=[ViewProbe],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    ViewProbe.run, scenario, id=f"view-{uuid.uuid4()}", task_queue=TQ
                )
                if drive is not None:
                    await drive(handle)
                return GraphRunView.model_validate_json(await handle.result()), handle


async def _poll_view(handle, predicate) -> GraphRunView:
    for _ in range(600):
        raw = await handle.query("view_json")
        if raw is not None:
            view = GraphRunView.model_validate_json(raw)
            if predicate(view):
                return view
        await asyncio.sleep(0.05)
    raise AssertionError("view never satisfied the predicate")


@pytest.mark.asyncio
async def test_concurrent_activations_attribute_their_own_subtasks():
    observed: dict = {}

    async def drive(handle):
        observed["live"] = await _poll_view(handle, lambda v: {"a#1", "b#1"} <= set(v.activations))
        observed["seen"] = await handle.query("attributions")
        await handle.signal("release")
        # Plan deviation (executor, E-75 Task 4): the plan queried `attributions`
        # after `_run` returned, but `_run` exits the WorkflowEnvironment context
        # (server down) before returning the handle -- a deterministic
        # connection-refused. Query here instead, while the worker is up; the
        # workflow appends "run:None" only after dispatcher.run() returns.
        await handle.result()
        observed["after"] = await handle.query("attributions")

    final, handle = await _run("parallel", drive)
    live = observed["live"]
    assert live.activations["a#1"].ended_at is None and live.activations["b#1"].ended_at is None
    assert sorted(observed["seen"]) == ["a#1:a#1", "a#1:a#1", "b#1:b#1", "b#1:b#1"]
    assert "run:None" in observed["after"]
    for aid in ("start#1", "a#1", "b#1", "sa#1", "sb#1"):
        facts = final.activations[aid]
        assert facts.ended_at is not None and facts.ended_at >= facts.started_at
    assert final.activations["a#1"].cost_usd == 0.5  # spend joined by activation id
    assert final.state.outcome == "completed"


@pytest.mark.asyncio
async def test_unrouted_failure_is_recorded_without_its_message():
    final, _ = await _run("unrouted")
    assert final.unrouted_failure is not None
    assert final.unrouted_failure.model_dump() == {
        "activation_id": "w#1",
        "error_type": "ApplicationError",
    }
    assert final.state.outcome == "failed"
    assert "boom" not in final.model_dump_json()


@pytest.mark.asyncio
async def test_the_escalating_emission_is_recorded():
    final, _ = await _run("escalation")
    assert final.state.outcome == "escalated"
    assert final.escalated_by == "u#2"
    assert final.state.traversals == {"u.fix->v.guidance": 1}


# ---------------------------------------------------------------------------
# E-77 T013 (RED): dispatcher per-activation facts — GraphDispatcher._attrib
# (spec data-model "Dispatcher per-activation facts"; FR-014/FR-015 until T031).
# ---------------------------------------------------------------------------

SRC = Path(__file__).resolve().parents[2] / "src" / "sdlc"
DEFAULT_GRAPH_YAML = SRC / "workflows" / "graphs" / "default.graph.yaml"
TQ2 = "e77-attrib-dispatch"

# The ViewProbe "escalation" graph, rebuilt module-level so the assertions can
# read node types without reaching into a workflow instance.
_ESCALATION_GRAPH = graph(
    [node("start", "start"), node("v", "loop"), node("u", "fixer")],
    [
        edge("start.ok", "v.trigger"),
        edge("v.out", "u.trigger"),
        edge("u.fix", "v.guidance", bound=1),
    ],
)
_ESCALATION_TYPES = {"start": "start", "v": "loop", "u": "fixer"}

# Happy-path out-port per shipped type in default.graph.yaml. intake takes the
# brownfield edge so every one of the 12 nodes activates exactly once (the
# greenfield ok path never reaches context); both gates approve on sight.
_DEFAULT_PORTS = {
    "intake": "brownfield",
    "context": "map",
    "clarify": "requirements",
    "architect": "spec",
    "gate.architecture": "approve",
    "plan": "plan",
    "gate.plan": "approve",
    "plan_check": "ok",
    "code": "results",
    "analyze": "analysis",
    "merge": "pr",
    "deploy": "done",
}


# T031-test: the T029 fail-edge fixture (tests/graph/test_fail_reentry.py),
# rebuilt locally so the probe workflow never imports a test module. The
# fixer's 'failure' in-port (payload NodeFailure) is the only legal fail-edge
# target in any graph buildable today (G4).
_FAILER = stage(
    "fixer",
    port_in("trigger", None),
    port_in("failure", "NodeFailure", required=False),
    port_in("guidance", "GateDecision", required=False),
    port_out("fixed", "ImplementationPlan"),
)
_FAILLOOP_REG = registry(*list(NODE_TYPES.values()), _FAILER)
_FAILLOOP_GRAPH = graph(
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


def _attrib_rows(d: GraphDispatcher) -> list[dict]:
    """The dispatcher's per-activation facts, as primitives a workflow result
    can carry. Raises AttributeError until T014 lands `_attrib`."""
    return [
        {
            "aid": aid,
            "node_id": a.node_id,
            "round": a.round,
            "node_stage": a.node_stage,
            "fail_reentry": a.fail_reentry,
        }
        for aid, a in sorted(d._attrib.items())
    ]


@workflow.defn(sandboxed=False)
class AttribProbe:
    def __init__(self) -> None:
        self.dispatcher: GraphDispatcher | None = None

    async def _check_budget(self, cfg) -> None:  # probe never rejects (gates are exiting)
        return None

    @workflow.run
    async def run(self, scenario: str) -> str:
        if scenario == "failloop":
            g, reg = _FAILLOOP_GRAPH, _FAILLOOP_REG

            async def ok(nc, act, cfg):
                return NodeResult(port="ok")

            async def fixed(nc, act, cfg):
                return NodeResult(port="fixed")

            async def approve(nc, act, cfg):
                return NodeResult(port="approve")

            async def flaky_code(nc, act, cfg):
                if act.round <= 2:  # two successive fail-edge re-entries of the fixer
                    raise ApplicationError(f"code round {act.round} failed", non_retryable=True)
                return NodeResult(port="results")

            handlers = {"intake": ok, "fixer": fixed, "code": flaky_code, "gate.plan": approve}
        else:
            if scenario == "escalation":
                g, reg, port_by_type = (
                    _ESCALATION_GRAPH,
                    REG,
                    {"start": "ok", "loop": "out", "fixer": "fix"},
                )
            else:
                g = from_yaml(DEFAULT_GRAPH_YAML.read_text(encoding="utf-8"))
                reg, port_by_type = NODE_TYPES, _DEFAULT_PORTS

            async def emit(nc, act, cfg):
                port = port_by_type[nc.node.type]
                return NodeResult(port=port, result="completed" if port == "done" else None)

            handlers = {t: emit for t in port_by_type}

        report = validate(g, reg, roles=roles())
        assert report.topology is not None, report.problems
        facts = RunFacts(
            idea=greenfield_idea(),
            repo_path="/r",
            run_id=workflow.info().workflow_id,
            seeded=None,
            memory_watermark=None,
        )
        self.dispatcher = GraphDispatcher(
            host=self,
            services=None,
            router=GraphRouter(report.topology),
            graph=g,
            registry=reg,
            handlers=handlers,
            facts=facts,
            cfg=PipelineConfig(),
        )
        await self.dispatcher.run()
        return json.dumps(_attrib_rows(self.dispatcher))


async def _run_attrib(scenario: str) -> list[dict]:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TQ2,
                workflows=[AttribProbe],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    AttribProbe.run, scenario, id=f"attrib-{uuid.uuid4()}", task_queue=TQ2
                )
                return json.loads(await handle.result())


@pytest.mark.asyncio
async def test_attrib_rows_carry_node_round_and_resolved_stage_for_every_issued_activation():
    """FR-014: _attrib[aid] names the node, the router round of that
    activation (round 2 on back-edge re-entry), and resolve_stage of the
    node's type — 'unknown' for the unmapped fixture registry."""
    rows = await _run_attrib("escalation")
    assert [r["aid"] for r in rows] == ["start#1", "u#1", "u#2", "v#1", "v#2"]
    for r in rows:
        node_id, _, round_ = r["aid"].rpartition("#")
        assert r["node_id"] == node_id
        assert r["round"] == int(round_)  # equal to the Activation's round
        assert r["node_stage"] == resolve_stage(_ESCALATION_TYPES[node_id], REG)
    # re-entry over the u.fix -> v.guidance back edge mints round 2
    assert next(r for r in rows if r["aid"] == "v#2")["round"] == 2
    assert next(r for r in rows if r["aid"] == "u#2")["round"] == 2
    # every fixture type is unmapped (canonical_stage=None) -> unknown (FR-006)
    assert all(r["node_stage"] == UNKNOWN_STAGE for r in rows)


@pytest.mark.asyncio
async def test_default_graph_fail_reentry_is_none_for_every_activation():
    """G4 tradeoff: no shipped type accepts a failure payload, so the shipped
    default graph can wire no fail edge — the axis is absent (None), never 0,
    until T031 derives it for graphs that express a fix loop."""
    rows = await _run_attrib("default")
    types = {n.id: n.type for n in from_yaml(DEFAULT_GRAPH_YAML.read_text(encoding="utf-8")).nodes}
    assert {r["aid"] for r in rows} == {f"{n}#1" for n in types}  # all 12 nodes, once each
    for r in rows:
        assert r["fail_reentry"] is None
        assert r["round"] == 1
        assert r["node_stage"] == resolve_stage(types[r["node_id"]], NODE_TYPES)
        assert r["node_stage"] != UNKNOWN_STAGE  # every shipped type is mapped (SC-001)


def test_attrib_is_written_only_in_dispatcher_start():
    """Data-model ownership row: _attrib is filled in _start next to
    _started[...] and nowhere else — the same grep-style pin shape as the
    ACTIVATION set-site pin (tests/graph_workflow/test_store_import_pin.py)."""
    lines = (SRC / "workflows" / "graph_dispatch.py").read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("    def _start")), None)
    assert start is not None
    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if line.startswith("    def ")),
        len(lines),
    )
    hits = [i for i, line in enumerate(lines) if "_attrib[" in line]
    assert hits, "no _attrib write site exists yet (T014 fills it in _start)"
    offenders = [lines[i].strip() for i in hits if not start < i < end]
    assert offenders == []


@pytest.mark.asyncio
async def test_fail_edge_reentry_indicator_is_0_1_1_over_three_fixer_activations():
    """E-77 T031 (RED): the R-5 indicator captured at issue time — 0 on the
    first (forward) activation of a node with an inbound fail back edge, 1 on
    each re-entry over that edge. The fixer is re-entered twice over
    code.fail (code raises on rounds 1 and 2, the dispatcher converts each
    raise into a fail emission routed over the back edge, and succeeds on
    round 3); the gate approves on sight, so gate.revise stays unused."""
    rows = await _run_attrib("failloop")
    fixer = [r for r in rows if r["node_id"] == "fixer"]
    assert [r["aid"] for r in fixer] == ["fixer#1", "fixer#2", "fixer#3"]
    assert [r["round"] for r in fixer] == [1, 2, 3]  # T014, already correct
    assert [r["fail_reentry"] for r in fixer] == [0, 1, 1]  # RED: None until T031
    # every node WITHOUT an inbound fail back edge keeps the axis absent
    others = [r for r in rows if r["node_id"] != "fixer"]
    assert others and all(r["fail_reentry"] is None for r in others)
    # T031 changes only the indicator: the other _attrib fields stay correct
    for r in rows:
        assert r["node_id"] == r["aid"].rpartition("#")[0]
        assert r["round"] == int(r["aid"].rpartition("#")[2])
