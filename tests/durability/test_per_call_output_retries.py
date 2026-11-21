"""FR-202 Review Focus #1: a per-call ``retries={'output': n}`` override
drives pydantic-ai's output-retry loop THROUGH the TemporalDurability
capability, inside a real workflow.

This is the branch's single risk pin. Tasks 1-7 forward the registry's
validated-output budget per call (``role_host._run_role``:
``kwargs.setdefault('retries', {'output': n})`` only when set, construction
left at pydantic-ai's default of 1). A builder check once read
``pydantic_ai/durable_exec/temporal/_agent.py:549`` as forwarding the kwarg;
this file makes that a permanent pin instead of a one-time reading. If the
durable wrapper dropped the override, the four cutover roles would silently
run at budget 1 and ONLY this test would catch it -- outside a workflow
``TemporalModel.request`` bypasses the activity entirely
(``if not workflow.in_workflow(): return await super().request(...)``), so
an in-process pin would prove nothing about the durable path. Hence the
``temporal`` marker: every model request below crosses to a real activity.

Budget arithmetic (measured; the same arithmetic test_payload_guard.py D5
case 7 pins in-process): an output budget of N tolerates exactly N malformed
final answers -- the (N+1)th raises ``UnexpectedModelBehavior('Exceeded
maximum output retries (N)')``. The brief's one-malformed stub therefore
cannot separate budget 1 from budget 2 (both succeed -- D5 case 7 is
precisely the default-budget-1, fail-once-pass run), so the stub answers
malformed TWICE before answering through ``final_result``: only an honored
``retries={'output': 2}`` rides past the second malformed answer, and the
no-override call dies at the construction default of 1.

Pinned:
- (a) with ``retries={'output': 2}`` the run succeeds and made exactly three
  model requests, each one an activity execution (the request log grows
  monotonically -- every retry is a later request);
- (b) the same agent called without the kwarg raises
  ``UnexpectedModelBehavior`` through the workflow failure (the construction
  default of 1 exhausted by the second malformed answer) after exactly two
  model requests -- the loop never schedules a third.
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from temporalio import workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.converter import sdlc_data_converter

pytestmark = [pytest.mark.temporal]

_TASK_QUEUE = "fr202-per-call-output-retries"

# --- the stub: two malformed answers, then a valid final_result call --------

_ANSWERS: list[list[TextPart | ToolCallPart]] = []
"""Seeded by each test; the activity-side model pops one answer per request."""

_REQUESTS: list[int] = []
"""One entry per model request (i.e. per activity execution): the message
count at that request, so a later entry being larger proves the request came
after the retry feedback landed in history."""


async def _model(messages: list[ModelMessage], info: object) -> ModelResponse:
    _REQUESTS.append(len(messages))
    return ModelResponse(parts=_ANSWERS.pop(0))


# Built at module level: a durability-bound agent must not be constructed
# inside a workflow (TemporalDurability._check_bindable). No `retries` at
# construction -- production leaves construction at pydantic-ai's default
# (output budget 1) and moves the budget per call only. output_type=int gives
# the tool output path of D5 case 7: a bare-text answer is a no-output
# response that consumes the run's output-retry budget, and the valid answer
# arrives through the final_result tool (its single argument is named
# 'response' for a plain output type).
_AGENT = Agent(
    FunctionModel(_model),
    name="per_call_output_retries_probe_agent",
    output_type=int,
    capabilities=[
        TemporalDurability(
            activity_config=AGENT_ACTIVITY_CONFIG,
            model_activity_config={"heartbeat_timeout": None},
        )
    ],
)


@workflow.defn
class _ProbeWorkflow:
    @workflow.run
    async def run(self, output_retries: int | None) -> int:
        # role_host._run_role's FR-202 branch verbatim: the kwarg rides the
        # call only when set -- a role at the default passes no kwarg at all.
        if output_retries is None:
            result = await _AGENT.run("give a number")
        else:
            result = await _AGENT.run("give a number", retries={"output": output_retries})
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


async def _probe(output_retries: int | None) -> tuple[int | None, list[int], str | None]:
    """Run one probe workflow against the two-malformed stub; returns
    (output_or_None, request_log, failure_chain_or_None)."""
    _ANSWERS[:] = [
        [TextPart("not an integer")],
        [TextPart("still not an integer")],
        [ToolCallPart(tool_name="final_result", args={"response": 7})],
    ]
    _REQUESTS.clear()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=_TASK_QUEUE,
            workflows=[_ProbeWorkflow],
            activities=TemporalDurability.from_agent(_AGENT).temporal_activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _ProbeWorkflow.run,
                output_retries,
                id=f"{_TASK_QUEUE}-{output_retries}",
                task_queue=_TASK_QUEUE,
            )
            try:
                output = await handle.result()
                return output, list(_REQUESTS), None
            except Exception as exc:  # the budget-exhaustion path
                return None, list(_REQUESTS), _failure_chain(exc)


@pytest.mark.asyncio
async def test_per_call_output_retries_drive_the_loop_under_durability():
    """(a) With the per-call override the run survives both malformed
    answers -- only possible if retries={'output': 2} reached the graph's
    output budget through the durable wrapper -- and every model request
    crossed to the activity: three entries, strictly growing."""
    output, requests, failure = await _probe(2)

    assert failure is None, f"the override run must succeed, got:\n{failure}"
    assert output == 7
    assert len(requests) == 3, (
        f"expected three model requests (two malformed answers ridden past, "
        f"one valid), got {len(requests)}: {requests}"
    )
    assert requests[1] > requests[0] and requests[2] > requests[1], (
        f"each retry is a later request with the retry feedback in history, "
        f"got non-growing request log: {requests}"
    )


@pytest.mark.asyncio
async def test_without_the_override_the_default_budget_fails_the_run():
    """(b) The same agent called without the kwarg runs at the construction
    default (1): the second malformed answer exhausts the budget and
    UnexpectedModelBehavior surfaces through the workflow failure, after
    exactly two model requests -- a third would mean the override leaked in."""
    output, requests, failure = await _probe(None)

    assert output is None, "a default-budget run must fail, not serve output"
    assert failure is not None
    assert "UnexpectedModelBehavior" in failure, (
        f"expected UnexpectedModelBehavior in the failure chain, got:\n{failure}"
    )
    assert "Exceeded maximum output retries (1)" in failure, (
        f"the failure must name the construction-default budget, got:\n{failure}"
    )
    assert len(requests) == 2, (
        f"budget 1 tolerates one malformed answer, so exactly two model "
        f"requests may happen, got {len(requests)}: {requests}"
    )
