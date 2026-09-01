from __future__ import annotations

import json
from pathlib import Path

from sdlc.benchmarks.judge import _set_judge_fn
from sdlc.eval.promptfoo.assertion import grade, load_rubric

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"


def _ctx(**over) -> dict:
    ctx = {
        "vars": {
            "role": "clarify",
            "case": "cat-cafe-monitoring",
            "author_model": "anthropic:glm-5.2",
            "judge_model": "openai/gpt-5.2",
            "cases_root": str(CASES),
        }
    }
    ctx["vars"].update(over)
    return ctx


def test_good_score_passes_and_reports():
    _set_judge_fn(lambda inp: json.dumps({"score": 0.82, "components": {"clarity": 0.9}}))
    try:
        res = grade('{"open_questions": []}', _ctx())
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True
    assert res["score"] == 0.82


def test_judge_error_is_advisory_pass_and_says_unavailable():
    _set_judge_fn(lambda inp: "not json at all")
    try:
        res = grade('{"open_questions": []}', _ctx())
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True  # advisory: never gates alone
    # promptfoo rejects a null score, so unavailability rides on the reason
    # sentinel; verdict._scores drops these rows before averaging.
    from sdlc.eval.verdict import JUDGE_UNAVAILABLE

    assert JUDGE_UNAVAILABLE in res["reason"]
    assert isinstance(res["score"], (int, float))


def test_adr6_violation_is_a_hard_fail():
    res = grade("{}", _ctx(judge_model="anthropic:claude-sonnet-4-6"))
    assert res["pass"] is False
    assert "adr-6" in res["reason"].lower()
    assert "anthropic" in res["reason"]


def test_adr6_check_is_case_insensitive_on_family():
    res = grade("{}", _ctx(judge_model="ANTHROPIC:something"))
    assert res["pass"] is False


def test_missing_rubric_names_the_file_to_author():
    res = grade("{}", _ctx(case="add-login-greenfield", role="planner"))
    assert res["pass"] is False
    assert "rubric-planner.md" in res["reason"]


def test_load_rubric_reads_the_case_file():
    text = load_rubric("cat-cafe-monitoring", "clarify", CASES)
    assert text.strip()


def test_get_assert_is_the_entry_point_promptfoo_calls():
    """promptfoo does getattr(module, "get_assert") -- the name is its
    contract, not ours. Missing it fails the whole eval with
    'module has no attribute get_assert'."""
    import json as _json

    from sdlc.benchmarks.judge import _set_judge_fn
    from sdlc.eval.promptfoo import absolute, assertion

    assert callable(assertion.get_assert)
    assert callable(absolute.get_assert)

    _set_judge_fn(lambda inp: _json.dumps({"score": 0.7, "components": {}}))
    try:
        res = assertion.get_assert('{"open_questions": []}', _ctx())
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True and res["score"] == 0.7


def test_get_assert_accepts_an_object_context():
    """promptfoo may hand a dict or an object exposing `vars`."""
    from sdlc.eval.promptfoo import assertion

    class _Ctx:
        vars = {
            "role": "clarify",
            "case": "cat-cafe-monitoring",
            "author_model": "anthropic:glm-5.2",
            "judge_model": "anthropic:claude-sonnet-4-6",
            "cases_root": str(CASES),
        }

    res = assertion.get_assert("{}", _Ctx())
    assert res["pass"] is False  # ADR-6 collision, reached the check


def test_same_weights_behind_different_prefixes_is_refused():
    """This repo runs `anthropic:glm-5.2` against ANTHROPIC_BASE_URL=api.z.ai,
    so the provider prefix says who SERVES the model, not what it is.
    `zai-coding-plan/glm-5.2` clears the family check while being the same
    weights -- exactly what loader.py:237 guards the adversary against."""
    res = grade("{}", _ctx(judge_model="zai-coding-plan/glm-5.2"))
    assert res["pass"] is False
    assert "same model" in res["reason"]
    assert "glm-5.2" in res["reason"]


def test_a_genuinely_decorrelated_judge_is_accepted():
    import json as _json

    _set_judge_fn(lambda inp: _json.dumps({"score": 0.9, "components": {}}))
    try:
        res = grade('{"open_questions": []}', _ctx(judge_model="google:gemini-3.5-flash"))
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True
    assert res["score"] == 0.9
