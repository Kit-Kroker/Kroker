"""The research stage is judged against a rubric, not hardcoded to a
contract score."""

import inspect

from sdlc.workflows import feature


def test_research_brief_is_judged():
    src = inspect.getsource(feature.FeatureWorkflow._pipeline)
    assert '"research"' in src
    assert "brief.model_dump_json()" in src
    assert "quality_score=_r_quality.score" in src


def test_research_record_no_longer_hardcodes_contract_judge():
    """The old record passed quality_score=None, judge="contract". Both must
    be gone from the SUCCESS-path research block, or the rubric can never
    affect a score.

    The research stage now has three `stage="research"` records: an early
    FAIL-path one for an ungrounded first brief, the success-path one, and a
    FAIL-path one for a refine round that lost grounding. Both FAIL-path
    records legitimately use quality_score=None, judge="error" (nothing was
    judged). So locate the SUCCESS record by its real-score marker rather
    than by position -- a position-based rindex silently targets whichever
    record happens to be last."""
    src = inspect.getsource(feature.FeatureWorkflow._pipeline)
    idx = src.index("quality_score=_r_quality.score")
    block = src[max(0, idx - 350) : idx + 50]
    assert "quality_score=None" not in block
    assert 'judge="contract"' not in block
