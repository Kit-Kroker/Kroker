"""The staged judge: rubric -> evaluation steps -> score.

A single-shot "score this against the rubric" prompt gave a gutted clarify
prompt 1.00 (OQ-P5). Generating explicit evaluation steps first is G-Eval's
actual mechanism, and the one half of it that works without logprobs --
which google:gemini-3.5-flash does not expose."""

import pytest

from sdlc.benchmarks import judge as judge_mod
from sdlc.benchmarks.judge import _clear_step_cache, generate_steps


@pytest.fixture(autouse=True)
def _clean_cache():
    _clear_step_cache()
    yield
    _clear_step_cache()


def test_generate_steps_parses_the_step_list(monkeypatch):
    calls = []

    def _fake(model, system_prompt, user_prompt):
        calls.append(model)
        return '{"steps": ["Check every activity is named", "Check red marking"]}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    steps = generate_steps("some rubric", "google:gemini-3.5-flash")
    assert steps == ["Check every activity is named", "Check red marking"]
    assert calls == ["google:gemini-3.5-flash"]


def test_generate_steps_is_cached_per_rubric_sha(monkeypatch):
    """One call per rubric per process. Baseline and working must be scored
    against IDENTICAL steps or the comparison is not a comparison."""
    calls = []

    def _fake(model, system_prompt, user_prompt):
        calls.append(user_prompt)
        return '{"steps": ["a"]}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    generate_steps("rubric one", "m")
    generate_steps("rubric one", "m")
    assert len(calls) == 1

    generate_steps("rubric two", "m")
    assert len(calls) == 2


def test_generate_steps_recaches_per_judge_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        judge_mod, "_run_judge_agent", lambda m, s, u: calls.append(m) or '{"steps": ["a"]}'
    )
    generate_steps("r", "model-a")
    generate_steps("r", "model-b")
    assert calls == ["model-a", "model-b"]


def test_generate_steps_raises_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: "not json")
    with pytest.raises(ValueError):
        generate_steps("r", "m")


def test_generate_steps_raises_on_an_empty_step_list(monkeypatch):
    """Zero steps would silently degrade phase 2 back to the single-shot
    judge under the new label -- the discontinuity marker would then lie."""
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: '{"steps": []}')
    with pytest.raises(ValueError):
        generate_steps("r", "m")


def test_default_judge_runs_both_phases(monkeypatch):
    prompts = []

    def _fake(model, system_prompt, user_prompt):
        prompts.append(system_prompt)
        if "checklist" in system_prompt:
            return '{"steps": ["Check the six activities are all named"]}'
        assert "Check the six activities are all named" in user_prompt
        return '{"score": 0.4, "components": {"scope_preserved": 0.4}}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    qs = judge_mod.judge_artifact.sync(
        judge_mod.JudgeInput(
            artifact_json='{"summary": "x"}',
            rubric="the rubric",
            author_model="anthropic:glm-5.2",
            judge_model="google:gemini-3.5-flash",
        )
    )
    assert len(prompts) == 2
    assert qs.score == 0.4
    assert qs.judge == "staged_rubric"


def test_step_generation_failure_is_not_measured(monkeypatch):
    """NOT a fallback to the old judge: that would make the discontinuity
    marker lie about which instrument produced the number."""
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: "garbage")
    qs = judge_mod.judge_artifact.sync(
        judge_mod.JudgeInput(artifact_json="{}", rubric="r", author_model="a", judge_model="b")
    )
    assert qs.score is None
    assert qs.judge == "error"


def test_injected_judge_fn_still_short_circuits_both_phases():
    """The _set_judge_fn seam is unchanged, so every existing test that
    injects a fake keeps working and makes no model call."""
    judge_mod._set_judge_fn(lambda _i: '{"score": 0.7, "components": {}}')
    try:
        qs = judge_mod.judge_artifact.sync(
            judge_mod.JudgeInput(artifact_json="{}", rubric="r", author_model="a", judge_model="b")
        )
    finally:
        judge_mod._set_judge_fn(None)
    assert qs.score == 0.7
    assert qs.judge == "staged_rubric"
