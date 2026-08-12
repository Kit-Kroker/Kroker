from __future__ import annotations

import json
from pathlib import Path

from sdlc.eval.verdict import GateVerdict, JudgeStatus, decide, write_result


def _results(baseline: list, working: list, *, absolute_ok: bool = True,
             provider_error: str | None = None) -> dict:
    """Shape of promptfoo's --output results.json, reduced to what we read."""
    def rows(label, scores):
        out = []
        for s in scores:
            out.append({
                "provider": {"label": label},
                "error": provider_error,
                "gradingResult": {"componentResults": [
                    {"assertion": {"value": "absolute.py"},
                     "pass": absolute_ok, "reason": "r"},
                    {"assertion": {"value": "assertion.py"},
                     "pass": True, "score": s, "reason": "r"},
                ]},
            })
        return out
    return {"results": {"results": rows("baseline", baseline)
                        + rows("working", working)}}


def test_improvement_passes():
    r = decide(_results([0.70, 0.70, 0.70], [0.85, 0.85, 0.85]))
    assert r.verdict is GateVerdict.PASS
    assert r.delta > 0


def test_dip_within_noise_passes():
    r = decide(_results([0.80, 0.80, 0.80], [0.78, 0.78, 0.78]))
    assert r.verdict is GateVerdict.PASS      # 0.02 < delta_min 0.05


def test_clear_regression_fails():
    r = decide(_results([0.85, 0.85, 0.85], [0.50, 0.50, 0.50]))
    assert r.verdict is GateVerdict.FAIL_REGRESSION
    assert "0.35" in r.reason or "-0.35" in r.reason


def test_noisy_data_widens_the_floor_and_passes():
    """Same means as the failing case, but high variance -- 2*pooled_stderr
    exceeds the gap, so the gate must NOT fire."""
    r = decide(_results([0.2, 0.9, 0.2, 0.9], [0.1, 0.8, 0.1, 0.8]))
    assert r.verdict is GateVerdict.PASS


def test_absolute_failure_beats_a_good_score():
    r = decide(_results([0.9], [0.9], absolute_ok=False))
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE


def test_native_cost_gate_failure_is_absolute():
    """Native cost/latency asserts carry no `value` path -- they must be
    recognised by `type` or the budget gates silently do nothing."""
    res = _results([0.9], [0.9])
    for row in res["results"]["results"]:
        row["gradingResult"]["componentResults"].append(
            {"assertion": {"type": "cost", "threshold": 0.5},
             "pass": False, "reason": "cost 0.91 > 0.5"})
    r = decide(res)
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE
    assert "cost" in r.reason


def test_provider_error_is_errored_not_failed():
    r = decide(_results([0.9], [0.9], provider_error="API down"))
    assert r.verdict is GateVerdict.ERRORED
    assert "API down" in r.reason


def test_all_judges_errored_is_unavailable_never_a_silent_pass():
    r = decide(_results([None, None], [None, None]))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.verdict is GateVerdict.PASS
    assert "unavailable" in r.reason.lower()


def test_partial_judge_errors_are_excluded_from_the_mean():
    r = decide(_results([0.8, None, 0.8], [0.8, None, 0.8]))
    assert r.judge_status is JudgeStatus.MEASURED
    assert r.mean_baseline == 0.8


def test_no_baseline_rows_reports_no_baseline():
    r = decide(_results([], [0.8]))
    assert r.judge_status is JudgeStatus.NO_BASELINE
    assert r.verdict is GateVerdict.PASS


def test_k_of_one_falls_back_to_delta_min():
    """One sample each -> no stderr -> the 0.05 floor decides."""
    assert decide(_results([0.80], [0.78])).verdict is GateVerdict.PASS
    assert decide(_results([0.80], [0.60])).verdict is (
        GateVerdict.FAIL_REGRESSION)


def test_write_result_round_trips(tmp_path):
    r = decide(_results([0.8], [0.8]))
    r.role, r.case = "clarify", "cat-cafe-monitoring"
    r.prompt_sha_baseline, r.prompt_sha_working = "a1b2", "c3d4"
    p = write_result(r, tmp_path)
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    assert data["prompt_sha_working"] == "c3d4"
    assert data["verdict"] == "pass"


