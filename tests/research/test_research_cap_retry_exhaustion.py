"""Retry exhaustion after a refused charge degrades once (feature 008, N4).

E1's harness shape (`.workspace/tmp/research-budget-enforcement-e1.py`,
`via_stage`): a CodeMode agent whose `web_search` tool charges the REAL
`charge_scoped`, a stubborn `FunctionModel` that always re-emits
`run_code`, run through `_research_subquestion_impl`. A model that keeps
retrying a refused search must end as one degraded finding that names the
refused bound and its spend (FR-003, FR-004); the same terminal error
with no refusal behind it must propagate untouched (FR-005), and a lock
timeout is not a refusal either (EC4, N3).
"""

import json

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai_harness import CodeMode

from sdlc.stages.research import budget_store
from sdlc.stages.research.budget_store import budget_path, charge_scoped
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps
from sdlc.stages.research.models import SubQuestion
from sdlc.stages.research.stage import SubQuestionInput
from sdlc.stages.research.stage import _research_subquestion_impl as research_subquestion

TWO_CALLS = 'r1 = await web_search(query="a")\nr2 = await web_search(query="b")\nr2'
ONE_CALL = 'r1 = await web_search(query="a")\nr1'


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _deps(run_id: str) -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id,
        provider="fake",
        max_searches=1,
        max_fetches=10,
        max_cost_usd=1.0,
        scope="sq-0",
        max_run_cost_usd=4.0,
    )


def _inp(run_id: str) -> SubQuestionInput:
    return SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="q"),
        deps=_deps(run_id),
        model="function",
        max_requests=40,
        max_run_cost_usd=4.0,
    )


def _run_code_model(code: str) -> FunctionModel:
    """E1's stubborn model (compliant=False): always emit the run_code
    script, never conclude."""

    def fn(messages, info):
        return ModelResponse(parts=[ToolCallPart("run_code", {"code": code})])

    return FunctionModel(fn)


def _research_agent(model: FunctionModel) -> Agent:
    """E1's agent: CodeMode plus a web_search tool that charges the real
    budget store through ctx.deps."""
    agent = Agent(model, deps_type=ResearchDeps, capabilities=[CodeMode()])

    @agent.tool
    async def web_search(ctx: RunContext[ResearchDeps], query: str) -> str:
        """Search the web."""
        await charge_scoped(
            ctx.deps, search=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd
        )
        return f"results for {query}"

    return agent


def _broken_network_agent(model: FunctionModel) -> Agent:
    """The same agent, but the tool fails for an unrelated reason every
    call: nothing is charged, so nothing notes a refusal."""
    agent = Agent(model, deps_type=ResearchDeps, capabilities=[CodeMode()])

    @agent.tool
    async def web_search(ctx: RunContext[ResearchDeps], query: str) -> str:
        """Search the web."""
        raise RuntimeError("network down")

    return agent


@pytest.mark.asyncio
async def test_retry_exhaustion_after_a_refusal_degrades_to_one_finding():
    model = _run_code_model(TWO_CALLS)
    out = await research_subquestion(_inp("t8-c1"), _model=model, _agent=_research_agent(model))

    assert out.failed is False
    assert out.usage.input_tokens > 0
    assert out.usage.calls == 1
    assert len(out.brief.gaps) == 1
    why = out.brief.gaps[0].why_it_matters
    assert "search budget exhausted" in why
    assert "sq-0 allowance" in why
    assert "search budget exhausted" in out.brief.summary
    assert "sq-0 allowance" in out.brief.summary
    assert "http" not in why
    assert "http" not in out.brief.summary
    assert len(why.split("; then ", 1)[1]) <= 200
    assert json.loads(budget_path("t8-c1", "run").read_text())["searches"] == 1


@pytest.mark.asyncio
async def test_an_unrelated_tool_failure_still_propagates():
    model = _run_code_model(ONE_CALL)
    with pytest.raises(UnexpectedModelBehavior):
        await research_subquestion(_inp("t8-c2"), _model=model, _agent=_broken_network_agent(model))
    assert not budget_path("t8-c2", "run").exists()


