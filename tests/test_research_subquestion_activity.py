"""research_subquestion: one sub-question, one activity, one budget scope.

Budget exhaustion DEGRADES (a partial brief with the shortfall as a gap); it
never crashes the stage. The counter is persisted, so an escaping
BudgetExceeded would retry against a cap that stays exhausted -- six
guaranteed failures with backoff."""

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel

from sdlc.research.deps import BudgetExceeded, ResearchDeps
from sdlc.research.stage import SubQuestionInput
from sdlc.research.stage import _research_subquestion_impl as research_subquestion
from sdlc.stages.research.models import (
    SubQuestion,
    SubQuestionFinding,
)


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _inp(sq_id: str = "sq-0") -> SubQuestionInput:
    return SubQuestionInput(
        sub_question=SubQuestion(id=sq_id, question="what is the timeline?"),
        deps=ResearchDeps(
            run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
        ),
        model="test-model",
        max_requests=40,
        max_run_cost_usd=4.0,
    )


class _Boom:
    """Stands in for the research agent when we need run() to raise."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(self, *a, **kw):
        raise self._exc


@pytest.mark.asyncio
async def test_returns_a_finding_carrying_the_brief_and_usage():
    out = await research_subquestion(
        _inp(),
        _model=TestModel(call_tools=[], custom_output_args={"summary": "the timeline is 2027"}),
    )
    assert isinstance(out, SubQuestionFinding)
    assert out.sub_question.id == "sq-0"
    assert out.brief.summary == "the timeline is 2027"
    assert out.failed is False
    assert out.usage.role == "research"


@pytest.mark.asyncio
async def test_budget_exceeded_degrades_to_a_gap_not_a_raise():
    out = await research_subquestion(
        _inp(), _agent=_Boom(BudgetExceeded("search budget exhausted"))
    )
    assert out.failed is False, "budget exhaustion is a degradation, not a failure"
    assert out.brief.grounded_findings == []
    assert len(out.brief.gaps) == 1
    assert "search budget exhausted" in out.brief.gaps[0].why_it_matters


@pytest.mark.asyncio
async def test_usage_limit_exceeded_also_degrades():
    out = await research_subquestion(
        _inp(), _agent=_Boom(UsageLimitExceeded("request_limit of 40 exceeded"))
    )
    assert out.failed is False
    assert "request_limit" in out.brief.gaps[0].why_it_matters


@pytest.mark.asyncio
async def test_the_gap_is_attributed_to_this_sub_question():
    out = await research_subquestion(_inp("sq-3"), _agent=_Boom(BudgetExceeded("x")))
    assert out.brief.gaps[0].sub_question_id == "sq-3"


@pytest.mark.asyncio
async def test_a_degraded_brief_is_never_grounded():
    # verify_brief only inspects grounded_findings, so an empty list means the
    # degraded brief flows through the SAME success path as a normal brief
    # instead of tripping the grounding gate too.
    out = await research_subquestion(_inp(), _agent=_Boom(BudgetExceeded("x")))
    assert out.brief.grounded_findings == []


@pytest.mark.asyncio
async def test_an_unexpected_error_propagates_for_temporal_to_retry():
    # Budget/usage exhaustion is expected and degrades. Everything else is a
    # real failure Temporal should retry, then the workflow turns into a Gap.
    with pytest.raises(RuntimeError):
        await research_subquestion(_inp(), _agent=_Boom(RuntimeError("network")))
