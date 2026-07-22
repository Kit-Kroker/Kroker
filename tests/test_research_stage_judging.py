"""The research stage is judged against a rubric, not hardcoded to a
contract score."""
import inspect

from sdlc.workflows import feature


def test_research_brief_is_judged():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    assert '"research"' in src
    assert "brief.model_dump_json()" in src
    assert "quality_score=_r_quality.score" in src


def test_research_record_no_longer_hardcodes_contract_judge():
    """The old record passed quality_score=None, judge="contract". Both must
    be gone from the SUCCESS-path research block, or the rubric can never
    affect a score.

    2026-07-20: research now has two `stage="research"` records — an early
    FAIL-path one (ungrounded brief, degrades instead of blocking; legitimately
    quality_score=None, judge="error" since nothing was judged) and the
    original success-path one. `rindex` targets the latter — the one this
    test actually guards."""
    src = inspect.getsource(feature.FeatureWorkflow.run)
    start = src.rindex('stage="research"')
    block = src[start:start + 400]
    assert "quality_score=None" not in block
    assert 'judge="contract"' not in block
