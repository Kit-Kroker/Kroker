"""A capped sub-question run reports what it spent (feature 008, plan D5).

This module pins the WIRE side of the refusal record: the record the
exhaustion handler will own lives in memory on `ResearchDeps` and must
never change what crosses the activity boundary. An input carrying a
noted refusal serializes to the same bytes as one without it, the
serialized deps keep exactly today's twelve keys, and a fresh round-trip
starts with an empty record -- so no replay, history or wire payload a
run has ever produced sees the record (FR-010, EC9).

Cases 1 and 4 drive the real `_research_subquestion_impl` seam: a run
that hits its request limit must return the spend of every completed
request, and a clean run must report exactly what an identical direct
run reports.
"""

import json

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from sdlc.core.models import RoleUsage
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps
from sdlc.stages.research.models import ResearchBrief, SubQuestion
from sdlc.stages.research.prompts import sub_question_prompt
from sdlc.stages.research.stage import SubQuestionInput
from sdlc.stages.research.stage import _research_subquestion_impl as research_subquestion


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _deps() -> ResearchDeps:
    return ResearchDeps(
        run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
    )


def _inp(max_requests: int = 40) -> SubQuestionInput:
    """The plan-D5 input shape: `_inp()` from test_research_subquestion_activity."""
    return SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="what is the timeline?"),
        deps=_deps(),
        model="test-model",
        max_requests=max_requests,
        max_run_cost_usd=4.0,
    )


def test_input_json_is_byte_identical_before_and_after_a_refusal():
    inp = _inp()
    before = inp.model_dump_json()
    inp.deps.note_refusal("x")
    assert inp.model_dump_json() == before


def test_deps_json_is_byte_identical_before_and_after_a_refusal():
    d = _deps()
    before = d.model_dump_json()
    d.note_refusal("x")
    assert d.model_dump_json() == before


def test_serialized_deps_keys_stay_exactly_today_twelve_with_a_refusal_noted():
    d = _deps()
    d.note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
    assert sorted(json.loads(d.model_dump_json()).keys()) == [
        "budget",
        "max_cost_usd",
        "max_fetches",
        "max_run_cost_usd",
        "max_searches",
        "memory_backend",
        "memory_bank",
        "memory_base_url",
        "memory_watermark",
        "provider",
        "run_id",
        "scope",
    ]


def test_a_round_trip_starts_with_an_empty_refusal_record():
    d = _deps()
    d.note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
    round_tripped = ResearchDeps.model_validate_json(d.model_dump_json())
    assert round_tripped.refusals == []


def test_a_fresh_deps_has_an_empty_refusal_record():
    assert _deps().refusals == []


def test_note_refusal_appends_in_order():
    d = _deps()
    d.note_refusal("first")
    d.note_refusal("second")
    assert d.refusals == ["first", "second"]


def test_reset_refusals_on_a_copy_leaves_the_source_record_intact():
    # model_copy shares the private list (measured, E4 A4): reset must hand the
    # copy a fresh list, never mutate the source's.
    d = _deps()
    d.note_refusal("first")
    d.note_refusal("second")
    c = d.model_copy(update={"scope": "sq-9"})
    c.reset_refusals()
    assert d.refusals == ["first", "second"]
    assert c.refusals == []


# ---------------------------------------------------------------------------
# Plan-D5 usage cases 1 and 4: the spend a capped or clean run reports,
# through the real impl seam (E1's harness shape, no CodeMode).


def _cap_agent(model: FunctionModel) -> Agent:
    """A real agent shaped like the research one: ResearchDeps, one trivial
    tool, ResearchBrief output."""
    agent = Agent(model, deps_type=ResearchDeps, output_type=ResearchBrief)

    @agent.tool
    async def trivial(ctx: RunContext[ResearchDeps], note: str) -> str:
        """A trivial tool the scripted model can call forever."""
        return "ok"

    return agent


