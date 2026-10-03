"""007 T007 (PIN, temporal tier): the guard inside a REAL workflow.

The fast-tier module proves the capability in isolation; this one proves the
durable end to end against a live ephemeral server (SC-001, FR-006, FR-007):
an over-limit prompt fails the workflow well inside a bounded wait — never
the R1 hot-retry hang — with the patch marker in its history and NO
scheduled activity; an under-limit prompt completes with no marker; and the
over-limit history replays clean. Expected green on first run (SG-2 if not).
T008a adds the US2 growth case: a tool return that pushes the HISTORY past
the limit on a later request fails THAT request, unscheduled (spec A1).

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
from pydantic_ai import Agent, RunContext
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
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


# --- T008a: the growth fixture -- a tool return pushes the HISTORY over -----

_GROWTH_AGENT_NAME = "payload_guard_growth_probe_agent"
_GROWTH_RETURN = "G" * (PROPOSER_PAYLOAD_LIMIT_BYTES + 65_536)

# (agent name, message count) per model-function call; the model function
# runs inside the worker's activity, i.e. this same process, so the list is
# visible here. The over-limit request must never add an entry.
_GROWTH_MODEL_CALLS: list[int] = []


async def _tool_then_text_model(messages: object, info: object) -> ModelResponse:
    """First request: call the grow tool. A second request would carry the
    grown history and must never happen -- the guard fires before it is
    scheduled."""
    _GROWTH_MODEL_CALLS.append(len(messages))
    if len(_GROWTH_MODEL_CALLS) == 1:
        return ModelResponse(parts=[ToolCallPart(tool_name="grow", args={})])
    return ModelResponse(parts=[TextPart("unreachable after growth")])


_GROWTH_AGENT = Agent(
    FunctionModel(_tool_then_text_model),
    name=_GROWTH_AGENT_NAME,
    capabilities=[
        TemporalDurability(
            activity_config=AGENT_ACTIVITY_CONFIG,
            model_activity_config={"heartbeat_timeout": None},
        ),
        payload_guard(),
    ],
)


@_GROWTH_AGENT.tool
async def grow(ctx: RunContext[None]) -> str:
    """Return a payload big enough that the NEXT request -- full history --
    exceeds the limit."""
    return _GROWTH_RETURN


@workflow.defn
class _GrowthProbeWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        result = await _GROWTH_AGENT.run(prompt)
        return result.output


def _history_text(history: WorkflowHistory) -> str:
    """The fetched history as one string. The patch marker's EVENT-TYPE
    spelling differs by server build, so the marker assertions search the
    serialized events instead of pinning a type (T007)."""
    return "\n".join(str(event) for event in history.events)


def _activity_names(history: WorkflowHistory) -> tuple[list[str], list[str]]:
    """(scheduled, completed) activity-type names, order and duplicates
    preserved -- the growth assertions are counts over these. A COMPLETED
    event's attributes carry no activity_type (only ids), so each completion
    resolves through the scheduled event it points at."""
    scheduled: list[str] = []
    completed: list[str] = []
    names_by_event_id: dict[int, str] = {}
    for event in history.events:
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            name = event.activity_task_scheduled_event_attributes.activity_type.name
            names_by_event_id[event.event_id] = name
            scheduled.append(name)
        elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            name = names_by_event_id.get(
                event.activity_task_completed_event_attributes.scheduled_event_id
            )
            if name is not None:
                completed.append(name)
    return scheduled, completed


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


# --- T008a: US2 scenario 1 -- growth during a call (spec A1) --------------------


@pytest.mark.asyncio
async def test_tool_growth_fails_the_crossing_request_unscheduled():
    """US2 scenario 1 / FR-002: a tool return that pushes the history past
    the limit fails the NEXT request. The earlier durable steps -- model
    request one and the tool execution -- are scheduled AND completed in the
    history, the failing branch records the marker, and the scheduled
    model-request count proves the over-limit request was never scheduled:
    exactly one model request activity for a run that needed two model
    calls, and exactly one model-function invocation."""
    _GROWTH_MODEL_CALLS.clear()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="s007-guard-growth",
            workflows=[_GrowthProbeWorkflow],
            activities=TemporalDurability.from_agent(_GROWTH_AGENT).temporal_activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _GrowthProbeWorkflow.run,
                "start growing",
                id="s007-guard-growth",
                task_queue="s007-guard-growth",
            )
            with pytest.raises(WorkflowFailureError) as excinfo:
                await asyncio.wait_for(handle.result(), timeout=_RESULT_BUDGET_S)
            history = await handle.fetch_history()

    cause = excinfo.value.cause
    assert isinstance(cause, ApplicationError), f"unexpected failure cause: {excinfo.value!r}"
    assert cause.type == OVERSIZE_ERROR_TYPE, f"wrong failure type: {cause.type!r}"
    assert cause.non_retryable is True, "the guard's failure must be non-retryable"

    scheduled, completed = _activity_names(history)
    model_request = f"agent__{_GROWTH_AGENT_NAME}__model_request"
    # The core assertion: one model request was scheduled and completed; a
    # second would have been needed (the history had grown past the limit)
    # and is absent -- the guard failed it before scheduling.
    assert scheduled.count(model_request) == 1, (
        f"expected exactly one scheduled model-request activity, got "
        f"{scheduled.count(model_request)} (scheduled: {scheduled})"
    )
    assert completed.count(model_request) == 1, (
        "the one served model request must also have completed"
    )
    assert len(_GROWTH_MODEL_CALLS) == 1, (
        f"the model function ran {len(_GROWTH_MODEL_CALLS)} times; the "
        "over-limit request must never reach it"
    )

    # The growth step itself ran to completion on the durable path: tool
    # calls offload to a GENERIC call_tool activity -- the tool name travels
    # as an argument (pydantic-ai's TemporalOperationNamer: there is no
    # per-tool activity, so count __call_tool, not __grow).
    tool_scheduled = [n for n in scheduled if n.endswith("__call_tool")]
    tool_completed = [n for n in completed if n.endswith("__call_tool")]
    assert len(tool_scheduled) == 1, (
        f"expected one call_tool activity scheduled, got {tool_scheduled}"
    )
    assert len(tool_completed) == 1, "the tool execution activity must have completed"

    assert GUARD_PATCH_ID in _history_text(history), "the failing branch recorded no patch marker"
