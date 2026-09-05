"""TaskHost -- per-task execution loop and integration branch merge (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Consumes: GateHost, ReportHost, BoardHost, BenchmarkHost, MemoryHost, RoleHost via the MRO.
Owns: _session_refs. (Eliminates _escalation_round as instance state per Rule 2).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import (
        resolve_role_model,
        t_adversary,
        t_deep_review,
        t_handoff,
        t_qa,
        t_reviewer,
    )
    from ..benchmarks.models import BenchmarkOutcome
    from ..core.models import (
        ArtifactRef,
        PipelineConfig,
        RoleConfig,
    )
    from ..harness.models import (
        DeferredToolUse,
        EscalationOutcome,
        ToolDenial,
        ToolEscalation,
    )
    from ..observability.trace import RunEventKind
    from ..stages.code.step import step as code_step
    from ..stages.plan.models import (
        DevTask,
    )
    from ..stages.review import (
        run_adversary as review_run_adversary,
    )
    from ..stages.review import (
        run_deep_review as review_run_deep_review,
    )
    from ..stages.review.models import DeepReviewReport, ReviewReport
    from ..vcs import (
        MergeInput,
        WorktreeInput,
        create_worktree,
        merge_into_integration,
    )
    from .models import TaskResult

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)

LONG_ACT_HEARTBEAT_MINUTES = int(os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
LONG_ACT_TIMEOUT_HOURS = int(os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
LONG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

DEFAULT_TEST_CMD = "pytest -q --maxfail=25"


def _long_act(role_cfg: RoleConfig | None = None) -> workflow.ActivityConfig:
    """LONG_ACT, with a role's own timeout/heartbeat overrides if it has any."""
    if role_cfg is None:
        return LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return LONG_ACT
    return workflow.ActivityConfig(
        start_to_close_timeout=timedelta(
            hours=hours if hours is not None else LONG_ACT_TIMEOUT_HOURS
        ),
        heartbeat_timeout=timedelta(
            minutes=minutes if minutes is not None else LONG_ACT_HEARTBEAT_MINUTES
        ),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )


def _contract_stack_directive(contract) -> str:
    """Surface the frozen stack as a standalone, non-negotiable line —
    not just one bullet among the assertions. A coding agent on a
    greenfield (empty) worktree has no existing scaffolding to anchor
    it to the required language/runtime, so the constraint needs to be
    unmissable rather than buried in prose."""
    if not contract or not contract.stack:
        return ""
    return f"MANDATORY STACK (do not deviate, even when revising): {contract.stack}\n"


def _contract_shell_cmd(commands: list[str] | None, default: str) -> str:
    """Join a contract's stack-specific test/lint commands into one shell
    command (`&&`-chained so an earlier failure short-circuits the rest).
    Falls back to `default` (a Python toolchain command) only when the
    contract carries none — e.g. a legacy/cached artifact predating this
    field, never as a silent stack-mismatch."""
    if not commands:
        return default
    return " && ".join(commands)


_TEST_OUTPUT_MAX = 1500

_HANDOFF_TAIL = 5


def _handoff_notes(prior_handoffs: list) -> list[str]:
    """FR-801/805: scoped context for the NEXT task.

    Claim TEXT only -- evidence quotes are for the cross-check and the
    benchmark record, and pasting transcript excerpts into a fresh prompt
    is how authoring context leaks sideways. A handoff with no claims
    contributes no line at all: 'task-3: no concerns' is noise that taught
    the reader nothing for every run this channel has existed.
    """
    notes: list[str] = []
    for h in prior_handoffs[-_HANDOFF_TAIL:]:
        parts: list[str] = []
        for label, claims in (
            ("did", h.what_changed),
            ("decided", h.decisions_made),
            ("concerns", h.open_concerns),
        ):
            if claims:
                parts.append(f"{label}: " + "; ".join(c.text for c in claims))
        if parts:
            notes.append(f"- {h.task_id}: " + " | ".join(parts))
    return notes


def _should_resume_session(qa, resumes: int, max_resumes: int, near_ceiling: bool) -> bool:
    """FR-802 resume budget, with a stack-mismatch override: a session
    that already committed to the wrong language/runtime is a worse
    starting point than a fresh one — the agent is anchored to files it
    would need to delete wholesale. Never resume it, regardless of
    remaining resume budget or context headroom."""
    if qa.stack_mismatch:
        return False
    return resumes < max_resumes and not near_ceiling


def escalations_from_denials(denials: list[ToolDenial]) -> list[ToolEscalation]:
    """Denials the hook could not escalate (batched call, unreadable
    transcript). No human was asked, so there is no gate and no round — but
    they must still be countable, or the size of the solo-only hole would be
    invisible (E-17 §6)."""
    return [
        ToolEscalation(
            tool=d.tool, rule_id=d.rule_id, target=d.target, outcome=EscalationOutcome.BATCHED
        )
        for d in denials
        if d.escalation_declined
    ]


def _escalation_summary(task_id: str, title: str, deferred: DeferredToolUse) -> str:
    """What the human is actually deciding, rendered into the GateContext
    field the E-6 channel contract already renders (the same way the budget
    gate puts its cost table there)."""
    return (
        f"Task {task_id} ({title}) is blocked on a tool call.\n"
        f"  tool:   {deferred.tool}\n"
        f"  target: {deferred.target or '(none)'}\n"
        f"  rule:   {deferred.rule_id} — {deferred.reason}\n"
        "Approve to permit exactly this one call; reject to refuse it "
        "(the task continues either way)."
    )


