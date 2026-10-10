"""Summary rows for benchmark records, built from runs (013, R-11).

Rows are keyed `(case, stage, harness, arm, generation)` from the run
model — one row per stage for a pre-012 cell however many model labels
its records carry, and never a row mixing generations. Quality is a
rubric score only (`RUBRIC_JUDGES`); a pass/fail verdict is a pass rate
with its denominator; the code row carries the two task scores and no
quality. The composite is decided per case by `composite_shown`
(FR-034): None unless the case has two arms with graded runs.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .models import (
    RUBRIC_JUDGES,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    BenchmarkSummary,
    CompositeWeights,
)
from .runs import Run, build_runs, composite_shown, gate_passed

_ROW_SCOPES = (BenchmarkScope.STAGE, BenchmarkScope.TASK_ATTEMPT)


def _safe_mean(xs: list[float]) -> float | None:
    return mean(xs) if xs else None


def _tokens_of(records: list[BenchmarkRecord]) -> int | None:
    total = 0
    measured = False
    for r in records:
        has = r.cost.input_tokens is not None or r.cost.output_tokens is not None
        measured = measured or has
        total += (r.cost.input_tokens or 0) + (r.cost.output_tokens or 0)
    return total if measured else None


def _row_scope(r: BenchmarkRecord) -> bool:
    """Stage and task-attempt records are measurements; the oracle-task
    records belong to the task/error matrices and the cell record is
    status, so neither enters a summary row (as at base)."""
    return r.scope in _ROW_SCOPES


def _normalisation(records: list[BenchmarkRecord]) -> dict[tuple[str, str], tuple]:
    """Per (case, stage) normalisation context for the composite — at this
    task the base normalisation (record maxima across the case+stage);
    R-10's arm means replace it in T005."""
    ctx: dict[tuple[str, str], tuple] = {}
    for case_id, stage in {(r.case_id, r.stage) for r in records}:
        group = [r for r in records if r.case_id == case_id and r.stage == stage]
        usd_vals = [r.cost.usd for r in group if r.cost.usd is not None]
        sec_vals = [r.speed.wall_clock_s for r in group if r.speed.wall_clock_s is not None]
        max_usd = max(usd_vals) if usd_vals else None
        max_sec = max(sec_vals) if sec_vals else None
        ctx[(case_id, stage)] = (
            max_usd,
            max_sec,
            len(usd_vals) >= 2 and bool(max_usd),
            len(sec_vals) >= 2 and bool(max_sec),
        )
    return ctx


def compute_summaries(
    records: list[BenchmarkRecord],
    weights: CompositeWeights | None = None,
) -> list[BenchmarkSummary]:
    w = weights or CompositeWeights()
    runs = build_runs(records)
    decisions = composite_shown(runs)

    # R-11: one row per (case, stage, harness, arm, generation), holding
    # the runs of that key and their records at that stage.
    stage_rows: dict[tuple[str, str, str, str, str], list[tuple[Run, list[BenchmarkRecord]]]] = (
        defaultdict(list)
    )
    oracle_rows: dict[tuple[str, str, str, str, str], list[Run]] = defaultdict(list)
    for run in runs:
        row_records = [r for r in run.records if _row_scope(r)]
        for stage in sorted({r.stage for r in row_records}):
            key = (run.case_id, stage, run.harness, run.arm, run.generation)
            stage_rows[key].append((run, [r for r in row_records if r.stage == stage]))
        if run.status == "graded" and any(r.scope is BenchmarkScope.ORACLE for r in run.records):
            # Contract §5.6: an oracle record of a lost run is in no row;
            # a graded run without an oracle record has nothing to add.
            okey = (run.case_id, "oracle", run.harness, run.arm, run.generation)
            oracle_rows[okey].append(run)

    row_eligible = [r for r in records if _row_scope(r) or r.scope is BenchmarkScope.ORACLE]
    ctx = _normalisation(row_eligible)

    summaries: list[BenchmarkSummary] = []
    summaries += [
        _stage_row(key, members, decisions, ctx, w) for key, members in stage_rows.items()
    ]
    summaries += [
        _oracle_row(key, members, decisions, ctx, w) for key, members in oracle_rows.items()
    ]
    summaries.sort(key=lambda s: (s.case_id, s.stage, s.generation, s.arm, s.model))
    return summaries


def _composite(mean_q, mean_usd, mean_sec, max_usd, max_sec, use_cost, use_speed, w):
    if mean_q is None:
        return None
    q_norm = mean_q
    # renormalize weights over available axes
    avail_w = {"quality": w.quality}
    norms = {"quality": q_norm}
    if use_cost and mean_usd is not None and max_usd:
        avail_w["cost"] = w.cost
        norms["cost"] = 1 - (mean_usd / max_usd)
    if use_speed and mean_sec is not None and max_sec:
        avail_w["speed"] = w.speed
        norms["speed"] = 1 - (mean_sec / max_sec)
    total = sum(avail_w.values())
    if total <= 0:
        return mean_q
    return sum(avail_w[k] * norms[k] for k in norms) / total


def _composite_for(
    case_id: str,
    stage: str,
    mean_q,
    mean_usd,
    mean_sec,
    decisions,
    ctx,
    w,
):
    """FR-034: no composite for a case with fewer than two graded arms —
    the decision is made by `composite_shown`, never inferred from the
    row's own values."""
    if not decisions[case_id].shown:
        return None
    max_usd, max_sec, use_cost, use_speed = ctx[(case_id, stage)]
    return _composite(mean_q, mean_usd, mean_sec, max_usd, max_sec, use_cost, use_speed, w)


