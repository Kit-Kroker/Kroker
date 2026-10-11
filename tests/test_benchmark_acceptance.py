"""Tests for benchmark acceptance record, offline verdict, separation,
and YAML persistence (T005, T014)."""

from pathlib import Path

import pytest
import yaml

from sdlc.benchmarks.acceptance import (
    MIN_RUNS_PER_ARM,
    SEPARATION_MARGIN,
    AcceptanceRecord,
    ArmEvidence,
    Reason,
    SeparationCheck,
    SuiteCheck,
    Verdict,
    decide,
    load_acceptance,
    save_acceptance,
    separation,
)
from sdlc.benchmarks.models import CaseRole, CaseVisibility
from sdlc.benchmarks.runs import Run


def _make_run(
    run_id: str,
    arm: str,
    passed: int | None = 10,
    total: int | None = 10,
    status: str = "graded",
    oracle_id: str | None = "oid-curr",
    case_id: str = "case-1",
) -> Run:
    return Run(
        run_id=run_id,
        bench_run_id="b1",
        case_id=case_id,
        harness="opencode",
        arm=arm,
        arm_recovered=False,
        generation="012",
        commit="c1",
        tree_dirty=False,
        started_at=None,
        status=status,  # type: ignore[arg-type]
        status_derived=False,
        last_stage="qa",
        pipeline_finished=True,
        oracle_passed=passed,
        oracle_total=total,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=100,
        wall_clock_s=10.0,
        records=(),
        oracle_id=oracle_id,
    )


def test_constants_of_names():
    assert SEPARATION_MARGIN == 0.15
    assert MIN_RUNS_PER_ARM == 3

    assert {v.value for v in Verdict} == {
        "accepted",
        "provisional",
        "rejected",
        "not_assessed",
    }
    assert {r.value for r in Reason} == {
        "reference",
        "floor",
        "saturated",
        "degenerate",
        "no_separation",
    }


def test_decide_with_failed_reference_gives_rejected_reference():
    ref = SuiteCheck(passed=False, tests_passed=3, tests_total=5, detail="test_x failed")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=5, detail="")
    verdict, reason, detail = decide(ref, floor)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.REFERENCE


def test_decide_reference_passed_and_floor_not_below_gives_rejected_floor():
    ref = SuiteCheck(passed=True, tests_passed=5, tests_total=5, detail="")
    # floor has same or more tests passed as reference -> not below it
    floor = SuiteCheck(passed=False, tests_passed=5, tests_total=5, detail="floor passed 5")
    verdict, reason, detail = decide(ref, floor)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.FLOOR

    # floor passed=True but tests_passed >= ref.tests_passed
    floor2 = SuiteCheck(passed=True, tests_passed=5, tests_total=5, detail="")
    verdict2, reason2, _ = decide(ref, floor2)
    assert verdict2 == Verdict.REJECTED
    assert reason2 == Reason.FLOOR


def test_decide_both_passed_and_no_separation_data_gives_not_assessed():
    ref = SuiteCheck(passed=True, tests_passed=5, tests_total=5, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=5, detail="")
    verdict, reason, detail = decide(ref, floor, separation=None)
    assert verdict == Verdict.NOT_ASSESSED
    assert reason is None


def test_decide_reference_check_none_gives_rejected_reference_with_detail_text():
    ref = SuiteCheck(passed=None, tests_passed=0, tests_total=5, detail="no reference/")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=5, detail="")
    verdict, reason, detail = decide(ref, floor)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.REFERENCE
    assert detail == "no reference/"


