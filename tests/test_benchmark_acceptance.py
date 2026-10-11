"""Tests for benchmark acceptance record, offline verdict, and YAML persistence (T005)."""

from pathlib import Path

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
)
from sdlc.benchmarks.models import CaseRole, CaseVisibility


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
    import pytest
    from pydantic import ValidationError

    # valid exposures
    rec1 = AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="repo_public")
    assert rec1.exposure == "repo_public"
    rec2 = AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="isolated")
    assert rec2.exposure == "isolated"

    # invalid exposure fails
    with pytest.raises(ValidationError):
        AcceptanceRecord(case_id="c", verdict=Verdict.NOT_ASSESSED, exposure="invalid")  # type: ignore[arg-type]
