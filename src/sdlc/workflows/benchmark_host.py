"""BenchmarkHost -- benchmark scoring, recording, and judging (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Consumes: ReportHost._emit via the MRO.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..benchmarks.judge import (
        JudgeInput,
        _build_judge_input,
        judge_artifact,
    )
    from ..benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        QualityScore,
        WasteBag,
    )
    from ..benchmarks.record_builder import stage_record
    from ..benchmarks.recorder import record_benchmark
    from ..core.models import PipelineConfig, RoleUsage
    from ..models import PlanDrift
    from ..observability.trace import RunEventKind

RECORD_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=5)
)


class BenchmarkHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _benchmarking(cfg: PipelineConfig) -> bool:
        return bool(cfg.benchmark and cfg.benchmark.case_id)

    def _stage_record(
        self,
        cfg: PipelineConfig,
        stage: str,
        role: str,
        started: datetime,
        ended: datetime,
        quality_score: float | None,
        judge: str,
        outcome: BenchmarkOutcome,
        model: str,
        harness=None,
        lead_harness=None,
        cost_usd: float | None = None,
        spend: RoleUsage | None = None,
        fix_attempts: int = 0,
        task_id: str | None = None,
        attempt: int | None = None,
        waste: WasteBag | None = None,
        plan_drift: PlanDrift | None = None,
        error: str | None = None,
    ) -> BenchmarkRecord:
        return stage_record(
            cfg,
            stage=stage,
            role=role,
            started=started,
            ended=ended,
            quality_score=quality_score,
            judge=judge,
            outcome=outcome,
            model=model,
            harness=harness,
            lead_harness=lead_harness,
            cost_usd=cost_usd,
            spend=spend,
            fix_attempts=fix_attempts,
            task_id=task_id,
            attempt=attempt,
            waste=waste,
            plan_drift=plan_drift,
            error=error,
            run_id=workflow.info().workflow_id,
        )

    async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord) -> None:
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.STAGE_ENDED,
            stage=record.stage,
            role=record.role,
            outcome=record.outcome.value,
            duration_s=str(record.speed.wall_clock_s),
            fix_attempts=str(record.fix_attempts),
            **({"cost_usd": str(record.cost.usd)} if record.cost.usd is not None else {}),
        )
        if not self._benchmarking(cfg):
            return
        await workflow.execute_activity(record_benchmark, record, **RECORD_ACT)

    async def _judge(
        self, cfg: PipelineConfig, artifact_json: str, stage: str, author_model: str
    ) -> QualityScore:
        """Judge a proposer-stage artifact iff benchmarking is on AND a
        rubric is registered for the stage.

        Returns a graceful QualityScore(score=None, judge='llm_judge') when
        judging is skipped — when not benchmarking, or no rubric exists for
        the stage — so the record still emits without failing the stage.
        The LLM call lives in the judge_artifact activity, never in workflow
        code.

        ``stage`` is the rubric-map key carried on cfg.benchmark.rubrics
        (e.g. 'clarifier', 'architect'), NOT the record's stage field.

        Author model: passed in by the caller, which knows both this rubric key
        and the stage name STAGE_MODELS is keyed by. The judge_model (e.g.
        'openai/gpt-5.2') differs from the author → ADR-6 cross-family satisfied.
        """
        fallback = QualityScore(score=None, judge="llm_judge")
        if not self._benchmarking(cfg):
            return fallback
        judge_input: JudgeInput | None = _build_judge_input(
            artifact_json=artifact_json,
            rubrics=cfg.benchmark.rubrics,
            stage=stage,
            author_model=author_model,
            judge_model=cfg.benchmark.judge_model,
            vetoes=cfg.benchmark.vetoes,
        )
        if judge_input is None:
            return fallback
        return await workflow.execute_activity(judge_artifact, judge_input, **RECORD_ACT)
