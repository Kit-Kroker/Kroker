"""E-74 §8.2: a parent in flight at cutover replays its started children as
FeatureWorkflow and starts every later child as GraphWorkflow (per-child ids)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.workflows.pipeline_child import execute_pipeline_child
from tests.fakes.canned import e2e_config, greenfield_idea

pytestmark = pytest.mark.temporal
TQ = "e74-parent"


@workflow.defn(name="FeatureWorkflow", sandboxed=False)
class StubFeature:
    @workflow.run
    async def run(self, idea: Any = None, cfg: Any = None, seeded: Any = None) -> str:
        return "feature-child"


@workflow.defn(name="GraphWorkflow", sandboxed=False)
class StubGraph:
    @workflow.run
    async def run(self, inp: Any = None) -> str:
        return "graph-child"


@workflow.defn(name="ParentProbe", sandboxed=False)
class ParentBeforeCutover:
    def __init__(self) -> None:
        self.go = False

    @workflow.signal
    def proceed(self) -> None:
        self.go = True

    @workflow.run
    async def run(self) -> list[str]:
        wid = workflow.info().workflow_id
        out = [
            await workflow.execute_child_workflow(
                "FeatureWorkflow",
                args=[greenfield_idea(), e2e_config(), None],
                id=f"{wid}-c1",
                task_queue=TQ,
            )
        ]
        await workflow.wait_condition(lambda: self.go)
        out.append(
            await workflow.execute_child_workflow(
                "FeatureWorkflow",
                args=[greenfield_idea(), e2e_config(), None],
                id=f"{wid}-c2",
                task_queue=TQ,
            )
        )
        return out


@workflow.defn(name="ParentProbe", sandboxed=False)
class ParentAfterCutover:
    def __init__(self) -> None:
        self.go = False

    @workflow.signal
    def proceed(self) -> None:
        self.go = True

    @workflow.run
    async def run(self) -> list[str]:
        wid = workflow.info().workflow_id
        out = [
            await execute_pipeline_child(
                child_id=f"{wid}-c1",
                idea=greenfield_idea(),
                cfg=e2e_config(),
                seeded=None,
                task_queue=TQ,
            )
        ]
        await workflow.wait_condition(lambda: self.go)
        out.append(
            await execute_pipeline_child(
                child_id=f"{wid}-c2",
                idea=greenfield_idea(),
                cfg=e2e_config(),
                seeded=None,
                task_queue=TQ,
            )
        )
        return out


def _child_types(history) -> list[str]:
    return [
        e.start_child_workflow_execution_initiated_event_attributes.workflow_type.name
        for e in history.events
        if e.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
    ]


@pytest.mark.asyncio
async def test_started_children_replay_as_feature_and_later_children_are_graph():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            wid = f"parent-{uuid.uuid4()}"
            async with Worker(
                env.client,
                task_queue=TQ,
                workflows=[ParentBeforeCutover, StubFeature],
                workflow_runner=UnsandboxedWorkflowRunner(),
                max_cached_workflows=0,
            ):
                handle = await env.client.start_workflow(
                    "ParentProbe", id=wid, task_queue=TQ, result_type=list
                )
                for _ in range(200):
                    events = (await handle.fetch_history()).events
                    if any(
                        e.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED
                        for e in events
                    ):
                        break
                    await asyncio.sleep(0.05)
            async with Worker(
                env.client,
                task_queue=TQ,
                workflows=[ParentAfterCutover, StubFeature, StubGraph],
                workflow_runner=UnsandboxedWorkflowRunner(),
                max_cached_workflows=0,
            ):
                await handle.signal("proceed")
                result = await handle.result()
            history = await handle.fetch_history()
    assert result == ["feature-child", "graph-child"]
    assert _child_types(history) == ["FeatureWorkflow", "GraphWorkflow"]


# --- E-77 T022 (RED): the on_graph callback (FR-010/SC-003) -----------------
# Unit level on purpose: workflow.patched() decides the branch, so faking it
# pins each branch without a Temporal server. These inherit the module's
# `temporal` mark; run with `pytest -m temporal <this file>` (the default
# addopts deselect everything in this module).


@pytest.mark.asyncio
async def test_on_graph_fires_once_with_content_sha_before_the_child_starts(monkeypatch):
    from sdlc.agents.roles import REGISTRY
    from sdlc.workflows.graph_catalog import build_run_input
    from sdlc.workflows.graph_nodes import HANDLERS

    events: list[tuple[str, str]] = []

    async def fake_child(run, *args, **kw):
        events.append(("child-started", kw["id"]))
        return "graph-child"

    async def on_graph(sha: str) -> None:
        events.append(("on-graph", sha))

    monkeypatch.setattr("temporalio.workflow.patched", lambda patch_id: True)
    monkeypatch.setattr("temporalio.workflow.execute_child_workflow", fake_child)
    result = await execute_pipeline_child(
        child_id="child-1",
        idea=greenfield_idea(),
        cfg=e2e_config(),
        seeded=None,
        task_queue=TQ,
        on_graph=on_graph,
    )
    assert result == "graph-child"
    expected = build_run_input(
        greenfield_idea(), e2e_config(), None, registry_roles=REGISTRY, handler_types=HANDLERS
    )
    assert events == [("on-graph", expected.graph.content_sha()), ("child-started", "child-1")]


@pytest.mark.asyncio
async def test_on_graph_is_never_called_on_the_feature_branch(monkeypatch):
    calls: list[str] = []

    async def fake_child(run, *args, **kw):
        return "feature-child"

    async def on_graph(sha: str) -> None:
        calls.append(sha)

    monkeypatch.setattr("temporalio.workflow.patched", lambda patch_id: False)
    monkeypatch.setattr("temporalio.workflow.execute_child_workflow", fake_child)
    result = await execute_pipeline_child(
        child_id="child-1",
        idea=greenfield_idea(),
        cfg=e2e_config(),
        seeded=None,
        task_queue=TQ,
        on_graph=on_graph,
    )
    assert result == "feature-child"
    assert calls == []
