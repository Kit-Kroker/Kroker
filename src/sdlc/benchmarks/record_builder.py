"""Pure constructor for BenchmarkRecord across stages and tasks (spec A §3.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from temporalio import workflow

from ..core.models import PipelineConfig, RoleUsage
from ..observability.usage import cost_bag_from_spend
from ..stages.plan.models import PlanDrift
from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    JudgeKind,
    QualityScore,
    SpeedBag,
    WasteBag,
)


def stage_record(
    cfg: PipelineConfig,
    stage: str,
    role: str,
    started: datetime,
    ended: datetime,
    quality_score: float | None,
    judge: str,
    outcome: BenchmarkOutcome,
    model: str,
    harness: Any = None,
    lead_harness: Any = None,
    cost_usd: float | None = None,
    spend: RoleUsage | None = None,
    fix_attempts: int = 0,
    task_id: str | None = None,
    attempt: int | None = None,
    waste: WasteBag | None = None,
    plan_drift: PlanDrift | None = None,
    error: str | None = None,
    run_id: str | None = None,
) -> BenchmarkRecord:
    scope = BenchmarkScope.TASK_ATTEMPT if task_id is not None else BenchmarkScope.STAGE
    if run_id is None:
        try:
            run_id = workflow.info().workflow_id
        except Exception:
            run_id = ""
    bench_cfg = cfg.benchmark
    bench_run_id = (bench_cfg.bench_run_id if bench_cfg else None) or "_unknown"
    case_id = (bench_cfg.case_id if bench_cfg else None) or "_unknown"
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=bench_run_id,
        case_id=case_id,
        scope=scope,
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        role=role,
        harness=harness,
        lead_harness=lead_harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=quality_score, judge=cast(JudgeKind, judge)),
        cost=cost_bag_from_spend(spend, cost_usd),
        speed=SpeedBag(
            wall_clock_s=(ended - started).total_seconds(), started_at=started, ended_at=ended
        ),
        waste=waste,
        plan_drift=plan_drift,
        outcome=outcome,
        fix_attempts=fix_attempts,
        error=error,
    )
