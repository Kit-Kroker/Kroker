"""026 T021 (FR-022, research R6): run 1's architect crash mode.

Run 1 died because the architect's `research` tool reached the research
agent, whose CodeMode `run_code` retried 3 times on a model's bad code, after
which pydantic-ai raised UnexpectedModelBehavior. `research_subquery_reported`
caught only BudgetExceeded and UsageLimitExceeded, so that exception escaped
the architect's tool activity and the child failed.

Decision (R6): add `except UnexpectedModelBehavior` beside UsageLimitExceeded.
It degrades to the gap brief with OUR text, never `str(exc)` (AM2/R9), and
still reports the spend. Only that type. Provider and other infra exceptions
keep propagating (residual R1).

MONTY: `pydantic_monty` and `pydantic_ai_harness.code_mode` import in the fast
tier, but a `run_code` call under TestModel is rejected by CodeMode's
type-checker, and tests/research/test_research_spike.py (finding B) records that
the drive path cannot be proven there. So the fast tier does not run a real
`run_code` loop. The stub below raises the exact type pydantic-ai raises after
the retries are exhausted (R6's verified chain), which is the boundary this
change owns.
"""

from __future__ import annotations

import json

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from sdlc.agents import roles
from sdlc.observability.sub_run_usage import SubRunUsage
from sdlc.stages.research import toolset
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps

_QUESTION = "what does the repo's retry policy look like?"
OUR_TEXT = "research tool exhausted its code-execution retries"
# What pydantic-ai actually puts in the message: the model's code error and the
# library's retry advice with its documentation URL. None of it may reach the brief.
LIBRARY_TEXT = (
    "Tool 'run_code' exceeded max retries count of 3: TypeError: unsupported "
    "operand for +: 'Result' and 'Result'. See https://ai.pydantic.dev/tools/"
)