def test_save_acceptance_then_load_acceptance_roundtrips_every_field(tmp_path: Path):
    rec = AcceptanceRecord(
        case_id="deveval-readtime",
        verdict=Verdict.NOT_ASSESSED,
        reason=Reason.REFERENCE,
        note="separation not yet assessed",
        oracle_id="sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        oracle_tests=12,
        reference=SuiteCheck(passed=True, tests_passed=12, tests_total=12, detail="all passed"),
        floor=SuiteCheck(passed=True, tests_passed=0, tests_total=12, detail="passed 0"),
        separation=SeparationCheck(
            passed=None,
            strong=ArmEvidence(
                arm="zai-coding-plan-glm-5.2",
                run_ids=["r1", "r2"],
                scores=[0.8, 0.9],
                mean=0.85,
            ),
            weak=ArmEvidence(
                arm="zai-coding-plan-glm-5.3-flash",
                run_ids=["r3"],
                scores=[0.5],
                mean=0.5,
            ),
            margin=0.35,
            not_comparable=1,
            detail="separation evidence recorded",
        ),
        role=CaseRole.CORPUS,
        visibility=CaseVisibility.PUBLIC,
        exposure="repo_public",
        kroker_commit="59022964",
        updated="2026-10-11T12:00:00Z",
    )

    yaml_path = save_acceptance(rec, tmp_path)
    assert yaml_path.exists()
    assert yaml_path.name == "acceptance.yaml"

    loaded = load_acceptance(tmp_path)
    assert loaded == rec

    # also roundtrips when passing direct file path to load_acceptance
    loaded_direct = load_acceptance(yaml_path)
    assert loaded_direct == rec


def test_acceptance_file_is_yaml_ascii_and_keys_in_fixed_order(tmp_path: Path):
    rec = AcceptanceRecord(
        case_id="test-case",
        verdict=Verdict.NOT_ASSESSED,
        role=CaseRole.CORPUS,
        exposure="repo_public",
        kroker_commit="abc",
        updated="2026-10-11",
    )
    saved_path = save_acceptance(rec, tmp_path)
    content = saved_path.read_bytes()

    # ASCII only: decoding with ascii must not raise
    text = content.decode("ascii")

    # Valid YAML
    data = yaml.safe_load(text)
    assert isinstance(data, dict)

    # Fixed key order matching AcceptanceRecord model fields
    expected_order = [
        "case_id",
        "verdict",
        "reason",
        "note",
        "oracle_id",
        "oracle_tests",
        "reference",
        "floor",
        "separation",
        "role",
        "visibility",
        "exposure",
        "kroker_commit",
        "updated",
    ]
    assert list(data.keys()) == expected_order


def test_load_acceptance_on_missing_file_returns_none(tmp_path: Path):
    assert load_acceptance(tmp_path / "nonexistent.yaml") is None
    assert load_acceptance(tmp_path / "empty_dir") is None


def test_exposure_validation():
    from pydantic import ValidationError

    # valid exposures
    rec1 = AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="repo_public")
    assert rec1.exposure == "repo_public"
    rec2 = AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="isolated")
    assert rec2.exposure == "isolated"

    # invalid exposure fails
    with pytest.raises(ValidationError):
        AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T014 Separation and full verdict tests (US1 scenarios 5-9, FR-007-009)
# ---------------------------------------------------------------------------


def test_separation_strong_only_not_all_1_gives_not_assessed():
    runs = [_make_run("r1", "strong", 8, 10)]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is None
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, detail = decide(ref, floor, sep)
    assert verdict == Verdict.NOT_ASSESSED
    assert reason is None


def test_separation_one_run_per_arm_margin_0_15_gives_provisional():
    runs = [
        _make_run("r1", "strong", 3, 4),  # 0.75
        _make_run("r2", "weak", 2, 4),  # 0.50
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is True
    assert sep.margin == pytest.approx(0.25)
    ref = SuiteCheck(passed=True, tests_passed=4, tests_total=4)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=4)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.PROVISIONAL
    assert reason is None


