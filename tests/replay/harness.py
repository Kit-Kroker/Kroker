"""Run one scenario against a workflow starter and read/write fixtures (E-74 §4.1)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from tests.replay.projection import TraceRecorder, close_projection, command_projection
from tests.replay.scenarios import Scenario

ROOT = Path(__file__).parent
HISTORIES = ROOT / "histories"
GOLDEN = ROOT / "golden"
TASK_QUEUE = "e74-replay"


@dataclass(frozen=True)
class Starter:
    name: str
    workflows: tuple[type, ...]
    start: Callable[[Client, Scenario, str], Awaitable[WorkflowHandle]]


async def _start_feature(client: Client, scenario: Scenario, wf_id: str) -> WorkflowHandle:
    from sdlc.workflows.feature import FeatureWorkflow

    return await client.start_workflow(
        FeatureWorkflow.run,
        args=[scenario.idea(), scenario.cfg(), scenario.seeded()],
        id=wf_id,
        task_queue=TASK_QUEUE,
    )


def _feature_workflows() -> tuple[type, ...]:
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow

    return (FeatureWorkflow, DeploymentWorkflow)


FEATURE_STARTER = Starter("FeatureWorkflow", _feature_workflows(), _start_feature)


@dataclass(frozen=True)
class Captured:
    workflow_id: str
    history: WorkflowHistory
    golden: dict[str, Any]


async def capture(
    scenario: Scenario,
    starter: Starter,
    monkeypatch: Any,
    tmp_path: Path,
    *,
    sandboxed: bool = False,
) -> Captured:
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    scenario.before()
    recorder = TraceRecorder()
    if not sandboxed:
        recorder.install(monkeypatch)
    wf_id = f"e74-{scenario.name}-{uuid.uuid4()}"
    runner_kw: dict[str, Any] = (
        {} if sandboxed else {"workflow_runner": UnsandboxedWorkflowRunner()}
    )
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=list(starter.workflows),
            activities=scenario.activities(),
            plugins=[PydanticAIPlugin()],
            **runner_kw,
        ):
            if scenario.mode == "then_skip":
                handle = await starter.start(env.client, scenario, wf_id)
                with env.auto_time_skipping_disabled():
                    await scenario.drive(handle, env)
                with contextlib.suppress(Exception):
                    await handle.result()
            else:
                with env.auto_time_skipping_disabled():
                    handle = await starter.start(env.client, scenario, wf_id)
                    driver = asyncio.create_task(scenario.drive(handle, env))
                    if scenario.mode == "partial":
                        await driver
                    else:
                        try:
                            await handle.result()
                        except Exception:
                            if scenario.mode != "expect_error":
                                raise
                        await driver
            history = await handle.fetch_history()
            if scenario.mode == "partial":
                await handle.terminate("e74 partial capture")
    golden = {
        "trace": recorder.trace(wf_id),
        "commands": command_projection(history),
        "close": close_projection(history),
    }
    return Captured(workflow_id=wf_id, history=history, golden=golden)


def source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def write_fixtures(name: str, captured: Captured, starter_name: str) -> None:
    HISTORIES.mkdir(exist_ok=True)
    GOLDEN.mkdir(exist_ok=True)
    commit = source_commit()
    (HISTORIES / f"{name}.json").write_text(
        json.dumps(
            {
                "workflow_id": captured.workflow_id,
                "workflow": starter_name,
                "source_commit": commit,
                "history": json.loads(captured.history.to_json()),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (GOLDEN / f"{name}.json").write_text(
        json.dumps(
            {"workflow": starter_name, "source_commit": commit, **captured.golden},
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_history(name: str) -> WorkflowHistory:
    data = json.loads((HISTORIES / f"{name}.json").read_text(encoding="utf-8"))
    return WorkflowHistory.from_json(data["workflow_id"], json.dumps(data["history"]))


def load_golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


async def _start_graph(client: Client, scenario: Scenario, wf_id: str) -> WorkflowHandle:
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.graph_catalog import build_run_input

    run_input = build_run_input(scenario.idea(), scenario.cfg(), scenario.seeded())
    return await client.start_workflow(
        GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
    )


def _graph_workflows() -> tuple[type, ...]:
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow

    return (GraphWorkflow, DeploymentWorkflow)


GRAPH_STARTER = Starter("GraphWorkflow", _graph_workflows(), _start_graph)