def _stubborn_model() -> FunctionModel:
    """Calls the trivial tool on every turn and never concludes."""

    def fn(messages, info):
        return ModelResponse(parts=[ToolCallPart("trivial", {"note": "again"})])

    return FunctionModel(fn)


def _concluding_model() -> FunctionModel:
    """Answers at once with a valid brief via the final_result tool. A
    BaseModel output's tool schema is the model's own flattened fields
    (pydantic-ai wraps only non-model outputs in a `response` arg)."""

    def fn(messages, info):
        call = ToolCallPart("final_result", args={"summary": "the timeline is 2027"})
        return ModelResponse(parts=[call])

    return FunctionModel(fn)


@pytest.mark.asyncio
async def test_request_limit_exhaustion_returns_the_spend_of_every_completed_request():
    model = _stubborn_model()
    out = await research_subquestion(_inp(max_requests=3), _model=model, _agent=_cap_agent(model))
    assert out.failed is False
    assert len(out.brief.gaps) == 1
    assert "request_limit" in out.brief.gaps[0].why_it_matters
    assert out.usage.input_tokens > 0
    assert out.usage.output_tokens > 0
    assert out.usage.calls == 1


@pytest.mark.asyncio
async def test_a_clean_run_is_unchanged_in_finding_and_usage():
    inp = _inp()
    model = _concluding_model()
    out = await research_subquestion(inp, _model=model, _agent=_cap_agent(model))

    assert out.failed is False
    assert out.brief.summary == "the timeline is 2027"
    assert out.usage.calls == 1

    # FR-010: an identical run made directly reports the same numbers.
    prompt = sub_question_prompt(inp.sub_question.question)
    deps = inp.deps.model_copy(
        update={
            "budget": inp.deps.budget.model_copy(),
            "scope": inp.sub_question.id,
            "max_run_cost_usd": inp.max_run_cost_usd,
        }
    )
    direct_usage = RunUsage()
    await _cap_agent(_concluding_model()).run(prompt, deps=deps, usage=direct_usage)
    assert out.usage.input_tokens == direct_usage.input_tokens
    assert out.usage.output_tokens == direct_usage.output_tokens
    assert out.usage.cache_read_tokens == direct_usage.cache_read_tokens
    assert out.usage.cache_write_tokens == direct_usage.cache_write_tokens


# ---------------------------------------------------------------------------
# Plan-D5 usage cases 2 and 3: a tool-refused run still reports the spend
# before the refusal; a run refused before any request keeps today's zero
# usage object.


def _refusing_agent(model: FunctionModel) -> Agent:
    """Like `_cap_agent`, but the tool refuses its second call with today's
    search-budget message (plan D5 case 2: a charge refused mid-run)."""
    agent = Agent(model, deps_type=ResearchDeps, output_type=ResearchBrief)
    calls = 0

    @agent.tool
    async def trivial(ctx: RunContext[ResearchDeps], note: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BudgetExceeded("search budget exhausted (1 searches)")
        return "ok"

    return agent


class _Boom:
    """Stands in for the research agent when run() must raise immediately."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(self, *a, **kw):
        raise self._exc


@pytest.mark.asyncio
async def test_a_tool_refused_mid_run_reports_the_spend_before_it():
    model = _stubborn_model()
    out = await research_subquestion(_inp(), _model=model, _agent=_refusing_agent(model))
    assert out.failed is False
    assert len(out.brief.gaps) == 1
    assert "search budget exhausted" in out.brief.gaps[0].why_it_matters
    assert out.usage.input_tokens > 0
    assert out.usage.output_tokens > 0
    assert out.usage.calls == 1


@pytest.mark.asyncio
async def test_exhaustion_before_any_request_returns_todays_zero_usage():
    # EC1: the zero object is load-bearing -- the workflow's fold still skips
    # a sub-question that was refused before any request completed.
    inp = _inp()
    out = await research_subquestion(inp, _agent=_Boom(BudgetExceeded("search budget exhausted")))
    assert out.usage == RoleUsage(role="research", model=inp.model)
