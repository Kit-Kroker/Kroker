"""024 T025 (R7a): every stored history still replays with routing forced on.

Research R7 found sdk-core does not compare activity queues on replay, so no
``workflow.patched()`` marker is needed. This is the permanent guard: replace
``sdlc.pools.on_harness`` with a wrapper that forces every harness queue to
``"forced-q"`` and replay every history under ``tests/replay/histories/``.
Call sites use the module-qualified ``**pools.on_harness(...)`` form
(T026-T028), so one ``setattr`` on the module reaches them all.

T028 removed the xfail: every call site routes through ``on_harness``
now, so the patch is exercised by every replayed history, and R7's
claim (a forced task_queue does not fail replay) is proven permanently.

T034 (R7b, SC-006) adds ``test_routing_on_projection``: the greenfield_happy
scenario runs LIVE, in-test, on two workers with ``cfg.harness_queue`` set, and
nothing is written under ``histories/`` or ``golden/``. Its history must replay,
and its ``command_projection`` must EQUAL the stored single-pool golden's. The
equality is the point: the projection is queue-blind by design (T025 proved
replay tolerates queue changes; this proves the recorded command sequence itself
is identical when routing is on), while the task-queue assertions prove the run
was genuinely routed and not vacuously equal.

Stop-guard SG-2: a replay failure means the command sequence changed. Never
re-record a history to turn it green (tests/replay/AGENTS.md).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import sdlc  # noqa: F401  (the package the workflow sandbox passes through)
from sdlc import pools
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.converter import sdlc_data_converter
from tests.replay.harness import GOLDEN, HISTORIES, load_history, replayer
from tests.replay.projection import command_projection
from tests.replay.scenarios import SCENARIOS

FORCED_QUEUE = "forced-q"


class NoForcedQueueApplied(AssertionError):
    """The patched ``on_harness`` was never reached: the patch was vacuous."""


def _replay_workflows() -> tuple[type, ...]:
    from sdlc.benchmarks.workflow import BenchmarkWorkflow
    from sdlc.workflows.assessment import AssessmentWorkflow
    from sdlc.workflows.crew import CrewTaskWorkflow
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.triage import TriageWorkflow

    return (
        GraphWorkflow,
        DeploymentWorkflow,
        CrewTaskWorkflow,
        AssessmentWorkflow,
        TriageWorkflow,
        BenchmarkWorkflow,
    )


def _history_names() -> list[str]:
    return sorted(p.stem for p in HISTORIES.glob("*.json"))


def test_history_corpus_is_not_empty() -> None:
    assert _history_names(), f"no histories under {HISTORIES}"


@pytest.mark.asyncio
async def test_forced_queue_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pools.on_harness
    forced: list[tuple[dict[str, Any], str | None]] = []

    def forcing(opts: Mapping[str, Any], queue: str | None) -> dict[str, Any]:
        forced.append((dict(opts), queue))
        return real(opts, FORCED_QUEUE)

    monkeypatch.setattr(pools, "on_harness", forcing)

    names = _history_names()
    assert names, f"no histories under {HISTORIES}"
    failures: dict[str, object] = {}
    workflows = _replay_workflows()
    for name in names:
        result = await replayer(*workflows).replay_workflow(
            load_history(name), raise_on_replay_failure=False
        )
        if result.replay_failure is not None:
            failures[name] = result.replay_failure
    assert not failures, f"histories failed to replay with forced queue: {failures}"

    if not forced:
        raise NoForcedQueueApplied("no on_harness call reached: the forced-queue patch is vacuous")


ROUTED_QUEUE = "replay-q"
CORE_QUEUE = "e74-pools-core"


def _split_by_name(activities: list[Any]) -> tuple[list[Any], list[Any]]:
    """(core, harness) by registered activity name, as tests/test_pools_routing.py."""

    def name(fn: Any) -> str:
        return str(fn.__temporal_activity_definition.name)

    core = [a for a in activities if name(a) not in pools.HARNESS_ACTIVITIES]
    harness = [a for a in activities if name(a) in pools.HARNESS_ACTIVITIES]
    return core, harness


async def _histories_with_children(client: Client, handle: WorkflowHandle) -> list[Any]:
    out: list[Any] = []
    pending = [handle]
    while pending:
        hist = await pending.pop().fetch_history()
        out.append(hist)
        for ev in hist.events:
            if ev.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED:
                attrs = ev.child_workflow_execution_started_event_attributes
                pending.append(client.get_workflow_handle(attrs.workflow_execution.workflow_id))
    return out


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_routing_on_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.graph_catalog import build_run_input

    monkeypatch.delenv("KROKER_HARNESS_QUEUE", raising=False)
    assert os.environ.get("KROKER_HARNESS_QUEUE") is None  # routing rides the cfg alone
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))

    scenario = next(s for s in SCENARIOS if s.name == "greenfield_happy")
    scenario.before()
    cfg = scenario.cfg()
    cfg.harness_queue = ROUTED_QUEUE
    core_acts, harness_acts = _split_by_name(scenario.activities())

    # start_local, not time-skipping: the scenario is signal-driven, and the
    # platform finding of this round is that DescribeTaskQueue needs the dev server.
    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        async with (
            Worker(
                env.client,
                task_queue=CORE_QUEUE,
                identity="core@test",
                workflows=[GraphWorkflow, DeploymentWorkflow],
                activities=core_acts,
                plugins=[SdlcPydanticAIPlugin()],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=ROUTED_QUEUE,
                identity="harness@test",
                activities=harness_acts,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
        ):
            handle = await env.client.start_workflow(
                GraphWorkflow.run,
                build_run_input(scenario.idea(), cfg, scenario.seeded()),
                id=f"e74-routing-on-{uuid.uuid4()}",
                task_queue=CORE_QUEUE,
            )
            driver = asyncio.ensure_future(scenario.drive(handle, env))
            await asyncio.wait_for(handle.result(), timeout=180)
            await driver
            history = await handle.fetch_history()
            histories = await _histories_with_children(env.client, handle)

    # 1. a routing-ON history replays (R7b)
    result = await replayer(*_replay_workflows()).replay_workflow(
        history, raise_on_replay_failure=False
    )
    assert result.replay_failure is None, result.replay_failure

    # 2. the recorded command sequence is the single-pool golden's, exactly
    golden = json.loads((GOLDEN / "greenfield_happy.json").read_text(encoding="utf-8"))
    assert command_projection(history) == golden["commands"]

    # 3. the run was genuinely routed: every harness activity named the harness
    # queue and ran on the harness worker (children included)
    scheduled_queue: dict[tuple[int, int], tuple[str, str]] = {}
    harness_started = 0
    for h_index, hist in enumerate(histories):
        for ev in hist.events:
            if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                a = ev.activity_task_scheduled_event_attributes
                scheduled_queue[(h_index, ev.event_id)] = (a.activity_type.name, a.task_queue.name)
            elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
                s = ev.activity_task_started_event_attributes
                name, queue = scheduled_queue[(h_index, s.scheduled_event_id)]
                if name in pools.HARNESS_ACTIVITIES:
                    assert queue == ROUTED_QUEUE, f"{name} scheduled on {queue!r}"
                    assert s.identity == "harness@test", f"{name} ran on {s.identity!r}"
                    harness_started += 1
                else:
                    assert queue == CORE_QUEUE, f"{name} scheduled on {queue!r}"
                    assert s.identity == "core@test", f"{name} ran on {s.identity!r}"
    assert harness_started, "no harness activity ran: the equality above would be vacuous"

    # 4. the stored corpus is untouched
    status = subprocess.run(
        ["git", "status", "--porcelain", "tests/replay/histories", "tests/replay/golden"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    ).stdout
    assert status == "", status


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_routing_off_projection_is_the_same_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The symmetric pin: ``harness_queue=None`` also yields the single-pool commands.

    One core worker hosts every activity. The projection is queue-blind in both
    directions, and "unrouted" means literally the core queue: every harness
    activity is scheduled on ``CORE_QUEUE`` (never on a routed queue, never empty).
    """
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.graph_catalog import build_run_input

    monkeypatch.delenv("KROKER_HARNESS_QUEUE", raising=False)
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))

    scenario = next(s for s in SCENARIOS if s.name == "greenfield_happy")
    scenario.before()
    cfg = scenario.cfg()
    cfg.harness_queue = None

    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        async with Worker(
            env.client,
            task_queue=CORE_QUEUE,
            identity="core@test",
            workflows=[GraphWorkflow, DeploymentWorkflow],
            activities=scenario.activities(),
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                GraphWorkflow.run,
                build_run_input(scenario.idea(), cfg, scenario.seeded()),
                id=f"e74-routing-off-{uuid.uuid4()}",
                task_queue=CORE_QUEUE,
            )
            driver = asyncio.ensure_future(scenario.drive(handle, env))
            await asyncio.wait_for(handle.result(), timeout=180)
            await driver
            history = await handle.fetch_history()
            histories = await _histories_with_children(env.client, handle)

    # (a) the command sequence is the stored single-pool golden's
    golden = json.loads((GOLDEN / "greenfield_happy.json").read_text(encoding="utf-8"))
    assert command_projection(history) == golden["commands"]

    # (b) every harness activity (children included) names the core queue
    harness_scheduled = 0
    for hist in histories:
        for ev in hist.events:
            if ev.event_type != EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                continue
            a = ev.activity_task_scheduled_event_attributes
            if a.activity_type.name in pools.HARNESS_ACTIVITIES:
                assert a.task_queue.name == CORE_QUEUE, (
                    f"{a.activity_type.name} scheduled on {a.task_queue.name!r}"
                )
                harness_scheduled += 1
    assert harness_scheduled, "no harness activity scheduled: the pin would be vacuous"

    status = subprocess.run(
        ["git", "status", "--porcelain", "tests/replay/histories", "tests/replay/golden"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    ).stdout
    assert status == "", status
