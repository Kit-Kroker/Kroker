import asyncio

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
    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="score coverage 0..1",
            author_model="anthropic:claude-sonnet-4-6",
        )
    )
    assert result.score == 0.82
    assert result.judge == "staged_rubric"
    assert result.components["coverage"] == 0.9


def test_judge_returns_error_on_unparseable():
    _set_judge_fn(lambda inp: "not json at all")
    result = judge_artifact.sync(
        JudgeInput(artifact_json="{}", rubric="r", author_model="anthropic:claude-sonnet-4-6")
    )
    assert result.score is None
    assert result.judge == "error"


def test_judge_clamps_out_of_range_score():
    _set_judge_fn(lambda inp: '{"score": 1.5}')
    result = judge_artifact.sync(
        JudgeInput(artifact_json="{}", rubric="r", author_model="anthropic:claude-sonnet-4-6")
    )
    assert result.score == 1.0  # clamped


def test_judge_input_accepts_judge_model():
    inp = JudgeInput(
        artifact_json="{}",
        rubric="r",
        author_model="anthropic:claude-sonnet-4-6",
        judge_model="openai/gpt-5.2",
    )
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
        # E-83: _default_judge runs two phases. Phase 1 (step generation)
        # uses the steps system prompt; serve it steps JSON, not score JSON.
        if "checklist" in system_prompt:
            return '{"steps": ["Check coverage"]}'
        return canned

    monkeypatch.setattr(judge_mod, "_run_judge_agent", fake_runner)
    _set_judge_fn(None)  # use the production default

    raw = _default_judge(
        JudgeInput(
            artifact_json='{"x": 1}',
            rubric="score coverage 0..1",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model="openai/gpt-5.2",
        )
    )

    assert raw == canned
    assert captured["model"] == "openai/gpt-5.2"
    # the user prompt must carry both the rubric and the artifact
    assert "score coverage 0..1" in captured["user_prompt"]
    assert '{"x": 1}' in captured["user_prompt"]
    # system prompt must demand JSON-only output
    assert "json" in captured["system_prompt"].lower()


def test_default_judge_flows_through_judge_sync(monkeypatch):
    """End-to-end: production default -> _judge_sync clamps/parses into a
    QualityScore(judge='staged_rubric')."""

    def _fake(model, system_prompt, user_prompt):
        # E-83: serve phase-1 step generation before phase-2 scoring.
        if "checklist" in system_prompt:
            return '{"steps": ["a"]}'
        return '{"score": 0.42, "components": {"a": 0.5}}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    _set_judge_fn(None)

    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="r",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model="openai/gpt-5.2",
        )
    )

    assert result.judge == "staged_rubric"
    assert result.score == 0.42
    assert result.components == {"a": 0.5}


def test_default_judge_clamps_through_judge_sync(monkeypatch):
    """A score above 1.0 from the agent is clamped, still judge='staged_rubric'."""

    def _fake(model, system_prompt, user_prompt):
        if "checklist" in system_prompt:
            return '{"steps": ["a"]}'
        return '{"score": 1.9}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    _set_judge_fn(None)

    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="r",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model="openai/gpt-5.2",
        )
    )

    assert result.judge == "staged_rubric"
    assert result.score == 1.0


def test_default_judge_raises_when_model_none():
    """No judge_model -> RuntimeError inside _judge_sync -> judge='error'."""
    _set_judge_fn(None)

    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="r",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model=None,
        )
    )

    assert result.judge == "error"
    assert result.score is None


def test_injectable_boundary_overrides_default(monkeypatch):
    """_set_judge_fn(fake) must win; the production default must NOT run."""
    _set_judge_fn(lambda inp: '{"score": 0.99, "components": {}}')

    def boom(model, system_prompt, user_prompt):
        raise AssertionError(
            "production _run_judge_agent must not be called when a judge "
            "fn is injected via _set_judge_fn"
        )

    monkeypatch.setattr(judge_mod, "_run_judge_agent", boom)

    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="r",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model="openai/gpt-5.2",
        )
    )

    assert result.judge == "staged_rubric"
    assert result.score == 0.99


def test_run_judge_agent_uses_pydantic_ai():
    """Exercises the REAL _run_judge_agent seam (Agent construction +
    run_sync + .output extraction) via TestModel — no live LLM call. The
    patched tests above skip this, so this guards the pydantic-ai wiring."""
    from pydantic_ai.models.test import TestModel

    canned = '{"score": 0.5, "components": {"k": 0.1}}'
    raw = _run_judge_agent(TestModel(custom_output_text=canned), "sys", "user prompt")
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
        rubrics={"architect": "r"},  # no "clarifier" key
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


