"""E-74 §5.4-§5.6: dispatch loop semantics on a probe workflow over test types."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError, CancelledError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import GraphRouter, validate
from sdlc.workflows.graph_dispatch import GraphDispatcher, outcome_string
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

pytestmark = pytest.mark.temporal
TQ = "e74-dispatch"

REG = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "NodeFailure", terminal="failed"),
    ),
    stage(
        "work.exiting",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "NodeFailure", terminal="failed"),
    ).model_copy(update={"budget_after": "exiting"}),
    stage("handler", port_in("failure", "NodeFailure"), port_out("done", None)),
    stage("sink", port_in("art", "P"), port_out("done", None)),
    # back-edge probe: v -> (u, x); u.fix -> v.guidance retires x while x is live
    stage(
        "loop",
        port_in("trigger", None),
        port_in("guidance", "GD", required=False),
        port_out("out", "P"),
    ),
    stage("fixer", port_in("trigger", "P"), port_out("fix", "GD"), port_out("done", None)),
    stage("waiter", port_in("trigger", "P"), port_out("done", None)),
)


@activity.defn
async def block_forever() -> None:
    while True:
        activity.heartbeat()
        await asyncio.sleep(0.1)


def _linear():
    return graph(
        [node("start", "start"), node("w", "work"), node("s", "sink")],
        [edge("start.ok", "w.trigger"), edge("w.out", "s.art")],
    )


def _parallel(first_type: str = "work"):
    return graph(
        [
            node("start", "start"),
            node("a", first_type),
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
    )


@workflow.defn(sandboxed=False)
class DispatchProbe:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.released: set[str] = set()
        self.reject_budget = False

    @workflow.signal
    def release(self, name: str) -> None:
        self.released.add(name)

    @workflow.signal
    def set_reject_budget(self) -> None:
        self.reject_budget = True

    @workflow.query
    def events(self) -> list[str]:
        return list(self.log)

    async def _check_budget(self, cfg: PipelineConfig) -> None:
        self.log.append("budget")
        if self.reject_budget:
            raise _BudgetRejected()

    @workflow.run
    async def run(self, scenario: str) -> str:
        host = self

        async def start(nc, act, cfg):
            return NodeResult(port="ok")

        async def sink(nc, act, cfg):
            host.log.append(f"{nc.node.id}-done")
            return NodeResult(port="done", result=f"done:{nc.node.id}")

        async def work_ok(nc, act, cfg):
            return NodeResult(port="out")

        async def wait_release(nc, act, cfg):
            try:
                await workflow.wait_condition(lambda: nc.node.id in host.released)
            except asyncio.CancelledError:
                host.log.append(f"{nc.node.id}-cancelled")
                raise
            host.log.append(f"{nc.node.id}-released")
            return NodeResult(port="out")

        async def boom(nc, act, cfg):
            raise ApplicationError("boom", type="X", non_retryable=True)

        async def crash(nc, act, cfg):
            raise RuntimeError("interpreter bug")

        async def result_on_edge(nc, act, cfg):
            return NodeResult(port="out", result="not-allowed")

        async def handled(nc, act, cfg):
            return NodeResult(port="done", result="handled")

        async def fix_once(nc, act, cfg):
            if act.round == 1:
                await workflow.wait_condition(lambda: "x-waiting" in host.log)
                return NodeResult(port="fix")
            return NodeResult(port="done", result="done:u")

        async def wait_first_round(nc, act, cfg):
            if act.round == 1:
                host.log.append("x-waiting")
                try:
                    await workflow.wait_condition(lambda: False)
                except asyncio.CancelledError:
                    host.log.append("x-cancelled")
                    raise
            host.log.append(f"x-round-{act.round}")
            return NodeResult(port="done", result="done:x")

        async def blocking(nc, act, cfg):
            host.log.append("blocking-started")
            await workflow.execute_activity(
                block_forever,
                start_to_close_timeout=timedelta(hours=1),
                heartbeat_timeout=timedelta(seconds=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            return NodeResult(port="out")

        async def exiting_with_finalize(nc, act, cfg):
            async def fin():
                host.log.append("finalize")

            await workflow.wait_condition(lambda: nc.node.id in host.released)
            return NodeResult(port="out", finalize=fin)

        table: dict[str, tuple[Any, dict[str, Any]]] = {
            "linear": (_linear(), {"start": start, "work": work_ok, "sink": sink}),
            "unrouted_failure": (_linear(), {"start": start, "work": boom, "sink": sink}),
            "routed_failure": (
                graph(
                    [
                        node("start", "start"),
                        node("w", "work"),
                        node("h", "handler"),
                        node("s", "sink"),
                    ],
                    [
                        edge("start.ok", "w.trigger"),
                        edge("w.fail", "h.failure"),
                        edge("w.out", "s.art"),
                    ],
                ),
                {"start": start, "work": boom, "handler": handled, "sink": sink},
            ),
            "crash": (_linear(), {"start": start, "work": crash, "sink": sink}),
            "result_on_edge": (_linear(), {"start": start, "work": result_on_edge, "sink": sink}),
            "budget_quiescence": (
                _parallel("work.exiting"),
                {"start": start, "work.exiting": work_ok, "work": wait_release, "sink": sink},
            ),
            "budget_halt": (
                _parallel("work.exiting"),
                {
                    "start": start,
                    "work.exiting": exiting_with_finalize,
                    "work": work_ok,
                    "sink": sink,
                },
            ),
            "failure_cancels_sibling": (_parallel(), {"start": start, "work": None, "sink": sink}),
            "cancel_fanout": (_linear(), {"start": start, "work": blocking, "sink": sink}),
            "back_edge_cancel": (
                graph(
                    [
                        node("start", "start"),
                        node("v", "loop"),
                        node("u", "fixer"),
                        node("x", "waiter"),
                    ],
                    [
                        edge("start.ok", "v.trigger"),
                        edge("v.out", "u.trigger"),
                        edge("v.out", "x.trigger"),
                        edge("u.fix", "v.guidance", bound=1),
                    ],
                ),
                {"start": start, "loop": work_ok, "fixer": fix_once, "waiter": wait_first_round},
            ),
        }
        g, handlers = table[scenario]
        if scenario == "failure_cancels_sibling":

            async def a_or_b(nc, act, cfg):
                return await (
                    boom(nc, act, cfg) if nc.node.id == "a" else wait_release(nc, act, cfg)
                )

            handlers = {**handlers, "work": a_or_b}
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
        dispatcher = GraphDispatcher(
            host=self,
            services=None,
            router=router,
            graph=g,
            registry=REG,
            handlers=handlers,
            facts=facts,
            cfg=PipelineConfig(),
        )
        outcome = await dispatcher.run()
        if outcome.stored_failure is not None:
            raise outcome.stored_failure
        return outcome_string(outcome, router.topology)


async def _env_run(scenario: str, drive=None):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TQ,
                workflows=[DispatchProbe],
                activities=[block_forever],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    DispatchProbe.run, scenario, id=f"probe-{uuid.uuid4()}", task_queue=TQ
                )
                return await (drive(handle) if drive else handle.result()), handle


async def _has_event(handle, event_type) -> bool:
    history = await handle.fetch_history()
    return any(e.event_type == event_type for e in history.events)


@pytest.mark.asyncio
async def test_linear_graph_completes_with_the_sink_result():
    result, _ = await _env_run("linear")
    assert result == "done:s"


@pytest.mark.asyncio
async def test_unrouted_failure_reraises_the_original_exception():
    async def drive(handle):
        with pytest.raises(WorkflowFailureError) as info:
            await handle.result()
        return info.value.cause

    cause, _ = await _env_run("unrouted_failure", drive)
    assert isinstance(cause, ApplicationError)
    assert (cause.type, cause.message, cause.non_retryable) == ("X", "boom", True)
    assert cause.cause is None


@pytest.mark.asyncio
async def test_routed_failure_is_topology():
    result, _ = await _env_run("routed_failure")
    assert result == "handled"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["crash", "result_on_edge"])
async def test_interpreter_bugs_fail_the_workflow_task_not_the_run(scenario):
    async def drive(handle):
        for _ in range(100):
            if await _has_event(handle, EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED):
                break
            await asyncio.sleep(0.1)
        described = await handle.describe()
        await handle.terminate("probe done")
        return described.status

    status, handle = await _env_run(scenario, drive)
    assert status.name == "RUNNING"


@pytest.mark.asyncio
async def test_budget_boundary_waits_for_quiescence():
    async def drive(handle):
        await asyncio.sleep(1.0)
        assert "budget" not in await handle.query(DispatchProbe.events)
        await handle.signal(DispatchProbe.release, "b")
        result = await handle.result()
        events = await handle.query(DispatchProbe.events)
        return result, events

    (result, events), _ = await _env_run("budget_quiescence", drive)
    assert events.index("b-released") < events.index("budget")
    assert result.startswith("done:")


@pytest.mark.asyncio
async def test_budget_rejection_halts_and_skips_finalize():
    async def drive(handle):
        await handle.signal(DispatchProbe.set_reject_budget)
        await handle.signal(DispatchProbe.release, "a")
        result = await handle.result()
        events = await handle.query(DispatchProbe.events)
        return result, events

    (result, events), _ = await _env_run("budget_halt", drive)
    assert result == "rejected:budget"
    assert "finalize" not in events


@pytest.mark.asyncio
async def test_failed_terminal_cancels_the_running_sibling():
    async def drive(handle):
        with pytest.raises(WorkflowFailureError):
            await handle.result()
        return await handle.query(DispatchProbe.events)

    events, _ = await _env_run("failure_cancels_sibling", drive)
    assert "b-cancelled" in events


@pytest.mark.asyncio
async def test_back_edge_traversal_cancels_a_live_region_activation():
    """§5.4 step 6: step.cancelled from a REGION invalidation cancels the live
    task; its late result is discarded (not live) and the node re-runs."""

    async def drive(handle):
        result = await handle.result()
        return result, await handle.query(DispatchProbe.events)

    (result, events), _ = await _env_run("back_edge_cancel", drive)
    assert events.index("x-cancelled") < events.index("x-round-2")
    assert "x-round-1" not in events
    assert result.startswith("done:")


@pytest.mark.asyncio
async def test_workflow_cancellation_fans_out_to_running_handlers():
    async def drive(handle):
        # ActivityTaskStarted reaches history only when the attempt closes,
        # so wait on the handler's own log line instead.
        for _ in range(200):
            if "blocking-started" in await handle.query(DispatchProbe.events):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)  # let the activity attempt reach the worker
        await handle.cancel()
        with pytest.raises(WorkflowFailureError) as info:
            await handle.result()
        assert isinstance(info.value.cause, CancelledError)
        return await _has_event(handle, EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED)

    cancel_requested, _ = await _env_run("cancel_fanout", drive)
    assert cancel_requested
