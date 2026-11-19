"""FR-702 / ADR-10: the 2MB wire guard — ``sdlc_data_converter``.

The guard fires at ``to_payload``, the one chokepoint every write
serialization in-process passes through (activity inputs scheduled from
workflow code, results, signals, start args); decode is NEVER guarded so
histories written by older raw-converter processes still replay.

The two temporal-tier legs pin the two documented failure modes (design
D7, both accepted):

- result oversized -> the ACTIVITY task fails, retries re-produce the
  same result and exhaust, and the workflow takes its existing failure
  path. Loud and terminal; never a silent 2MB history write.
- input oversized -> the WORKFLOW task fails at input encoding and
  Temporal retries workflow tasks indefinitely: the run wedges RUNNING
  with the guard's error in history until an operator terminates it.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta

import pytest
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType, RetryState
from temporalio.client import WorkflowExecutionStatus
from temporalio.common import RetryPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ActivityError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.converter import MAX_PAYLOAD_BYTES, PayloadTooLargeError, sdlc_data_converter

CLAIM_CHECK_HINT = "claim-check it via ArtifactRef (FR-702)"


def _sized_str(data_bytes: int) -> str:
    """An ASCII str whose pydantic JSON encoding is exactly ``data_bytes`` bytes.

    ``pydantic_core.to_json`` wraps a plain ASCII str in two quotes and
    escapes nothing, so the wire data is ``len(s) + 2``.
    """
    return "x" * (data_bytes - 2)


# ---------------------------------------------------------------------- unit


def test_payload_too_large_error_is_a_runtime_error() -> None:
    assert issubclass(PayloadTooLargeError, RuntimeError)


def test_to_payload_passes_one_byte_under_the_limit() -> None:
    just_under = _sized_str(MAX_PAYLOAD_BYTES - 1)
    raw = pydantic_data_converter.payload_converter.to_payload(just_under)
    assert raw is not None and len(raw.data) == MAX_PAYLOAD_BYTES - 1  # exact fixture

    payload = sdlc_data_converter.payload_converter.to_payload(just_under)
    assert payload is not None
    assert len(payload.data) == MAX_PAYLOAD_BYTES - 1


def test_to_payload_raises_at_exactly_the_limit() -> None:
    fat = _sized_str(MAX_PAYLOAD_BYTES)
    raw = pydantic_data_converter.payload_converter.to_payload(fat)
    assert raw is not None and len(raw.data) == MAX_PAYLOAD_BYTES  # exact fixture

    with pytest.raises(PayloadTooLargeError):
        sdlc_data_converter.payload_converter.to_payload(fat)


def test_error_message_names_count_limit_and_fix() -> None:
    way_over = _sized_str(MAX_PAYLOAD_BYTES + 1000)
    raw = pydantic_data_converter.payload_converter.to_payload(way_over)
    assert raw is not None and len(raw.data) == MAX_PAYLOAD_BYTES + 1000

    with pytest.raises(PayloadTooLargeError) as excinfo:
        sdlc_data_converter.payload_converter.to_payload(way_over)
    message = str(excinfo.value)
    assert f"{MAX_PAYLOAD_BYTES + 1000} bytes >= {MAX_PAYLOAD_BYTES}" in message
    assert CLAIM_CHECK_HINT in message


def test_from_payload_decodes_oversized_payloads_untouched() -> None:
    """Decode is never guarded: a fat payload built by the RAW converter (a
    history written before the guard) still decodes under the guarded one."""
    raw = pydantic_data_converter.payload_converter.to_payload(_sized_str(MAX_PAYLOAD_BYTES))
    assert raw is not None

    (value,) = sdlc_data_converter.payload_converter.from_payloads([raw], [str])
    assert value == _sized_str(MAX_PAYLOAD_BYTES)  # round-trips intact


def test_pydantic_ai_plugin_preserves_the_guarded_converter() -> None:
    """pydantic-ai's Temporal plugin (pydantic-ai 2.61, ``_data_converter``)
    replaces any converter whose ``payload_converter_class`` is not a genuine
    ``PydanticPayloadConverter`` subclass with its own guard-less
    ``PydanticAIPayloadConverter``. The production worker runs this plugin
    (``worker.py`` / ``SdlcPydanticAIPlugin``), so the guarded composite MUST
    subclass ``PydanticPayloadConverter`` or the FR-702 guard would be
    silently discarded on every plugin-bearing client and worker."""
    from sdlc.agents.runner import SdlcPydanticAIPlugin

    configured = SdlcPydanticAIPlugin().configure_client({"data_converter": sdlc_data_converter})[
        "data_converter"
    ]
    assert configured is sdlc_data_converter, "the plugin must preserve, not replace"
    with pytest.raises(PayloadTooLargeError):
        configured.payload_converter.to_payload(_sized_str(MAX_PAYLOAD_BYTES))


# ------------------------------------------------------------------ temporal

# Every wall-clock wait in the two legs below is capped: a guard test must
# never be able to hang the suite (the input-path run is wedged BY DESIGN,
# so an unbounded await on it would never return).
_RESULT_CAP_S = 120  # the failure path completes in seconds; this is a tripwire
_RPC_CAP_S = 30  # any single client RPC
_WEDGE_POLL_S = 60  # how long to watch for the workflow-task failure


@activity.defn
async def _huge_result() -> str:
    return _sized_str(MAX_PAYLOAD_BYTES)


@activity.defn
async def _echo(value: str) -> str:
    return "ok"


@workflow.defn
class _ResultGuardWorkflow:
    @workflow.run
    async def run(self) -> str:
        try:
            await workflow.execute_activity(
                _huge_result,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError:
            return "failed:activity-result-over-2mb"
        return "unreachable:the-guard-did-not-fire"


@workflow.defn
class _InputGuardWorkflow:
    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            _echo,
            _sized_str(MAX_PAYLOAD_BYTES),
            start_to_close_timeout=timedelta(seconds=30),
        )


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_activity_result_over_2mb_fails_the_task_and_exhausts_retries() -> None:
    """Result path (D7): the activity task fails with the guard's error, the
    retry re-produces the same result and exhausts, and the workflow takes
    its failure path — never a silent oversized history write."""
    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        async with Worker(
            env.client,
            task_queue="wire-guard-result",
            workflows=[_ResultGuardWorkflow],
            activities=[_huge_result],
            plugins=[SdlcPydanticAIPlugin()],  # the production worker shape: the
            workflow_runner=UnsandboxedWorkflowRunner(),  # guard must hold under the
        ):  # plugin's converter-replacement hook too
            handle = await env.client.start_workflow(
                _ResultGuardWorkflow.run,
                id=f"wire-guard-result-{uuid.uuid4()}",
                task_queue="wire-guard-result",
            )
            result = await asyncio.wait_for(handle.result(), timeout=_RESULT_CAP_S)
            history = await asyncio.wait_for(handle.fetch_history(), timeout=_RPC_CAP_S)

    assert result == "failed:activity-result-over-2mb"
    started = [
        ev.activity_task_started_event_attributes
        for ev in history.events
        if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED
    ]
    failed = [
        ev for ev in history.events if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED
    ]
    completed = [
        ev for ev in history.events if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
    ]
    # The server carries the retry loop in the single ActivityTaskStarted's
    # attempt counter (observed shape: one started event, attempt=2), and
    # exhaustion surfaces as ONE failed event with MAXIMUM_ATTEMPTS_REACHED.
    attempts = [s.attempt for s in started]
    assert attempts and attempts[-1] == 2, f"the retry really ran: {attempts}"
    assert len(failed) == 1
    failure = failed[0].activity_task_failed_event_attributes.failure
    assert (
        failed[0].activity_task_failed_event_attributes.retry_state
        == RetryState.RETRY_STATE_MAXIMUM_ATTEMPTS_REACHED
    )
    assert not completed, "an oversized result must never reach history"
    assert CLAIM_CHECK_HINT in failure.message, failure.message
    assert failure.application_failure_info.type == "PayloadTooLargeError"


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_activity_input_over_2mb_wedges_the_workflow_until_terminated() -> None:
    """Input path (D7): the workflow task fails at input encoding and Temporal
    retries workflow tasks indefinitely — the run wedges RUNNING with the
    guard's error in history until an operator terminates it."""
    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        async with Worker(
            env.client,
            task_queue="wire-guard-input",
            workflows=[_InputGuardWorkflow],
            activities=[_echo],
            plugins=[SdlcPydanticAIPlugin()],  # production worker shape (see above)
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _InputGuardWorkflow.run,
                id=f"wire-guard-input-{uuid.uuid4()}",
                task_queue="wire-guard-input",
            )
            deadline = time.monotonic() + _WEDGE_POLL_S
            messages: list[str] = []
            while time.monotonic() < deadline:
                history = await asyncio.wait_for(handle.fetch_history(), timeout=_RPC_CAP_S)
                messages = [
                    ev.workflow_task_failed_event_attributes.failure.message
                    for ev in history.events
                    if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED
                ]
                if any(CLAIM_CHECK_HINT in m for m in messages):
                    break
                await asyncio.sleep(1)
            assert any(CLAIM_CHECK_HINT in m for m in messages), messages

            info = await asyncio.wait_for(handle.describe(), timeout=_RPC_CAP_S)
            assert info.status == WorkflowExecutionStatus.RUNNING, "the run must wedge"
            assert not [
                ev
                for ev in history.events
                if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
            ], "the failure is at input encoding: nothing may be scheduled"
            await asyncio.wait_for(
                handle.terminate("test: release the documented input-path wedge"),
                timeout=_RPC_CAP_S,
            )
