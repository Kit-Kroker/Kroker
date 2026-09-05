"""Review stage step execution (spec A §3.3).

Executes clean-context primary review against task diff, frozen contract assertions,
and deterministic test results. Also hosts the decorrelated adversary lens (spec 3.2)
and the advisory deep-review transcript lens (E-39).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...artifacts.read import LoadSessionInput, load_session
from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import PipelineConfig, RoleUsage
from ...harness.session import session_text_from_jsonl
from ...memory.models import MemoryKind
from .models import DeepReviewReport, ReviewReport
from .prompts import adversary_prompt, deep_review_prompt, reviewer_prompt

_LOGGER = logging.getLogger(__name__)

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


def _log_warning(msg: str, *args: Any, exc_info: bool = False) -> None:
    try:
        from temporalio.workflow import _context

        if _context._Runtime.maybe_current() is not None:
            workflow.logger.warning(msg, *args, exc_info=exc_info)
            return
    except Exception:
        pass
    _LOGGER.warning(msg, *args, exc_info=exc_info)


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


def _get_patch(diff: dict[str, Any] | str) -> str:
    if isinstance(diff, dict):
        return str(diff.get("patch", ""))
    return str(diff)


def _get_qa_raw_json(qa_raw: Any) -> str:
    if qa_raw is None:
        return ""
    if hasattr(qa_raw, "model_dump_json"):
        return qa_raw.model_dump_json()
    return str(qa_raw)


def _role_model(cfg: PipelineConfig, role: str, agent: Any = None, default: str = "unknown") -> str:
    rc = cfg.roles.get(role)
    if rc and rc.model and isinstance(rc.model, str):
        return rc.model
    if hasattr(agent, "model"):
        m = agent.model
        name = (
            getattr(m, "model_name", None)
            or getattr(m, "name", None)
            or (m if isinstance(m, str) else None)
        )
        if isinstance(name, str) and name:
            return name
    return default


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    task: Any,
    contract: Any,
    diff: dict[str, Any] | str,
    worktree: str = "",
    reviewer_agent: Any = None,
    adversary_agent: Any = None,
    deep_review_agent: Any = None,
    qa_raw: Any = None,
    reviewer_model: str = "",
    attempt: int = 0,
    started: Any = None,
    run: Any = None,
) -> ReviewReport | None:
    """Execute clean-context primary reviewer on the task deliverable.

    Receives frozen contract assertions, diff, and deterministic test output (qa_raw).
    Emits benchmark record for review stage. Never calls a gate directly.
    """
    if not cfg.review_enabled or reviewer_agent is None:
        return None

    _started = started or _now()
    assertions: list[str] = (
        list(contract.assertions)
        if contract and getattr(contract, "assertions", None)
        else list(getattr(task, "acceptance_criteria", []))
    )
    patch = _get_patch(diff)
    qa_raw_json = _get_qa_raw_json(qa_raw)
    model = reviewer_model or _role_model(cfg, "reviewer", reviewer_agent, default="unknown")

    role_res = await ctx.run_role(
        cfg,
        "reviewer",
        model,
        reviewer_agent,
        reviewer_prompt(assertions, qa_raw_json, patch),
    )
    review: ReviewReport = getattr(role_res, "output", role_res)

    if review is not None and hasattr(ctx, "record"):
        rec_builder = getattr(ctx, "stage_record", stage_record)
        await ctx.record(
            cfg,
            rec_builder(
                cfg,
                stage="review",
                role="reviewer",
                started=_started,
                ended=_now(),
                quality_score=(1.0 if review.approve else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if review.approve else BenchmarkOutcome.FAIL),
                model=model,
                task_id=getattr(task, "id", None),
                attempt=attempt,
                fix_attempts=0,
            ),
        )

    return review


async def run_adversary(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    contract: Any,
    assertions: Sequence[str],
    diff: dict[str, Any] | str,
    qa_raw: Any,
    task: Any,
    adversary_agent: Any = None,
    adversary_model: str = "",
) -> ReviewReport | None:
    """Decorrelated second opinion on the approving path (spec 3.2) — a
    rejection is already headed for the fix loop.

    Clean-context, exactly like the primary: contract + diff + test output,
    never the session (that is deep_review's job). Identical inputs are what
    make disagreement interpretable as model variance rather than information
    asymmetry.

    FAIL-OPEN: any failure returns None, which the caller treats as
    agreement. The primary reviewer is the sole designated blocking lens; a
    lens added for safety must not become a new way to fail. (Deliberately
    asymmetric to the E-38 scrub, which is fail-closed: a leaked credential
    is unrecoverable, a missed opinion is not.)
    """
    if not (cfg.adversarial_review_enabled and adversary_agent is not None):
        return None

    _started = _now()
    model = adversary_model or _role_model(cfg, "adversary", adversary_agent, default="unknown")
    try:
        spend = RoleUsage(role="adversary", model=model)
        patch = _get_patch(diff)
        qa_raw_json = _get_qa_raw_json(qa_raw)
        prompt = adversary_prompt(assertions, qa_raw_json, patch)
        role_res = await ctx.run_role(
            cfg,
            "adversary",
            model,
            adversary_agent,
            prompt,
            into=spend,
        )
        report: ReviewReport = getattr(role_res, "output", role_res)
        if hasattr(ctx, "record"):
            rec_builder = getattr(ctx, "stage_record", stage_record)
            await ctx.record(
                cfg,
                rec_builder(
                    cfg,
                    stage="adversary",
                    role="adversary",
                    started=_started,
                    ended=_now(),
                    quality_score=(1.0 if report.approve else 0.0),
                    judge="adversary",
                    outcome=(BenchmarkOutcome.PASS if report.approve else BenchmarkOutcome.FAIL),
                    model=model,
                    spend=spend,
                    task_id=getattr(task, "id", None),
                    fix_attempts=0,
                ),
            )
        if not report.approve and hasattr(ctx, "retain"):
            run_id = _workflow_id()
            await ctx.retain(
                cfg,
                MemoryKind.GOTCHA,
                cfg.memory.project_bank,
                text=f"adversary split from reviewer on task {getattr(task, 'id', '')}: "
                + "; ".join(f"{f.assertion}: {f.detail}" for f in report.blocking_findings),
                metadata={"task_id": getattr(task, "id", ""), "run_id": run_id},
            )
        return report
    except Exception:
        _log_warning(
            "adversary lens failed for task %s; treating as agreement",
            getattr(task, "id", ""),
            exc_info=True,
        )
        return None


async def run_deep_review(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    run: Any,
    contract: Any,
    assertions: Sequence[str],
    diff: dict[str, Any] | str,
    task: Any,
    deep_review_agent: Any = None,
    deep_review_model: str = "",
) -> DeepReviewReport | None:
    """E-39 advisory lens: read scrubbed harness transcript and emit DeepReviewReport.

    Recorded and retained for signal ONLY. Never consulted in task success condition.
    FAIL-OPEN: any failure returns None so an observability lens never fails
    delivery. Once per task, over the final HarnessRunResult; recorded and
    retained for signal only — never consulted in the task's success
    condition.
    """
    if not (
        cfg.deep_review_enabled
        and deep_review_agent is not None
        and run is not None
        and getattr(run, "session_ref", None) is not None
    ):
        return None

    _started = _now()
    try:
        loaded = await workflow.execute_activity(
            load_session, LoadSessionInput(ref=run.session_ref), **ACT
        )
        transcript = session_text_from_jsonl(loaded.text) + (
            f"\n[transcript truncated; digest follows]\n{run.session_digest.model_dump_json()}"
            if loaded.truncated and getattr(run, "session_digest", None) is not None
            else ""
        )
        model = deep_review_model or _role_model(
            cfg, "deep_review", deep_review_agent, default="unknown"
        )
        spend = RoleUsage(role="deep_review", model=model)
        patch = _get_patch(diff)
        task_json = task.model_dump_json() if hasattr(task, "model_dump_json") else str(task)
        prompt = deep_review_prompt(assertions, task_json, patch, transcript)

        role_res = await ctx.run_role(
            cfg,
            "deep_review",
            model,
            deep_review_agent,
            prompt,
            into=spend,
        )
        report: DeepReviewReport = getattr(role_res, "output", role_res)
        from ...handoff import verified_integrity_flags, verified_plan_deviations

        kept_flags, dropped_flags = verified_integrity_flags(report.integrity_flags, transcript)
        if dropped_flags:
            _log_warning(
                "deep_review: dropped %d integrity flag(s) for task %s "
                "whose evidence is not in the transcript",
                dropped_flags,
                getattr(task, "id", ""),
            )
        kept_devs, dropped_devs = verified_plan_deviations(report.plan_deviations, transcript)
        if dropped_devs:
            _log_warning(
                "deep_review: dropped %d plan deviation(s) for task %s "
                "whose evidence is not in the transcript",
                dropped_devs,
                getattr(task, "id", ""),
            )
        report = report.model_copy(
            update={"integrity_flags": kept_flags, "plan_deviations": kept_devs}
        )

        if hasattr(ctx, "record"):
            rec_builder = getattr(ctx, "stage_record", stage_record)
            await ctx.record(
                cfg,
                rec_builder(
                    cfg,
                    stage="deep_review",
                    role="deep_review",
                    started=_started,
                    ended=_now(),
                    quality_score=(0.0 if report.cheat_detected or not report.approve else 1.0),
                    judge="deep_review",
                    outcome=(
                        BenchmarkOutcome.FAIL if report.cheat_detected else BenchmarkOutcome.PASS
                    ),
                    model=model,
                    spend=spend,
                    task_id=getattr(task, "id", None),
                ),
            )

        if report.cheat_detected and hasattr(ctx, "retain"):
            run_id = _workflow_id()
            await ctx.retain(
                cfg,
                MemoryKind.GOTCHA,
                cfg.memory.project_bank,
                text=f"deep_review flagged task {getattr(task, 'id', '')}: "
                + "; ".join(f"{f.kind}: {f.detail}" for f in report.integrity_flags),
                metadata={"task_id": getattr(task, "id", ""), "run_id": run_id},
            )
        return report
    except Exception:
        _log_warning(
            "deep_review lens failed for task %s; continuing without it",
            getattr(task, "id", ""),
            exc_info=True,
        )
        return None
