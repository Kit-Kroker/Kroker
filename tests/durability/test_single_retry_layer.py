"""One model request makes at most its agent's attempt budget of HTTP
requests (004 T009, FR-008; former 003 SC-007).

A registry-model durable agent — same model string, same AGENT_ACTIVITY_CONFIG
and heartbeat-neutrality shape as ``shared_durability()`` builds — runs inside
a real worker against the local counting stub (``_http_stub.py``) via
``ANTHROPIC_BASE_URL``. On main the provider SDK's own retries stack under the
engine's attempt budget: the always-429 count is 9 (3 attempts x (1 + 2 SDK
retries)), so the bound assertion here FAILS on main. After 004 Phase B the
count is at most AGENT_ACTIVITY_MAX_ATTEMPTS.

always-400 (E7), base-measured on 730f085 (see baseline.md): the activity is
scheduled ONCE and started 3 times — the engine retries the retryable
ApplicationError wrap of ModelHTTPError, and the anthropic SDK itself never
retries a 400. The single-layer invariant for non-retryable provider errors
is therefore "exactly one HTTP request per engine attempt": the total equals
AGENT_ACTIVITY_MAX_ATTEMPTS (3 today). A stacked SDK would push it above that
number. (The plan text's literal "== 1" contradicted Q3 — no engine-policy
edits — and the measured base; corrected here, flagged to the orchestrator.)

The exhausted always-429 call must FAIL through the activity — the failure
chain carries the activity's ApplicationError, which is exactly the shape the
stage's existing degrade / fail-closed paths handle today (FR-011). A
fail-once stub must land on exactly 2 requests — one failed attempt, one
served — proving retries still happen at exactly one layer.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.model_ids import single_retry_layer
from sdlc.agents.roles import (
    AGENT_ACTIVITY_CONFIG,
    AGENT_ACTIVITY_MAX_ATTEMPTS,
    REGISTRY,
)
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.stages.research.stage import research_subquestion

from ._http_stub import ProviderStub

pytestmark = [pytest.mark.temporal]

_REGISTRY_MODEL = REGISTRY["architect"].model
assert _REGISTRY_MODEL is not None

# Built at module level: a durability-bound agent must not be constructed
# inside a workflow (TemporalDurability._check_bindable). No output_type —
# the stub serves plain text and output-validation retries would add model
# requests the count here is not about (the bound is per model request, E8).
# The capability pair mirrors build_agents exactly (T012): durability plus
# the single-retry resolver, both fresh instances.
_AGENT = Agent(
    _REGISTRY_MODEL,
    name="single_retry_layer_probe_agent",
    capabilities=[
        TemporalDurability(
            activity_config=AGENT_ACTIVITY_CONFIG,
            model_activity_config={"heartbeat_timeout": None},
        ),
        single_retry_layer(),
    ],
)


@workflow.defn
class _OneModelCallWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        result = await _AGENT.run(prompt)
        return result.output


def _failure_chain(exc: BaseException | None) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
    return "\n".join(parts)


async def _run_one_call(mode: str) -> tuple[str | None, int, BaseException | None]:
    """Run one agent call against the stub in `mode`; returns
    (output_or_None, stub.count, failure_or_None). The workflow either
    completes or its failure propagates out of handle.result() — both are
    expected shapes depending on the mode."""
    with ProviderStub(mode=mode) as stub:
        import os

        os.environ["ANTHROPIC_BASE_URL"] = stub.base_url
        try:
            async with await WorkflowEnvironment.start_time_skipping(
                data_converter=pydantic_data_converter
            ) as env:
                async with Worker(
                    env.client,
                    task_queue="s004-single-retry-layer",
                    workflows=[_OneModelCallWorkflow],
                    activities=TemporalDurability.from_agent(_AGENT).temporal_activities,
                    plugins=[SdlcPydanticAIPlugin()],
                    workflow_runner=UnsandboxedWorkflowRunner(),
                ):
                    handle = await env.client.start_workflow(
                        _OneModelCallWorkflow.run,
                        "Say ok.",
                        id="s004-single-retry-layer",
                        task_queue="s004-single-retry-layer",
                    )
                    try:
                        output = await handle.result()
                        return output, stub.count, None
                    except Exception as exc:  # the exhaustion path (429/400)
                        return None, stub.count, exc
        finally:
            os.environ.pop("ANTHROPIC_BASE_URL", None)


@pytest.mark.asyncio
async def test_always_429_requests_are_bounded_by_the_attempt_budget():
    _, count, failure = await _run_one_call("always_429")
    assert count <= AGENT_ACTIVITY_MAX_ATTEMPTS, (
        f"always-429 stub saw {count} HTTP requests for one model request; "
        f"the engine's attempt budget is {AGENT_ACTIVITY_MAX_ATTEMPTS} — the "
        f"provider SDK is still stacking retries beneath it (FR-008)"
    )
    # FR-011: exhaustion fails through the activity (ApplicationError chain
    # carrying the provider error), the same failure the stage's degrade /
    # fail-closed path handles today.
    assert failure is not None, "an always-429 provider must fail the call"
    chain = _failure_chain(failure)
    assert "ApplicationError" in chain and "429" in chain, (
        f"expected the activity's ApplicationError carrying the 429 in the "
        f"failure chain, got:\n{chain}"
    )


@pytest.mark.asyncio
async def test_fail_once_succeeds_on_exactly_two_requests():
    output, count, _ = await _run_one_call("fail_once")
    assert output == "ok"
    assert count == 2, f"fail-once stub saw {count} HTTP requests, expected 2"


@pytest.mark.asyncio
async def test_always_400_costs_one_request_per_engine_attempt():
    output, count, failure = await _run_one_call("always_400")
    assert output is None, "an always-400 provider must fail the call, not serve it"
    assert failure is not None
    chain = _failure_chain(failure)
    assert "ApplicationError" in chain, (
        f"expected the activity's ApplicationError in the failure chain, got:\n{chain}"
    )
    # E7, base-measured (baseline.md): the SDK never retries a 400, the
    # engine attempts the activity exactly its budget times — so one HTTP
    # request per engine attempt. A stacked SDK would exceed this.
    assert count == AGENT_ACTIVITY_MAX_ATTEMPTS, (
        f"always-400 stub saw {count} HTTP requests; the SDK must add no "
        f"retries for a non-retryable provider error — expected exactly one "
        f"request per engine attempt ({AGENT_ACTIVITY_MAX_ATTEMPTS}; E7)"
    )


# --- T015: the research sub-question fan-out's own budget (V13) -------------
#
# The sub-question activity runs the PLAIN registry research_agent in-process
# (stage.py falls back to in-process execution inside an activity), under
# RESEARCH_SQ_ACT's 6-attempt policy (stages/research/step.py). The registry
# agent carries the single-retry resolver since T012, so one sub-question call
# against an always-429 provider must cost at most 6 HTTP requests — a 429 is
# a transport failure, not an output-validation retry, so each engine attempt
# makes exactly one model request (E8).


@workflow.defn
class _OneSubquestionWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        from sdlc.agents.roles import REGISTRY as _reg
        from sdlc.stages.research.deps import ResearchDeps
        from sdlc.stages.research.models import SubQuestion
        from sdlc.stages.research.stage import SubQuestionInput
        from sdlc.stages.research.step import RESEARCH_SQ_ACT

        model = _reg["research"].model
        assert model is not None, "research role has no registry model"
        inp = SubQuestionInput(
            sub_question=SubQuestion(id="sq-t015", question=prompt),
            deps=ResearchDeps(
                run_id="t015-subquestion",
                provider="fake",
                max_searches=1,
                max_fetches=1,
                max_cost_usd=1.0,
            ),
            model=model,
            max_requests=3,
            max_run_cost_usd=1.0,
        )
        finding = await workflow.execute_activity(
            research_subquestion,
            inp,
            schedule_to_close_timeout=timedelta(minutes=5),
            **RESEARCH_SQ_ACT,
        )
        return finding.brief.summary


@pytest.mark.asyncio
async def test_subquestion_always_429_is_bounded_by_the_research_budget():
    import os

    with ProviderStub(mode="always_429") as stub:
        os.environ["ANTHROPIC_BASE_URL"] = stub.base_url
        try:
            async with await WorkflowEnvironment.start_time_skipping(
                data_converter=pydantic_data_converter
            ) as env:
                async with Worker(
                    env.client,
                    task_queue="s004-subquestion-retry",
                    workflows=[_OneSubquestionWorkflow],
                    activities=[research_subquestion],
                    plugins=[SdlcPydanticAIPlugin()],
                    workflow_runner=UnsandboxedWorkflowRunner(),
                ):
                    handle = await env.client.start_workflow(
                        _OneSubquestionWorkflow.run,
                        "One question.",
                        id="s004-subquestion-retry",
                        task_queue="s004-subquestion-retry",
                    )
                    failure: BaseException | None = None
                    try:
                        await handle.result()
                    except Exception as exc:  # exhaustion is the expected path
                        failure = exc
        finally:
            os.environ.pop("ANTHROPIC_BASE_URL", None)

    assert failure is not None, "an always-429 provider must fail the sub-question call"
    chain = _failure_chain(failure)
    assert "ApplicationError" in chain and "429" in chain, (
        f"expected the activity failure carrying the 429, got:\n{chain}"
    )
    # V13 / T015: the research sub-question budget is 6 engine attempts and
    # the SDK adds none beneath it.
    assert stub.count <= 6, (
        f"always-429 stub saw {stub.count} HTTP requests for one sub-question "
        f"call; RESEARCH_SQ_ACT allows 6 attempts and the provider SDK must "
        f"add none beneath them (FR-008, V13)"
    )
