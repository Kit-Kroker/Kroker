"""Stage 4 task scheduler, shared by FeatureWorkflow and the graph `code` node
(E-74 spec §4.3). Moved verbatim from feature.py's _build_and_merge; the host
supplies the TaskHost/BoardHost/RoleHost capabilities.

Determinism: task dicts are insertion-ordered and keyed by task id, and the
wave gather runs over the batch in plan order. Both orderings are replay-safe
and must never be "fixed" by sorting (that changes FeatureWorkflow's command
sequence and fails tests/replay/test_feature_replay.py).
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..board.models import TaskStatus
    from ..core.models import ExecutionMode, PipelineConfig
    from ..stages.plan.models import DevTask, ImplementationPlan
    from .models import TaskResult


async def run_tasks(
    host: Any, *, cfg: PipelineConfig, plan: ImplementationPlan, repo_path: str
) -> tuple[dict[str, TaskResult], str | None]:
    """4. DEV / TEST / DEVOPS tasks -- ADR-13: serial by default; wave mode
    parallelizes, but tasks sharing declared overlaps serialize regardless.
    Handoffs flow task -> task (FR-805). Returns (done, None) or
    (done_so_far, terminal failure string)."""
    done: dict[str, TaskResult] = {}
    handoffs: list = []
    remaining = {t.id: t for t in plan.tasks}

    async def run_one(t: DevTask) -> TaskResult:
        """Execute the task only. Merging is a separate concern -- see
        _merge_task (Resolution B: merging inside run_one would race
        the integration worktree under wave mode's asyncio.gather)."""
        await host._board_task_status(cfg, t.id, TaskStatus.IN_PROGRESS)
        try:
            r = await host._dev_task(t, repo_path, host._integration_head, cfg, handoffs)
        except Exception as exc:
            # _dev_task's own fix loop is exhausted before it raises, so a
            # propagating exception means the run is aborting. Record a
            # terminal status so the board (which agents read for live
            # state) does not leave this task looking forever in_progress
            # -- indistinguishable from a task still running.
            await host._board_task_status(
                cfg, t.id, TaskStatus.FAILED, error=f"unhandled: {type(exc).__name__}: {exc}"
            )
            raise
        _BOARD_STATUS = {
            "done": TaskStatus.DONE,
            "failed": TaskStatus.FAILED,
            "quarantined": TaskStatus.QUARANTINED,
        }
        await host._board_task_status(
            cfg,
            t.id,
            _BOARD_STATUS[r.status],
            fix_attempts=r.attempts,
            branch=r.branch,
            error=(r.notes or None if r.status != "done" else None),
        )
        for kind, report in (
            ("qa", r.qa),
            ("review", r.review),
            ("deep_review", r.deep_review),
        ):
            if report is not None:
                await host._board_evidence(cfg, t.id, kind, report.model_dump_json())
        done[r.task_id] = r
        if r.handoff:
            handoffs.append(r.handoff)
        remaining.pop(r.task_id)
        return r

    while remaining:
        ready = [
            t for t in remaining.values() if all(d in done for d in t.depends_on)
        ]  # determinism: insertion-ordered task dict
        if not ready:
            return done, "failed:dependency-cycle"

        if cfg.execution_mode == ExecutionMode.SERIAL:
            # SERIAL: execute + merge sequentially so the next task
            # branches from the updated integration head.
            tr = await run_one(ready[0])
            if tr.status == "done":
                conflict = await host._merge_task(tr, repo_path)
                if conflict:
                    return done, conflict
        else:
            # Wave mode: execute the batch in parallel (preserving the
            # gather), THEN merge results sequentially so integration
            # updates are ordered -- two tasks racing the integration
            # worktree would corrupt the merge (Resolution B).
            batch: list[DevTask] = []
            seen: set[str] = set()
            for t in ready:
                if seen.isdisjoint(t.overlaps):
                    batch.append(t)
                    seen.update(t.overlaps)
            results = await asyncio.gather(
                *[run_one(t) for t in batch]
            )  # determinism: wave batch order
            for tr in results:
                if tr.status == "done":
                    conflict = await host._merge_task(tr, repo_path)
                    if conflict:
                        return done, conflict

        if any(
            r.status == "quarantined" for r in done.values()
        ):  # determinism: insertion-ordered task dict
            return done, "failed:quarantined-tasks"

        await host._check_budget(cfg)  # E-33: serial boundary per task wave

    return done, None
