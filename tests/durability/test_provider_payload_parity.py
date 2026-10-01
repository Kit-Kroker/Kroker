"""Provider payload parity on the migrated durable path (T029, FR-020a).

The T008 capture (tests/replay/capture_provider_requests.py, run on main
203e7dd) recorded what the concrete model's ``request`` received on every
call while a tool-bearing architect stand-in ran through the DURABLE path.
This test re-runs the same scenario through the MIGRATED mechanism — a
capability-durable Agent (TemporalDurability + ResolveModelId), not the old
TemporalAgent wrapper — inside a real worker, and asserts the recorded turns
equal the frozen fixture
tests/replay/fixtures/architect_provider_requests_pre_migration.json.
The fixture is never regenerated (SG-2 family rule): if this goes red the
migration changed provider-visible request payloads and the executor
escalates (research.md R4a).

Diff policy: per-run volatile fields (run_id, conversation_id, timestamp)
are stripped on BOTH sides before the deep compare. Everything else — tool
args, the deterministic tool_call_id, usage token counts, model_settings,
the params summary — must match exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from pydantic_ai import Agent, RunContext
from pydantic_ai import messages as _messages
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief
from tests.fakes.canned import ARCH

pytestmark = [pytest.mark.temporal]

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "replay"
    / "fixtures"
    / "architect_provider_requests_pre_migration.json"
)

_VOLATILE = ("run_id", "conversation_id", "timestamp")

_RECORDED: list[dict[str, Any]] = []
_message_adapter: TypeAdapter[list[_messages.ModelMessage]] = TypeAdapter(
    list[_messages.ModelMessage]
)


class _RecordingTestModel(TestModel):
    """TestModel that records exactly what the durable layer hands a concrete
    model. Recording at the concrete-model boundary is the point: whatever
    preparation the capability path does has already happened by here."""

    async def request(  # type: ignore[override]
        self, messages, model_settings, model_request_parameters
    ):
        params = model_request_parameters
        _RECORDED.append(
            {
                "messages": json.loads(_message_adapter.dump_json(list(messages))),
                "model_settings": dict(model_settings or {}),
                "params": {
                    "allow_image_output": getattr(params, "allow_image_output", None),
                    "expect_mode": repr(getattr(params, "expect_mode", None)),
                    "function_tools": sorted(
                        t.name for t in (getattr(params, "function_tools", None) or ())
                    ),
                },
            }
        )
        return await super().request(messages, model_settings, model_request_parameters)


def _build_agent() -> Agent:
    recording_model = _RecordingTestModel(
        custom_output_args=ARCH.model_dump(mode="json"), call_tools=["research"]
    )
    agent = Agent(
        recording_model,
        name="architect_agent",
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            # Even if a model-id string crosses the durability boundary, it
            # resolves back to THE recording model — the parity assertion
            # stays about the same instance.
            ResolveModelId(lambda ctx, model_id: recording_model),
        ],
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        return ResearchBrief(summary="provider-capture canned brief")

    return agent


# A durability-bound agent must NOT be constructed inside a workflow
# (TemporalDurability._check_bindable) — build at module level, reference
# from the workflow, unlike the old wrapper the capture script built in-run.
_AGENT = _build_agent()


@workflow.defn
class _ArchitectRunWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        deps = ResearchDeps(
            run_id="provider-capture",
            provider="fake",
            max_searches=1,
            max_fetches=1,
            max_cost_usd=1.0,
        )
        result = await _AGENT.run(prompt, deps=deps)
        return result.output.model_dump_json()


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in _VOLATILE}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _kinds(turns: list[dict[str, Any]]) -> list[list[Any]]:
    return [[m.get("kind") for m in turn["messages"]] for turn in turns]


@pytest.mark.asyncio
async def test_provider_request_messages_match_the_frozen_capture():
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="s003-provider-capture-parity",
            workflows=[_ArchitectRunWorkflow],
            activities=TemporalDurability.from_agent(_AGENT).temporal_activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _ArchitectRunWorkflow.run,
                "Design a greeting endpoint.",
                id="s003-provider-capture-parity",
                task_queue="s003-provider-capture-parity",
            )
            await handle.result()

    assert len(_RECORDED) == 2, f"expected a two-turn model run, got {len(_RECORDED)}"
    live = _strip_volatile(_RECORDED)
    expected = _strip_volatile(fixture["turns"])
    assert live == expected, (
        "provider payloads drifted from the pre-migration capture "
        f"(base {fixture.get('base_commit', '?')[:7]}): "
        f"live kinds={_kinds(_RECORDED)} vs fixture kinds={_kinds(fixture['turns'])}"
    )
