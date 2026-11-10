"""020 T022 (US5, R-1, plan T046): a new parent starts GraphWorkflow children,
and its history replays.

The E-74 §8.2 upgrade test is retired. It pinned an in-flight parent whose
started children replayed as FeatureWorkflow. FeatureWorkflow is deleted this
round, so no child starts on that branch. What remains is the replay safety of
the GraphWorkflow child path: a fresh parent's history replays, and the
on_graph callback fires once, before the child starts.
"""

from __future__ import annotations

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
from tests.replay.harness import replayer

pytestmark = pytest.mark.temporal
TQ = "e74-parent"


@workflow.defn(name="GraphWorkflow", sandboxed=False)
class StubGraph:
    @workflow.run
    async def run(self, inp: Any = None) -> str:
        return "graph-child"


@workflow.defn(name="ParentProbe", sandboxed=False)
class ParentProbe:
    @workflow.run
    async def run(self) -> list[str]:
        wid = workflow.info().workflow_id
        out: list[str] = []
        for n in (1, 2):
            out.append(
                await execute_pipeline_child(
                    child_id=f"{wid}-c{n}",
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
async def test_a_new_parent_starts_graph_children_and_its_history_replays():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TQ,
            workflows=[ParentProbe, StubGraph],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                "ParentProbe", id=f"parent-{uuid.uuid4()}", task_queue=TQ, result_type=list
            )
            result = await handle.result()
            history = await handle.fetch_history()
    assert result == ["graph-child", "graph-child"]
    assert _child_types(history) == ["GraphWorkflow", "GraphWorkflow"]

    replay = await replayer(ParentProbe, StubGraph).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert replay.replay_failure is None


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