class TaskHost:
    """Mixin. Owns the dev task execution loop (_dev_task) and branch merge (_merge_task).

    Consumes: GateHost, ReportHost, BoardHost, BenchmarkHost, MemoryHost, RoleHost.
    Owns: _session_refs. (Eliminates _escalation_round as instance state per Rule 2).
    """

    def __init__(self) -> None:
        super().__init__()
        self._session_refs: list[ArtifactRef] = []

    async def _merge_task(self, tr: TaskResult, repo_path: str) -> str | None:
        """Merge a completed task branch into the integration branch and
        advance self._integration_head.

        Returns a terminal status string on conflict (falsified overlaps
        declaration), else None. A conflict means the task's declared
        `overlaps` were incomplete → falsified contract → the run terminates
        with an observable status rather than raising (a raise would make
        Temporal retry a deterministic conflict). Called from both SERIAL and
        wave paths; never inside run_one (Resolution B)."""
        merge_res = await workflow.execute_activity(
            merge_into_integration,
            MergeInput(
                repo_path=repo_path,
                run_id=workflow.info().workflow_id,
                task_branch=tr.branch,
                integration_path=getattr(self, "_integration_wt", ""),
            ),
            **ACT,
        )
        if merge_res.conflict:
            # Falsified `overlaps` declaration → terminal status, not a raise.
            return f"failed:integration-conflict:{tr.task_id}"
        self._integration_head = merge_res.integration_head
        return None

    async def _record_escalation(
        self, cfg: PipelineConfig, task: DevTask, esc: ToolEscalation
    ) -> None:
        """Trace event (events.jsonl / report.html) plus a benchmark record
        so E-36's case x stage heatmap sees approval friction."""
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.TOOL_ESCALATION,
            stage="tool_approval",
            task_id=task.id,
            tool=esc.tool,
            rule_id=esc.rule_id,
            outcome=esc.outcome.value,
            decided_by=esc.decided_by,
            round=str(esc.round),
            **({"target": esc.target} if esc.target else {}),
        )
        now = workflow.now()
        # `judge` is a constrained Literal on QualityScore — "policy" is not a
        # member. A gate-decided outcome is a human override; a capped or
        # batched one was decided deterministically, with nobody asked.
        judge = "human_override" if esc.decided_by == "human" else "contract"
        await self._record(  # type: ignore[attr-defined]
            cfg,
            self._stage_record(  # type: ignore[attr-defined]
                cfg,
                stage="tool_approval",
                role="human",
                started=now,
                ended=now,
                quality_score=None,
                judge=judge,
                outcome=(
                    BenchmarkOutcome.PASS
                    if esc.outcome is EscalationOutcome.APPROVED
                    else BenchmarkOutcome.ESCALATED
                ),
                model="human",
                task_id=task.id,
            ),
        )

    async def _dev_task(
        self,
        task: DevTask,
        repo_path: str,
        from_ref: str,
        cfg: PipelineConfig,
        prior_handoffs: list,
    ) -> TaskResult:
        """dev → clean-context QA vs. frozen contract, bounded fix loop.

        FR-802: sessions resume across attempts up to max_session_resumes;
        past that, a FRESH session is seeded with a structured handoff —
        compacted context is treated as failure, never continued.
        FR-804: the QA validator sees contract + diff + test output only.
        Delegates task execution to stages.code.step (spec A §3.3).
        escalation_round is scoped per-task in step(), not instance state.
        """
        role_cfg = cfg.roles.get(
            task.role, cfg.roles.get("dev", RoleConfig(model="claude-3-5-sonnet"))
        )
        assert role_cfg.model is not None
        handle = await workflow.execute_activity(
            create_worktree,
            WorktreeInput(
                repo_path=repo_path,
                run_id=workflow.info().workflow_id,
                task_id=task.id,
                from_ref=from_ref,
            ),
            **ACT,
        )
        handoff_notes = _handoff_notes(prior_handoffs)
        return await code_step(
            self._ctx,  # type: ignore[attr-defined]
            cfg=cfg,
            task=task,
            contract=task.contract,
            worktree=handle.path,
            notes=handoff_notes,
            branch=handle.branch,
            branch_point=handle.branch_point or from_ref,
            dev_agent=None,
            qa_agent=t_qa,
            reviewer_agent=t_reviewer,
            adversary_agent=t_adversary,
            deep_review_agent=t_deep_review,
            handoff_agent=t_handoff,
            session_refs=self._session_refs,
        )

    async def _run_adversary(
        self,
        cfg: PipelineConfig,
        contract: Any,
        assertions: list[str],
        diff: dict[str, Any],
        qa_raw: Any,
        task: Any,
    ) -> ReviewReport | None:
        """Spec 3.2: the decorrelated second opinion, on the APPROVING path only."""
        if not (cfg.adversarial_review_enabled and t_adversary is not None):
            return None
        return await review_run_adversary(
            self._ctx,  # type: ignore[attr-defined]
            cfg=cfg,
            contract=contract,
            assertions=assertions,
            diff=diff,
            qa_raw=qa_raw,
            task=task,
            adversary_agent=t_adversary,
            adversary_model=resolve_role_model(cfg, "adversary"),
        )

    async def _run_deep_review(
        self,
        cfg: PipelineConfig,
        run: Any,
        contract: Any,
        assertions: list[str],
        diff: dict[str, Any],
        task: Any,
    ) -> DeepReviewReport | None:
        """E-39 advisory lens: read the SCRUBBED harness transcript as data and
        emit DeepReviewReport.
        """
        if not (
            cfg.deep_review_enabled
            and t_deep_review is not None
            and run is not None
            and run.session_ref is not None
        ):
            return None
        return await review_run_deep_review(
            self._ctx,  # type: ignore[attr-defined]
            cfg=cfg,
            run=run,
            contract=contract,
            assertions=assertions,
            diff=diff,
            task=task,
            deep_review_agent=t_deep_review,
            deep_review_model=resolve_role_model(cfg, "deep_review"),
        )
