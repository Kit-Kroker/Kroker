"""SPIKE (research spec, Task 1 / finding 8). Two load-bearing mechanisms
proven here before the rest of the plan builds on them. The FINDING recorded
at the bottom of this file is this task's real output.

A. An @agent.output_validator that raises ModelRetry survives TemporalAgent
   and runs ACTIVITY-side (reading files there is legal; the workflow sandbox
   forbids it — test_factory_purity.py).
B. pydantic-ai-harness[codemode] imports and a trivial run_code executes
   through a TemporalAgent on a time-skipping worker.

NOTE on deviations from the task brief (structurally required; assertion
bodies are verbatim):
  1. `from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG` is wrapped in
     `with workflow.unsafe.imports_passed_through():` because roles.py calls
     Path.cwd() at import time (registry discovery), which the workflow
     sandbox forbids. This is the established codebase convention — see
     tests/test_spike_agent_stub.py:19 and tests/test_reflect_workflow.py:17.
     Without it the verbatim import raised RestrictedWorkflowAccessError on
     pathlib.Path.cwd.__call__ during workflow validation.
  2. Test B's `_CodeModeWorkflow` (and its CodeMode agent + TemporalAgent)
     were hoisted to module scope. Temporal forbids @workflow.defn on a
     local class ("<locals>" in __qualname__); the verbatim in-function
     definition raised ValueError at decoration time. The test body and
     its no-raise assertion are unchanged.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
from pydantic_ai.models.test import TestModel
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG


pytestmark = pytest.mark.temporal


class _Out(BaseModel):
    text: str


# A validator that records WHERE it runs. workflow.unsafe.is_replaying() is
# only callable in a workflow sandbox; in an activity it raises. We use that
# to observe the execution context without needing a file.
_VALIDATOR_RAN_IN: list[str] = []


def _build_validated_agent(retry_once: bool) -> TemporalAgent:
    agent = Agent(
        TestModel(custom_output_args={"text": "hello"}),
        name="spike_validated_agent",
        output_type=_Out,
    )

    @agent.output_validator
    async def _check(ctx: RunContext, out: _Out) -> _Out:
        try:
            in_workflow = workflow.in_workflow()
        except Exception:
            in_workflow = False
        _VALIDATOR_RAN_IN.append("workflow" if in_workflow else "activity")
        return out

    return TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)


t_spike = _build_validated_agent(retry_once=False)


@workflow.defn
class _SpikeWorkflow:
    @workflow.run
    async def run(self) -> str:
        return (await t_spike.run("go")).output.text


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="Task 1 finding A: TemporalAgent silently drops @agent.output_validator (runs in no context). Recorded decision-gate output; see FINDING block. A future pydantic-ai release that fixes this will turn this xfail green (strict=True flags that).")
async def test_output_validator_survives_temporalization_and_runs_activity_side():
    _VALIDATOR_RAN_IN.clear()
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(
                env.client, task_queue="spike-ov",
                workflows=[_SpikeWorkflow],
                activities=list(t_spike.temporal_activities),
                plugins=[PydanticAIPlugin()]):
            out = await env.client.execute_workflow(
                _SpikeWorkflow.run, id=f"spike-ov-{uuid.uuid4()}",
                task_queue="spike-ov")
    assert out == "hello"
    # THE finding: the validator ran, and it ran activity-side.
    assert _VALIDATOR_RAN_IN, "output_validator did not run at all"
    assert _VALIDATOR_RAN_IN[-1] == "activity", (
        f"output_validator ran in {_VALIDATOR_RAN_IN[-1]} context — "
        "verification must move to a post-run activity (see FINDING)")


# --- Test B setup (module-level — Temporal forbids local workflow classes).
from pydantic_ai_harness import CodeMode

_cm_agent = Agent(
    TestModel(call_tools=["run_code"]),
    name="spike_codemode_agent",
    capabilities=[CodeMode(tools="all")],
)


@_cm_agent.tool_plain
def _add_one(n: int) -> int:
    return n + 1


t_cm = TemporalAgent(_cm_agent, activity_config=AGENT_ACTIVITY_CONFIG)


@workflow.defn
class _CodeModeWorkflow:
    @workflow.run
    async def run(self) -> str:
        return str((await t_cm.run("use the tool")).output)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Task 1 finding B: CodeMode's run_code cannot be exercised via TestModel under TemporalAgent — Monty rejects TestModel's dummy code, Temporal retries the failing activity forever with no bound. The body's asyncio.wait_for(timeout=60) used to convert that hang into a deterministic TimeoutError but every run paid 60s for it. See FINDING B below; this stays skip until a real-LLM integration test proves the path.")
async def test_codemode_run_code_executes_through_temporal_agent():
    # NOTE: asyncio.wait_for bounds an observed INDEFINITE HANG. With plain
    # TestModel(call_tools=['run_code']), CodeMode's Monty type-checker
    # rejects TestModel's dummy code (e.g. 'a') and raises ModelRetry;
    # Temporal then retries the failing activity forever. The wait_for
    # converts that hang into a deterministic asyncio.TimeoutError so the
    # suite can complete. See FINDING B.
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(
                env.client, task_queue="spike-cm",
                workflows=[_CodeModeWorkflow],
                activities=list(t_cm.temporal_activities),
                plugins=[PydanticAIPlugin()]):
            await asyncio.wait_for(
                env.client.execute_workflow(
                    _CodeModeWorkflow.run, id=f"spike-cm-{uuid.uuid4()}",
                    task_queue="spike-cm"),
                timeout=60.0)
    # Reaching here without an exception proves run_code executed through the
    # temporalized agent. (TestModel's tool-call shape may vary; assert only
    # that dispatch did not raise.)


# ---------------------------------------------------------------------------
# FINDING (OBSERVED result on Python 3.14.3 / Windows / pydantic-ai-slim
# 0.4 temporal plugin / pydantic-ai-harness 0.7.0 / pydantic-monty 0.0.18):
#
#   A. output_validator + TemporalAgent: DID NOT RUN AT ALL. The workflow
#      completed and returned 'hello', but _VALIDATOR_RAN_IN stayed empty —
#      the @agent.output_validator is silently dropped when an Agent is wrapped
#      in a TemporalAgent and run through a workflow. Control: the same agent
#      WITHOUT TemporalAgent runs the validator (recorded 'activity/plain').
#      -> This is NOT 'workflow-side' (which the brief also named a STOP); it
#         is a stronger negative: the validator is not invoked in any context.
#      -> STOP for the plan as written. Task 7 CANNOT wire quote verification
#         as an @agent.output_validator — it would never execute. Re-plan
#         Task 7 as an explicit post-run `verify_brief` ACTIVITY called from
#         feature.py (the brief's own workflow-side fallback applies a
#         fortiori), with the stage failing (not the model retrying) on a
#         violation. Flag to plan owner before continuing.
#
#   B. pydantic-ai-harness[codemode] IMPORT + run_code through TemporalAgent:
#      import OK; run FAILED (indefinite hang). TestModel(call_tools=
#      ['run_code']) generates dummy code that CodeMode's Monty type-checker
#      rejects (MontyTypingError: unresolved-reference 'a'), raising
#      ModelRetry; Temporal retries the failing activity forever. On a PLAIN
#      (non-temporal) agent the same setup exhausts pydantic-ai's
#      max-retries=3 and raises UnexpectedModelBehavior. Under TemporalAgent
#      there is no bound on retries, so the workflow hangs (bounded here to
#      60s by asyncio.wait_for to get a deterministic TimeoutError).
#      -> The spike as written cannot prove run_code dispatches through a
#         TemporalAgent, because TestModel cannot generate the valid Python
#         source CodeMode requires. Whether CodeMode works through
#         TemporalAgent with a REAL model is NOT determined by this spike.
#      -> STOP for the plan as written. The Task 6 tools/CodeMode design is
#         blocked until either (a) a real-LLM integration test proves the
#         path, or (b) the design drops CodeMode for plain sequential tools.
#         Flag to plan owner before continuing.
#
# Both load-bearing mechanisms the plan assumed are UNVERIFIED on this
# platform. The remaining 9 tasks should NOT proceed on autopilot.
# ---------------------------------------------------------------------------
