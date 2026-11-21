"""FR-702 D7: the 2MB wire guard at the serialization chokepoint.

Unit legs (fast tier): to_payload passes one byte under MAX_PAYLOAD_BYTES,
raises PayloadTooLargeError at exactly the limit with a message naming the
claim-check fix, and decode is untouched (a fat payload built by the raw
converter still decodes under sdlc_data_converter).

Temporal legs (temporal tier): an activity whose RESULT exceeds 2MB fails
its task, retries exhaust, and the workflow takes its existing failure path
— never a silent 2MB history write; an activity whose INPUT exceeds 2MB
fails the WORKFLOW task, which Temporal retries indefinitely — the run
wedges Running until terminated, with the guard's error in history (spec
D7's two accepted failure modes, each pinned by its own trip).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowExecutionStatus
from temporalio.common import RetryPolicy
from temporalio.contrib.pydantic import (
    PydanticJSONPlainPayloadConverter,
    PydanticPayloadConverter,
)
from temporalio.exceptions import ActivityError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.converter import MAX_PAYLOAD_BYTES, PayloadTooLargeError, sdlc_data_converter


def test_to_payload_passes_one_byte_under_the_limit():
    value = "a" * (MAX_PAYLOAD_BYTES - 3)  # JSON adds two quotes -> MAX-1 bytes
    raw = PydanticJSONPlainPayloadConverter().to_payload(value)
    assert len(raw.data) == MAX_PAYLOAD_BYTES - 1, "fixture guard: exact size math"
    out = sdlc_data_converter.payload_converter.to_payload(value)
    assert len(out.data) == MAX_PAYLOAD_BYTES - 1


def test_to_payload_raises_at_exactly_the_limit():
    value = "a" * (MAX_PAYLOAD_BYTES - 2)  # JSON adds two quotes -> exactly MAX
    with pytest.raises(PayloadTooLargeError):
        sdlc_data_converter.payload_converter.to_payload(value)


def test_the_error_names_the_claim_check_fix():
    value = "a" * (MAX_PAYLOAD_BYTES - 2)
    with pytest.raises(PayloadTooLargeError) as ei:
        sdlc_data_converter.payload_converter.to_payload(value)
    assert "claim-check" in str(ei.value) and "ArtifactRef" in str(ei.value)


def test_decode_is_untouched_a_fat_payload_still_decodes():
    value = "a" * (MAX_PAYLOAD_BYTES + 100)
    raw = PydanticPayloadConverter().to_payload(value)  # raw converter: no guard
    out = sdlc_data_converter.payload_converter.from_payload(raw, str)
    assert out == value


# --- temporal legs ------------------------------------------------------------

_FAT = "x" * (MAX_PAYLOAD_BYTES + 65_536)  # ASCII: chars == serialized bytes


@activity.defn
async def _fat_result_activity() -> str:
    return _FAT


@activity.defn
async def _echo(text: str) -> str:
    return "ok"


@workflow.defn
class _FatResultWorkflow:
    @workflow.run
    async def run(self) -> str:
        try:
            await workflow.execute_activity(
                _fat_result_activity,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError:
            return "failed-path"
        return "completed"


@workflow.defn
class _FatInputWorkflow:
    @workflow.run
    async def run(self) -> str:
        await workflow.execute_activity(
            _echo,
            args=[_FAT],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return "unreachable"


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_oversized_activity_result_fails_loudly_not_silently():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="wire-guard-result",
            workflows=[_FatResultWorkflow],
            activities=[_fat_result_activity],
        ):
            handle = await env.client.start_workflow(
                _FatResultWorkflow.run,
                id="wire-guard-result-run",
                task_queue="wire-guard-result",
            )
            result = await asyncio.wait_for(handle.result(), timeout=60)
            assert result == "failed-path", (
                "an oversized result must exhaust retries and land in the "
                "workflow's failure path, not complete silently"
            )
            history = await handle.fetch_history()
            assert "ActivityTaskCompleted" not in str(history), (
                "the fat result must never complete a task — no 2MB history write"
            )


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_oversized_activity_input_wedges_until_terminated():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="wire-guard-input",
            workflows=[_FatInputWorkflow],
            activities=[_echo],
        ):
            handle = await env.client.start_workflow(
                _FatInputWorkflow.run,
                id="wire-guard-input-run",
                task_queue="wire-guard-input",
            )
            # D7: the workflow task fails at the guard and retries
            # indefinitely -- the run stays Running with the error in
            # history until an operator terminates it.
            guard_error_seen = False
            for _ in range(20):
                await asyncio.sleep(0.5)
                desc = await handle.describe()
                if desc.status != WorkflowExecutionStatus.RUNNING:
                    break
                history = await handle.fetch_history()
                text = str(history)
                if "PayloadTooLargeError" in text or "claim-check" in text:
                    guard_error_seen = True
                    break
            try:
                assert guard_error_seen, (
                    "the guard's error must appear in history while the run wedges"
                )
                desc = await handle.describe()
                assert desc.status == WorkflowExecutionStatus.RUNNING, (
                    "an oversized input wedges the run (retried workflow tasks), "
                    "it must not fail over or complete"
                )
            finally:
                await handle.terminate()
