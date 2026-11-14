"""The research role's validated-output retry budget after the FR-202
cutover: construction at the default, the widened budget in the
registry, forwarded per call at every research run site.

Measured live in the research-partial-salvage assessment (error string
"Exceeded maximum output retries (1)"): one malformed final brief ended
the attempt and restarted the whole sub-question from scratch, burning
its remaining request budget. pydantic_ai's default budget of 1 spends
the only retry on the first, uncorrected attempt; the retry re-prompts
with the exact validation error, the stronger correction signal the
self-correction loop needs room to use. Since FR-202 the widened budget
lives in the registry (agents/research/agent.yaml, the planner
precedent — planner carries its 3 the same way) and is forwarded per
call at the run sites (VR-3): the plan and synthesis agents built ad
hoc in stage.py (previously at the default — the spec's one flagged
behaviour delta, VR-4), the sub-question fan-out's three model branches,
and the architect tool's two branches in toolset.py (the role is
"research" at every site). Construction stays at pydantic-ai's default
so the registry is the one source of the budget; these pins fail if a
future refactor re-pins the budget in code or the registry value
silently drops back to the default.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic_ai import RunUsage
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings

import sdlc.agents.roles as roles
from sdlc.agents.roles import OUTPUT_RETRIES
from sdlc.stages.research import stage, toolset
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief, SubQuestion, SubQuestionFinding

AGENT_PY = Path(__file__).resolve().parents[2] / "agents" / "research" / "agent.py"


def _build(provider: str = "fake"):
    spec = importlib.util.spec_from_file_location("_test_research_agent", AGENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # provider "fake" skips the exa branch (no EXA key needed); no tool
    # paths, so nothing is imported from agents/research/tools/.
    return module.build("openai:gpt-5", "be a researcher", ModelSettings(), [], provider)


def test_research_builds_at_the_default_output_retry_budget():
    agent = _build()
    assert agent._max_output_retries == 1


def test_research_budget_lives_in_the_registry():
    assert OUTPUT_RETRIES["research"] == 3


# ---------------------------------------------------------------------------
# The run sites forward the registry budget (VR-3). The shipped registry
# itself carries research=3, so the fake-agent seams below see
# retries={"output": 3} naturally — no OUTPUT_RETRIES monkeypatching.
# ---------------------------------------------------------------------------


class _FakeRunResult:
    """Just enough of a pydantic-ai run result: every site reads .output
    and folds .usage."""

    def __init__(self, output):
        self.output = output
        self.usage = RunUsage(input_tokens=1, output_tokens=1)


class _RecordingAgent:
    """Fake research agent for the seams that take an agent instance (the
    sub-question `_agent` seam, the toolset's monkeypatched t_research —
    the slice's existing fake shape): records the kwargs run() received."""

    def __init__(self):
        self.kwargs: dict = {}

    async def run(self, *args, **kwargs):
        self.kwargs = dict(kwargs)
        return _FakeRunResult(ResearchBrief(summary="canned"))


def _constructed_agent_spy(recorded: dict, output):
    """A stand-in for the Agent SYMBOL the plan/synthesis impls construct
    from (their `_model` seam reaches only the construction, not the
    run): the returned class records its run kwargs into `recorded` and
    answers with `output`."""

    class _SpyAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, *args, **kwargs):
            recorded.update(kwargs)
            return _FakeRunResult(output)

    return _SpyAgent


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_plan_site_forwards_the_registry_output_retries(monkeypatch):
    recorded: dict = {}
    monkeypatch.setattr(
        stage,
        "Agent",
        _constructed_agent_spy(recorded, stage._PlannerOutput(sub_questions=["a?"])),
    )
    plan = await stage._plan_research_impl(
        stage.PlanInput(idea_json='{"title": "x"}', max_sub_questions=2, model="test-model")
    )
    assert [s.question for s in plan.sub_questions] == ["a?"]
    assert recorded.get("retries") == {"output": 3}


