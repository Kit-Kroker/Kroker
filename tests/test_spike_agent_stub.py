"""Spike + permanent smoke test: a same-named fake TemporalAgent dispatches
through a time-skipping Temporal worker and returns the canned typed output.
If this fails, the e2e agent seam (Task 5) cannot work — see the plan's
Task 1 fallback note."""

from __future__ import annotations

import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.stages.clarify.models import (
    ClarifiedRequirements,
    OpenQuestion,
)

with workflow.unsafe.imports_passed_through():
    from sdlc.agents.roles import t_clarify
    from tests.fakes.fake_agents import fake_agent_activities


pytestmark = pytest.mark.temporal


CANNED = ClarifiedRequirements(
    summary="CANNED-SUMMARY",
    functional_requirements=["fr1"],
    non_functional_requirements=[],
    out_of_scope=[],
    open_questions=[
        OpenQuestion(id="q1", question="?", why_it_matters="x", suggested_answer="yes")
    ],
)


@workflow.defn
class _OneShotWorkflow:
    @workflow.run
    async def run(self) -> str:
        reqs = (await t_clarify.run("hi")).output
        return reqs.summary


@pytest.mark.asyncio
async def test_fake_agent_dispatches_canned_output():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        acts = fake_agent_activities(
            [
                ("clarify_agent", ClarifiedRequirements, CANNED),
            ]
        )
        async with Worker(
            env.client,
            task_queue="spike",
            workflows=[_OneShotWorkflow],
            activities=acts,
            plugins=[PydanticAIPlugin()],
        ):
            result = await env.client.execute_workflow(
                _OneShotWorkflow.run, id=f"spike-{uuid.uuid4()}", task_queue="spike"
            )
    assert result == "CANNED-SUMMARY"
