"""Fan-out wiring: failure tiers and usage folding.

These exercise the workflow's helpers directly rather than booting Temporal --
the stage's ORCHESTRATION decisions are what matter here, and the activities
themselves are covered by Tasks 7-9."""
import pytest

from sdlc.models import (ResearchBrief, RoleUsage, SubQuestion,
                         SubQuestionFinding)
from sdlc.workflows.feature import (RESEARCH_PLAN_ACT, RESEARCH_SQ_ACT,
                                    RESEARCH_SYNTH_ACT,
                                    _findings_from_results)


def _ok(sq_id: str) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question="q"),
        brief=ResearchBrief(summary="s"),
        usage=RoleUsage(role="research", model="m", calls=1,
                        input_tokens=10, output_tokens=5))


def test_all_successful_results_pass_through():
    subs = [SubQuestion(id="sq-0", question="q0")]
    out = _findings_from_results(subs, [_ok("sq-0")])
    assert len(out) == 1
    assert out[0].failed is False


def test_an_exception_becomes_a_failed_finding_not_a_raise():
    subs = [SubQuestion(id="sq-0", question="q0")]
    out = _findings_from_results(subs, [RuntimeError("worker died")])
    assert len(out) == 1
    assert out[0].failed is True
    assert "worker died" in out[0].error
    assert out[0].sub_question.id == "sq-0"


def test_one_failure_does_not_discard_its_siblings():
    subs = [SubQuestion(id="sq-0", question="q0"),
            SubQuestion(id="sq-1", question="q1")]
    out = _findings_from_results(subs, [RuntimeError("boom"), _ok("sq-1")])
    assert [f.failed for f in out] == [True, False]


def test_sub_question_activity_config_satisfies_the_heartbeat_invariant():
    # interval < heartbeat_timeout < start_to_close. Violating it either times
    # out a healthy activity or leaves a dead worker undetected until
    # start_to_close.
    from sdlc.research.stage import HEARTBEAT_INTERVAL_SECONDS
    hb = RESEARCH_SQ_ACT["heartbeat_timeout"].total_seconds()
    stc = RESEARCH_SQ_ACT["start_to_close_timeout"].total_seconds()
    assert HEARTBEAT_INTERVAL_SECONDS < hb < stc


def test_budget_exhaustion_is_classified_non_retryable():
    # The counter is PERSISTED. Retrying hits the same exhausted cap -- six
    # guaranteed failures with backoff.
    names = RESEARCH_SQ_ACT["retry_policy"].non_retryable_error_types
    assert "BudgetExceeded" in names
    assert "UsageLimitExceeded" in names


def test_plan_and_synthesis_configs_exist_with_retries():
    assert RESEARCH_PLAN_ACT["retry_policy"].maximum_attempts >= 3
    assert RESEARCH_SYNTH_ACT["retry_policy"].maximum_attempts >= 3