@pytest.mark.asyncio
async def test_a_lock_timeout_still_propagates(monkeypatch):
    async def _always_timeout(lock_path):
        raise TimeoutError("research budget lock held too long")

    monkeypatch.setattr(budget_store, "_acquire_lock", _always_timeout)
    model = _run_code_model(ONE_CALL)
    with pytest.raises(UnexpectedModelBehavior):
        await research_subquestion(_inp("t8-c3"), _model=model, _agent=_research_agent(model))
    assert not budget_path("t8-c3", "run").exists()


# ---------------------------------------------------------------------------
# Plan-D5 retry case 4 (EC3, spec A2 -- accepted behaviour, pinned) and case
# 5: the handler's branch logic with plain fake agents, no CodeMode.


SWALLOW_THEN_FAIL = """try:
    r1 = await web_search(query="a")
    r2 = await web_search(query="b")
except Exception:
    pass
raise ValueError("after")
"""


def _counting_research_agent(model: FunctionModel) -> tuple[Agent, dict]:
    """`_research_agent` plus a tool-entry counter: proves the tool body ran
    even when the script swallows the refusal (E3's P4 was rejected by the
    sandbox type check before any tool ran, so it measured nothing)."""
    agent = Agent(model, deps_type=ResearchDeps, capabilities=[CodeMode()])
    calls = {"n": 0}

    @agent.tool
    async def web_search(ctx: RunContext[ResearchDeps], query: str) -> str:
        """Search the web."""
        calls["n"] += 1
        await charge_scoped(
            ctx.deps, search=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd
        )
        return f"results for {query}"

    return agent, calls


@pytest.mark.asyncio
async def test_a_swallowed_refusal_then_another_error_degrades_naming_the_terminal_error():
    # The terminal error's first sentence is pydantic-ai's fixed retry
    # wrapper ("Tool 'run_code' exceeded max retries count of 3", the
    # original error rides only in the cause chain -- tool_manager.py
    # `_check_max_retries`, E3's chains), so that is what the gap carries
    # alongside the refusal.
    model = _run_code_model(SWALLOW_THEN_FAIL)
    agent, calls = _counting_research_agent(model)
    out = await research_subquestion(_inp("t8-c4"), _model=model, _agent=agent)

    assert calls["n"] >= 1, "the tool body never ran (E3's P4 trap)"
    assert out.failed is False
    why = out.brief.gaps[0].why_it_matters
    assert "search budget exhausted" in why
    assert why.endswith("Tool 'run_code' exceeded max retries count of 3")
    assert "http" not in why


class _NotingThenUmb:
    """5a: refuses a charge on the run's own deps, then dies in retry
    exhaustion (docs URL and all)."""

    async def run(self, prompt, **kw):
        kw["deps"].note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
        raise UnexpectedModelBehavior(
            "Tool 'run_code' exceeded max retries count of 3. Consider "
            "raising the retry limit, or see the docs on tool retries: "
            "https://example.invalid/docs"
        )


class _UmbNoNote:
    """5b: the same terminal error with nothing refused behind it."""

    async def run(self, prompt, **kw):
        raise UnexpectedModelBehavior("boom")


class _NotingThenBudget:
    """5c: a refusal noted, then an ordinary exhaustion."""

    async def run(self, prompt, **kw):
        kw["deps"].note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
        raise BudgetExceeded("x")


@pytest.mark.asyncio
async def test_retry_exhaustion_after_a_note_degrades_and_cuts_the_docs_url():
    out = await research_subquestion(_inp("t8-c5a"), _agent=_NotingThenUmb())
    assert out.failed is False
    why = out.brief.gaps[0].why_it_matters
    assert why.endswith("Tool 'run_code' exceeded max retries count of 3")
    assert "http" not in why


@pytest.mark.asyncio
async def test_retry_exhaustion_with_no_note_still_raises():
    with pytest.raises(UnexpectedModelBehavior):
        await research_subquestion(_inp("t8-c5b"), _agent=_UmbNoNote())


@pytest.mark.asyncio
async def test_budget_exceeded_with_a_note_keeps_todays_gap_text():
    out = await research_subquestion(_inp("t8-c5c"), _agent=_NotingThenBudget())
    assert out.brief.gaps[0].why_it_matters == "research stopped early: x"
