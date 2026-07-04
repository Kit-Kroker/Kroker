"""Composite-score computation for benchmark records.

Pure functions: given a bag of BenchmarkRecords and weights, produce one
BenchmarkSummary per (case, stage, harness, model) cell. Quality is the
dominant axis; cost/speed are normalized within the (case, stage) group.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from ..models import HarnessKind
from .models import BenchmarkRecord, BenchmarkSummary, CompositeWeights


def _safe_mean(xs: list[float]) -> float | None:
    return mean(xs) if xs else None


def compute_summaries(
    records: list[BenchmarkRecord],
    weights: CompositeWeights | None = None,
) -> list[BenchmarkSummary]:
    w = weights or CompositeWeights()
    # group raw records by cell identity
    by_cell: dict[tuple[str, str, str | None, str], list[BenchmarkRecord]] = (
        defaultdict(list))
    for r in records:
        by_cell[(r.case_id, r.stage, r.harness.value if r.harness else None,
                 r.model)].append(r)

    summaries: list[BenchmarkSummary] = []
    # normalization happens within (case_id, stage) across all cells in it
    for case_id, stage in {(r.case_id, r.stage) for r in records}:
        group = [r for r in records
                 if r.case_id == case_id and r.stage == stage]
        costed = [r for r in group if r.cost.usd is not None]
        timed = [r for r in group if r.speed.wall_clock_s is not None]
        max_usd = max((r.cost.usd for r in costed), default=None)
        max_sec = max((r.speed.wall_clock_s for r in timed), default=None)
        use_cost = len(costed) >= 2 and max_usd
        use_speed = len(timed) >= 2 and max_sec

        for (_c, _s, h, m), cell_recs in by_cell.items():
            if _c != case_id or _s != stage:
                continue
            scored = [r for r in cell_recs if r.quality.score is not None]
            mean_q = _safe_mean([r.quality.score for r in scored])
            mean_usd = _safe_mean([r.cost.usd for r in cell_recs
                                   if r.cost.usd is not None])
            mean_sec = _safe_mean([r.speed.wall_clock_s for r in cell_recs
                                   if r.speed.wall_clock_s is not None])

            composite = _composite(mean_q, mean_usd, mean_sec,
                                   max_usd, max_sec, use_cost, use_speed, w)
            harness = (HarnessKind(h) if h else None)
            summaries.append(BenchmarkSummary(
                case_id=case_id, stage=stage, harness=harness, model=m,
                n=len(cell_recs), mean_quality=mean_q, mean_cost_usd=mean_usd,
                mean_wall_clock_s=mean_sec, composite=composite,
            ))
    return summaries


def _composite(mean_q, mean_usd, mean_sec, max_usd, max_sec,
               use_cost, use_speed, w):
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
