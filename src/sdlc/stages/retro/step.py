"""Retro stage step execution (spec A §3.3).

Stage 14 retro (E-32): fires on every terminal path, populates run_summary(),
emits completion events, exports run artifacts, and updates episodic memory.
Strictly best-effort: any internal failure is trapped so the run's outcome
is never modified.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...artifacts.retention import RetentionInput, apply_session_retention, keep_full_transcripts
from ...core.context import StageContext
from ...core.models import ArtifactRef, PipelineConfig, RunSummary
from ...memory.activities import ReflectInput, reflect
from ...memory.models import MemoryKind
from ...observability.activities import RunExportInput, export_run_artifacts
from ...observability.trace import RunEvent, RunEventKind

_MEM_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=5),
)
_EXPORT_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=1),
)


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    summary: RunSummary,
    session_refs: list[ArtifactRef],
    trace: list[RunEvent],
) -> None:
    """Execute the retro stage.

    Best-effort: any internal exception is trapped so the run outcome is never changed.
    """
    try:
        if cfg.memory.enabled:
            ctx.emit(RunEventKind.MEMORY_RETAINED, stage="retro", item="run_summary")
        ctx.emit(RunEventKind.RUN_FINISHED, stage="retro", outcome=summary.outcome)

        if cfg.memory.enabled:
            await ctx.retain(
                cfg,
                MemoryKind.RUN_SUMMARY,
                cfg.memory.project_bank,
                text=summary.model_dump_json(),
                metadata={"run_id": summary.run_id, "stage": "retro"},
            )
            try:
                await workflow.execute_activity(
                    reflect,
                    ReflectInput(
                        bank=cfg.memory.project_bank,
                        backend=cfg.memory.backend,
                        base_url=cfg.memory.base_url,
                    ),
                    **_MEM_ACT,
                )
            except Exception:
                pass

        try:
            await workflow.execute_activity(
                export_run_artifacts,
                RunExportInput(
                    run_id=summary.run_id,
                    summary=summary,
                    trace=trace,
                ),
                **_EXPORT_ACT,
            )
        except Exception:
            pass

        # E-38: OQ-B7 retention — downgrade clean-green non-benchmark
        # runs to digest-only. Best-effort like the export above.
        try:
            had_fix = any(
                ev.kind == RunEventKind.FIX_ATTEMPT and ev.data.get("attempt") not in (None, "1")
                for ev in trace
            )
            await workflow.execute_activity(
                apply_session_retention,
                RetentionInput(
                    refs=session_refs,
                    keep_full=keep_full_transcripts(
                        outcome=summary.outcome,
                        had_fix_attempts=had_fix,
                        is_benchmark=cfg.benchmark.case_id is not None,
                    ),
                ),
                **_EXPORT_ACT,
            )
        except Exception:
            pass
    except Exception:
        # Retro must never change the run outcome (best-effort stage).
        pass
