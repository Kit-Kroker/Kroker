# tests/test_benchmark_heatmap_fix_inflation.py
"""Adversarial edges of the ruled fix for bug heatmap-fix-inflation.

Bug: heatmap-fix-inflation (branch fix/heatmap-fix-inflation; card
`.specify/specs/001-canonical-stage-graph-sha/spec.md:273` E77-OQ-1).
`src/sdlc/stages/code/step.py:784` stamps `fix_attempts = attempt - 1` on
EVERY code attempt record (a running counter, strictly monotone 0..n-1
within one (run_id, task_id)), and `src/sdlc/benchmarks/heatmap.py:101`
SUMS the field across records -- so a task needing n attempts reports
n(n-1)/2 instead of n-1 (3 -> 3, 4 -> 6, 5 -> 10) and recorded baselines
re-aggregate inflated.

RULED SEMANTICS (cause gate, Direction A -- assertions here are written
against THIS):

- The fix axis groups records by (case_id, stage, run_id, task_id) where
  task_id is not None; each group contributes MAX(fix_attempts over its
  records); the cell sums the group maxima.
- task_id=None records pass through PER-RECORD (each contributes its own
  value) -- sub-ruling; item 1 guards it against a future (run, None)
  group collapse.
- Everything else unchanged: gate rejects, oracle fails, n_runs, density,
  and the E-77 fail_reentry pass stays additive and separate (FR-016).

Inventory (ruled value -> value summed today): items 2, 3, 4, 6, 8 are
RED today (assertion value mismatches, not errors); items 1, 5, 7 are
GREEN guards -- they pin sub-rulings that hold today and must survive
the fix. The plain per-task ladder regression is not duplicated here.

Determinism: pure in-memory aggregation over synthetic records with a
fixed timestamp -- no filesystem, CWD, network, or clock dependence, no
pytest-timeout marks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sdlc.benchmarks.heatmap import build_heatmap
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    GraphAttribution,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import (
    HarnessKind,
)


def _rec(
    *,
    case="c1",
    run="r1",
    stage="code",
    task=None,
    attempt=None,
    scope=None,
    outcome=BenchmarkOutcome.PASS,
    fix=0,
    graph=None,
):
    t = datetime(2026, 7, 24, 10)
    return BenchmarkRecord(
        run_id=run,
        bench_run_id="b1",
        case_id=case,
        # record_builder.py:47 -- task identity is what makes a record a
        # TASK_ATTEMPT record; explicit scope (e.g. ORACLE_TASK) wins.
        scope=scope or (BenchmarkScope.TASK_ATTEMPT if task is not None else BenchmarkScope.STAGE),
        stage=stage,
        task_id=task,
        attempt=attempt,
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
        model="m",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=outcome,
        fix_attempts=fix,
        graph=graph,
    )


def _code_cell(recs):
    hm = build_heatmap(recs)
    return next(c for c in hm.cells if c.case == "c1" and c.stage == "code")


def _cells(recs):
    return sorted(((c.case, c.stage), c.model_dump()) for c in build_heatmap(recs).cells)


# --- item 1: task_id=None passthrough (GREEN guard for the sub-ruling) -------


def test_taskless_records_pass_through_per_record_not_grouped():
    """Sub-ruling guard (GREEN today, must stay green): records without a
    task_id each contribute their OWN value -- 2 + 3 = 5 -- never a
    (run_id, None) group maximum of 3."""
    cell = _code_cell(
        [
            _rec(task=None, fix=2),
            _rec(task=None, fix=3),
        ]
    )
    assert cell.fix_attempts == 5


# --- item 2: None-identity and task groups never merge (RED) -----------------


def test_taskless_and_task_groups_in_one_run_stay_separate():
    """A taskless record (fix=4, passthrough) next to a T01 group with the
    real ladder 0,1,2: 4 + max(0,1,2) = 4 + 2 = 6. The sum reports 7; a
    fix that folds the taskless record INTO the T01 group would report
    max(4,0,1,2) = 4 -- both wrong shapes fail here."""
    recs = [
        _rec(task=None, fix=4),
        _rec(task="T01", attempt=0, fix=0),
        _rec(task="T01", attempt=1, fix=1),
        _rec(task="T01", attempt=2, fix=2),
    ]
    cell = _code_cell(recs)
    assert cell.fix_attempts == 6


# --- item 3: aggregation must not assume monotonicity (RED) ------------------


def test_non_monotone_group_maxes_rather_than_sums():
    """Garbage / corrupted history in one (run, task) group -- fix stamps
    2,5,1 (attempt stamps mirrored, non-monotone): the group contributes
    max = 5, not the sum 8, and nothing may blow up on the non-monotone
    shape. Also the duplicate-emission class: maxing is idempotent when a
    record reappears."""
    recs = [
        _rec(task="T01", attempt=2, fix=2),
        _rec(task="T01", attempt=5, fix=5),
        _rec(task="T01", attempt=1, fix=1),
    ]
    cell = _code_cell(recs)
    assert cell.fix_attempts == 5


# --- item 4: missing attempt field on task records (RED) ---------------------


def test_missing_attempt_field_does_not_break_group_max():
    """Records can carry task identity without an attempt stamp (the field
    is optional on BenchmarkRecord): grouping must not depend on it --
    no crash, and the group still maxes over the VALUES (1, 3 -> 3, not
    the sum 4)."""
    recs = [
        _rec(task="T01", attempt=None, fix=1),
        _rec(task="T01", attempt=None, fix=3),
    ]
    cell = _code_cell(recs)
    assert cell.fix_attempts == 3


# --- item 5: order independence (GREEN guard) ---------------------------------


def test_cell_values_are_order_independent():
    """The aggregator consumes records in whatever order runs wrote them;
    the heatmap is a function of the record MULTISET. Shuffled and
    reversed inputs must give identical cells. GREEN today (a sum is
    order-free); a "last record of the group wins" mechanic would be
    order-sensitive and fails here."""
    recs = [
        _rec(task=None, fix=4),
        _rec(task="T01", attempt=0, fix=0),
        _rec(task="T01", attempt=1, fix=1),
        _rec(task="T01", attempt=2, fix=2),
        _rec(task="T02", attempt=0, fix=0),
        _rec(task="T02", attempt=1, fix=1),
        _rec(run="r2", task="T01", attempt=0, fix=0),
        _rec(run="r2", task="T01", attempt=1, fix=1),
    ]
    forward = _cells(recs)
    assert _cells(list(reversed(recs))) == forward
    assert _cells(recs[3:] + recs[:3]) == forward


# --- item 6: E-77 interplay, no double-count (RED) ----------------------------


def test_fail_reentry_adds_one_beside_the_group_max():
    """FR-016: the handler axis and the reentry axis stay separate. The
    T01 ladder (0,1,2) with the last TWO records stamped as one reentered
    activation (fail_reentry=1, node_stage code): the group max
    contributes 2, the once-per-activation pass adds exactly +1 (two
    records, ONE activation), total 3. Today the sum contributes 3 and
    the pass 1 -> 4; a fix that folds the reentry into the group max
    loses the +1 (2), one that maxes the reentry per record doubles it
    (4) -- both fail here."""
    reentry = GraphAttribution(
        graph_sha="a" * 64,
        activation_id="code#2",
        node_id="code",
        round=2,
        node_stage="code",
        fail_reentry=1,
    )
    recs = [
        _rec(task="T01", attempt=0, fix=0),
        _rec(task="T01", attempt=1, fix=1, graph=reentry),
        _rec(task="T01", attempt=2, fix=2, graph=reentry),
    ]
    cell = _code_cell(recs)
    assert cell.fix_attempts == 3


# --- item 7: ORACLE_TASK exclusion holds under task grouping (GREEN guard) ----


def test_oracle_task_records_stay_excluded_with_task_identity():
    """Scope-based exclusion (E-36) must survive task grouping: an
    ORACLE_TASK record carrying task_id='T01' and fix=2 changes nothing
    relative to the same stream without it -- no oracle cell, identical
    cells everywhere. GREEN today; a fix that groups by task_id first and
    forgets the scope guard would admit it."""
    base = [
        _rec(task="T01", attempt=0, fix=0),
        _rec(task="T01", attempt=1, fix=1),
    ]
    with_oracle = base + [
        _rec(
            stage="oracle",
            scope=BenchmarkScope.ORACLE_TASK,
            task="T01",
            attempt=0,
            fix=2,
            outcome=BenchmarkOutcome.FAIL,
        )
    ]
    assert _cells(with_oracle) == _cells(base)
    assert "oracle" not in {c.stage for c in build_heatmap(with_oracle).cells}


# --- item 8: density honesty (RED) --------------------------------------------


def test_density_reports_honest_fix_units_per_run():
    """One (run, task) group at n=4 (the configured max_fix_attempts=3
    budget), one REVISED attempt among them: gate = 1 reject, fix =
    max(0,1,2,3) = 3, over n_runs = 1 -> density 4.0. Today the ladder
    sums to 6 and the density reads 7.0 -- the quadratic, per run."""
    recs = [
        _rec(task="T01", attempt=0, fix=0),
        _rec(task="T01", attempt=1, fix=1, outcome=BenchmarkOutcome.REVISED),
        _rec(task="T01", attempt=2, fix=2),
        _rec(task="T01", attempt=3, fix=3),
    ]
    cell = _code_cell(recs)
    assert cell.fix_attempts == 3
    assert cell.gate_rejects == 1
    assert cell.n_runs == 1
    assert cell.density == 4.0
