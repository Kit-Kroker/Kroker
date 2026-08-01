"""The primary research stage (feature.py) runs t_research.run() with no
try/except at all -- a pydantic-ai UsageLimitExceeded (the request_limit
ceiling) or a BudgetExceeded (the persisted search/fetch/cost cap, see
budget_store.py) propagates straight out and crashes the whole
FeatureWorkflow, taking down every other stage's records with it
(bench-todo-api-greenfield-1785485669: the research stage alone burned past
pydantic-ai's default request_limit=50, and the entire benchmark cell
recorded nothing but a stale oracle grade). research/toolset.py's
research_subquery already has the right shape for this -- catch the
exhaustion and substitute a partial ResearchBrief with the shortfall
recorded as a gap, exactly like an ordinary budget-exhausted mid-run call --
these tests pin the primary stage's version of that same fallback."""
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
