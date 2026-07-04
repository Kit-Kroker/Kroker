from sdlc.benchmarks.judge import JudgeInput, judge_artifact, _set_judge_fn


def test_judge_parses_valid_json():
    def fake(inp: JudgeInput) -> str:
        # rubric expects {"score": 0.0..1.0, "components": {...}}
        return '{"score": 0.82, "components": {"coverage": 0.9, "specificity": 0.74}}'
    _set_judge_fn(fake)
    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="score coverage 0..1",
        author_model="anthropic:claude-sonnet-4-6"))
    assert result.score == 0.82
    assert result.judge == "llm_judge"
    assert result.components["coverage"] == 0.9


def test_judge_returns_error_on_unparseable():
    _set_judge_fn(lambda inp: "not json at all")
    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6"))
    assert result.score is None
    assert result.judge == "error"


def test_judge_clamps_out_of_range_score():
    _set_judge_fn(lambda inp: '{"score": 1.5}')
    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6"))
    assert result.score == 1.0     # clamped
