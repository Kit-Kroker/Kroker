from __future__ import annotations

import json
from pathlib import Path

from sdlc.benchmarks.judge import _set_judge_fn
from sdlc.eval.promptfoo.assertion import grade, load_rubric

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"


def _ctx(**over) -> dict:
    ctx = {"vars": {"role": "clarify", "case": "cat-cafe-monitoring",
                    "author_model": "anthropic:glm-5.2",
                    "judge_model": "openai/gpt-5.2",
                    "cases_root": str(CASES)}}
    ctx["vars"].update(over)
    return ctx


def test_good_score_passes_and_reports():
    _set_judge_fn(lambda inp: json.dumps(
        {"score": 0.82, "components": {"clarity": 0.9}}))
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
    assert res["pass"] is True                 # advisory: never gates alone
    assert res["score"] is None                # NOT 0.0 -- not-measured
    assert "unavailable" in res["reason"].lower()


def test_adr6_violation_is_a_hard_fail():
    res = grade('{}', _ctx(judge_model="anthropic:claude-sonnet-4-6"))
    assert res["pass"] is False
    assert "adr-6" in res["reason"].lower()
    assert "anthropic" in res["reason"]


def test_adr6_check_is_case_insensitive_on_family():
    res = grade('{}', _ctx(judge_model="ANTHROPIC:something"))
    assert res["pass"] is False


def test_missing_rubric_names_the_file_to_author():
    res = grade('{}', _ctx(case="add-login-greenfield", role="planner"))
    assert res["pass"] is False
    assert "rubric-planner.md" in res["reason"]


def test_load_rubric_reads_the_case_file():
    text = load_rubric("cat-cafe-monitoring", "clarify", CASES)
    assert text.strip()