class _ExhaustedRunCodeAgent:
    """Fake t_research. It banks known token counts on the caller-owned
    `usage=` kwarg (the way the real inner run does before it stops), then
    raises the exception it was handed."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def run(self, question, *args, **kwargs):
        usage = kwargs.get("usage")
        if usage is not None:
            usage.input_tokens += 40
            usage.output_tokens += 9
            usage.cache_read_tokens += 2
            usage.cache_write_tokens += 1
        raise self.exc


def _deps(**extra) -> ResearchDeps:
    return ResearchDeps(
        run_id="r1",
        provider="fake",
        max_searches=5,
        max_fetches=10,
        max_cost_usd=1.0,
        **extra,
    )


def _exhausted(monkeypatch, exc: BaseException) -> None:
    monkeypatch.setattr(roles, "t_research", _ExhaustedRunCodeAgent(exc))


# --- (1) the degrade: our text, no library text -------------------------------


@pytest.mark.asyncio
async def test_exhausted_code_retries_degrade_to_a_gap_brief_with_our_text(monkeypatch):
    _exhausted(monkeypatch, UnexpectedModelBehavior(LIBRARY_TEXT))

    brief, _report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    serialized = brief.model_dump_json()
    assert OUR_TEXT in serialized, "the degrade must name what happened, in our words"
    assert len(brief.gaps) == 1
    assert brief.gaps[0].what_is_missing == _QUESTION


@pytest.mark.asyncio
async def test_exhausted_code_retries_never_leak_the_library_text(monkeypatch):
    _exhausted(monkeypatch, UnexpectedModelBehavior(LIBRARY_TEXT))

    brief, _report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    serialized = brief.model_dump_json()
    assert "unsupported operand" not in serialized
    assert "exceeded max retries" not in serialized
    assert "pydantic" not in serialized.lower()
    assert "http" not in serialized
    # the structured fields are the brief's own text, not the exception's
    assert json.loads(serialized)["summary"] != LIBRARY_TEXT


# --- (2) the spend is still reported on the degrade path ----------------------


@pytest.mark.asyncio
async def test_exhausted_code_retries_still_report_the_spend_made_so_far(monkeypatch):
    _exhausted(monkeypatch, UnexpectedModelBehavior(LIBRARY_TEXT))

    _brief, report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    assert isinstance(report, SubRunUsage)
    assert (report.input_tokens, report.output_tokens) == (40, 9)
    assert (report.cache_read_tokens, report.cache_write_tokens) == (2, 1)


# --- (3) residual R1 stays: infra failures still propagate --------------------


@pytest.mark.asyncio
async def test_a_provider_failure_still_propagates(monkeypatch):
    """Only UnexpectedModelBehavior degrades. A provider 502 is infra, not a
    bound being exceeded, so it must keep failing the call (residual R1)."""
    _exhausted(monkeypatch, RuntimeError("provider 502"))

    with pytest.raises(RuntimeError, match="provider 502"):
        await toolset.research_subquery_reported(_deps(), _QUESTION)


# --- (4) the two existing degrades are pinned, so T022 cannot regress them ----


@pytest.mark.asyncio
async def test_budget_exhaustion_still_degrades_with_its_own_summary(monkeypatch):
    exc_text = "search budget exhausted (5 searches)"
    _exhausted(monkeypatch, BudgetExceeded(exc_text))

    brief, report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    assert len(brief.gaps) == 1
    assert brief.gaps[0].why_it_matters == exc_text
    assert brief.summary == (
        f"Research budget exhausted before this sub-question could be answered: {exc_text}"
    )
    assert isinstance(report, SubRunUsage)


@pytest.mark.asyncio
async def test_request_limit_still_degrades_with_its_own_summary(monkeypatch):
    exc = UsageLimitExceeded("The next request would exceed the request_limit of 7")
    _exhausted(monkeypatch, exc)

    brief, report = await toolset.research_subquery_reported(_deps(max_requests=7), _QUESTION)

    reason = "request limit exhausted (7 requests)"
    assert brief.gaps[0].why_it_matters == reason
    assert brief.summary == (
        f"Research stopped before this sub-question could be answered: {reason}"
    )
    assert "Consider raising the limit" not in brief.model_dump_json()
    assert isinstance(report, SubRunUsage)


# --- chaos / edge cases (026 T021, chaos QA) --------------------------------
#
# Where OUR text must land: _gap_brief puts the sub-question in
# `what_is_missing` and the reason in `why_it_matters`. The degrade's reason
# is OUR text, so it must be a verbatim substring of `why_it_matters`, and the
# question must still name the sub-question.


@pytest.mark.asyncio
async def test_edge_our_text_is_verbatim_in_the_gap_and_the_question_is_kept(monkeypatch):
    _exhausted(monkeypatch, UnexpectedModelBehavior(LIBRARY_TEXT))

    brief, _report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    gap = brief.gaps[0]
    assert OUR_TEXT in gap.why_it_matters  # exact substring, not a paraphrase
    assert gap.what_is_missing == _QUESTION  # the brief still names the sub-question
    assert _QUESTION in brief.model_dump_json()


@pytest.mark.asyncio
async def test_edge_other_unexpected_behaviour_causes_degrade_the_same_way(monkeypatch):
    """The except type is the boundary, not the message: an output-validation
    exhaustion is a different cause and degrades with the same OUR text, and
    its library wording never leaks."""
    output_msg = "Exceeded maximum output retries (1)"
    _exhausted(monkeypatch, UnexpectedModelBehavior(output_msg))

    brief, report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    assert OUR_TEXT in brief.gaps[0].why_it_matters
    serialized = brief.model_dump_json()
    assert output_msg not in serialized
    assert isinstance(report, SubRunUsage)


@pytest.mark.asyncio
async def test_edge_degrade_fires_on_the_outer_type_even_with_a_provider_cause(monkeypatch):
    """UnexpectedModelBehavior wrapping a RuntimeError cause: the except is on
    the outer type, so it degrades. The provider cause text must not leak."""
    exc = UnexpectedModelBehavior("model misbehaved")
    exc.__cause__ = RuntimeError("provider 502 from upstream")
    _exhausted(monkeypatch, exc)

    brief, _report = await toolset.research_subquery_reported(_deps(), _QUESTION)

    assert OUR_TEXT in brief.gaps[0].why_it_matters
    assert "provider 502" not in brief.model_dump_json()


@pytest.mark.asyncio
async def test_edge_a_runtime_error_caused_by_unexpected_behaviour_still_propagates(monkeypatch):
    """No cause-walking: a RuntimeError whose __cause__ is an
    UnexpectedModelBehavior is infra by its outer type, so it propagates."""
    exc = RuntimeError("provider call failed")
    exc.__cause__ = UnexpectedModelBehavior("Exceeded maximum output retries (1)")
    _exhausted(monkeypatch, exc)

    with pytest.raises(RuntimeError, match="provider call failed"):
        await toolset.research_subquery_reported(_deps(), _QUESTION)
