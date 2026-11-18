"""026 T023 chaos/edge cases: the SC-3 split by lint-only loops (A-4, FR-021).

Companion to the 026 T023 block in tests/test_benchmark_sc_rollup.py. That
file is at 972 lines, so these cases live beside it rather than in it. Same
contract as qa-happy's block:

- A loop (a (run, task) with any attempt at fix_attempts > 0) is LINT-ONLY
  when it has a failed code record and EVERY failed code record carries
  failure.checks == ["lint"] exactly. Anything else is NON-LINT.
- Only FAILED records vote. A passing attempt carries no failure (failures
  ride failed records only), so it neither makes a loop lint nor non-lint.
- Legacy records (failure None) count as non-lint, wherever they sit.
- A check list with any extra entry (e.g. ["lint", "no_feedback"]) is not
  lint-only: the loop also starved the dev of feedback, a different failure.
- SC-3 overall keeps its label and note exactly (regression pin).

No src/ changes. The model field and the split rows are built by T020/T023.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.sc_rollup import MIN_RUNS, build_sc_rollup
from sdlc.core.models import HarnessKind, RunSummary

T = datetime(2026, 11, 18, 10, tzinfo=UTC)


def _summary(run_id, offset=0):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset),
        duration_s=0.0,
    )


def _n_summaries(n):
    return [_summary(f"run-{i}", offset=i) for i in range(n)]


def _code(run, task, outcome, fix):
    return BenchmarkRecord(
        run_id=run,
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id=task,
        attempt=fix,
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=outcome,
        fix_attempts=fix,
    )


def _failed(run, task, fix, checks=None):
    """A FAILED code record. checks=None is the legacy shape (failure None)."""
    from sdlc.benchmarks.models import AttemptFailure

    rec = _code(run, task, BenchmarkOutcome.FAIL, fix)
    if checks is None:
        return rec
    return rec.model_copy(update={"failure": AttemptFailure(checks=list(checks), summary="x")})


def _passed(run, task, fix):
    return _code(run, task, BenchmarkOutcome.PASS, fix)


def _rate(rollup, criterion):
    rows = [r for r in rollup.rates if r.criterion == criterion]
    assert rows, f"no {criterion} row in the rollup (the T023 split is not built yet)"
    return rows[0]


def _split(recs):
    rollup = build_sc_rollup(_n_summaries(MIN_RUNS), recs)
    return _rate(rollup, "SC-3-lint"), _rate(rollup, "SC-3-non-lint")


# --- (1) one unclassified record drags the whole loop to non-lint -----------


def test_edge_a_legacy_record_late_in_a_lint_loop_makes_it_non_lint():
    """Legacy (failure None) sits at the END of the failing run, after two
    lint-only failures. Position does not matter: any unclassified failed
    record is non-lint, never lint."""
    recs = [
        _failed("r1", "t", 0, ["lint"]),
        _failed("r1", "t", 1, ["lint"]),
        _failed("r1", "t", 2, None),
        _passed("r1", "t", 3),
    ]
    lint, nonlint = _split(recs)
    assert (lint.n, nonlint.n) == (0, 1)


# --- (2) only FAILED records vote; passing attempts are ignored -------------


def test_edge_a_passing_attempt_mid_loop_does_not_flip_a_lint_loop():
    """lint, pass (no failure), lint, pass: the passing attempts carry no
    failure and cast no vote, so the loop stays lint-only."""
    recs = [
        _failed("r1", "t", 0, ["lint"]),
        _passed("r1", "t", 1),
        _failed("r1", "t", 2, ["lint"]),
        _passed("r1", "t", 3),
    ]
    lint, nonlint = _split(recs)
    assert (lint.n, nonlint.n) == (1, 0)


# --- (3) an extra check beside lint is not lint-only -------------------------


def test_edge_lint_plus_no_feedback_is_not_lint_only():
    """["lint", "no_feedback"] is not the exact list ["lint"]: the loop also
    starved the dev of feedback, a different failure, so it is non-lint."""
    recs = [_failed("r1", "t", 0, ["lint", "no_feedback"]), _passed("r1", "t", 1)]
    lint, nonlint = _split(recs)
    assert (lint.n, nonlint.n) == (0, 1)


# --- regression pin: SC-3 overall is byte-identical to today ----------------


def test_edge_sc3_overall_label_and_note_are_unchanged():
    recs = [
        _failed("r1", "t", 0, ["lint"]),
        _passed("r1", "t", 1),
        _failed("r1", "u", 0, ["tests"]),
        _passed("r1", "u", 1),
    ]
    sc3 = _rate(build_sc_rollup(_n_summaries(MIN_RUNS), recs), "SC-3")
    assert sc3.label == "fix loops that resolved"
    assert "a loop = a (run, task) with any attempt at fix_attempts>0" in sc3.note
    assert sc3.note.endswith("and the n/a floor of 5 applies to loops")
