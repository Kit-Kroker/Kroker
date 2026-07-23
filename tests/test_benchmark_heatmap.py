from datetime import datetime, timedelta

from sdlc.benchmarks.heatmap import (
    ORACLE_STAGE, Heatmap, HeatmapCell, build_heatmap,
)
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag,
)
from sdlc.models import HarnessKind


def _rec(*, case="c1", run="r1", stage="code", scope=BenchmarkScope.STAGE,
         outcome=BenchmarkOutcome.PASS, fix=0):
    t = datetime(2026, 7, 24, 10)
    return BenchmarkRecord(
        run_id=run, bench_run_id="b1", case_id=case, scope=scope, stage=stage,
        role="dev", harness=HarnessKind.CLAUDE_CODE, model="m",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=outcome, fix_attempts=fix)


def test_density_blends_rejects_fixes_and_oracle_over_runs():
    recs = [
        _rec(run="r1", stage="code", outcome=BenchmarkOutcome.REVISED, fix=2),
        _rec(run="r2", stage="code", outcome=BenchmarkOutcome.FAIL, fix=3),
        # oracle failure for the same case, distinct synthetic column
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE,
             outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    by = {(c.case, c.stage): c for c in hm.cells}
    code = by[("c1", "code")]
    # 2 rework outcomes (REVISED + FAIL) + 5 fix attempts = 7 over 2 runs
    assert code.gate_rejects == 2
    assert code.fix_attempts == 5
    assert code.n_runs == 2
    assert code.density == 3.5
    oracle = by[("c1", ORACLE_STAGE)]
    assert oracle.oracle_fails == 1
    assert oracle.gate_rejects == 0
    assert oracle.density == 0.5   # 1 oracle fail / 2 runs


def test_n_runs_dedups_distinct_run_ids_per_case():
    recs = [_rec(run="r1", stage="qa", outcome=BenchmarkOutcome.FAIL),
            _rec(run="r1", stage="code", outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs)
    assert all(c.n_runs == 1 for c in hm.cells)


def test_unknown_stage_appended_before_oracle_not_dropped():
    recs = [_rec(stage="clarify", outcome=BenchmarkOutcome.FAIL),
            _rec(stage="mystery", outcome=BenchmarkOutcome.FAIL),
            _rec(stage="oracle", scope=BenchmarkScope.ORACLE,
                 outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs)
    assert hm.stages == ["clarify", "mystery", "oracle"]


def test_language_map_recorded_per_case():
    recs = [_rec(case="py", stage="code", outcome=BenchmarkOutcome.FAIL),
            _rec(case="go", stage="code", outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs, language_by_case={"py": "python"})
    assert hm.language_by_case == {"py": "python", "go": ""}


def test_empty_records_give_empty_heatmap():
    hm = build_heatmap([])
    assert hm.cells == [] and hm.cases == [] and hm.stages == []
    assert hm.max_density == 0.0


def test_oracle_non_fail_rework_not_counted_as_oracle_failure():
    recs = [
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE,
             outcome=BenchmarkOutcome.ESCALATED),
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE,
             outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    cell = next(c for c in hm.cells if c.stage == ORACLE_STAGE)
    assert cell.oracle_fails == 1   # only the FAIL, not the ESCALATED
