"""The judge Literal must admit every value the workflow actually emits.

Regression test for the E-39 defect: judge="deep_review" was not a member,
so _stage_record raised ValidationError inside _run_deep_review's bare
`except Exception: return None` — the lens paid for its LLM call and
recorded nothing, silently, on every run.
"""
import pytest

from sdlc.benchmarks.models import QualityScore

# Every judge value emitted anywhere in workflows/feature.py.
EMITTED_JUDGES = [
    "contract", "llm_judge", "human_override", "error", "oracle",
    "deep_review", "adversary", "handoff",
]


@pytest.mark.parametrize("judge", EMITTED_JUDGES)
def test_judge_literal_admits_every_emitted_value(judge):
    assert QualityScore(score=1.0, judge=judge).judge == judge


def test_judge_literal_still_rejects_unknown():
    with pytest.raises(Exception):
        QualityScore(score=1.0, judge="not_a_judge")
