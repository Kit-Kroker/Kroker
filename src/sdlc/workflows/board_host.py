"""BoardHost -- task board writes and artifact publishing (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Owns: _plan_version. Nothing else may write it --
see workflows/AGENTS.md for the full attribute-ownership table.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..board.activities import (
        AttachEvidenceInput,
        PublishArtifactInput,
        SetTaskStatusInput,
        SyncPlanTasksInput,
        attach_task_evidence,
        publish_artifact_version,
        set_task_authoritative,
        sync_plan_tasks,
    )
    from ..board.models import ArtifactStatus, TaskStatus
    from ..core.models import PipelineConfig
    from ..models import DevTask

# E-78: the board is NOT best-effort like EXPORT_ACT. Agents read tasks from
# it, so a lost write is a correctness bug, not a missing report. The store's
# writes are idempotent (sync uses ON CONFLICT DO NOTHING), so retrying is
# safe.
BOARD_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=5)
)


class BoardHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        # E-78: surrogate artifact_version.id of the current plan, captured
        # when the plan stage publishes. Task board writes key off it.
        self._plan_version: int | None = None

    async def _board_publish(
        self, cfg: PipelineConfig, key: str, content_json: str, *, approved: bool = True
    ) -> int:
        """Publish one project artifact version. A rejected gate still writes
        history — the pointer just does not move."""
        run_id = workflow.info().workflow_id
        result = await workflow.execute_activity(
            publish_artifact_version,
            PublishArtifactInput(
                project=cfg.project_key,
                key=key,
                run_id=run_id,
                content_json=content_json,
                actor=f"workflow:{run_id}",
                status=(ArtifactStatus.CURRENT if approved else ArtifactStatus.REJECTED),
            ),
            **BOARD_ACT,
        )
        return result.version_id

    async def _board_sync_tasks(
        self, cfg: PipelineConfig, plan_version: int, tasks: list[DevTask]
    ) -> None:
        run_id = workflow.info().workflow_id
        await workflow.execute_activity(
            sync_plan_tasks,
            SyncPlanTasksInput(
                project=cfg.project_key,
                plan_version=plan_version,
                run_id=run_id,
                tasks=tasks,
                actor=f"workflow:{run_id}",
            ),
            **BOARD_ACT,
        )

    async def _board_task_status(
        self,
        cfg: PipelineConfig,
        task_id: str,
        status: TaskStatus,
        *,
        fix_attempts: int | None = None,
        error: str | None = None,
        branch: str | None = None,
    ) -> None:
        if self._plan_version is None:
            return  # no plan published (early rejection)
        run_id = workflow.info().workflow_id
        await workflow.execute_activity(
            set_task_authoritative,
            SetTaskStatusInput(
                project=cfg.project_key,
                plan_version=self._plan_version,
                task_id=task_id,
                status=status,
                actor=f"workflow:{run_id}",
                fix_attempts=fix_attempts,
                error=error,
                branch=branch,
            ),
            **BOARD_ACT,
        )

    async def _board_evidence(
        self, cfg: PipelineConfig, task_id: str, kind: str, content_json: str
    ) -> None:
        if self._plan_version is None:
            return
        await workflow.execute_activity(
            attach_task_evidence,
            AttachEvidenceInput(
                project=cfg.project_key,
                plan_version=self._plan_version,
                task_id=task_id,
                run_id=workflow.info().workflow_id,
                kind=kind,
                content_json=content_json,
            ),
            **BOARD_ACT,
        )