def test_separation_three_runs_per_arm_with_margin_gives_accepted():
    runs = [
        _make_run("s1", "strong", 8, 10),
        _make_run("s2", "strong", 9, 10),
        _make_run("s3", "strong", 7, 10),  # mean 0.80
        _make_run("w1", "weak", 5, 10),
        _make_run("w2", "weak", 6, 10),
        _make_run("w3", "weak", 4, 10),  # mean 0.50
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is True
    assert sep.margin == pytest.approx(0.30)
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.ACCEPTED
    assert reason is None


def test_separation_three_on_one_arm_two_on_other_gives_provisional():
    runs = [
        _make_run("s1", "strong", 8, 10),
        _make_run("s2", "strong", 9, 10),
        _make_run("s3", "strong", 7, 10),
        _make_run("w1", "weak", 5, 10),
        _make_run("w2", "weak", 5, 10),
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is True
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.PROVISIONAL
    assert reason is None


def test_separation_margin_0_1499_gives_rejected_no_separation():
    runs = [
        _make_run("s1", "strong", 7499, 10000),  # 0.7499
        _make_run("w1", "weak", 6000, 10000),  # 0.6000
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is False
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION


def test_separation_margin_tolerance_0_75_minus_0_60():
    runs = [
        _make_run("s1", "strong", 75, 100),  # 0.75
        _make_run("w1", "weak", 60, 100),  # 0.60
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is True
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.PROVISIONAL


def test_separation_weak_above_strong_gives_rejected_no_separation_with_both_means():
    runs = [
        _make_run("s1", "strong", 5, 10),  # 0.5
        _make_run("w1", "weak", 8, 10),  # 0.8
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.passed is False
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, detail = decide(ref, floor, sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION
    assert sep.strong is not None and sep.strong.mean == 0.5
    assert sep.weak is not None and sep.weak.mean == 0.8
    assert "0.5" in str(detail) and "0.8" in str(detail)


def test_separation_strong_all_1_gives_rejected_saturated():
    runs = [
        _make_run("s1", "strong", 10, 10),
        _make_run("s2", "strong", 10, 10),
        _make_run("w1", "weak", 5, 10),
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.SATURATED

    runs_strong_only = [
        _make_run("s1", "strong", 10, 10),
    ]
    sep2 = separation(runs_strong_only, strong="strong", weak="weak", oracle_id="oid-curr")
    verdict2, reason2, _ = decide(ref, floor, sep2)
    assert verdict2 == Verdict.REJECTED
    assert reason2 == Reason.SATURATED


def test_separation_strong_all_0_gives_rejected_degenerate():
    runs = [
        _make_run("s1", "strong", 0, 10),
        _make_run("s2", "strong", 0, 10),
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.DEGENERATE


def test_order_of_reasons_failed_reference_beats_saturated():
    runs = [_make_run("s1", "strong", 10, 10)]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    ref = SuiteCheck(passed=False, tests_passed=8, tests_total=10, detail="ref failed")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, _ = decide(ref, floor, sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.REFERENCE


def test_runs_of_another_identity_counted_in_not_comparable():
    runs = [
        _make_run("s1", "strong", 8, 10, oracle_id="oid-curr"),
        _make_run("s2", "strong", 8, 10, oracle_id="oid-other"),
        _make_run("w1", "weak", 5, 10, oracle_id="oid-other"),
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.not_comparable == 2
    assert sep.strong is not None and len(sep.strong.run_ids) == 1
    assert sep.weak is not None and sep.weak.run_ids == []


def test_lost_runs_and_grading_failures_enter_nothing():
    runs = [
        _make_run("s1", "strong", 8, 10, status="graded"),
        _make_run("s2", "strong", None, None, status="lost"),
        _make_run("s3", "strong", None, None, status="grading_failed"),
    ]
    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-curr")
    assert sep.strong is not None and len(sep.strong.run_ids) == 1
    assert sep.not_comparable == 0


def test_case_with_no_strong_arm_gives_not_assessed_with_note():
    runs = [_make_run("r1", "some-arm", 8, 10)]
    sep = separation(runs, strong=None, weak="weak", oracle_id="oid-curr")
    assert sep.passed is None
    ref = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, note = decide(ref, floor, sep)
    assert verdict == Verdict.NOT_ASSESSED
    assert note is not None


def test_smoke_probe_parked_separation_not_assessed_failed_ref_rejected():
    sep_parked = SeparationCheck(passed=None, detail="separation not assessed for parked case")
    ref_ok = SuiteCheck(passed=True, tests_passed=10, tests_total=10)
    floor_ok = SuiteCheck(passed=True, tests_passed=0, tests_total=10)
    verdict, reason, detail = decide(ref_ok, floor_ok, sep_parked)
    assert verdict == Verdict.NOT_ASSESSED
    assert reason is None

    # But failed reference still gives rejected
    ref_bad = SuiteCheck(passed=False, tests_passed=5, tests_total=10, detail="ref failed")
    verdict2, reason2, _ = decide(ref_bad, floor_ok, sep_parked)
    assert verdict2 == Verdict.REJECTED
    assert reason2 == Reason.REFERENCE