# --- E-83: vetoes override the judge at Layer 3 -----------------------------


def test_veto_failure_forces_score_zero_regardless_of_the_judge():
    """The judge's own number is overridden. This is the whole point: an
    LLM asked to enforce an absolute override inside a weighted mean does
    not reliably do it."""
    _set_judge_fn(lambda _inp: '{"score": 0.95, "components": {"internal_consistency": 0.9}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true, "failing_tests": ["t::a"], "issues": []}',
                rubric="anything",
                author_model="anthropic:glm-5.2",
                judge_model="google:gemini-3.5-flash",
                vetoes_yaml="- id: internal_consistency\n"
                "  kind: not_both\n"
                "  field: tests_passed\n"
                "  equals: true\n"
                "  and_any_nonempty: [failing_tests, issues]\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.0
    assert qs.components["internal_consistency"] == 0.0


def test_no_vetoes_leaves_the_judge_score_untouched():
    _set_judge_fn(lambda _inp: '{"score": 0.95, "components": {"a": 0.9}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true}',
                rubric="r",
                author_model="a",
                judge_model="b",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.95


def test_veto_wins_when_the_judge_errors():
    """A veto is a measurement that SUCCEEDED. Reporting not-measured would
    discard a real deterministic finding."""

    def _boom(_inp):
        raise RuntimeError("judge down")

    _set_judge_fn(_boom)
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true, "issues": ["x"]}',
                rubric="r",
                author_model="a",
                judge_model="b",
                vetoes_yaml="- id: ic\n  kind: not_both\n  field: tests_passed\n"
                "  equals: true\n  and_any_nonempty: [issues]\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.0
    assert qs.judge != "error"


def test_malformed_vetoes_yaml_is_not_measured():
    """A veto file that does not parse is a config error, and a config error
    is NOT a zero -- it is an absent measurement."""
    _set_judge_fn(lambda _inp: '{"score": 0.9, "components": {}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true}',
                rubric="r",
                author_model="a",
                judge_model="b",
                vetoes_yaml="- id: v\n  kind: vibes\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score is None
    assert qs.judge == "error"


def test_build_judge_input_carries_the_stage_veto_text():
    ji = _build_judge_input(
        artifact_json="{}",
        rubrics={"qa": "rubric text"},
        stage="qa",
        author_model="a",
        judge_model="b",
        vetoes={"qa": "- id: v\n  kind: nonempty\n  fields: [x]\n"},
    )
    assert ji is not None
    assert "nonempty" in ji.vetoes_yaml


def test_build_judge_input_defaults_vetoes_to_empty():
    ji = _build_judge_input(
        artifact_json="{}", rubrics={"qa": "r"}, stage="qa", author_model="a", judge_model="b"
    )
    assert ji is not None
    assert ji.vetoes_yaml == ""


def test_judge_never_raises_even_on_a_non_dict_artifact_with_vetoes():
    """The judge's governing invariant (judge.py:5-7): on ANY failure return
    QualityScore(score=None, judge='error'). A non-dict artifact_json with a
    not_both veto makes check() do artifact.get(...) on a list -- that must
    surface as not-measured, never propagate out and fail a benchmark cell."""
    _set_judge_fn(lambda _i: '{"score": 0.9, "components": {}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json="[1, 2, 3]",
                rubric="r",
                author_model="a",
                judge_model="b",
                vetoes_yaml="- id: ic\n  kind: not_both\n  field: tests_passed\n"
                "  equals: true\n  and_any_nonempty: [issues]\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score is None
    assert qs.judge == "error"


# --- 005 T012: the judge site routes strings through the shared seam -------
#
# _run_judge_agent holds a bare model string, so before 005 it built
# Agent(<string>) and the framework resolved the model eagerly on the SDK
# default base URL — a zai: id never reached the coding endpoint (plan D2
# site 6, contract C4/C7). These tests capture the Agent CONSTRUCTION (the
# same patchable seam the module docstring names) instead of running a real
# request: a red here must be an assertion about what the site built, never
# a live call to api.z.ai. The url helper matches test_zai_route.py.

_GATEWAY = "https://gateway.example.com/zai"


def _url(base_url: object) -> str:
    """A client base URL as a string, without the trailing slash the
    OpenAI-style client normalises onto every URL."""
    return str(base_url).rstrip("/")


_LAST_BUILT: list[object] = []


class _RecordingAgent:
    """Stands in for pydantic_ai.Agent: records what the site built, serves
    a canned output without any network."""

    def __init__(self, model, **kwargs):
        self.model = model
        _LAST_BUILT.append(model)

    def run_sync(self, prompt):
        from types import SimpleNamespace

        return SimpleNamespace(output="ok")


def test_run_judge_agent_resolves_a_zai_string_through_the_seam(monkeypatch):
    """005 T012 (contract C4): a zai: judge string must be resolved through
    resolve_model BEFORE Agent construction — the agent must receive a MODEL
    whose client sits on the ZAI_BASE_URL honoured at call time, not the
    bare string."""
    monkeypatch.setattr(judge_mod, "Agent", _RecordingAgent)
    monkeypatch.setenv("ZAI_BASE_URL", _GATEWAY)

    raw = _run_judge_agent("zai:glm-5.3", "sys", "user prompt")

    assert raw == "ok", "the judge site must still return the agent output"
    built = _LAST_BUILT[-1]
    assert built is not None and not isinstance(built, str), (
        "the judge site built Agent from the bare string "
        f"{built!r} — route it through sdlc.agents.model_ids.resolve_model "
        "so zai: ids reach the coding endpoint (plan D2 site 6, contract C7)"
    )
    assert _url(built.client.base_url) == _GATEWAY, (
        f"the resolved judge model sits on {_url(built.client.base_url)!r}; "
        "the zai URL policy must reach the judge site (C1, C4)"
    )


def test_run_judge_agent_builds_a_google_string_through_the_framework(monkeypatch):
    """A google judge string changes NOTHING about the framework path:
    resolve_model leaves non-zai providers exactly as infer_provider builds
    them, so the site must still produce the model infer_model() itself
    builds — same class, same model name (C4: URL policy applies to zai
    only)."""
    monkeypatch.setattr(judge_mod, "Agent", _RecordingAgent)
    # google's provider resolves the key at construction; the conftest dummy
    # pattern — offline, never run.
    monkeypatch.setenv("GOOGLE_API_KEY", "test-dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "test-dummy")

    from pydantic_ai.models import infer_model

    _run_judge_agent("google:gemini-2.5-pro", "sys", "user prompt")

    built = _LAST_BUILT[-1]
    assert built is not None and not isinstance(built, str), (
        "the judge site built Agent from the bare string "
        f"{built!r} — route it through sdlc.agents.model_ids.resolve_model "
        "(plan D2 site 6, contract C7)"
    )
    reference = infer_model("google:gemini-2.5-pro")  # the plain framework path
    assert type(built) is type(reference), (
        "the judge site built a different model class than the framework's "
        f"own path ({type(built).__name__} vs {type(reference).__name__}); a "
        "non-zai string must be built exactly as infer_model builds it (C4)"
    )
    assert built.model_name == reference.model_name, (
        "the judge site changed the model name on the framework path"
    )


# --- 012 T004 (RED): a missing registered rubric stops the activity --------
# contract §1.4/§1.5, data-model §2.1 (MISSING_CASE_ASSET), research R-2:
# load_case_assets must raise a non-retryable ApplicationError typed
# MissingCaseAsset naming the map key and the resolved path, instead of
# silently skipping the stage; an empty rubric map still returns {}.


def test_load_case_assets_missing_registered_rubric_raises(monkeypatch, tmp_path):
    from temporalio.exceptions import ApplicationError

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    case_id = "asset-case"
    (tmp_path / case_id).mkdir()

    # relative registered path: resolved against paths.cases_dir()/case_id
    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(judge_mod.load_case_assets(case_id, {"architect": "absent-rubric.md"}))
    exc = excinfo.value
    assert exc.type == "MissingCaseAsset"
    assert exc.non_retryable is True
    assert "architect" in str(exc), "the error must name the registered map key"
    assert str(tmp_path / case_id / "absent-rubric.md") in str(exc), (
        "the error must name the resolved path"
    )

    # absolute registered path: checked as given, raises the same way
    absent_abs = tmp_path / "elsewhere" / "nope.md"
    with pytest.raises(ApplicationError) as excinfo_abs:
        asyncio.run(judge_mod.load_case_assets("ignored", {"architect": str(absent_abs)}))
    assert excinfo_abs.value.type == "MissingCaseAsset"
    assert excinfo_abs.value.non_retryable is True
    assert str(absent_abs) in str(excinfo_abs.value)


def test_load_case_assets_empty_maps_return_empty_without_raising():
    """contract §1.5: a case registering no rubrics at all passes through
    load_case_assets untouched — no failure, empty dict."""
    assert asyncio.run(judge_mod.load_case_assets("ignored", {})) == {}
