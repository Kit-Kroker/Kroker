"""research -> clarify through a time-skipping worker with fake agents. Proves
the stage runs, verifies grounding (no grounded findings -> no violation),
gates, and hands off to clarify without a live provider."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
from pydantic_ai.models.test import TestModel
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.activities import evaluate_gate  # pure — reused, not faked
from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.models import (
    GateConfig, GateDecision, GateOutcome, GatePolicy, GroundedFinding,
    PipelineConfig, ResearchBrief,
)
from sdlc.research.verify import verify_brief_activity
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "e2e-research"

# The research fake: a brief with NO grounded_findings, so verify_brief_activity
# returns an empty violations list — the happy path for an offline run.
_RESEARCH = ResearchBrief(summary="found nothing external", confidence=0.5)

# Code-review I1: a brief WITH a grounded finding whose source_url was NEVER
# fetched this run. verify_brief_activity reads
# $SDLC_RUNS_ROOT/<run_id>/research/pages/<sha256(url)>.txt — no such file
# exists for "https://x/never-fetched" under the test's empty tmp_path, so the
# activity RETURNS [Violation(kind="source_never_fetched", ...)] and the
# workflow returns "rejected:research.grounding". This exercises the fail-closed
# path that the old `except GroundingViolation` could never catch (C1) and the
# retry_policy=1 (C2): under the old raise-based form, temporalio wrapped the
# GroundingViolation in ActivityError(ApplicationError), the workflow's typed
# catch never matched, and the workflow crashed instead of rejecting.
_RESEARCH_WITH_VIOLATION = ResearchBrief(
    summary="a grounded claim with no page file",
    confidence=0.5,
    grounded_findings=[
        GroundedFinding(source_url="https://x/never-fetched",
                        quote="anything", claim="c")])


def _research_fake_activities(brief: ResearchBrief = _RESEARCH) -> list:
    """The research agent is the only proposer with FUNCTION tools registered
    (web_search, fetch_page, …). The workflow-side model_request activity
    carries the production agent's function_tools in ModelRequestParameters,
    which reach the activity-side TestModel — and TestModel's default
    `call_tools='all'` would then emit a tool call to each of them. The fake
    agent's toolset has none of those tools, so dispatch would raise
    'Tool web_search not found in toolset'.

    Suppress that by forcing TestModel to call_tools=[] — emit the canned
    ResearchBrief directly via request_final_output, skipping the tool-call
    branch entirely. The OTHER proposer fakes (clarify/architect/etc.) have no
    function tools, so the default TestModel behaviour already produces [] for
    them and this override is unnecessary there."""
    agent = Agent(
        TestModel(custom_output_args=brief.model_dump(mode="json"),
                  call_tools=[]),
        name="research_agent",
        output_type=ResearchBrief,
    )
    ta = TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)
    return list(ta.temporal_activities)


async def _wait_for_status(handle, target: str, timeout_s: float = 30.0):
    """Poll status() until it reports `target` (e.g. 'awaiting:clarify')."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    while asyncio.get_event_loop().time() < deadline:
        status = await handle.query(FeatureWorkflow.status)
        if status != last:
            last = status
        if status == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"timed out waiting for status {target!r} (last={last!r})")


async def _drive(handle):
    # 1. clarify — answer the one open question (proves research handed off)
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question,
                            args=[qid, "yes"])
    # 2. deploy gate — architecture/plan/research are OFF (auto-approved);
    #    merge auto-passes with clean fakes. Only deploy waits on a human.
    await _wait_for_status(handle, "awaiting:deploy")
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate="deploy", round=1, outcome=GateOutcome.APPROVE,
                     decided_by="human"))


@pytest.mark.asyncio
async def test_research_stage_runs_and_hands_off():
    """With research_enabled=True the workflow MUST dispatch the research
    agent (registered as a fake) and invoke verify_brief_activity (registered
    as the production activity) before reaching clarify. Reaching
    `awaiting:clarify` proves research ran without crashing — if the research
    agent activity or verify_brief_activity were unregistered, the workflow
    would fail with a Temporal activity-not-found error long before clarify."""
    activities = [evaluate_gate, verify_brief_activity, *GIT_FAKES,
                  *_research_fake_activities(),
                  *fake_agent_activities(AGENT_SPECS)]
    cfg = PipelineConfig(
        research_enabled=True,
        gates={"research": GateConfig(policy=GatePolicy.OFF),
               "architecture": GateConfig(policy=GatePolicy.OFF),
               "plan": GateConfig(policy=GatePolicy.OFF),
               # clarify + merge + deploy default to HARD; the merge auto-passes
               # on green fakes (no advisory blocking -> no human merge gate).
               "deploy": GateConfig(policy=GatePolicy.HARD)},
        memoization_enabled=False,
        review_enabled=True,
    )
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        # Disable auto-skipping: real (48h) gate timers otherwise race the
        # signal delivery (same justification as test_e2e_greenfield).
        with env.auto_time_skipping_disabled():
            async with Worker(
                    env.client, task_queue=TASK_QUEUE,
                    workflows=[FeatureWorkflow], activities=activities,
                    plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"e2e-research-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver

    assert result.startswith("deployed:"), result


@pytest.mark.asyncio
async def test_research_stage_rejects_on_grounding_violation(tmp_path,
                                                              monkeypatch):
    """Code-review I1: a brief with an ungrounded finding (source_url never
    fetched this run) must cause the workflow to return
    "rejected:research.grounding" — NOT crash with ActivityError and NOT
    proceed to clarify.

    Under the OLD raise-based form, verify_brief_activity raised
    GroundingViolation; temporalio's execute_activity wrapped it in
    ActivityError(ApplicationError); the workflow's `except GroundingViolation`
    never matched (C1); the workflow crashed. This test exercises the catch by
    feeding the workflow a brief with `source_url="https://x/never-fetched"`
    and asserting a clean rejection. It would have caught both C1 and C2.

    The research gate policy is OFF (auto-approve) so the gate doesn't block
    before verification runs. $SDLC_RUNS_ROOT points at an empty tmp_path —
    no page file for the violating URL, so the activity returns
    [Violation(kind="source_never_fetched", ...)] and the workflow inspects it
    (`if violations:`) and rejects. No driver task: the workflow returns
    before reaching any human-gated stage."""
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    activities = [evaluate_gate, verify_brief_activity, *GIT_FAKES,
                  *_research_fake_activities(_RESEARCH_WITH_VIOLATION),
                  *fake_agent_activities(AGENT_SPECS)]
    cfg = PipelineConfig(
        research_enabled=True,
        gates={"research": GateConfig(policy=GatePolicy.OFF),
               "architecture": GateConfig(policy=GatePolicy.OFF),
               "plan": GateConfig(policy=GatePolicy.OFF),
               "deploy": GateConfig(policy=GatePolicy.HARD)},
        memoization_enabled=False,
        review_enabled=True,
    )
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                    env.client, task_queue=TASK_QUEUE,
                    workflows=[FeatureWorkflow], activities=activities,
                    plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"e2e-research-violation-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE)
                result = await handle.result()

    assert result == "rejected:research.grounding", result
