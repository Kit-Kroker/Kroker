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
    be gone from the research block, or the rubric can never affect a score."""
    src = inspect.getsource(feature.FeatureWorkflow.run)
    start = src.index('stage="research"')
    block = src[start:start + 400]
    assert "quality_score=None" not in block
    assert 'judge="contract"' not in block
