from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.core.models import (
    HarnessKind,
)


def _rec(case, harness, model, q, usd, secs, lead_harness=None):
    return BenchmarkRecord(
        run_id="r",
        bench_run_id="b",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=harness,
        lead_harness=lead_harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd, input_tokens=10, output_tokens=5),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _summarize(records, weights=None):
    return {s.model: s for s in compute_summaries(records, weights)}


def test_composite_ranks_better_quality_higher_even_if_pricier():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].composite > s["opus"].composite


def test_cost_axis_dropped_when_fewer_than_two_costed():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=None, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=None, secs=50),
    ]
    s = _summarize(recs)
    # both composites still produced; quality + speed only (renormalized)
    assert s["sonnet"].composite is not None
    assert s["opus"].composite is not None


def test_judge_error_records_excluded_from_composite():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=None, usd=2.0, secs=200),
    ]
    # The opus record had a judge error (q=None). It still appears as a summary
    # row but its composite is None.
    s = _summarize(recs)
    assert s["opus"].composite is None
    assert s["opus"].mean_quality is None


def test_custom_weights_change_ranking():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.1, secs=10),
    ]
    # weight cost heavily -> cheap opus wins
    s = _summarize(recs, CompositeWeights(quality=0.1, cost=0.8, speed=0.1))
    assert s["opus"].composite > s["sonnet"].composite


def _oracle_rec(case, harness, model, q, *, scope=BenchmarkScope.ORACLE, task_id=None):
    t = datetime(2026, 7, 27, 10)
    return BenchmarkRecord(
        run_id="r",
        bench_run_id="b",
        case_id=case,
        scope=scope,
        stage="oracle",
        task_id=task_id,
        role="oracle",
        harness=harness,
        model=model,
        quality=QualityScore(score=q, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )


def test_oracle_task_records_excluded_from_oracle_summary():
    # ORACLE_TASK records (E-31 task matrix) share stage="oracle" and the
    # cell's harness/model with the case-level ORACLE record. They must NOT
    # merge into the same BenchmarkSummary row -- that would inflate n and
    # blend mean_quality/composite the moment a case has tasks.yaml tasks.
    oracle_only = [
        _oracle_rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.8),
    ]
    with_tasks = oracle_only + [
        _oracle_rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            q=1.0,
            scope=BenchmarkScope.ORACLE_TASK,
            task_id="t01",
        ),
        _oracle_rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            q=0.0,
            scope=BenchmarkScope.ORACLE_TASK,
            task_id="t02",
        ),
    ]
    s_only = _summarize(oracle_only)
    s_with = _summarize(with_tasks)
    assert s_with["sonnet"].n == s_only["sonnet"].n == 1
    assert s_with["sonnet"].mean_quality == s_only["sonnet"].mean_quality == 0.8
    assert s_with["sonnet"].composite == s_only["sonnet"].composite


def test_multiple_records_averaged_per_cell():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.8, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.6, usd=2.0, secs=200),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].n == 2
    assert abs(s["sonnet"].mean_quality - 0.7) < 1e-9


def test_crew_leads_summarize_into_separate_cells():
    """spec §5: harness=CREW records for two different leads share
    (case_id, stage, harness, model) -- without lead_harness in the group
    key they would blend into one composite, hiding the very comparison
    the crew:<lead_harness> sweep exists to make."""
    recs = [
        _rec(
            "c1",
            HarnessKind.CREW,
            "glm",
            q=0.9,
            usd=1.0,
            secs=100,
            lead_harness=HarnessKind.CLAUDE_CODE,
        ),
        _rec(
            "c1",
            HarnessKind.CREW,
            "glm",
            q=0.1,
            usd=1.0,
            secs=100,
            lead_harness=HarnessKind.OPENCODE,
        ),
    ]
    summaries = compute_summaries(recs)
    assert len(summaries) == 2
    by_lead = {s.lead_harness: s for s in summaries}
    assert by_lead[HarnessKind.CLAUDE_CODE].mean_quality == 0.9
    assert by_lead[HarnessKind.OPENCODE].mean_quality == 0.1


# --- 012 T009 (RED): rows never mix pre-012 and 012 records (contract §7.2) -

_CELL_STATUS = CellStatus(
    pipeline_finished=True,
    code_finished=True,
    completed=True,
    last_stage="merge",
    grading="graded",
    child_result="ok",
)


def _012_rec(case, stage, role, model, q, *, cell_id, arm, usd=0.1, secs=10.0):
    """A 012-shape record: provenance + cell identity set (harness None --
    a proposer record -- so the cell label is the only grouping that can
    hold the row together)."""
    r = _rec(case, None, model, q, usd, secs)
    return r.model_copy(
        update={
            "stage": stage,
            "role": role,
            "kroker_commit": "abc123",
            "cell_id": cell_id,
            "arm": arm,
        }
    )


