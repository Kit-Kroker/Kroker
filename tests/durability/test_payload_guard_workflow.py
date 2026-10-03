"""007 T007 (PIN, temporal tier): the guard inside a REAL workflow.

The fast-tier module proves the capability in isolation; this one proves the
durable end to end against a live ephemeral server (SC-001, FR-006, FR-007):
an over-limit prompt fails the workflow well inside a bounded wait — never
the R1 hot-retry hang — with the patch marker in its history and NO
scheduled activity; an under-limit prompt completes with no marker; and the
over-limit history replays clean. Expected green on first run (SG-2 if not).

Construction mirrors tests/durability/test_provider_payload_parity.py: the
durability-bound agent is built at MODULE level (TemporalDurability.
_check_bindable forbids constructing it inside a workflow), the workflow
takes the prompt as its input, and the worker registers the agent's bound
temporal_activities under the SdlcPydanticAIPlugin with the unsandboxed
runner. The replay half follows tests/durability/test_inflight_resume.py.

The prompt is padded 64 KiB past the limit in ASCII (serialized bytes ==
characters, plus request-parameters overhead on top): inside the guard's
window (over 1 MiB) but far under the engine's own 2 MiB payload cap from
research R1, so the GUARD is what fires — the point of the feature.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowFailureError, WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from sdlc.agents.payload_guard import (
    GUARD_PATCH_ID,
    OVERSIZE_ERROR_TYPE,
    PROPOSER_PAYLOAD_LIMIT_BYTES,
    payload_guard,
)
from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin

pytestmark = [pytest.mark.temporal]

_OVER_LIMIT_PROMPT = "x" * (PROPOSER_PAYLOAD_LIMIT_BYTES + 65_536)
_UNDER_LIMIT_PROMPT = "Say ok."
# A wedged result await must fail THIS test (SC-001: the failure arrives in
# one workflow task), never stall the tier -- the R1 defect is precisely a
# result that never arrives.
_RESULT_BUDGET_S = 60.0


async def _ok_model(messages: object, info: object) -> ModelResponse:
    return ModelResponse(parts=[TextPart("ok")])


_AGENT = Agent(
    FunctionModel(_ok_model),
    name="payload_guard_probe_agent",
    capabilities=[
        TemporalDurability(
            activity_config=AGENT_ACTIVITY_CONFIG,
            model_activity_config={"heartbeat_timeout": None},
        ),
        payload_guard(),
    ],
)


@workflow.defn
class _PayloadGuardProbeWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        result = await _AGENT.run(prompt)
        return result.output


def _history_text(history: WorkflowHistory) -> str:
    """The fetched history as one string. The patch marker's EVENT-TYPE
    spelling differs by server build, so the marker assertions search the
    serialized events instead of pinning a type (T007)."""
    return "\n".join(str(event) for event in history.events)


def _schedules_an_activity(history: WorkflowHistory) -> bool:
    return any(
        event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED for event in history.events
    )


def _replayer() -> Replayer:
    """Same construction as test_inflight_resume's (and the sandbox-marking
    pin inspects this surface): the plugin's sandbox passthrough covers
    sdlc.agents, so the replay re-derives the module-level agent safely."""
    return Replayer(
        workflows=[_PayloadGuardProbeWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[SdlcPydanticAIPlugin()],
    )


async def _run_once(prompt: str, name: str) -> tuple[object | None, WorkflowHistory | None]:
    """Run one prompt through a fresh environment; returns
    (output_or_None, history). The workflow either completes or fails -- both
    shapes are expected depending on the prompt; a FAILED handle's history is
    still fetchable (the first-workflow-task-time tests do exactly that)."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=name,
            workflows=[_PayloadGuardProbeWorkflow],
            activities=TemporalDurability.from_agent(_AGENT).temporal_activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _PayloadGuardProbeWorkflow.run,
                prompt,
                id=name,
                task_queue=name,
            )
            output: object | None = None
            try:
                output = await asyncio.wait_for(handle.result(), timeout=_RESULT_BUDGET_S)
            except WorkflowFailureError:
                pass  # the caller decides whether failing is the expectation
            return output, await handle.fetch_history()


@pytest.mark.asyncio
async def test_over_limit_prompt_fails_before_scheduling_with_marker():
    """SC-001/FR-001: the over-limit run FAILS (never hangs) with a cause
    that is the guard's non-retryable ApplicationError; its history carries
    the patch id on the failing branch and schedules NO activity."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="s007-guard-over",
            workflows=[_PayloadGuardProbeWorkflow],
            activities=TemporalDurability.from_agent(_AGENT).temporal_activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _PayloadGuardProbeWorkflow.run,
                _OVER_LIMIT_PROMPT,
                id="s007-guard-over",
                task_queue="s007-guard-over",
            )
            with pytest.raises(WorkflowFailureError) as excinfo:
                await asyncio.wait_for(handle.result(), timeout=_RESULT_BUDGET_S)
            history = await handle.fetch_history()

    cause = excinfo.value.cause
    assert isinstance(cause, ApplicationError), f"unexpected failure cause: {excinfo.value!r}"
    assert cause.type == OVERSIZE_ERROR_TYPE, f"wrong failure type: {cause.type!r}"
    assert cause.non_retryable is True, "the guard's failure must be non-retryable"

    assert GUARD_PATCH_ID in _history_text(history), "the failing branch recorded no patch marker"
    assert not _schedules_an_activity(history), (
        "an over-limit run scheduled an activity -- the guard must fail the "
        "request BEFORE it is scheduled (FR-001/SC-001)"
    )


@pytest.mark.asyncio
async def test_under_limit_prompt_completes_without_marker():
    """FR-007: the under-limit run completes through the normal durable path
    (its model request IS scheduled as an activity) and no history event
    carries the patch id -- an under-limit run records no marker."""
    output, history = await _run_once(_UNDER_LIMIT_PROMPT, "s007-guard-under")
    assert history is not None

    assert output == "ok", "an under-limit prompt must complete"
    assert _schedules_an_activity(history), (
        "the under-limit run did not schedule the model request activity -- "
        "the normal durable path must be intact"
    )
    assert GUARD_PATCH_ID not in _history_text(history), (
        "an under-limit run recorded a patch marker (FR-007: command-identical)"
    )


@pytest.mark.asyncio
async def test_over_limit_history_replays_without_nondeterminism():
    """FR-006: the over-limit history -- patch marker and raised failure
    included -- replays under the same workflow code with no
    non-determinism error."""
    _, history = await _run_once(_OVER_LIMIT_PROMPT, "s007-guard-replay-source")
    assert history is not None
    assert GUARD_PATCH_ID in _history_text(history), "fixture: the history must carry the marker"

    result = await _replayer().replay_workflow(history, raise_on_replay_failure=True)
    assert result.replay_failure is None
