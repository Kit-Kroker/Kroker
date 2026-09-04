"""Analyze stage step execution (spec A §3.3).

Executes the analyze stage (stage 9 / FR-106): clean-context Analyst role proposes
the acceptance criterion -> test traceability mapping across the integrated changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import PipelineConfig, RoleUsage
from ...memory.models import MemoryKind
from ...vcs.git import DiffInput, get_task_diff
from .models import AnalysisReport, untraced_criteria
from .prompts import analyst_prompt

if TYPE_CHECKING:
    from ...workflows.models import TaskResult
    from ..architecture.models import ValidationContract
    from ..plan.models import DevTask, ImplementationPlan

_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


def _now() -> datetime:
    try:
        return workflow.now()
    except Exception:
        return datetime.now(UTC)


def _workflow_id() -> str:
    try:
        return workflow.info().workflow_id
    except Exception:
        return ""


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    integration_wt: str,
    plan: ImplementationPlan | None = None,
    tasks: list[DevTask] | None = None,
    task_results: list[TaskResult] | dict[str, TaskResult] | None = None,
    diff: dict[str, str] | None = None,
    contract: ValidationContract | None = None,
    base_branch: str = "main",
    analyst_agent: Any = None,
    analyst_model: str | None = None,
) -> AnalysisReport:
    """Execute the analyze stage.

    Runs the clean-context Analyst proposer role against the integrated changes
    and returns the AnalysisReport artifact.
    """
    ctx.stage("analyzing", "analyze")
    _an_started = _now()

    if diff is None:
        diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=integration_wt, branch_point=base_branch),
            **_ACT,
        )

    authoritative: list[tuple[str, str]] = []
    if tasks is not None:
        authoritative = [(t.id, c) for t in tasks for c in t.acceptance_criteria]
    elif plan is not None:
        authoritative = [(t.id, c) for t in plan.tasks for c in t.acceptance_criteria]
    elif contract is not None:
        authoritative = [(contract.task_id, a) for a in contract.assertions]

    _criteria_lines = "\n".join(f"- [{tid}] {crit}" for tid, crit in authoritative)

    if isinstance(task_results, dict):
        results_iter = list(task_results.values())
    elif isinstance(task_results, list):
        results_iter = task_results
    else:
        results_iter = []

    _qa_lines = "\n".join(
        f"- {r.task_id}: tests_passed={r.qa.tests_passed if r.qa else 'n/a'}"
        f" failing={r.qa.failing_tests if r.qa else []}"
        for r in results_iter
    )

    if not analyst_model or not isinstance(analyst_model, str):
        rc = cfg.roles.get("analyze") or cfg.roles.get("analyst")
        if rc is not None and rc.model is not None:
            analyst_model = str(rc.model)
        elif (
            hasattr(analyst_agent, "model")
            and hasattr(analyst_agent.model, "model_name")
            and isinstance(analyst_agent.model.model_name, str)
        ):
            analyst_model = analyst_agent.model.model_name
        elif hasattr(analyst_agent, "model") and isinstance(analyst_agent.model, str):
            analyst_model = analyst_agent.model
        else:
            analyst_model = "unknown"
    resolved_model = str(analyst_model)
    analyst_spend = RoleUsage(role="analyst", model=resolved_model)

    diff_stat = diff.get("stat", "") if diff is not None else ""
    diff_patch = diff.get("patch", "") if diff is not None else ""

    res = await ctx.run_role(
        cfg,
        "analyst",
        resolved_model,
        analyst_agent,
        analyst_prompt(
            _criteria_lines,
            _qa_lines,
            diff_stat,
            diff_patch,
        ),
        into=analyst_spend,
    )
    analysis: AnalysisReport = res.output

    untraced = untraced_criteria(authoritative, analysis)

    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="analyze",
            role="analyst",
            started=_an_started,
            ended=_now(),
            quality_score=(1.0 if not untraced else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.PASS if not untraced else BenchmarkOutcome.FAIL),
            model=resolved_model,
            spend=analyst_spend,
        ),
    )

    run_id = _workflow_id()
    await ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"analyze: {len(authoritative)} criteria, "
        f"{len(untraced)} untraced. {analysis.summary}",
        metadata={"stage": "analyze", "run_id": run_id},
    )
    if untraced:
        await ctx.retain(
            cfg,
            MemoryKind.GOTCHA,
            cfg.memory.project_bank,
            text=f"untraced acceptance criteria at merge: {untraced}",
            metadata={"stage": "analyze", "run_id": run_id},
        )

    return analysis