def _cell_scope_rec(case, cell_id, arm):
    r = _rec(case, None, "deterministic", None, None, 0.0)
    return r.model_copy(
        update={
            "scope": BenchmarkScope.CELL,
            "stage": "cell",
            "role": "cell",
            "quality": QualityScore(score=None, judge="contract"),
            "cell": _CELL_STATUS,
            "kroker_commit": "abc123",
            "cell_id": cell_id,
            "arm": arm,
        }
    )


def test_cell_scope_records_are_excluded_from_summaries():
    """contract §7.2: the one cell record per cell is status, not a
    measurement -- it enters no row and no count."""
    recs = [_rec("c1", None, "m1", q=0.8, usd=0.5, secs=10)]
    with_cell = recs + [_cell_scope_rec("c1", "c1#opencode#a1", "a1")]
    s_without = compute_summaries(recs)
    s_with = compute_summaries(with_cell)
    assert len(s_with) == len(s_without) == 1
    assert s_with[0].model == "m1"
    assert s_with[0].n == 1


def test_pre012_and_012_records_form_separate_rows():
    """contract §7.2/§7.3: grouping is by (case, stage, cell_key, is_pre012)
    -- the same case and stage from a pre-012 and a 012 record are two rows,
    one pre012 True and one False. A row never mixes kinds."""
    pre = _rec("c1", None, "m1", q=0.8, usd=0.5, secs=10)
    new = _012_rec("c1", "code", "dev", "m1", q=0.2, cell_id="c1#opencode#a1", arm="a1")
    rows = compute_summaries([pre, new])
    assert len(rows) == 2
    by_kind = {s.pre012: s for s in rows}
    assert by_kind[True].mean_quality == 0.8
    assert by_kind[False].mean_quality == 0.2
    assert by_kind[True].n == 1 and by_kind[False].n == 1


def test_012_row_keys_by_cell_and_joins_distinct_models_sorted():
    """contract §7.3 / data-model §1.4: a 012 row is keyed by the cell, so
    two records of the same cell with different models land in ONE row
    whose model is the sorted comma-joined distinct models, with cell_id
    and arm carried from the records."""
    cell_id = "c1#opencode#a1"
    recs = [
        _012_rec("c1", "code", "architect", "anthropic:glm-5.2", q=0.8, cell_id=cell_id, arm="a1"),
        _012_rec(
            "c1",
            "code",
            "dev",
            "zai-coding-plan/glm-5.3",
            q=0.6,
            cell_id=cell_id,
            arm="a1",
        ),
    ]
    rows = compute_summaries(recs)
    assert len(rows) == 1
    row = rows[0]
    assert row.model == "anthropic:glm-5.2,zai-coding-plan/glm-5.3"
    assert row.cell_id == cell_id
    assert row.arm == "a1"


def test_not_evaluated_record_changes_no_count_and_no_mean():
    """A `not_evaluated` record (score None) enters no count and no mean:
    the row it lands in keeps the n and mean_quality it had without it."""
    scored = _012_rec("c1", "merge", "dev", "m1", q=0.8, cell_id="c1#opencode#a1", arm="a1")
    not_evaluated = scored.model_copy(
        update={
            "role": "merge_verdict",
            "outcome": BenchmarkOutcome.NOT_EVALUATED,
            "quality": QualityScore(score=None, judge="contract"),
        }
    )
    without = compute_summaries([scored])
    with_row = compute_summaries([scored, not_evaluated])
    assert len(with_row) == len(without) == 1
    assert with_row[0].n == without[0].n == 1
    assert with_row[0].mean_quality == without[0].mean_quality == 0.8


def test_pre012_only_records_pin_base_values_and_carry_no_cell_identity():
    """PIN over the existing fixtures' shapes: with only pre-012 records,
    every row equals its base value and carries pre012 True, cell_id None,
    arm None -- a row never starts out marked 012."""
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.8, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.6, usd=2.0, secs=200),
    ]
    rows = compute_summaries(recs)
    assert len(rows) == 1
    s = rows[0]
    assert s.n == 2
    assert abs(s.mean_quality - 0.7) < 1e-9
    assert abs(s.mean_cost_usd - 1.5) < 1e-9
    assert abs(s.mean_wall_clock_s - 150.0) < 1e-9
    # default weights (0.6, 0.2, 0.2), both axes renormalized:
    # 0.6*0.7 + 0.2*(1-1.5/2) + 0.2*(1-150/200) = 0.42 + 0.05 + 0.05
    assert abs(s.composite - 0.52) < 1e-9
    assert s.pre012 is True
    assert s.cell_id is None
    assert s.arm is None
