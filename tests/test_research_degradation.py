"""The research stage never lets a model-call failure escape to the workflow
runner. Per-sub-question exhaustion (BudgetExceeded / UsageLimitExceeded) is
caught inside research_subquestion and turned into a gap; a plan or synthesis
ActivityError (after its retries exhaust) is caught at the stage call site
and substitutes a _degraded_research_brief (spec §8 tier 1;
bench-todo-api-greenfield-1785485669: an uncaught UsageLimitExceeded once
killed the whole FeatureWorkflow, taking every other stage's records with
it). _degraded_research_brief is the shape both paths land on -- these tests
pin it: no findings, the shortfall recorded as a gap, empty grounded_findings
so verify_brief passes it through the ordinary success path."""

from pydantic_ai.exceptions import UsageLimitExceeded

from sdlc.models import ResearchBrief
from sdlc.research.deps import BudgetExceeded
from sdlc.workflows.feature import _degraded_research_brief


def test_degraded_brief_on_budget_exceeded_has_no_findings():
    brief = _degraded_research_brief(BudgetExceeded("fetch budget exhausted (10 fetches)"))
    assert isinstance(brief, ResearchBrief)
    assert brief.grounded_findings == []
    assert brief.inferred_findings == []


def test_degraded_brief_records_the_shortfall_as_a_gap():
    brief = _degraded_research_brief(BudgetExceeded("fetch budget exhausted (10 fetches)"))
    assert len(brief.gaps) == 1
    assert "fetch budget exhausted" in brief.gaps[0].why_it_matters


def test_degraded_brief_on_usage_limit_exceeded_has_no_findings():
    brief = _degraded_research_brief(UsageLimitExceeded("request_limit of 40 exceeded"))
    assert isinstance(brief, ResearchBrief)
    assert brief.grounded_findings == []
    assert "request_limit" in brief.gaps[0].why_it_matters


def test_degraded_brief_is_never_grounded_so_verification_trivially_passes():
    # verify_brief_activity only inspects grounded_findings for a fetched
    # source_url; an empty list means it always returns zero violations,
    # so the degraded brief flows through the SAME success path as a normal
    # (if disappointing) brief instead of tripping the grounding gate too.
    brief = _degraded_research_brief(BudgetExceeded("x"))
    assert brief.grounded_findings == []
