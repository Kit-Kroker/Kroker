"""Tests for benchmark acceptance stalled verdict (017 FR-024, C-4, D-7)."""

import shutil
from pathlib import Path

from sdlc.benchmarks.acceptance import (
    Reason,
    SuiteCheck,
    Verdict,
    decide,
    load_acceptance,
    separation,
)
from sdlc.benchmarks.cli import dispatch_accept
from sdlc.benchmarks.evidence import load_evidence
from sdlc.benchmarks.models import StageReach
from sdlc.benchmarks.oracle_id import oracle_identity
from sdlc.benchmarks.runs import Run, build_runs


def _make_run(
    run_id: str,
    arm: str,
    passed: int | None = 1,
    total: int | None = 56,
    status: str = "graded",
    oracle_id: str | None = "oid-1",
    case_id: str = "case-1",
    stage_reach: StageReach | None = None,
    last_stage: str = "merge",
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
        last_stage=last_stage,
        pipeline_finished=False,
        oracle_passed=passed,
        oracle_total=total,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=100,
        wall_clock_s=10.0,
        records=(),
        oracle_id=oracle_id,
        stage_reach=stage_reach,
    )


def test_two_stalled_arms_r1_shape():
    """Two stalled arms at merge (R1 shape, score 1/56 <= 0.05) -> NOT_ASSESSED stalled."""
    strong_reach = StageReach(
        last_stage="merge",
        last_stage_outcome="fail",
        final_stage="merge",
        merge_outcome="fail",
        merge_blocking_checks=["integration_checks"],
    )
    weak_reach = StageReach(
        last_stage="merge",
        last_stage_outcome="fail",
        final_stage="merge",
        merge_outcome="fail",
        merge_blocking_checks=["integration_checks"],
    )

    runs = [
        _make_run("r-s1", arm="strong", passed=1, total=56, stage_reach=strong_reach),
        _make_run("r-s2", arm="strong", passed=1, total=56, stage_reach=strong_reach),
        _make_run("r-w1", arm="weak", passed=1, total=56, stage_reach=weak_reach),
        _make_run("r-w2", arm="weak", passed=1, total=56, stage_reach=weak_reach),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    assert sep.strong is not None
    assert sep.weak is not None
    assert sep.strong.stall_points == ["merge", "merge"]
    assert sep.weak.stall_points == ["merge", "merge"]

    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    assert verdict == Verdict.NOT_ASSESSED
    assert reason == Reason.STALLED
    assert note == "not separable: stalled at merge"


def test_two_arms_finished_at_final_stage_with_pass():
    """Two arms finished at final_stage with PASS and <= eps -> today's verdict (no_separation)."""
    reach = StageReach(
        last_stage="merge",
        last_stage_outcome="pass",
        final_stage="merge",
        merge_outcome="pass",
    )

    # 1/56 is ~0.0178 <= 0.05, but last_stage_outcome is pass and last_stage == final_stage
    runs = [
        _make_run("r-s1", arm="strong", passed=1, total=56, stage_reach=reach),
        _make_run("r-w1", arm="weak", passed=1, total=56, stage_reach=reach),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    # Precondition 4 fails because both runs completed their final stage.
    # Falling through: strong mean == weak mean, margin == 0.0 < 0.15 -> REJECTED NO_SEPARATION
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION


def test_one_run_without_stage_reach():
    """One run without stage_reach -> today's verdict (does not fire stalled)."""
    reach = StageReach(
        last_stage="merge",
        last_stage_outcome="fail",
        final_stage="merge",
        merge_outcome="fail",
    )

    runs = [
        _make_run("r-s1", arm="strong", passed=1, total=56, stage_reach=reach),
        _make_run("r-s2", arm="strong", passed=1, total=56, stage_reach=None),  # Missing reach
        _make_run("r-w1", arm="weak", passed=1, total=56, stage_reach=reach),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    assert sep.strong is not None
    # Only the run with reach contributes to stall_points
    assert sep.strong.stall_points == ["merge"]

    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION


def test_stalled_at_different_stages():
    """Stalled at different stages -> today's verdict (precondition 3 fails)."""
    strong_reach = StageReach(
        last_stage="merge",
        last_stage_outcome="fail",
        final_stage="merge",
        merge_outcome="fail",
    )
    weak_reach = StageReach(
        last_stage="analyze",
        last_stage_outcome="fail",
        final_stage="merge",
    )

    runs = [
        _make_run("r-s1", arm="strong", passed=1, total=56, stage_reach=strong_reach),
        _make_run(
            "r-w1", arm="weak", passed=1, total=56, stage_reach=weak_reach, last_stage="analyze"
        ),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION


def test_all_zero_strong_arm_that_stalled():
    """All-zero strong arm that stalled -> stalled, not degenerate."""
    reach = StageReach(
        last_stage="code",
        last_stage_outcome="fail",
        final_stage="merge",
    )

    runs = [
        _make_run("r-s1", arm="strong", passed=0, total=56, stage_reach=reach, last_stage="code"),
        _make_run("r-w1", arm="weak", passed=0, total=56, stage_reach=reach, last_stage="code"),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    # Stalled branch sits before DEGENERATE, so it resolves to NOT_ASSESSED stalled
    assert verdict == Verdict.NOT_ASSESSED
    assert reason == Reason.STALLED
    assert note == "not separable: stalled at code"


def test_mixed_outcome_same_last_stage_merge():
    """Advisor-unlock-21 pin: same last_stage=merge, <= eps, but one run PASS -> today's verdict."""
    fail_reach = StageReach(
        last_stage="merge",
        last_stage_outcome="fail",
        final_stage="merge",
        merge_outcome="fail",
    )
    pass_reach = StageReach(
        last_stage="merge",
        last_stage_outcome="pass",
        final_stage="merge",
        merge_outcome="pass",
    )

    runs = [
        _make_run("r-s1", arm="strong", passed=1, total=56, stage_reach=fail_reach),
        _make_run("r-s2", arm="strong", passed=1, total=56, stage_reach=pass_reach),
        _make_run("r-w1", arm="weak", passed=1, total=56, stage_reach=fail_reach),
    ]

    sep = separation(runs, strong="strong", weak="weak", oracle_id="oid-1")
    ref = SuiteCheck(passed=True, tests_passed=56, tests_total=56, detail="")
    floor = SuiteCheck(passed=True, tests_passed=0, tests_total=56, detail="")

    verdict, reason, note = decide(ref, floor, separation=sep)
    # Precondition 4 requires all runs did not complete; here r-s2 passed final_stage
    assert verdict == Verdict.REJECTED
    assert reason == Reason.NO_SEPARATION


def test_sc003_recompute_stored_acceptance(tmp_path: Path):
    """SC-003: recompute stored acceptance.yaml via non-offline accept path on tmp_path copy."""
    cases_dir = Path("benchmarks/cases")
    checked = 0

    for case_path in sorted(cases_dir.iterdir()):
        if not case_path.is_dir():
            continue
        stored_yaml = case_path / "acceptance.yaml"
        if not stored_yaml.is_file():
            continue

        stored = load_acceptance(case_path)
        if stored is None:
            continue

        oracle_dir = case_path / "oracle"
        current_oid = oracle_identity(oracle_dir) if oracle_dir.is_dir() else None

        # Check if stored records matching current oracle identity exist
        ev = load_evidence(case=case_path.name)
        runs = build_runs(ev.records) if (ev and ev.records) else []
        matching_runs = [r for r in runs if r.oracle_id == current_oid]
        if not matching_runs:
            # Skip cases with no stored records matching the oracle identity
            continue

        # Copy case dir to tmp_path
        tmp_case_dir = tmp_path / case_path.name
        shutil.copytree(case_path, tmp_case_dir)

        # Run non-offline accept with cases_root pointing to tmp_path
        dispatch_accept(case=case_path.name, offline=False, cases_root=str(tmp_path))

        recomputed = load_acceptance(tmp_case_dir)
        assert recomputed is not None

        assert recomputed.verdict == stored.verdict
        assert recomputed.reason == stored.reason
        assert recomputed.note == stored.note
        assert recomputed.separation == stored.separation
        checked += 1

    assert checked > 0, "At least one case with stored records must be verified for SC-003"
