import pytest

import sdlc.benchmarks.judge as judge_mod
from sdlc.benchmarks.judge import (
    JudgeInput,
    _build_judge_input,
    _default_judge,
    _run_judge_agent,
    _set_judge_fn,
    judge_artifact,
)


@pytest.fixture(autouse=True)
def _reset_judge_fn():
    """Ensure no judge fn leaks between tests (default vs injected)."""
    yield
    _set_judge_fn(None)


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


def test_judge_input_accepts_judge_model():
    inp = JudgeInput(artifact_json="{}", rubric="r",
                     author_model="anthropic:claude-sonnet-4-6",
                     judge_model="openai/gpt-5.2")
    assert inp.judge_model == "openai/gpt-5.2"


def test_judge_input_judge_model_defaults_none():
    inp = JudgeInput(artifact_json="{}", rubric="r", author_model="m")
    assert inp.judge_model is None


# --- A2: production judge default ----------------------------------------

def test_default_judge_returns_agent_response(monkeypatch):
    """_default_judge calls _run_judge_agent with judge_model + prompt and
    returns the raw response string (no parsing here)."""
    captured = {}
    canned = '{"score": 0.77, "components": {"coverage": 0.8}}'

    def fake_runner(model, system_prompt, user_prompt):
        captured["model"] = model
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return canned

    monkeypatch.setattr(judge_mod, "_run_judge_agent", fake_runner)
    _set_judge_fn(None)  # use the production default

    raw = _default_judge(JudgeInput(
        artifact_json='{"x": 1}', rubric="score coverage 0..1",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2"))

    assert raw == canned
    assert captured["model"] == "openai/gpt-5.2"
    # the user prompt must carry both the rubric and the artifact
    assert "score coverage 0..1" in captured["user_prompt"]
    assert '{"x": 1}' in captured["user_prompt"]
    # system prompt must demand JSON-only output
    assert "json" in captured["system_prompt"].lower()


def test_default_judge_flows_through_judge_sync(monkeypatch):
    """End-to-end: production default -> _judge_sync clamps/parses into a
    QualityScore(judge='llm_judge')."""
    monkeypatch.setattr(
        judge_mod, "_run_judge_agent",
        lambda model, system_prompt, user_prompt:
        '{"score": 0.42, "components": {"a": 0.5}}')
    _set_judge_fn(None)

    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2"))

    assert result.judge == "llm_judge"
    assert result.score == 0.42
    assert result.components == {"a": 0.5}


def test_default_judge_clamps_through_judge_sync(monkeypatch):
    """A score above 1.0 from the agent is clamped, still judge='llm_judge'."""
    monkeypatch.setattr(
        judge_mod, "_run_judge_agent",
        lambda model, system_prompt, user_prompt: '{"score": 1.9}')
    _set_judge_fn(None)

    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2"))

    assert result.judge == "llm_judge"
    assert result.score == 1.0


def test_default_judge_raises_when_model_none():
    """No judge_model -> RuntimeError inside _judge_sync -> judge='error'."""
    _set_judge_fn(None)

    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model=None))

    assert result.judge == "error"
    assert result.score is None


def test_injectable_boundary_overrides_default(monkeypatch):
    """_set_judge_fn(fake) must win; the production default must NOT run."""
    _set_judge_fn(lambda inp: '{"score": 0.99, "components": {}}')

    def boom(model, system_prompt, user_prompt):
        raise AssertionError(
            "production _run_judge_agent must not be called when a judge "
            "fn is injected via _set_judge_fn")

    monkeypatch.setattr(judge_mod, "_run_judge_agent", boom)

    result = judge_artifact.sync(JudgeInput(
        artifact_json="{}", rubric="r",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2"))

    assert result.judge == "llm_judge"
    assert result.score == 0.99


def test_run_judge_agent_uses_pydantic_ai():
    """Exercises the REAL _run_judge_agent seam (Agent construction +
    run_sync + .output extraction) via TestModel — no live LLM call. The
    patched tests above skip this, so this guards the pydantic-ai wiring."""
    from pydantic_ai.models.test import TestModel

    canned = '{"score": 0.5, "components": {"k": 0.1}}'
    raw = _run_judge_agent(
        TestModel(custom_output_text=canned), "sys", "user prompt")
    assert raw == canned


# --- A3: JudgeInput construction helper ----------------------------------

def test_build_judge_input_returns_input_when_rubric_present():
    ji = _build_judge_input(
        artifact_json='{"summary": "login"}',
        rubrics={"clarifier": "score materiality 0..1"},
        stage="clarifier",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2",
    )
    assert ji is not None
    assert isinstance(ji, JudgeInput)
    assert ji.artifact_json == '{"summary": "login"}'
    assert ji.rubric == "score materiality 0..1"
    assert ji.author_model == "anthropic:claude-sonnet-4-6"
    assert ji.judge_model == "openai/gpt-5.2"


def test_build_judge_input_passes_judge_model_none_through():
    ji = _build_judge_input(
        artifact_json="{}",
        rubrics={"architect": "r"},
        stage="architect",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model=None,
    )
    assert ji is not None
    assert ji.judge_model is None


def test_build_judge_input_returns_none_when_stage_missing():
    ji = _build_judge_input(
        artifact_json="{}",
        rubrics={"architect": "r"},   # no "clarifier" key
        stage="clarifier",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2",
    )
    assert ji is None


def test_build_judge_input_returns_none_when_rubric_empty():
    # an empty-string rubric is treated as "no rubric" so the caller
    # skips judging gracefully (no stage fails for a blank rubric).
    ji = _build_judge_input(
        artifact_json="{}",
        rubrics={"clarifier": ""},
        stage="clarifier",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2",
    )
    assert ji is None


def test_build_judge_input_supports_research_key():
    ji = _build_judge_input(
        artifact_json='{"findings": []}',
        rubrics={"research": "score grounding 0..1"},
        stage="research",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is not None
    assert ji.rubric == "score grounding 0..1"


def test_build_judge_input_research_absent_returns_none():
    """A case with no research rubric must skip judging gracefully rather
    than fail the stage."""
    ji = _build_judge_input(
        artifact_json='{"findings": []}',
        rubrics={"clarifier": "r"},
        stage="research",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is None


def test_build_judge_input_supports_qa_key():
    ji = _build_judge_input(
        artifact_json='{"tests_passed": true, "issues": []}',
        rubrics={"qa": "score determinism 0..1"},
        stage="qa",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is not None
    assert ji.rubric == "score determinism 0..1"
