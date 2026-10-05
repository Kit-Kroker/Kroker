"""The architect-research-usage replay scenario (C12, plan D5): the
architect's research tool hands a ToolReturn report beside the brief, and the
run reaches `awaiting:architecture` with the harvest priced.

This module is NOT a test module and the scenario is NOT a member of
`tests.replay.scenarios.SCENARIOS` (FR-012; the 009 precedent
`tests/replay/research_retain.py`): list membership would force a golden file
and edits to two existing pin tests. Its history fixture — the FIRST
GraphWorkflow history — is captured ONCE, after the harvest is green, by
`test_architect_research_usage_replay.test_capture_architect_research_usage_history`,
which listens to `SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE`, never to
`SDLC_CAPTURE_HISTORIES`.

Modelled on `scenarios._architect_research_activities` (same agent name,
deps type, output type, durability capability, tool name/signature and
docstring), with ONE delta: the tool returns
`ToolReturn(return_value=RESEARCH_BRIEF_FAKE, metadata=metadata_for(REPORT))`.
Built inline so the module depends on the pure `sub_run_usage` module only
and can be copied onto the base commit for the negative control."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.observability.sub_run_usage import SubRunUsage, metadata_for
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief
from tests.fakes.canned import ARCH
from tests.replay import scenarios as S
from tests.replay.scenarios import RESEARCH_BRIEF_FAKE, Scenario

NAME = "architect_research_usage"

REPORT = SubRunUsage(
    model="fake:research-answer",
    input_tokens=11,
    output_tokens=2,
    cache_read_tokens=3,
    cache_write_tokens=4,
)


def _usage_agent() -> Agent:
    """The architect fake whose model calls its research tool once — the
    `scenarios._architect_research_activities` recipe with ONE delta: the
    tool returns the brief with the report beside it as ToolReturn metadata
    the model never sees."""
    test_model = TestModel(custom_output_args=ARCH.model_dump(mode="json"), call_tools=["research"])

    agent = Agent(
        test_model,
        name="architect_agent",
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(lambda ctx, model_id: test_model),
        ],
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        return ToolReturn(  # type: ignore[return-value]
            return_value=RESEARCH_BRIEF_FAKE, metadata=metadata_for(REPORT)
        )

    return agent


def activities() -> list:
    """The `architect_research_tool` scenario's registration bundle with
    every activity of its base architect fake dropped by activity name, plus
    this module's reported fake."""
    bound = TemporalDurability.from_agent(_usage_agent())
    assert bound is not None  # attached above
    keep = [
        a
        for a in S._research_tool_activities()
        if not getattr(a, "__temporal_activity_definition").name.startswith(
            "agent__architect_agent__"
        )
    ]
    return [*keep, *bound.temporal_activities]


def cfg():
    return S._deploying(S.e2e_config())


async def drive(handle: Any, env: Any) -> None:
    await S.answer_clarify(handle)
    await S.wait_for(handle, "awaiting:architecture")


SCENARIO = Scenario(
    NAME,
    S.greenfield_idea,
    cfg,
    activities,
    drive,
    before=S.reset_deploy,
    mode="partial",
    golden=False,
)


__all__ = [
    "NAME",
    "REPORT",
    "SCENARIO",
    "activities",
    "cfg",
    "drive",
]
