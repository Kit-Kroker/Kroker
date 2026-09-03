from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
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
