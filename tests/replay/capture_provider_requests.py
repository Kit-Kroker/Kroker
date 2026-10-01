"""Capture the pre-migration provider-level request messages (spec 003, T008).

Run on UNMODIFIED main (203e7dd), before any TemporalDurability migration
change lands:

    uv run --no-sync python tests/replay/capture_provider_requests.py

FR-020(a): the differential proof of message neutrality. This script runs
the tool-bearing architect stand-in (the T005 shape: same agent name,
deps_type, output type and `research` tool) through the DURABLE path -- a
TemporalAgent inside a workflow on a real worker -- while recording what the
CONCRETE model's ``request`` receives on every call: (messages,
model_settings, model_request_parameters). The multi-turn run (model turn ->
research tool call -> final answer) is exactly what the wrapper's
``_reprepare_messages`` step would perturb if the capability path behaved
differently. The output is frozen evidence; T029 re-runs the same capture on
migrated code and asserts byte-identical messages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Run as a script (not via pytest), so the repo root must be on sys.path for
# the `tests.fakes` import below.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import TypeAdapter
from pydantic_ai import Agent, RunContext
from pydantic_ai import messages as _messages
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
from pydantic_ai.models.test import TestModel
from temporalio import workflow
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

# Mirror tests/conftest.py: agent construction at import time reads these.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")
os.environ.setdefault("EXA_API_KEY", "test-dummy")
if not Path(os.environ.get("SDLC_GRAPH_STORE", "")).is_absolute():
    os.environ["SDLC_GRAPH_STORE"] = str(Path(tempfile.gettempdir()) / "sdlc-test-graphs")

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG  # noqa: E402
from sdlc.stages.architecture.models import ArchitectureSpec  # noqa: E402
from sdlc.stages.research.deps import ResearchDeps  # noqa: E402
from sdlc.stages.research.models import ResearchBrief  # noqa: E402
from tests.fakes.canned import ARCH  # noqa: E402

OUT = Path(__file__).parent / "fixtures" / "architect_provider_requests_pre_migration.json"

RECORDED: list[dict[str, Any]] = []

_message_adapter: TypeAdapter[list[_messages.ModelMessage]] = TypeAdapter(
    list[_messages.ModelMessage]
)


class _RecordingTestModel(TestModel):
    """TestModel that records exactly what the durable layer hands a concrete
    model. Recording at the concrete-model boundary is the point: whatever
    re-preparation the wrapper did has already happened by here."""

    async def request(self, messages, model_settings, model_request_parameters):  # type: ignore[override]
        params = model_request_parameters
        RECORDED.append(
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


def _build_durable_architect() -> TemporalAgent:
    model = _RecordingTestModel(
        custom_output_args=ARCH.model_dump(mode="json"), call_tools=["research"]
    )
    agent = Agent(
        model,
        name="architect_agent",
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        return ResearchBrief(summary="provider-capture canned brief")

    return TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)


@workflow.defn
class _ArchitectRunWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        ta = _build_durable_architect()
        deps = ResearchDeps(
            run_id="provider-capture",
            provider="fake",
            max_searches=1,
            max_fetches=1,
            max_cost_usd=1.0,
        )
        result = await ta.run(prompt, deps=deps)
        return result.output.model_dump_json()


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


async def main() -> None:
    durable = _build_durable_architect()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        client: Client = env.client
        async with Worker(
            client,
            task_queue="s003-provider-capture",
            workflows=[_ArchitectRunWorkflow],
            activities=durable.temporal_activities,
            plugins=[PydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await client.start_workflow(
                _ArchitectRunWorkflow.run,
                "Design a greeting endpoint.",
                id="s003-provider-capture",
                task_queue="s003-provider-capture",
            )
            await handle.result()

    assert len(RECORDED) == 2, f"expected a two-turn model run, got {len(RECORDED)} turns"
    fixture = {
        "base_commit": _source_commit(),
        "agent": "architect_agent",
        "turns": RECORDED,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(RECORDED)} turns, base {fixture['base_commit'][:7]})")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
