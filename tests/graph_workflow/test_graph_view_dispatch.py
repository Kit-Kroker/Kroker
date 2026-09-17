# tests/graph_workflow/test_graph_view_dispatch.py
"""E-75 spec §4.2: the dispatcher's per-activation facts and view()."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import ACTIVATION, GraphRouter, GraphRunView, validate
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
