"""Composite-score computation for benchmark records.

Pure functions: given a bag of BenchmarkRecords and weights, produce one
BenchmarkSummary per (case, stage, harness, model) cell. Quality is the
dominant axis; cost/speed are normalized within the (case, stage) group.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    BenchmarkSummary,
    CompositeWeights,
    cell_key,
    is_pre012,
)


def _safe_mean(xs: list[float]) -> float | None:
    return mean(xs) if xs else None


def compute_summaries(
    records: list[BenchmarkRecord],
    weights: CompositeWeights | None = None,
) -> list[BenchmarkSummary]:
    w = weights or CompositeWeights()
    # ORACLE_TASK records (E-31 task matrix) share stage="oracle" and the
    # cell's harness/model with the case-level ORACLE record; they belong to
    # the task/error matrices, not this per-cell summary, so they're
    # excluded before grouping to avoid inflating n / blending mean_quality
    # and composite into the oracle summary row. CELL records (012) are the
    # one status record per cell, not a measurement — they enter no row and
    # no count either (contract §7.3).
    records = [
        r
        for r in records
        if r.scope is not BenchmarkScope.ORACLE_TASK and r.scope is not BenchmarkScope.CELL
    ]
    # 012 (contract §7.3): group by (case, stage, cell_key, is_pre012) — the
    # pre-012 key embeds harness/lead/model so those rows partition exactly
    # as before; a 012 row is one cell (records of one cell_id), and no row
    # ever mixes kinds (ruling R3: pre-012 aggregates are untrusted and are
    # never averaged together with 012 ones).
    by_cell: dict[tuple[str, str, str | None, bool], list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        by_cell[(r.case_id, r.stage, cell_key(r), is_pre012(r))].append(r)

    summaries: list[BenchmarkSummary] = []
    # normalization happens within (case_id, stage) across all cells in it
    for case_id, stage in {(r.case_id, r.stage) for r in records}:
        group = [r for r in records if r.case_id == case_id and r.stage == stage]
        costed = [r for r in group if r.cost.usd is not None]
        timed = [r for r in group if r.speed.wall_clock_s is not None]
        usd_vals = [r.cost.usd for r in costed if r.cost.usd is not None]
        sec_vals = [r.speed.wall_clock_s for r in timed if r.speed.wall_clock_s is not None]
        max_usd = max(usd_vals) if usd_vals else None
        max_sec = max(sec_vals) if sec_vals else None
        use_cost = len(costed) >= 2 and max_usd
        use_speed = len(timed) >= 2 and max_sec

        for (_c, _s, _key, pre), cell_recs in by_cell.items():
            if _c != case_id or _s != stage:
                continue
            # No reader guesses (plan rule 3): a not_evaluated outcome
            # enters no count and no mean. A score-None record under any
            # other outcome still counts (it was attempted; only its
            # quality is unknown).
            counted = [r for r in cell_recs if r.outcome is not BenchmarkOutcome.NOT_EVALUATED]
            scored = [r for r in counted if r.quality.score is not None]
            mean_q = _safe_mean([r.quality.score for r in scored if r.quality.score is not None])
            mean_usd = _safe_mean([r.cost.usd for r in counted if r.cost.usd is not None])
            mean_sec = _safe_mean(
                [r.speed.wall_clock_s for r in counted if r.speed.wall_clock_s is not None]
            )

            composite = _composite(
                mean_q, mean_usd, mean_sec, max_usd, max_sec, use_cost, use_speed, w
            )
            harness = next((r.harness for r in cell_recs if r.harness is not None), None)
            lead_harness = next(
                (r.lead_harness for r in cell_recs if r.lead_harness is not None), None
            )
            errors = [r.error for r in cell_recs if r.error]
            summaries.append(
                BenchmarkSummary(
                    case_id=case_id,
                    stage=stage,
                    harness=harness,
                    lead_harness=lead_harness,
                    # A 012 row spans the cell's records: the model column is
                    # the sorted comma-joined distinct models (data-model
                    # §1.4). A pre-012 row's key embeds one model, so the
                    # join yields it unchanged.
                    model=",".join(sorted({r.model for r in cell_recs})),
                    n=len(counted),
                    mean_quality=mean_q,
                    mean_cost_usd=mean_usd,
                    mean_wall_clock_s=mean_sec,
                    composite=composite,
                    errors=errors,
                    cell_id=next((r.cell_id for r in cell_recs if r.cell_id is not None), None),
                    arm=next((r.arm for r in cell_recs if r.arm is not None), None),
                    pre012=pre,
                )
            )
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