def _stage_row(
    key: tuple[str, str, str, str, str],
    members: list[tuple[Run, list[BenchmarkRecord]]],
    decisions,
    ctx,
    w,
) -> BenchmarkSummary:
    case_id, stage, _harness_s, arm, generation = key
    run_records = [r for _run, recs in members for r in recs]
    # No reader guesses (plan rule 3): a not_evaluated outcome enters no
    # count and no mean. A score-None record under any other outcome still
    # counts (it was attempted; only its quality is unknown).
    counted = [r for r in run_records if r.outcome is not BenchmarkOutcome.NOT_EVALUATED]
    rubric = [
        r for r in counted if r.quality.judge in RUBRIC_JUDGES and r.quality.score is not None
    ]
    mean_q = _safe_mean([r.quality.score for r in rubric if r.quality.score is not None])
    if stage == "code":
        # Contract §5.4: no share of attempts is shown as a quality score.
        mean_q = None

    # Contract §5.5: a qa row of only copy runs shows `copy of code` in
    # place of its pass rate; a mixed row counts only the non-copy runs.
    qa_is_copy = stage == "qa" and bool(members) and all(run.qa_is_copy for run, _ in members)
    if qa_is_copy:
        pass_records: list[BenchmarkRecord] = []
    else:
        pass_records = (
            [r for run, recs in members if not run.qa_is_copy for r in recs]
            if stage == "qa"
            else counted
        )
        pass_records = [r for r in pass_records if r.outcome is not BenchmarkOutcome.NOT_EVALUATED]
    pass_n = pass_d = None
    if not rubric and pass_records:
        verdicts = [gate_passed(stage, r.outcome) for r in pass_records]
        pass_d = sum(1 for v in verdicts if v is not None)
        pass_n = sum(1 for v in verdicts if v is True)

    first_attempt = after_repair = None
    if stage == "code":
        # Contract §5.4: the sums of the row's runs' (k, n).
        firsts = [run.first_attempt for run, _ in members]
        lasts = [run.after_repair for run, _ in members]
        first_attempt = (sum(k for k, _n in firsts), sum(n for _k, n in firsts))
        after_repair = (sum(k for k, _n in lasts), sum(n for _k, n in lasts))

    per_run_tokens = [t for t in (_tokens_of(recs) for _run, recs in members) if t is not None]
    mean_usd = _safe_mean([r.cost.usd for r in counted if r.cost.usd is not None])
    mean_sec = _safe_mean(
        [r.speed.wall_clock_s for r in counted if r.speed.wall_clock_s is not None]
    )
    harness = next((r.harness for r in run_records if r.harness is not None), None)
    lead_harness = next((r.lead_harness for r in run_records if r.lead_harness is not None), None)
    return BenchmarkSummary(
        case_id=case_id,
        stage=stage,
        harness=harness,
        lead_harness=lead_harness,
        # The model column is the sorted comma-joined distinct models of
        # the row (data-model §2) — the run key does not include it.
        model=",".join(sorted({r.model for r in counted})),
        n=len(counted),
        mean_quality=mean_q,
        mean_cost_usd=mean_usd,
        mean_wall_clock_s=mean_sec,
        composite=_composite_for(case_id, stage, mean_q, mean_usd, mean_sec, decisions, ctx, w),
        errors=[r.error for r in counted if r.error],
        cell_id=next((r.cell_id for r in run_records if r.cell_id is not None), None),
        arm=arm,
        pre012=(generation == "pre012"),
        generation=generation,
        pass_n=pass_n,
        pass_d=pass_d,
        first_attempt=first_attempt,
        after_repair=after_repair,
        tokens=round(mean(per_run_tokens)) if per_run_tokens else None,
        qa_is_copy=qa_is_copy,
    )


def _oracle_row(
    key: tuple[str, str, str, str, str],
    graded_runs: list[Run],
    decisions,
    ctx,
    w,
) -> BenchmarkSummary:
    case_id, _stage, _harness_s, arm, generation = key
    oracle_records = [
        [r for r in run.records if r.scope is BenchmarkScope.ORACLE][-1] for run in graded_runs
    ]
    counted = [r for r in oracle_records if r.outcome is not BenchmarkOutcome.NOT_EVALUATED]
    # Contract §5.2: the oracle row's mean quality is the mean partial
    # credit of its graded runs, never a mean of oracle scores.
    mean_q = _safe_mean(
        [run.partial_credit for run in graded_runs if run.partial_credit is not None]
    )
    mean_usd = _safe_mean([r.cost.usd for r in counted if r.cost.usd is not None])
    mean_sec = _safe_mean(
        [r.speed.wall_clock_s for r in counted if r.speed.wall_clock_s is not None]
    )
    harness = next((r.harness for r in counted if r.harness is not None), None)
    lead_harness = next((r.lead_harness for r in counted if r.lead_harness is not None), None)
    return BenchmarkSummary(
        case_id=case_id,
        stage="oracle",
        harness=harness,
        lead_harness=lead_harness,
        model=",".join(sorted({r.model for r in counted})),
        n=len(counted),
        mean_quality=mean_q,
        mean_cost_usd=mean_usd,
        mean_wall_clock_s=mean_sec,
        composite=_composite_for(case_id, "oracle", mean_q, mean_usd, mean_sec, decisions, ctx, w),
        errors=[r.error for r in counted if r.error],
        cell_id=next((r.cell_id for r in counted if r.cell_id is not None), None),
        arm=arm,
        pre012=(generation == "pre012"),
        generation=generation,
        all_pass=(sum(1 for run in graded_runs if run.all_pass), len(graded_runs)),
        tokens=(
            round(mean(ts))
            if (ts := [t for t in (_tokens_of([r]) for r in oracle_records) if t is not None])
            else None
        ),
    )