@pytest.mark.asyncio
async def test_synthesis_site_forwards_the_registry_output_retries(monkeypatch):
    recorded: dict = {}
    monkeypatch.setattr(
        stage,
        "Agent",
        _constructed_agent_spy(recorded, stage._SynthesisOutput(summary="s", confidence=0.5)),
    )
    finding = SubQuestionFinding(
        sub_question=SubQuestion(id="sq-0", question="q?"), brief=ResearchBrief(summary="b")
    )
    brief, _usage = await stage._synthesize_brief_impl(
        stage.SynthesizeInput(idea_json='{"title": "x"}', findings=[finding], model="test-model")
    )
    assert brief.summary == "s"
    assert recorded.get("retries") == {"output": 3}


def _sq_inp(model: str = "test-model") -> stage.SubQuestionInput:
    return stage.SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="what is the timeline?"),
        deps=ResearchDeps(
            run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
        ),
        model=model,
        max_requests=40,
        max_run_cost_usd=4.0,
    )


@pytest.mark.asyncio
async def test_subquestion_site_forwards_on_the_model_seam_branch():
    """Branch 1 of the fan-out site (the `_model` test seam): the run made
    with an explicit model carries the registry budget."""
    agent = _RecordingAgent()
    await stage._research_subquestion_impl(_sq_inp(), _model=TestModel(), _agent=agent)
    assert "model" in agent.kwargs, "pin the branch under test"
    assert agent.kwargs.get("retries") == {"output": 3}


@pytest.mark.asyncio
async def test_subquestion_site_forwards_under_a_model_override():
    """Branch 2 (004 D7a path b): inp.model differs from the registry
    model, so the call carries model=inp.model — and the retries with
    it."""
    registry_model = roles.REGISTRY["research"].model
    assert registry_model is not None and registry_model != "test-model"
    agent = _RecordingAgent()
    await stage._research_subquestion_impl(_sq_inp(), _agent=agent)
    assert agent.kwargs.get("model") == "test-model", "pin the branch under test"
    assert agent.kwargs.get("retries") == {"output": 3}


@pytest.mark.asyncio
async def test_subquestion_site_forwards_on_the_plain_branch(monkeypatch):
    """Branch 3 (no override): the registry model equals inp.model, so the
    call carries no model kwarg at all — the retries still ride along."""
    entry = roles.REGISTRY["research"]
    monkeypatch.setitem(
        roles.REGISTRY, "research", entry.model_copy(update={"model": "test-model"})
    )
    agent = _RecordingAgent()
    await stage._research_subquestion_impl(_sq_inp(), _agent=agent)
    assert "model" not in agent.kwargs, "pin the branch under test"
    assert agent.kwargs.get("retries") == {"output": 3}


def _tool_deps(**extra) -> ResearchDeps:
    return ResearchDeps(
        run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0, **extra
    )


@pytest.mark.asyncio
async def test_toolset_site_forwards_the_registry_output_retries(monkeypatch):
    """The architect tool's plain branch (no model override on the deps).
    The role here is `research` even though the caller is the architect —
    the inner run validates a ResearchBrief (VR-3)."""
    agent = _RecordingAgent()
    monkeypatch.setattr(roles, "t_research", agent)
    brief, _report = await toolset.research_subquery_reported(_tool_deps(), "q?")
    assert brief.summary == "canned"
    assert "model" not in agent.kwargs, "pin the branch under test"
    assert agent.kwargs.get("retries") == {"output": 3}


@pytest.mark.asyncio
async def test_toolset_site_forwards_under_a_model_override(monkeypatch):
    """The architect tool's override branch (004 D7 path c): the deps
    carry research_model, so the call forwards it — with the retries."""
    agent = _RecordingAgent()
    monkeypatch.setattr(roles, "t_research", agent)
    await toolset.research_subquery_reported(_tool_deps(research_model="override-model"), "q?")
    assert agent.kwargs.get("model") == "override-model", "pin the branch under test"
    assert agent.kwargs.get("retries") == {"output": 3}
