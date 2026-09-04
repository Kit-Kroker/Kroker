"""ResearchConfig gains fan-out bounds. The existing per-run caps are
REINTERPRETED as per-sub-question; max_run_cost_usd is the new run ceiling."""

from sdlc.core.models import (
    ResearchConfig,
)


def test_fan_out_defaults():
    cfg = ResearchConfig()
    assert cfg.max_sub_questions == 4
    assert cfg.max_run_cost_usd == 4.0
    assert cfg.max_refine_rounds == 1


def test_per_sub_question_caps_keep_their_values():
    # The NUMBERS are unchanged; only their meaning moved from per-run to
    # per-sub-question. Guards against a well-meaning "fix" that divides them.
    cfg = ResearchConfig()
    assert cfg.max_searches == 5
    assert cfg.max_fetches == 10
    assert cfg.max_cost_usd == 1.0
    assert cfg.max_requests == 40


def test_run_ceiling_covers_the_default_fan_out_width():
    cfg = ResearchConfig()
    assert cfg.max_run_cost_usd >= cfg.max_sub_questions * cfg.max_cost_usd


from sdlc.core.models import (
    RoleUsage,
)
from sdlc.stages.research.models import (
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)


def test_research_plan_carries_usage():
    # Returning a bare list of sub-questions silently drops one model call per
    # run -- the exact bug this type exists to prevent.
    plan = ResearchPlan()
    assert isinstance(plan.usage, RoleUsage)
    assert plan.sub_questions == []


def test_sub_question_finding_carries_usage_and_a_brief():
    f = SubQuestionFinding(
        sub_question=SubQuestion(id="sq-0", question="what?"), brief=ResearchBrief(summary="s")
    )
    assert isinstance(f.usage, RoleUsage)
    assert f.failed is False
    assert f.error == ""


def test_sub_question_finding_can_represent_a_permanent_failure():
    f = SubQuestionFinding(
        sub_question=SubQuestion(id="sq-1", question="what?"),
        brief=ResearchBrief(),
        failed=True,
        error="RefusalError: declined",
    )
    assert f.failed
    assert "declined" in f.error
