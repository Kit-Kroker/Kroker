"""016 T007: the judge's output budget (ruling R3, plan D-8).

Split out of tests/test_benchmark_judge.py when the 016 additions
crossed the 1000-line ceiling (the file-size ratchet is the authority).
The process seam is exact: every test here is about the judge's
max_tokens budget and its call-time env read; the parent file keeps the
judge's parsing/retry/staged-call contract tests.
"""

import asyncio

import pytest

import sdlc.benchmarks.judge as judge_mod
from sdlc.benchmarks.judge import JudgeInput, _set_judge_fn, judge_artifact


@pytest.fixture(autouse=True)
def _reset_judge_fn():
    """Ensure no judge fn leaks between tests (default vs injected)."""
    yield
    _set_judge_fn(None)


# --- 016 T007 (RED): the judge output budget (R3, D-8) -------------------------


def _run_staged_judge_recording_settings(monkeypatch, recorded) -> None:
    """Drive the production staged judge (judge_artifact, no injected fn)
    over a FunctionModel that records info.model_settings of every call
    and serves the canned step/scoring responses -- the same shape as
    test_judge_artifact_runs_the_sync_judge_off_the_event_loop."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    def _handler(messages, info):
        recorded.append(info.model_settings)
        user_text = ""
        for m in messages:
            if isinstance(m, ModelRequest):
                for part in m.parts:
                    content = getattr(part, "content", None)
                    if isinstance(content, str):
                        user_text = content
        if user_text.startswith("Rubric:"):
            return ModelResponse(
                parts=[TextPart('{"steps": ["does the artifact follow the rubric?"]}')]
            )
        return ModelResponse(parts=[TextPart('{"score": 0.5, "components": {}}')])

    monkeypatch.setattr(judge_mod, "resolve_model", lambda _model: FunctionModel(_handler))
    _set_judge_fn(None)  # the production default must run, no injected fn

    inp = JudgeInput(
        artifact_json='{"summary": "login"}',
        rubric="score clarity 0..1",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="test-stub",  # non-empty; resolve_model is stubbed above
        vetoes_yaml="",
    )
    judge_mod._clear_step_cache()  # generate_steps must really run the stub
    try:
        result = asyncio.run(judge_artifact(inp))
    finally:
        judge_mod._clear_step_cache()

    # Harness guard: the staged run itself must be healthy, so a red below
    # is about the budget, not about the staged path.
    assert result.judge == "staged_rubric"
    assert result.score == 0.5


def test_judge_staged_calls_carry_the_default_max_tokens(monkeypatch):
    """R3/D-8: with SDLC_JUDGE_MAX_TOKENS unset, BOTH staged calls (step
    generation, then scoring) run with model_settings.max_tokens ==
    16000, the DEFAULT_JUDGE_MAX_TOKENS."""
    monkeypatch.delenv("SDLC_JUDGE_MAX_TOKENS", raising=False)
    recorded: list = []
    _run_staged_judge_recording_settings(monkeypatch, recorded)

    assert len(recorded) == 2, f"expected the two staged calls, got {len(recorded)}"
    for call, settings in enumerate(recorded):
        assert settings is not None, f"call {call}: model_settings missing"
        assert settings.get("max_tokens") == 16000


def test_judge_staged_calls_carry_the_env_max_tokens(monkeypatch):
    """R3/D-8: with SDLC_JUDGE_MAX_TOKENS set, both staged calls see
    exactly that value."""
    monkeypatch.setenv("SDLC_JUDGE_MAX_TOKENS", "22222")
    recorded: list = []
    _run_staged_judge_recording_settings(monkeypatch, recorded)

    assert len(recorded) == 2, f"expected the two staged calls, got {len(recorded)}"
    for call, settings in enumerate(recorded):
        assert settings is not None, f"call {call}: model_settings missing"
        assert settings.get("max_tokens") == 22222


def test_judge_module_exposes_the_budget_constants():
    """Names: the judge module exposes JUDGE_MAX_TOKENS_ENV and
    DEFAULT_JUDGE_MAX_TOKENS."""
    assert judge_mod.JUDGE_MAX_TOKENS_ENV == "SDLC_JUDGE_MAX_TOKENS"
    assert judge_mod.DEFAULT_JUDGE_MAX_TOKENS == 16000


# --- 016 T007 (RED, chaos): the judge budget is read at call time --------------


def test_judge_max_tokens_follows_the_env_between_two_runs_in_one_process(monkeypatch):
    """D-8: house style (paths.py) -- the value is read at call time, never
    captured at import or on first use. One test, two staged runs, the env
    changed between them: each run's calls see the value current at that
    run."""
    first: list = []
    monkeypatch.setenv("SDLC_JUDGE_MAX_TOKENS", "11111")
    _run_staged_judge_recording_settings(monkeypatch, first)

    second: list = []
    monkeypatch.setenv("SDLC_JUDGE_MAX_TOKENS", "22222")
    _run_staged_judge_recording_settings(monkeypatch, second)

    assert len(first) == 2
    assert len(second) == 2
    for settings in first:
        assert settings is not None
        assert settings.get("max_tokens") == 11111
    for settings in second:
        assert settings is not None
        assert settings.get("max_tokens") == 22222


def test_judge_max_tokens_empty_env_means_the_default(monkeypatch):
    """An empty SDLC_JUDGE_MAX_TOKENS is unset, as private_cases_dir treats
    an empty SDLC_PRIVATE_CASES_ROOT: the default 16000, no ValueError."""
    monkeypatch.setenv("SDLC_JUDGE_MAX_TOKENS", "")
    recorded: list = []
    _run_staged_judge_recording_settings(monkeypatch, recorded)

    assert len(recorded) == 2
    for settings in recorded:
        assert settings is not None
        assert settings.get("max_tokens") == 16000
