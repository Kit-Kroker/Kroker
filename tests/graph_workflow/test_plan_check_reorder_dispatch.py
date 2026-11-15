"""FR-301 Task 3: the reorder through the real dispatcher.

The shipped default graph, the REAL plan_check handler, scripted fakes for
everything else. An always-invalid plan drives the full D3 loop: two revise
rounds (planner rounds 2 and 3), then the exhausted loop keeps today's
terminal halt, and the run's return string is today's exact
`failed:plan-validation:<reason>` wire text. The board sync never fires
before a published version exists.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import NODE_TYPES, GraphRouter, from_yaml, validate
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.workflows.graph_dispatch import GraphDispatcher, outcome_string
from sdlc.workflows.graph_nodes import postplan
from sdlc.workflows.graph_nodes.base import NodeResult, RunFacts
from tests.fakes.canned import greenfield_idea
from tests.graph.fixtures.registries import roles

pytestmark = pytest.mark.temporal
TQ = "fr301-reorder-dispatch"
DEFAULT_GRAPH_YAML = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "sdlc"
    / "workflows"
    / "graphs"
    / "default.graph.yaml"
)

# Happy out-port per type; the planner and plan_check are real/scripted below.
HAPPY = {
    "intake": "ok",
    "clarify": "requirements",
    "architect": "spec",
    "gate.architecture": "approve",
    "gate.plan": "approve",
    "code": "results",
    "analyze": "analysis",
    "merge": "pr",
    "deploy": "done",
}


def _bad_plan() -> ImplementationPlan:
    return ImplementationPlan(
        tasks=[
            DevTask(id="a", title="a", description="a", acceptance_criteria=["x"], depends_on=["z"])
        ]
    )


@workflow.defn(sandboxed=False)
class ReorderProbe:
    def __init__(self) -> None:
        self._plan_version: int | None = None
        self.synced: tuple[int, list[str]] | None = None
        self.dispatcher: GraphDispatcher | None = None

    async def _check_budget(self, cfg) -> None:  # probe never rejects
        return None

    async def _board_sync_tasks(self, cfg, version, tasks) -> None:
        self.synced = (version, [t.id for t in tasks])

    @workflow.query
    def attribution(self) -> str:
        d = self.dispatcher
        assert d is not None
        return json.dumps(
            {
                "synced": self.synced,
                "rounds": sorted((aid, a.round) for aid, a in d._attrib.items()),
            }
        )

    @workflow.run
    async def run(self) -> str:
        graph = from_yaml(DEFAULT_GRAPH_YAML.read_text(encoding="utf-8"))
        report = validate(graph, NODE_TYPES, roles=roles())
        assert report.topology is not None, [p.message for p in report.problems]
        bad = _bad_plan()

        async def emit(nc, act, cfg):
            port = HAPPY[nc.node.type]
            return NodeResult(port=port, result="completed" if port == "done" else None)

        async def planner(nc, act, cfg):
            return NodeResult(port="plan", payload=bad)

        handlers = {t: emit for t in HAPPY}
        handlers["plan"] = planner
        handlers["plan_check"] = postplan.plan_check_node
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
            graph=graph,
            registry=NODE_TYPES,
            handlers=handlers,
            facts=facts,
            cfg=PipelineConfig(),
        )
        outcome = await self.dispatcher.run()
        return outcome_string(outcome, self.dispatcher.topology)


@pytest.mark.asyncio
async def test_an_always_invalid_plan_revises_twice_then_halts_with_todays_string():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TQ,
                workflows=[ReorderProbe],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    ReorderProbe.run, id=f"fr301-{uuid.uuid4()}", task_queue=TQ
                )
                result = await handle.result()
                facts = json.loads(await handle.query("attribution"))

    assert result == "failed:plan-validation:task 'a' depends on unknown task id(s) ['z']"
    rounds = dict(facts["rounds"])
    assert [rounds[f"planner#{i}"] for i in (1, 2, 3)] == [1, 2, 3]
    assert [rounds[f"plan_check#{i}"] for i in (1, 2, 3)] == [1, 2, 3]
    assert "plan#1" not in rounds  # the gate never ran: no approval before validation
    assert facts["synced"] is None  # no version published, nothing synced
