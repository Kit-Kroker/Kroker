import json
from datetime import datetime, timedelta

from sdlc.benchmarks.heatmap import (
    ORACLE_STAGE,
    build_heatmap,
    render_heatmap_json,
)
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
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
    scope=BenchmarkScope.STAGE,
    outcome=BenchmarkOutcome.PASS,
    fix=0,
):
    t = datetime(2026, 7, 24, 10)
    return BenchmarkRecord(
        run_id=run,
        bench_run_id="b1",
        case_id=case,
        scope=scope,
        stage=stage,
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
        model="m",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=outcome,
        fix_attempts=fix,
    )


def test_density_blends_rejects_fixes_and_oracle_over_runs():
    recs = [
        _rec(run="r1", stage="code", outcome=BenchmarkOutcome.REVISED, fix=2),
        _rec(run="r2", stage="code", outcome=BenchmarkOutcome.FAIL, fix=3),
        # oracle failure for the same case, distinct synthetic column
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE, outcome=BenchmarkOutcome.FAIL),
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
    assert oracle.density == 0.5  # 1 oracle fail / 2 runs


def test_n_runs_dedups_distinct_run_ids_per_case():
    recs = [
        _rec(run="r1", stage="qa", outcome=BenchmarkOutcome.FAIL),
        _rec(run="r1", stage="code", outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    assert all(c.n_runs == 1 for c in hm.cells)


def test_unknown_stage_appended_before_oracle_not_dropped():
    recs = [
        _rec(stage="clarify", outcome=BenchmarkOutcome.FAIL),
        _rec(stage="mystery", outcome=BenchmarkOutcome.FAIL),
        _rec(stage="oracle", scope=BenchmarkScope.ORACLE, outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    assert hm.stages == ["clarify", "mystery", "oracle"]


def test_language_map_recorded_per_case():
    recs = [
        _rec(case="py", stage="code", outcome=BenchmarkOutcome.FAIL),
        _rec(case="go", stage="code", outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs, language_by_case={"py": "python"})
    assert hm.language_by_case == {"py": "python", "go": ""}


def test_empty_records_give_empty_heatmap():
    hm = build_heatmap([])
    assert hm.cells == [] and hm.cases == [] and hm.stages == []
    assert hm.max_density == 0.0


def test_oracle_task_records_excluded_from_rework_density():
    # a case-level ORACLE record plus several ORACLE_TASK records (E-31 task
    # matrix) for the same case/run must produce the SAME heatmap cell as if
    # the ORACLE_TASK records were entirely absent -- there is no gate on the
    # oracle stage, so task-level fails/revises must not be double-counted
    # as gate_rejects.
    without_tasks = [
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE, outcome=BenchmarkOutcome.FAIL),
    ]
    with_tasks = without_tasks + [
        _rec(
            run="r1",
            stage="oracle",
            scope=BenchmarkScope.ORACLE_TASK,
            outcome=BenchmarkOutcome.FAIL,
            fix=1,
        ),
        _rec(
            run="r1",
            stage="oracle",
            scope=BenchmarkScope.ORACLE_TASK,
            outcome=BenchmarkOutcome.REVISED,
            fix=2,
        ),
        _rec(
            run="r1",
            stage="oracle",
            scope=BenchmarkScope.ORACLE_TASK,
            outcome=BenchmarkOutcome.ESCALATED,
        ),
    ]
    hm_without = build_heatmap(without_tasks)
    hm_with = build_heatmap(with_tasks)
    cell_without = next(c for c in hm_without.cells if c.stage == ORACLE_STAGE)
    cell_with = next(c for c in hm_with.cells if c.stage == ORACLE_STAGE)
    assert cell_with.gate_rejects == cell_without.gate_rejects == 0
    assert cell_with.oracle_fails == cell_without.oracle_fails == 1
    assert cell_with.fix_attempts == cell_without.fix_attempts == 0
    assert cell_with.density == cell_without.density


def test_oracle_non_fail_rework_not_counted_as_oracle_failure():
    recs = [
        _rec(
            run="r1",
            stage="oracle",
            scope=BenchmarkScope.ORACLE,
            outcome=BenchmarkOutcome.ESCALATED,
        ),
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE, outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    cell = next(c for c in hm.cells if c.stage == ORACLE_STAGE)
    assert cell.oracle_fails == 1  # only the FAIL, not the ESCALATED


def test_unknown_stage_renders_in_trailing_bucket_before_oracle():
    """E-77 T028 pin (existing behaviour): records stamped stage='unknown'
    (unmapped/unregistered node types, FR-004/FR-005) aggregate into the
    trailing non-canonical bucket like any other stage -- never dropped, never
    folded into a canonical column -- and render before the synthetic oracle
    column. Pinned now so E-77's heatmap pass (T033) keeps it byte-stable."""
    recs = [
        _rec(stage="code", outcome=BenchmarkOutcome.REVISED, fix=1),
        _rec(stage="unknown", outcome=BenchmarkOutcome.FAIL, fix=2),
        _rec(stage="unknown", outcome=BenchmarkOutcome.PASS, fix=3),
        _rec(stage="oracle", scope=BenchmarkScope.ORACLE, outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    assert hm.stages == ["code", "unknown", "oracle"]
    by = {(c.case, c.stage): c for c in hm.cells}
    bucket = by[("c1", "unknown")]
    assert bucket.gate_rejects == 1  # the FAIL; PASS is not rework
    assert bucket.fix_attempts == 5  # 2 + 3, summed like any other stage
    assert bucket.n_runs == 1
    assert bucket.density == 6.0  # (1 gate + 5 fix) over 1 run
    rendered = json.loads(render_heatmap_json(hm))
    assert rendered["stages"] == ["code", "unknown", "oracle"]
    unknown_cells = [c for c in rendered["cells"] if c["stage"] == "unknown"]
    assert len(unknown_cells) == 1
    assert unknown_cells[0]["gate_rejects"] == 1
    assert unknown_cells[0]["fix_attempts"] == 5
    assert unknown_cells[0]["density"] == 6.0


# --- E-77 T032 (RED): the once-per-activation fix pass (FR-017 / R-12) -------

_PIN_RECORDS = [
    _rec(case="pin", run="p1", stage="clarify", outcome=BenchmarkOutcome.REVISED, fix=1),
    _rec(case="pin", run="p1", stage="code", outcome=BenchmarkOutcome.FAIL, fix=2),
    _rec(case="pin", run="p2", stage="code", outcome=BenchmarkOutcome.PASS, fix=0),
    _rec(
        case="pin",
        run="p1",
        stage="oracle",
        scope=BenchmarkScope.ORACLE,
        outcome=BenchmarkOutcome.FAIL,
    ),
    _rec(case="pin", run="p1", stage="mystery", outcome=BenchmarkOutcome.FAIL, fix=1),
]

_PINNED_JSON = """{
  "cells": [
    {
      "case": "pin",
      "stage": "clarify",
      "gate_rejects": 1,
      "fix_attempts": 1,
      "oracle_fails": 0,
      "n_runs": 2,
      "density": 1.0
    },
    {
      "case": "pin",
      "stage": "code",
      "gate_rejects": 1,
      "fix_attempts": 2,
      "oracle_fails": 0,
      "n_runs": 2,
      "density": 1.5
    },
    {
      "case": "pin",
      "stage": "oracle",
      "gate_rejects": 0,
      "fix_attempts": 0,
      "oracle_fails": 1,
      "n_runs": 2,
      "density": 0.5
    },
    {
      "case": "pin",
      "stage": "mystery",
      "gate_rejects": 1,
      "fix_attempts": 1,
      "oracle_fails": 0,
      "n_runs": 2,
      "density": 1.0
    }
  ],
  "cases": [
    "pin"
  ],
  "stages": [
    "clarify",
    "code",
    "mystery",
    "oracle"
  ],
  "max_density": 1.5,
  "language_by_case": {
    "pin": ""
  }
}"""


def test_current_records_render_byte_identical_to_the_pinned_literal():
    """T032(a): captured on the pre-T033 code over fixed current-shape
    records (varied stages, an oracle record, no graph field). No record
    carries fail_reentry == 1, so T033's extra pass must be a no-op here --
    byte-identical forever."""
    assert render_heatmap_json(build_heatmap(_PIN_RECORDS)) == _PINNED_JSON


def _stamped(rec, activation_id, node_id, round_, node_stage, fail_reentry):
    from sdlc.benchmarks.models import GraphAttribution

    return rec.model_copy(
        update={
            "graph": GraphAttribution(
                graph_sha="a" * 64,
                activation_id=activation_id,
                node_id=node_id,
                round=round_,
                node_stage=node_stage,
                fail_reentry=fail_reentry,
            )
        }
    )


def test_fail_reentry_adds_exactly_one_per_reentered_activation():
    """FR-017 / R-12, as written: "add 1 to the fix count of (case_id,
    graph.node_stage) once per distinct (run_id, graph.activation_id) where
    graph.fail_reentry == 1". The distinct key is (run_id, activation_id)
    alone, so an activation counts ONCE however many records it emitted, on
    the cell of its node_stage. Records of one activation share that stage
    (it is the activation's node's stage), so the fixture keeps node_stage
    uniform per activation: code#2 (fail_reentry=1) and qa#1 (fail_reentry=1)
    each add 1 to their own stage cell; code#1 (fail_reentry=0) adds nothing.
    Expected delta: (fx, code) +1 and (fx, qa) +1 -- exactly 2 in total,
    and no other cell moves."""
    plain = [
        _rec(case="fx", run="r1", stage="code", outcome=BenchmarkOutcome.PASS, fix=1),
        _rec(case="fx", run="r1", stage="code", outcome=BenchmarkOutcome.FAIL, fix=2),
        _rec(case="fx", run="r1", stage="code", outcome=BenchmarkOutcome.REVISED, fix=1),
        _rec(case="fx", run="r1", stage="code", outcome=BenchmarkOutcome.PASS, fix=0),
        _rec(case="fx", run="r1", stage="qa", outcome=BenchmarkOutcome.PASS, fix=3),
        _rec(case="fx", run="r1", stage="qa", outcome=BenchmarkOutcome.FAIL, fix=1),
    ]
    stamped = [
        _stamped(plain[0], "code#1", "code", 1, "code", 0),
        _stamped(plain[1], "code#1", "code", 1, "code", 0),
        _stamped(plain[2], "code#2", "code", 2, "code", 1),
        _stamped(plain[3], "code#2", "code", 2, "code", 1),
        _stamped(plain[4], "qa#1", "qa", 1, "qa", 1),
        _stamped(plain[5], "qa#1", "qa", 1, "qa", 1),
    ]
    base = {(c.case, c.stage): c.fix_attempts for c in build_heatmap(plain).cells}
    got = {(c.case, c.stage): c.fix_attempts for c in build_heatmap(stamped).cells}
    assert got == {
        ("fx", "code"): base[("fx", "code")] + 1,  # code#2: two records, one add
        ("fx", "qa"): base[("fx", "qa")] + 1,  # qa#1: two records, one add
    }


def test_duplicate_records_of_one_reentered_activation_add_one_not_two():
    plain = [
        _rec(case="dupe", run="r1", stage="code", outcome=BenchmarkOutcome.FAIL, fix=0),
        _rec(case="dupe", run="r1", stage="code", outcome=BenchmarkOutcome.FAIL, fix=0),
    ]
    stamped = [
        _stamped(plain[0], "code#3", "code", 3, "code", 1),
        _stamped(plain[1], "code#3", "code", 3, "code", 1),
    ]
    base = {(c.case, c.stage): c.fix_attempts for c in build_heatmap(plain).cells}
    got = {(c.case, c.stage): c.fix_attempts for c in build_heatmap(stamped).cells}
    assert got == {("dupe", "code"): base[("dupe", "code")] + 1}  # once per activation


def test_fail_reentry_none_everywhere_is_byte_identical_to_no_graph():
    """FR-017's other half: when no record carries fail_reentry == 1, the
    output is byte-identical to main -- even with full graph attribution
    (activation, round, node stage) present on every record."""
    plain = [
        _rec(case="absent", run="r1", stage="code", outcome=BenchmarkOutcome.FAIL, fix=1),
        _rec(case="absent", run="r1", stage="qa", outcome=BenchmarkOutcome.REVISED, fix=2),
    ]
    axis_absent = [
        _stamped(plain[0], "code#1", "code", 1, "code", None),
        _stamped(plain[1], "qa#1", "qa", 1, "qa", None),
    ]
    assert render_heatmap_json(build_heatmap(axis_absent)) == render_heatmap_json(
        build_heatmap(plain)
    )
