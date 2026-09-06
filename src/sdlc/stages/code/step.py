"""Code stage step execution (spec A §3.3).

Executes the code stage: drives harness/crew execution inside an isolated worktree,
evaluates tool escalations, runs clean-context QA and review, drives the bounded
fix loop, and returns TaskResult.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...workflows.models import TaskResult
    from ..review.models import DeepReviewReport, ReviewReport

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...artifacts.read import LoadSessionInput, load_session
from ...benchmarks.models import BenchmarkOutcome, WasteBag
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import (
    ArtifactRef,
    GateOutcome,
    GatePolicy,
    HarnessKind,
    PipelineConfig,
    RoleConfig,
    RoleUsage,
)
from ...crew.activities import LoadCrewInput, load_crew
from ...harness.models import (
    DeferredToolUse,
    EscalationOutcome,
    HarnessRunResult,
    ToolDenial,
    ToolEscalation,
    ToolGrant,
)
from ...memory.models import MemoryKind
from ...observability.trace import RunEventKind
from ...pending import GateContext
from ...vcs import DiffInput, DriftInput, DriftReport, check_test_drift, get_task_diff
from ...workflows.crew import FS_ACT, CrewTaskInput, CrewTaskWorkflow
from ..plan.models import DevTask, compute_plan_drift
from ..qa import step as qa_step
from ..qa.activities import QAInput, run_test_suite
from ..qa.step import _fix_loop_issues
from .activities import CodingTaskInput, DriftGlobsInput, load_drift_globs, run_coding_task
from .freeze import _drift_note, _is_repair_attempt, _next_anchor
from .models import HandoffSummary

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3),
)

LONG_ACT_HEARTBEAT_MINUTES = int(os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
LONG_ACT_TIMEOUT_HOURS = int(os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
LONG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

DEFAULT_TEST_CMD = "pytest -q --maxfail=25"


def _now() -> datetime:
    try:
        return workflow.now()
    except Exception:
        return datetime.now(UTC)


def _workflow_id() -> str:
    try:
        return workflow.info().workflow_id
    except Exception:
        return "local"


def _long_act(role_cfg: RoleConfig | None = None) -> workflow.ActivityConfig:
    if role_cfg is None:
        return LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return LONG_ACT
    return workflow.ActivityConfig(
        start_to_close_timeout=timedelta(hours=hours or LONG_ACT_TIMEOUT_HOURS),
        heartbeat_timeout=timedelta(minutes=minutes or LONG_ACT_HEARTBEAT_MINUTES),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )


def _contract_stack_directive(contract: Any) -> str:
    """Surface the frozen stack as a standalone, non-negotiable line —
    not just one bullet among the assertions. A coding agent on a
    greenfield (empty) worktree has no existing scaffolding to anchor
    it to the required language/runtime, so the constraint needs to be
    unmissable rather than buried in prose."""
    if not contract or not getattr(contract, "stack", None):
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
        if isinstance(h, str):
            notes.append(h)
            continue
        parts: list[str] = []
        for label, claims in (
            ("did", getattr(h, "what_changed", [])),
            ("decided", getattr(h, "decisions_made", [])),
            ("concerns", getattr(h, "open_concerns", [])),
        ):
            if claims:
                parts.append(f"{label}: " + "; ".join(c.text for c in claims))
        if parts:
            notes.append(f"- {h.task_id}: " + " | ".join(parts))
    return notes


def _should_resume_session(qa: Any, resumes: int, max_resumes: int, near_ceiling: bool) -> bool:
    if qa is not None and getattr(qa, "stack_mismatch", False):
        return False
    if near_ceiling:
        return False
    return resumes < max_resumes


def escalations_from_denials(denials: list[ToolDenial]) -> list[ToolEscalation]:
    return [
        ToolEscalation(
            tool=d.tool,
            rule_id=d.rule_id,
            target=d.target,
            outcome=EscalationOutcome.BATCHED,
        )
        for d in denials
        if d.escalation_declined
    ]


def _escalation_summary(task_id: str, title: str, deferred: DeferredToolUse) -> str:
    return (
        f"Task {task_id} ({title}) suspended at {deferred.tool}({deferred.target}): "
        f"matched rule {deferred.rule_id}"
    )


async def _record_escalation(
    ctx: StageContext, cfg: PipelineConfig, task: DevTask, esc: ToolEscalation
) -> None:
    ctx.emit(
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
    now = _now()
    judge = "human_override" if esc.decided_by == "human" else "contract"
    await ctx.record(
        cfg,
        stage_record(
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


async def _record_thaw(
    ctx: StageContext, cfg: PipelineConfig, task: DevTask, decision, attempt: int
) -> None:
    """A thaw is a human override of a deterministic fence, so it gets the
    same treatment as one: a trace event AND a benchmark record with
    judge='human_override'. Gate history alone would not show that attempt N
    ran with the tests writable."""
    ctx.emit(
        RunEventKind.TOOL_ESCALATION,
        stage="tool_approval",
        task_id=task.id,
        tool="TestFreeze",
        rule_id="no-test-edit-during-repair",
        outcome="thawed",
        decided_by=decision.decided_by,
        round=str(attempt),
    )
    now = _now()
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="tool_approval",
            role="human",
            started=now,
            ended=now,
            quality_score=None,
            judge="human_override",
            outcome=BenchmarkOutcome.ESCALATED,
            model="human",
            task_id=task.id,
        ),
    )


async def _execute_coding_task(
    *,
    role_cfg: RoleConfig,
    prompt: str,
    worktree: str,
    session_id: str | None,
    task_id: str,
    attempt: int,
    grants: list[ToolGrant],
    cfg: PipelineConfig,
    crew_layout: Any = None,
    crew_roles: Any = None,
    crew_protocol: str = "",
    crew_sessions: dict[str, str] | None = None,
    repair: bool = False,
) -> tuple[HarnessRunResult, dict[str, str], list[ArtifactRef]]:
    if role_cfg.harness is HarnessKind.CREW:
        assert crew_layout is not None
        assert crew_roles is not None
        crew = await workflow.execute_child_workflow(  # type: ignore[call-overload]
            CrewTaskWorkflow.run,
            CrewTaskInput(
                layout=crew_layout.layout,
                lead=crew_layout.lead,
                roles=crew_roles,
                prompt=prompt,
                worktree=worktree,
                task_id=task_id,
                attempt=attempt,
                deliverable_path=crew_layout.deliverable.path,
                rounds_max=crew_layout.rounds.max,
                wall_clock_s=crew_layout.limits.wall_clock_s,
                turn_timeout_s=crew_layout.limits.turn_timeout_s,
                cost_usd=crew_layout.limits.cost_usd,
                sessions=crew_sessions or {},
                protocol=crew_protocol,
                containment_enabled=cfg.containment_enabled,
                containment_policy_path=cfg.containment.policy_path,
                containment_strict=cfg.containment.strict,
                repair=repair,
                gate_settings=cfg.gate_settings(),
                max_tool_escalations=cfg.max_tool_escalations,
            ),
            id=f"{_workflow_id()}-crew-{task_id}-{attempt}",
            execution_timeout=timedelta(seconds=crew_layout.limits.wall_clock_s + 600),
        )
        return crew.run, crew.sessions, crew.session_refs
    else:
        assert role_cfg.harness is not None
        run = await workflow.execute_activity(
            run_coding_task,
            CodingTaskInput(
                harness=role_cfg.harness,
                prompt=prompt,
                worktree=worktree,
                model=role_cfg.model,
                session_id=session_id,
                task_id=task_id,
                attempt=attempt,
                containment_enabled=cfg.containment_enabled,
                containment_policy_path=cfg.containment.policy_path,
                containment_strict=cfg.containment.strict,
                grants=grants,
                repair=repair,
            ),
            **_long_act(role_cfg),
        )
        refs = [run.session_ref] if run.session_ref is not None else []
        return run, {}, refs


async def _run_adversary(
    ctx: StageContext,
    cfg: PipelineConfig,
    contract: Any,
    assertions: list[str],
    diff: dict[str, Any],
    qa_raw: Any,
    task: Any,
    adversary_agent: Any = None,
) -> ReviewReport | None:
    if not cfg.adversarial_review_enabled or adversary_agent is None:
        return None
    from ...agents.roles import resolve_role_model
    from ..review.step import run_adversary as review_run_adversary

    return await review_run_adversary(
        ctx,
        cfg=cfg,
        contract=contract,
        assertions=assertions,
        diff=diff,
        qa_raw=qa_raw,
        task=task,
        adversary_agent=adversary_agent,
        adversary_model=resolve_role_model(cfg, "adversary"),
    )


async def _run_deep_review(
    ctx: StageContext,
    cfg: PipelineConfig,
    run: Any,
    contract: Any,
    assertions: list[str],
    diff: dict[str, Any],
    task: Any,
    deep_review_agent: Any = None,
) -> DeepReviewReport | None:
    if not (
        cfg.deep_review_enabled
        and deep_review_agent is not None
        and run is not None
        and getattr(run, "session_ref", None) is not None
    ):
        return None
    from ...agents.roles import resolve_role_model
    from ..review.step import run_deep_review as review_run_deep_review

    return await review_run_deep_review(
        ctx,
        cfg=cfg,
        run=run,
        contract=contract,
        assertions=assertions,
        diff=diff,
        task=task,
        deep_review_agent=deep_review_agent,
        deep_review_model=resolve_role_model(cfg, "deep_review"),
    )


async def _run_handoff(
    ctx: StageContext,
    cfg: PipelineConfig,
    run: Any,
    contract: Any,
    assertions: list[str],
    diff: dict[str, Any],
    task: Any,
    handoff_agent: Any = None,
) -> HandoffSummary:
    files = diff.get("files", [])
    fallback = HandoffSummary(task_id=task.id, files_touched=files)
    if not (
        handoff_agent is not None
        and run is not None
        and getattr(run, "session_ref", None) is not None
    ):
        return fallback
    _started = _now()
    try:
        from ...agents.roles import resolve_role_model
        from ...handoff import claim_survival_score, cross_check_claims
        from ...harness.session import session_text_from_jsonl

        loaded = await workflow.execute_activity(
            load_session, LoadSessionInput(ref=run.session_ref), **ACT
        )
        model = resolve_role_model(cfg, "handoff")
        spend = RoleUsage(role="handoff", model=model)
        session_text = session_text_from_jsonl(loaded.text)
        out = (
            await ctx.run_role(
                cfg,
                "handoff",
                model,
                handoff_agent,
                "Frozen contract assertions:\n- "
                + "\n- ".join(assertions)
                + f"\nDiff:\n{diff.get('patch', '')}"
                + "\nScrubbed harness transcript:\n"
                + session_text,
                into=spend,
            )
        ).output

        kept_total = 0
        dropped_total = 0
        fields = {}
        for name in ("what_changed", "decisions_made", "open_concerns"):
            checked = cross_check_claims(getattr(out, name), files, session_text=session_text)
            fields[name] = checked.kept
            kept_total += len(checked.kept)
            dropped_total += checked.dropped_paths + checked.dropped_quotes

        handoff = HandoffSummary(task_id=task.id, files_touched=files, **fields)
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="handoff",
                role="handoff",
                started=_started,
                ended=_now(),
                quality_score=claim_survival_score(kept_total, dropped_total).value,
                judge="handoff",
                outcome=BenchmarkOutcome.PASS,
                model=model,
                spend=spend,
                task_id=task.id,
                fix_attempts=0,
            ),
        )
        return handoff
    except Exception:
        workflow.logger.warning(
            "handoff extraction failed for task %s; using mechanical handoff",
            task.id,
            exc_info=True,
        )
        return fallback


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    task: DevTask,
    contract: Any = None,
    worktree: str,
    notes: list[str] | None = None,
    dev_agent: Any = None,
    crew_layout: Any = None,
    branch: str = "",
    branch_point: str = "",
    qa_agent: Any = None,
    reviewer_agent: Any = None,
    adversary_agent: Any = None,
    deep_review_agent: Any = None,
    handoff_agent: Any = None,
    session_refs: list[ArtifactRef] | None = None,
) -> TaskResult:
    """Execute the code stage (stage 4) for one task.

    Runs harness / crew within worktree, runs clean-context QA and review,
    coordinates the fix loop, records benchmark records, and returns TaskResult.
    """
    from ...agents.roles import STAGE_MODELS, resolve_role_model
    from ...workflows.models import TaskResult
    from ..review.step import step as review_step

    role_cfg = cfg.roles.get(task.role, cfg.roles.get("dev", RoleConfig(model="claude-3-5-sonnet")))
    contract = contract or task.contract
    assertions = contract.assertions if contract else task.acceptance_criteria
    handoff_notes = notes or []
    stack_directive = _contract_stack_directive(contract)
    prompt = (
        f"Task: {task.title}\n{task.description}\n"
        + stack_directive
        + "Your work will be validated against this frozen contract:\n- "
        + "\n- ".join(assertions)
        + ("\nHandoffs from preceding tasks:\n" + "\n".join(handoff_notes) if handoff_notes else "")
        + "\nWork only in this worktree. Run the tests before finishing."
        + "\nThis worktree is already a git repository (checked out on its"
        " own branch) even if the task looks like a fresh/greenfield"
        " project — do NOT run `git init`, and do NOT delete or modify"
        " the `.git` file/directory."
    )

    crew_roles = None
    crew_protocol = ""
    crew_sessions: dict[str, str] = {}
    if role_cfg.harness is HarnessKind.CREW:
        if crew_layout is None:
            crew = await workflow.execute_activity(
                load_crew,
                LoadCrewInput(
                    layout=role_cfg.layout or "code",
                    lead_harness=role_cfg.lead_harness,
                    lead_model=role_cfg.model,
                ),
                **FS_ACT,
            )
            crew_layout, crew_roles, crew_protocol = (crew.layout, crew.roles, crew.protocol)

    session_id: str | None = None
    resumes = 0
    run: HarnessRunResult | None = None
    attempt = 0
    escalation_round = 0
    budget = cfg.max_fix_attempts + 1
    gate_round = 0
    # C2 anchor A: the checkpoint of the last attempt in which tests were
    # freely writable -- attempt 1, plus any thawed attempt. Captured once
    # and never re-anchored to the PREVIOUS attempt, or attempt 2 could
    # weaken a test and attempt 3 would inherit the weakened state as its
    # baseline. Plain workflow state derived from activity output: replay-safe.
    anchor: str | None = None
    thawed = False  # set by an operator thaw for exactly one attempt (below)

    while True:
        attempt += 1
        _attempt_started = _now()
        ctx.emit(
            RunEventKind.FIX_ATTEMPT,
            stage="code",
            task_id=task.id,
            attempt=str(attempt),
        )
        grants: list[ToolGrant] = []
        asked = 0
        capped = False
        while True:
            exec_out = await _execute_coding_task(
                role_cfg=role_cfg,
                prompt=prompt,
                worktree=worktree,
                session_id=session_id,
                task_id=task.id,
                attempt=attempt,
                grants=grants,
                cfg=cfg,
                crew_layout=crew_layout,
                crew_roles=crew_roles,
                crew_protocol=crew_protocol,
                crew_sessions=crew_sessions,
                repair=_is_repair_attempt(attempt, thawed),
            )
            if isinstance(exec_out, tuple):
                run, crew_sessions, c_refs = exec_out
            else:
                run = exec_out
                crew_sessions = {}
                c_refs = [run.session_ref] if getattr(run, "session_ref", None) else []

            if session_refs is not None:
                for ref in c_refs:
                    if ref not in session_refs:
                        session_refs.append(ref)

            assert run is not None
            for esc in run.escalations:
                await _record_escalation(ctx, cfg, task, esc)
            for esc in escalations_from_denials(run.denials):
                await _record_escalation(ctx, cfg, task, esc)
            if run.deferred is None or capped:
                break

            session_id = run.session_id
            if asked >= cfg.max_tool_escalations:
                capped = True
                grants = [
                    ToolGrant(
                        tool_use_id=run.deferred.tool_use_id,
                        tool=run.deferred.tool,
                        input_digest=run.deferred.input_digest,
                        rule_id=run.deferred.rule_id,
                        approved=False,
                        reason="escalation cap reached",
                    )
                ]
                await _record_escalation(
                    ctx,
                    cfg,
                    task,
                    ToolEscalation(
                        tool=run.deferred.tool,
                        rule_id=run.deferred.rule_id,
                        target=run.deferred.target,
                        outcome=EscalationOutcome.CAPPED,
                        decided_by="policy",
                    ),
                )
                continue

            asked += 1
            escalation_round += 1
            decision = await ctx.gate(
                "tool_approval",
                cfg.gate_settings(),
                round=escalation_round,
                context=GateContext(
                    spec_summary=_escalation_summary(task.id, task.title, run.deferred)
                ),
                default_policy=GatePolicy.HARD,
            )
            grants = [
                ToolGrant(
                    tool_use_id=run.deferred.tool_use_id,
                    tool=run.deferred.tool,
                    input_digest=run.deferred.input_digest,
                    rule_id=run.deferred.rule_id,
                    approved=decision.approved,
                    reason=decision.comments or "",
                )
            ]
            await _record_escalation(
                ctx,
                cfg,
                task,
                ToolEscalation(
                    tool=run.deferred.tool,
                    rule_id=run.deferred.rule_id,
                    target=run.deferred.target,
                    outcome=(
                        EscalationOutcome.APPROVED
                        if decision.approved
                        else EscalationOutcome.TIMEOUT
                        if decision.decided_by == "timeout"
                        else EscalationOutcome.REJECTED
                    ),
                    decided_by=decision.decided_by,
                    round=escalation_round,
                ),
            )

        # Capture A on the first attempt that produced a checkpoint; a thawed
        # attempt RE-anchors on completion so the human-authorized edits
        # become the new baseline rather than firing drift forever after.
        # The rule is a pure helper so the ratchet is testable as a table.
        anchor = _next_anchor(
            anchor, run.commit_sha, freely_writable=not _is_repair_attempt(attempt, thawed)
        )

        drift = DriftReport()
        if cfg.containment_enabled and anchor is not None and _is_repair_attempt(attempt, thawed):
            policy_globs = await workflow.execute_activity(
                load_drift_globs,
                DriftGlobsInput(policy_path=cfg.containment.policy_path),
                **ACT,
            )
            drift = await workflow.execute_activity(
                check_test_drift,
                DriftInput(
                    worktree=worktree,
                    anchor=anchor,
                    fence_globs=policy_globs.fence,
                    report_globs=policy_globs.report,
                ),
                **ACT,
            )
        elif cfg.containment_enabled and _is_repair_attempt(attempt, thawed):
            # Skip-and-RECORD, never skip-and-report-clean: with no anchor
            # there is nothing to measure against, and an all-default
            # DriftReport would read as a backstop that ran and found
            # nothing. found stays False -- no forced gate -- but the gate
            # analysis must say the backstop never ran.
            drift = DriftReport(
                available=False,
                unavailable_reason="no anchor captured (attempt 1 produced no checkpoint)",
            )
        thawed = False  # a thaw is single-attempt by construction

        code_spend = RoleUsage(role="dev", model=role_cfg.model or "")
        ctx.emit(
            RunEventKind.MODEL_USAGE,
            stage="code",
            role="dev",
            model=role_cfg.model or "",
            calls="1",
            input_tokens=str(run.input_tokens or 0),
            output_tokens=str(run.output_tokens or 0),
            cost_usd=str(run.cost_usd or 0.0),
        )

        test_cmd = _contract_shell_cmd(
            contract.test_commands if contract else None, DEFAULT_TEST_CMD
        )
        qa_raw = await workflow.execute_activity(
            run_test_suite,
            QAInput(worktree=worktree, test_cmd=test_cmd),
            **_long_act(cfg.roles.get("test", role_cfg)),
        )
        diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=worktree, branch_point=branch_point),
            **ACT,
        )
        qa_spend = RoleUsage(role="qa", model=resolve_role_model(cfg, "qa"))
        qa = await qa_step(
            ctx,
            cfg=cfg,
            task=task,
            contract=contract,
            diff=diff,
            worktree=worktree,
            qa_agent=qa_agent,
            qa_raw=qa_raw,
            qa_spend=qa_spend,
        )

        review = await review_step(
            ctx,
            cfg=cfg,
            task=task,
            contract=contract,
            diff=diff,
            worktree=worktree,
            reviewer_agent=reviewer_agent,
            qa_raw=qa_raw,
            reviewer_model=STAGE_MODELS.get("review", "unknown"),
            attempt=attempt - 1,
            started=_attempt_started,
        )

        task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)

        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="code",
                role=task.role,
                started=_attempt_started,
                ended=_now(),
                quality_score=(1.0 if task_passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                model=role_cfg.model or "",
                harness=role_cfg.harness,
                lead_harness=role_cfg.lead_harness,
                cost_usd=run.cost_usd,
                spend=code_spend,
                waste=WasteBag.from_digest(run.session_digest),
                plan_drift=compute_plan_drift(task, diff.get("files", [])),
                fix_attempts=attempt - 1,
                task_id=task.id,
                attempt=attempt - 1,
            ),
        )

        _qa_quality = await ctx.judge(
            cfg, qa.model_dump_json(), "qa", author_model=resolve_role_model(cfg, "qa")
        )
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="qa",
                role="qa",
                started=_attempt_started,
                ended=_now(),
                quality_score=_qa_quality.score,
                judge=_qa_quality.judge,
                outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                model=resolve_role_model(cfg, "qa"),
                spend=qa_spend,
                task_id=task.id,
                attempt=attempt - 1,
            ),
        )

        review_ok = review is None or review.approve

        adversary = None
        if task_passed and review_ok:
            if review is not None:
                adversary = await _run_adversary(
                    ctx,
                    cfg,
                    contract,
                    assertions,
                    diff,
                    qa_raw,
                    task,
                    adversary_agent=adversary_agent,
                )
            if adversary is None or adversary.approve or not adversary.blocking_findings:
                deep = await _run_deep_review(
                    ctx,
                    cfg,
                    run,
                    contract,
                    assertions,
                    diff,
                    task,
                    deep_review_agent=deep_review_agent,
                )
                handoff = await _run_handoff(
                    ctx, cfg, run, contract, assertions, diff, task, handoff_agent=handoff_agent
                )
                return TaskResult(
                    task_id=task.id,
                    status="done",
                    attempts=attempt,
                    branch=branch,
                    run=run,
                    handoff=handoff,
                    qa=qa_raw,
                    review=review,
                    deep_review=deep,
                )

        issues = "" if attempt >= budget else _fix_loop_issues(qa, qa_raw, review, adversary)
        drift_note = _drift_note(drift)
        if drift.found:
            # Ground truth beats the manipulated signal, and a frozen session
            # cannot honestly restore what it broke -- restoring a protected
            # test is itself a denied write -- so another attempt could only
            # succeed by going around the fence again. Straight to the human,
            # with the patch.
            budget = attempt
            issues = "\n- ".join(x for x in (issues, drift_note) if x)
        if attempt < budget and not issues:
            workflow.logger.warning(
                "task %s attempt %s failed with no actionable feedback "
                "(qa_raw.tests_passed=%s) - abandoning fix loop",
                task.id,
                attempt,
                qa_raw.tests_passed,
            )
            budget = attempt

        if attempt >= budget:
            gate_round += 1
            analysis = _fix_loop_issues(qa, qa_raw, review) if qa else ""
            analysis = "\n".join(x for x in (analysis, drift_note) if x)
            if getattr(getattr(run, "containment", None), "freeze_vacuous", False):
                analysis += (
                    "\nNOTE: the test-freeze globs matched 0 files in this repo, so the "
                    "freeze fenced nothing this attempt (likely an unfamiliar test layout)."
                )
            decision = await ctx.gate(
                f"task:{task.id}",
                cfg.gate_settings(),
                round=gate_round,
                context=GateContext(task_id=task.id, analysis=analysis, attempts=attempt),
            )
            if decision.outcome is GateOutcome.REVISE and gate_round <= cfg.max_gate_rounds:
                guidance = decision.guidance or decision.comments or ""
                budget = attempt + 1
                session_id = None
                # C2: single-attempt, human-only, and it also RE-ANCHORS A
                # (see the capture above) -- without that, the backstop would
                # flag the very edits the operator just authorized.
                thawed = bool(decision.thaw_tests)
                if thawed:
                    await _record_thaw(ctx, cfg, task, decision, attempt + 1)
                prompt = (
                    stack_directive
                    + f"Task: {task.title}\n{task.description}\n"
                    + "An operator reviewed the previous attempts and "
                    "asked for these changes:\n"
                    + f"{guidance}\n"
                    + "Contract:\n- "
                    + "\n- ".join(assertions)
                )
                continue

            deep = await _run_deep_review(
                ctx, cfg, run, contract, assertions, diff, task, deep_review_agent=deep_review_agent
            )
            return TaskResult(
                task_id=task.id,
                status="done" if decision.approved else "quarantined",
                attempts=attempt,
                branch=branch,
                qa=qa_raw,
                review=review,
                deep_review=deep,
                notes=decision.comments or "",
            )

        await ctx.retain(
            cfg,
            MemoryKind.GOTCHA,
            cfg.memory.project_bank,
            text=f"task {task.id} ({task.title}) attempt {attempt} failed: {issues}",
            metadata={"task_id": task.id, "run_id": _workflow_id()},
        )
        if _should_resume_session(qa, resumes, cfg.max_session_resumes, run.near_context_ceiling()):
            session_id = run.session_id
            resumes += 1
            prompt = stack_directive + f"Previous attempt has issues. Fix them:\n- {issues}"
        else:
            session_id = None
            discard_note = (
                "The previous attempt used the WRONG language/runtime "
                "entirely. Delete that wrong-stack scaffolding rather "
                "than patching it, and reimplement from scratch in the "
                "mandated stack below.\n"
                if getattr(qa, "stack_mismatch", False)
                else "A previous session implemented part of this in the same "
                f"worktree (files: {', '.join(diff.get('files', [])[:20])}). "
                "Review the current state, then fix these unmet contract "
                "assertions.\n"
            )
            prompt = (
                stack_directive
                + f"Task: {task.title}\n{task.description}\n"
                + discard_note
                + f"Unmet contract assertions:\n- {issues}\n"
                "Contract:\n- " + "\n- ".join(assertions)
            )
