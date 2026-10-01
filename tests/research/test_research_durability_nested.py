"""FR-011 (T033): the architect's mid-run research tool stays a NESTED
plain run under the capability — the tool activity is the durable boundary,
so the research agent fans out NO workflow activities of its own and the
run's persisted budget keeps bounding spend.

The architect fake mirrors tests/replay/scenarios.py::_architect_research_activities
but its `research` tool calls the REAL `research_subquery` with the
workflow's own deserialized ResearchDeps; `roles.t_research` is patched to a
plain (non-durable) TestModel agent — research_subquery imports it lazily
INSIDE the call, so the patch lands activity-side exactly where production
executes. With a tool-less nested agent nothing charges during the run
(charging lives in the exa/fetch tools), so the budget half exercises the
persisted store against THIS run's identity: charge, read back, and prove
the cap still raises — FR-011's mechanism, not the exact number.

Temporal tier: spawns an ephemeral dev server.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import sdlc.agents.roles as roles
from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.observability.activities import export_run_artifacts
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.stages.research.budget_store import budget_path, charge_persisted
from sdlc.stages.research.deps import Budget, BudgetExceeded, ResearchDeps
from sdlc.stages.research.models import ResearchBrief
from sdlc.stages.research.toolset import research_subquery
from sdlc.stages.research.verify import verify_brief_activity
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.fakes.canned import AGENT_SPECS, ARCH, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy
from tests.replay.projection import command_projection
from tests.replay.scenarios import (
    A,
    _research_cfg,
    answer_clarify,
    decide,
    fake_notify,
    fake_plan_research,
)

QUEUE = "003-nested-research"

CANNED_BRIEF = ResearchBrief(summary="Nested in-activity research answer (003 T033).")


def _architect_research_subquery_activities(captured: list) -> list:
    """The scenario's architect fake, delta: the `research` tool records the
    deps that crossed the wire and calls the REAL research_subquery."""
    test_model = TestModel(custom_output_args=ARCH.model_dump(mode="json"), call_tools=["research"])

    agent = Agent(
        test_model,
        name="architect_agent",
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(lambda ctx, model_id: test_model),
        ],
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        captured.append(ctx.deps)
        return await research_subquery(ctx.deps, question)

    bound = TemporalDurability.from_agent(agent)
    assert bound is not None  # attached above
    return list(bound.temporal_activities)


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_nested_research_runs_in_activity_and_budget_still_bounds(tmp_path, monkeypatch):
    captured: list = []
    nested = Agent(
        TestModel(custom_output_args=CANNED_BRIEF.model_dump(mode="json"), call_tools=[]),
        name="research_agent",
        output_type=ResearchBrief,
    )
    monkeypatch.setattr(roles, "t_research", nested)
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))
    reset_deploy()

    activities = [
        evaluate_gate,
        verify_brief_activity,
        export_run_artifacts,
        fake_notify,
        fake_plan_research,  # empty plan: the research stage degrades, no fan-out
        *GIT_FAKES,
        *DEPLOY_FAKES,
        *fake_agent_activities([s for s in AGENT_SPECS if s[0] != "architect_agent"]),
        *_architect_research_subquery_activities(captured),
    ]

    async def drive(handle, env) -> None:  # scenarios._drive_research shape
        await answer_clarify(handle)
        await decide(handle, "deploy", 1, A)

    cfg = _research_cfg()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        # Sandbox runner (default) through the mitigated plugin: the
        # production-shaped worker.
        async with Worker(
            env.client,
            task_queue=QUEUE,
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=activities,
            plugins=[SdlcPydanticAIPlugin()],
        ):
            with env.auto_time_skipping_disabled():
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"003-nested-{uuid.uuid4()}",
                    task_queue=QUEUE,
                )
                driver = asyncio.create_task(drive(handle, env))
                result = await handle.result()
                await driver
            history = await handle.fetch_history()

    assert result.startswith("deployed:")
    proj = command_projection(history)
    call_tools = [
        c
        for c in proj
        if c.startswith("activity:agent__architect_agent__toolset__") and c.endswith("__call_tool")
    ]
    assert len(call_tools) == 1, f"expected exactly one architect tool activity, got {call_tools}"
    assert not [c for c in proj if "agent__research_agent__" in c], (
        "the nested research run fanned out its own workflow activities — "
        "FR-011's in-activity plain run broke"
    )

    # The persisted budget keeps bounding spend for THIS run's identity.
    assert captured, "the architect's research tool never ran"
    deps = captured[0]
    assert deps.run_id
    path = budget_path(deps.run_id, "run")
    await charge_persisted(deps, search=1, scope="run")
    stored = Budget.model_validate_json(path.read_text(encoding="utf-8"))
    assert stored.searches == 1
    tight = deps.model_copy(update={"max_searches": 1})
    with pytest.raises(BudgetExceeded):
        await charge_persisted(tight, search=1, scope="run")
