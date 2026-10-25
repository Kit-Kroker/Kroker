"""Analyze stage step execution (spec A §3.3).

Executes the analyze stage (stage 9 / FR-106): clean-context Analyst role proposes
the acceptance criterion -> test traceability mapping across the integrated changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# This module executes inside the workflow sandbox (feature.py's
# pipeline calls analyze.step) and shares model classes with it — without
# the marker the sandbox re-imports them isolated, duplicating classes
# pydantic then rejects (first post-B0 brownfield run, DS12).
with workflow.unsafe.imports_passed_through():
    from ...agents.loader import model_id
    from ...agents.model_ids import forwarded_model
    from ...benchmarks.models import BenchmarkOutcome, TraceBag
    from ...benchmarks.record_builder import stage_record
    from ...core.context import StageContext
    from ...core.models import PipelineConfig, RoleUsage
    from ...memory.models import MemoryKind
    from ...vcs.git import DiffInput, get_task_diff
    from .activities import InventoryInput, TaskBranchRef, build_trace_inventory
    from .models import (
        AnalysisReport,
        AnalyzeOutcome,
        criterion_keys,
        enforce_traces,
        untraced_criteria,
    )
    from .prompts import analyst_prompt, analyst_prompt_v2

if TYPE_CHECKING:
    from ...workflows.models import TaskResult
    from ..architecture.models import ValidationContract
    from ..plan.models import DevTask, ImplementationPlan

ANALYZE_EVIDENCE_PATCH = "017-analyze-evidence"


def _in_workflow() -> bool:
    try:
        workflow.info()
        return True
    except Exception:
        return False


def _EVIDENCE_V2() -> bool:
    """Return True if patched in workflow; False outside workflow by default."""
    if not _in_workflow():
        return False
    return workflow.patched(ANALYZE_EVIDENCE_PATCH)


async def _exec_activity(activity_fn: Any, arg: Any, **kwargs: Any) -> Any:
    if _in_workflow():
        return await workflow.execute_activity(activity_fn, arg, **kwargs)
    res = activity_fn(arg)
    import inspect

    if inspect.isawaitable(res):
        return await res
    return res


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
    base_sha: str | None = None,
    analyst_agent: Any = None,
    analyst_model: str | None = None,
) -> AnalyzeOutcome:
    """Execute the analyze stage.

    Runs the clean-context Analyst proposer role against the integrated changes
    and returns the AnalyzeOutcome artifact.
    """
    ctx.stage("analyzing", "analyze")
    _an_started = _now()
    patched = _EVIDENCE_V2()

    if diff is None:
        diff = await _exec_activity(
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

    # 004 T031 (FR-002): when the run overrides `analyst` with a non-registry
    # model, that override is what _run_role forwards — the label must name
    # it, never a provider-less fallback (V11). No override: unchanged chain.
    fwd = forwarded_model(cfg, "analyst")
    if fwd is not None:
        analyst_model = fwd
    elif not analyst_model or not isinstance(analyst_model, str):
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
            # 003/FR-014: strip the provider prefix so the label matches the
            # pre-migration wrapper's concrete-model name (T046 parity).
            analyst_model = model_id(analyst_agent.model)
        else:
            analyst_model = "unknown"
    resolved_model = str(analyst_model)
    analyst_spend = RoleUsage(role="analyst", model=resolved_model)

    diff_stat = diff.get("stat", "") if diff is not None else ""
    diff_patch = diff.get("patch", "") if diff is not None else ""

    if patched:
        crit_objects = criterion_keys(authoritative)
        task_refs = [
            TaskBranchRef(
                task_id=r.task_id,
                branch=getattr(r, "branch", "") or "",
                start_ref=getattr(r, "start_ref", None),
            )
            for r in results_iter
        ]
        if tasks is not None:
            task_order = [t.id for t in tasks]
        elif plan is not None:
            task_order = [t.id for t in plan.tasks]
        else:
            task_order = [r.task_id for r in results_iter]

        inv = await _exec_activity(
            build_trace_inventory,
            InventoryInput(
                integration_wt=integration_wt,
                base_sha=base_sha or base_branch,
                tasks=task_refs,
            ),
            **_ACT,
        )
        prompt_text = analyst_prompt_v2(
            crit_objects,
            inv,
            task_order,
            _qa_lines,
            diff_stat,
            diff_patch,
        )
    else:
        _criteria_lines = "\n".join(f"- [{tid}] {crit}" for tid, crit in authoritative)
        prompt_text = analyst_prompt(
            _criteria_lines,
            _qa_lines,
            diff_stat,
            diff_patch,
        )

    res = await ctx.run_role(
        cfg,
        "analyst",
        resolved_model,
        analyst_agent,
        prompt_text,
        into=analyst_spend,
    )
    analysis: AnalysisReport = res.output

    if patched:
        enforcement = enforce_traces(crit_objects, analysis, inv)
        untraced = enforcement.untraced
        trace_bag: TraceBag | None = TraceBag(
            traced_by_test=enforcement.buckets.get("test", 0),
            traced_by_file=enforcement.buckets.get("file", 0),
            traced_by_command=enforcement.buckets.get("command", 0),
            untraced=len(untraced),
            criteria_trace=enforcement.criteria_trace,
            truncated=enforcement.truncated,
        )
        command_only_set = set(enforcement.command_only)
        error_text = (
            None
            if not untraced
            else f"{len(untraced)} untraced criterion(s): "
            + "; ".join(
                f"{lbl} (command only)" if lbl in command_only_set else lbl for lbl in untraced[:3]
            )
            + ("; ..." if len(untraced) > 3 else "")
        )
    else:
        untraced = untraced_criteria(authoritative, analysis)
        trace_bag = None
        error_text = (
            None
            if not untraced
            else f"{len(untraced)} untraced criterion(s): "
            + "; ".join(untraced[:3])
            + ("; ..." if len(untraced) > 3 else "")
        )

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
            trace=trace_bag,
            error=error_text,
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

    return AnalyzeOutcome(report=analysis, untraced=untraced)