def test_judge_unavailable_sentinel_is_excluded_from_the_mean():
    """The assertion cannot send score=null (promptfoo rejects it) and cannot
    omit it (promptfoo would default a passing assertion to 1.0). It sends a
    placeholder plus the sentinel; verdict must drop those rows, or an
    unavailable judge would read as a perfect 0.0 or 1.0 score."""
    from sdlc.eval.verdict import JUDGE_UNAVAILABLE

    res = _results([0.8], [0.8])
    for row in res["results"]["results"]:
        for c in row["gradingResult"]["componentResults"]:
            if "assertion.py" in str(c["assertion"].get("value")):
                c["score"] = 0.0
                c["reason"] = f"{JUDGE_UNAVAILABLE}: judge errored"
    r = decide(res)
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.mean_baseline is None
    assert r.verdict is GateVerdict.PASS


def test_real_scores_survive_the_sentinel_filter():
    r = decide(_results([0.8, 0.8], [0.8, 0.8]))
    assert r.judge_status is JudgeStatus.MEASURED
    assert r.mean_baseline == 0.8


def test_assertion_failure_is_not_a_provider_error():
    """promptfoo copies a failed assertion's reason into row.error. decide
    must not treat that as a provider error -- an absolute failure on real
    output is FAIL_ABSOLUTE, not ERRORED. This is the E-83 mutation suite's
    scope_dropped case: the veto fires, and the gate must show its teeth."""
    res = _results([0.9], [0.9])
    work_row = res["results"]["results"][-1]
    reason = "veto scope_preserved: required term(s) absent: litter box"
    work_row["error"] = reason
    for c in work_row["gradingResult"]["componentResults"]:
        if "absolute.py" in str(c["assertion"].get("value")):
            c["pass"] = False
            c["reason"] = reason
    r = decide(res)
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE
    assert "scope_preserved" in r.reason


def test_a_genuine_provider_error_is_still_errored():
    """A provider error whose message is NOT an assertion reason is a real
    'gate could not run', even though the empty output also fails the type
    assertion (spec 6: provider error -> ERRORED, not a prompt regression)."""
    res = _results([0.9], [0.9])
    work_row = res["results"]["results"][-1]
    work_row["error"] = "RuntimeError: model timed out"
    for c in work_row["gradingResult"]["componentResults"]:
        if "absolute.py" in str(c["assertion"].get("value")):
            c["pass"] = False
            c["reason"] = "empty output - cannot validate as ClarifiedRequirements"
    r = decide(res)
    assert r.verdict is GateVerdict.ERRORED
    assert "model timed out" in r.reason


def test_one_sided_judge_still_records_the_measured_mean():
    """A judge score that WAS produced must survive to the record.

    The regression is correctly not evaluated -- but reporting only n=1 and
    dropping the 1.00 is how OQ-P5's evidence was lost."""
    # NOTE (E-83 plan deviation): the plan specified _results([], [1.0]), but
    # an empty baseline list hits the earlier NO_BASELINE branch (verdict.py
    # `if not base_rows:`), which already sets mean_working. The UNAVAILABLE
    # branch the plan is fixing needs baseline ROWS that produce no SCORES --
    # one errored judge row ([None]) -- so base=[] but base_rows is non-empty.
    r = decide(_results([None], [1.0]))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.verdict is GateVerdict.PASS
    assert r.n_working == 1
    assert r.mean_working == 1.0
    assert r.mean_baseline is None
    # NOT a regression comparison -- these must stay unset.
    assert r.delta is None
    assert r.floor is None


def test_one_sided_baseline_records_its_mean_too():
    r = decide(_results([0.4, 0.6], []))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.mean_baseline == 0.5
    assert r.mean_working is None
    assert r.n_baseline == 2


def test_individual_scores_are_persisted():
    r = decide(_results([0.70, 0.80], [0.90, 0.95]))
    assert r.scores_baseline == [0.70, 0.80]
    assert r.scores_working == [0.90, 0.95]


def test_unavailable_rows_are_excluded_from_persisted_scores():
    """A JUDGE_UNAVAILABLE row carries a placeholder number that must not
    be persisted as if it were a measurement."""
    from sdlc.eval.verdict import JUDGE_UNAVAILABLE

    res = _results([0.5], [0.5])
    working_row = res["results"]["results"][-1]
    working_row["gradingResult"]["componentResults"][1]["reason"] = (
        f"{JUDGE_UNAVAILABLE}: judge errored")
    r = decide(res)
    assert r.scores_baseline == [0.5]
    assert r.scores_working == []


def test_scores_persisted_on_the_one_sided_path():
    r = decide(_results([], [1.0]))
    assert r.scores_working == [1.0]
    assert r.scores_baseline == []
