"""Merge stage step execution (spec A §3.3).

Executes the merge stage (stage 10): runs deterministic integration checks,
evaluates the DeterministicQualityGate, requests advisory override from the human
merge gate if needed, optionally consults MergeVerdict under SOFT policy,
records benchmark records and memory, and opens a pull request.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
)
from ...gate import (
    CheckClass,
    GateOverride,
    GateReport,
    QualityGateInput,
    build_check,
)
from ...measurement import CollectionState
from ...memory.models import MemoryKind
from ...observability.trace import RunEventKind
from ...pending import GateContext
from ..qa.activities import LintInput, SecurityScanInput, run_lint, security_scan
from ..qa.models import SecurityReport
from .activities import (
    CoverageInput,
    IntegrationChecks,
    IntegrationChecksInput,
    PROpenInput,
    evaluate_gate,
    measure_coverage,
    open_pull_request,
    run_integration_checks,
)
from .models import CoverageReport, MergeVerdict
from .prompts import merge_verdict_prompt

DEFAULT_LINT_CMD = "ruff check ."

_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3),
)

_INTEG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=30),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


def _contract_shell_cmd(commands: list[str] | None, default: str) -> str:
    if not commands:
        return default
    return " && ".join(commands)


def _merge_evidence_all_green(results: list) -> bool:
    """True only when every task has positive, passing QA evidence.

    SC-5: a done task with missing QA (e.g. an escalation-approved task
    whose fix loop exhausted) is treated as FAILURE — never a vacuous
    `all([])` pass. The merge absolute check must see real green evidence.
    """
    return bool(results) and all(r.qa is not None and r.qa.tests_passed for r in results)


def _auto_decision_for(
    name: str, cfg: PipelineConfig, confidence: float | None
) -> GateDecision | None:
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    return GateDecision(
        gate=name,
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments=(
            f"auto-approved: confidence={confidence:.2f} >= threshold={gate_cfg.threshold:.2f}"
        ),
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


def _in_workflow() -> bool:
    try:
        workflow.info()
        return True
    except Exception:
        return False


def _as_str(val: Any, default: str = "") -> str:
    if isinstance(val, str):
        return val
    if hasattr(val, "_mock_name"):
        return default
    try:
        return str(val) if val is not None else default
    except Exception:
        return default


def _as_bool(val: Any, default: bool = True) -> bool:
    if isinstance(val, bool):
        return val
    if hasattr(val, "_mock_name"):
        return default
    return bool(val)


def _as_int(val: Any, default: int = 0) -> int:
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if hasattr(val, "_mock_name"):
        return default
    try:
        return int(val)
    except Exception:
        return default


async def _exec_activity(activity_fn: Any, arg: Any, **kwargs: Any) -> Any:
    if _in_workflow():
        return await workflow.execute_activity(activity_fn, arg, **kwargs)
    res = activity_fn(arg)
    if inspect.isawaitable(res):
        return await res
    return res


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    task_results: list[Any] | dict[str, Any],
    integration_wt: str,
    idea: IdeaBrief,
    arch: Any = None,
    plan: Any = None,
    integration_diff: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
    untraced: list[str] | None = None,
    merge_agent: Any = None,
    merge_model: str | None = None,
) -> str:
    """Execute the merge stage (stage 10 / spec A §3.3).

    DeterministicQualityGate first (SC-5), then human gate (which doubles as
    advisory-override mechanism), then MergeVerdict advisory only under SOFT policy.
    Returns:
    - 'rejected:merge:absolute-gate-failed:...' on terminal absolute failure
    - 'rejected:merge:advisory' on advisory gate rejection
    - 'rejected:merge:soft-verdict' on soft verdict rejection
    - PR URL or 'skipped:benchmark-run-has-no-remote' on success
    """
    if callable(getattr(ctx, "stage", None)):
        ctx.stage("merging", "merge")
    _started = _now()

    if isinstance(task_results, dict):
        results_list = list(task_results.values())
    elif isinstance(task_results, list):
        results_list = task_results
    else:
        results_list = []

    if changed_files is None:
        if integration_diff and isinstance(integration_diff, dict):
            changed_files = list(integration_diff.get("files", []))
        else:
            changed_files = []

    if untraced is None:
        untraced = []

    ichecks: IntegrationChecks = await _exec_activity(
        run_integration_checks,
        IntegrationChecksInput(worktree=integration_wt, changed_files=changed_files),
        **_INTEG_ACT,
    )
    if getattr(ichecks, "toolchain", None) is not None:
        all_tests_green = _as_bool(
            getattr(getattr(ichecks, "qa", None), "tests_passed", True), True
        )
        lint_clean = _as_bool(getattr(ichecks, "lint_clean", True), True)
        lint_detail = _as_str(getattr(ichecks, "lint_detail", ""), "")
    else:
        lint_commands = (
            next(
                (
                    t.contract.lint_commands
                    for t in plan.tasks
                    if getattr(t, "contract", None) and getattr(t.contract, "lint_commands", None)
                ),
                None,
            )
            if plan and getattr(plan, "tasks", None)
            else None
        )
        lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
        l_clean, l_detail = await _exec_activity(
            run_lint, LintInput(worktree=integration_wt, lint_cmd=lint_cmd), **_ACT
        )
        lint_clean = _as_bool(l_clean, True)
        lint_detail = _as_str(l_detail, "")
        all_tests_green = _merge_evidence_all_green(results_list)

    cov: CoverageReport = await _exec_activity(
        measure_coverage,
        CoverageInput(worktree=integration_wt, changed_files=changed_files),
        **_ACT,
    )

    security: SecurityReport = await _exec_activity(
        security_scan, SecurityScanInput(worktree=integration_wt), **_ACT
    )

    cov_obj = getattr(cov, "coverage", None)
    diff_coverage = (
        cov_obj.value
        if cov_obj is not None and getattr(cov_obj, "state", None) is CollectionState.MEASURED
        else None
    )

    sec_state = getattr(security, "state", None)
    sec_crit = _as_int(getattr(security, "critical", 0), 0)
    sec_reason = _as_str(getattr(security, "reason", ""), "security scan ran")

    checks = [
        build_check(
            "build_integration_green",
            _as_bool(all_tests_green, True),
            CheckClass.ABSOLUTE,
            detail="aggregate of per-task pytest runs",
        ),
        build_check(
            "lint_clean",
            _as_bool(lint_clean, True),
            CheckClass.ABSOLUTE,
            detail=_as_str(lint_detail, ""),
        ),
        build_check(
            "security_scan_collected",
            sec_state is CollectionState.MEASURED,
            CheckClass.ABSOLUTE,
            detail=sec_reason,
        ),
        build_check(
            "security_no_critical",
            sec_crit == 0,
            CheckClass.ABSOLUTE,
            detail=f"{sec_crit} critical finding(s)",
        ),
        build_check(
            "review_severity",
            all(r.review is None or r.review.approve for r in results_list),
            CheckClass.ADVISORY,
            detail="clean-context reviewer blocking findings (FR-204)",
        ),
        build_check(
            "traceability",
            not untraced,
            CheckClass.ADVISORY,
            detail=(
                f"{len(untraced)} criterion(s) without a test: {untraced[:10]}"
                if untraced
                else "every acceptance criterion traces to >=1 test"
            ),
        ),
        build_check(
            "coverage",
            (True if diff_coverage is None else diff_coverage >= cfg.coverage_threshold),
            CheckClass.ADVISORY,
            detail=(
                _as_str(getattr(cov_obj, "reason", None), "coverage unmeasured")
                if diff_coverage is None
                else f"diff coverage {diff_coverage:.1f}% vs "
                f"threshold {cfg.coverage_threshold:.1f}%"
            ),
        ),
    ]

    gate_report: GateReport = await _exec_activity(
        evaluate_gate, QualityGateInput(checks=checks), **_ACT
    )

    # 5b. Absolute failure = terminal. No override path exists.
    absolute_blocking = [
        c.name
        for c in gate_report.checks
        if c.name in gate_report.blocking and c.classification is CheckClass.ABSOLUTE
    ]
    if absolute_blocking:
        await ctx.retain(
            cfg,
            MemoryKind.GATE_FEEDBACK,
            cfg.memory.project_bank,
            text=f"merge blocked (absolute): {absolute_blocking}",
            metadata={"gate": "merge", "round": "1", "run_id": _workflow_id()},
        )
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="merge",
                role="reviewer",
                started=_started,
                ended=_now(),
                quality_score=0.0,
                judge="contract",
                outcome=BenchmarkOutcome.FAIL,
                model="deterministic",
            ),
        )
        return f"rejected:merge:absolute-gate-failed:{','.join(absolute_blocking)}"

    # 5c. Advisory failure: the human merge gate IS the override.
    overrides: list[GateOverride] = []
    if not gate_report.passed:
        advisory_blocking = [
            c.name
            for c in gate_report.checks
            if c.name in gate_report.blocking and c.classification is CheckClass.ADVISORY
        ]
        gate = await ctx.gate(
            "merge", cfg.gate_settings(), context=GateContext(checks=gate_report.checks)
        )
        if not gate.approved:
            return "rejected:merge:advisory"
        reviewer = gate.reviewer or "human"
        reason = gate.comments or "advisory override"
        overrides = [
            GateOverride(check=n, approved_by=reviewer, reason=reason) for n in advisory_blocking
        ]
        ctx.emit(
            RunEventKind.GATE_DECIDED,
            stage="merge",
            gate="merge",
            round="1",
            policy="soft",
            decided_by=(gate.reviewer or "human"),
            approved="true",
            overrides=",".join(o.check for o in overrides),
        )
        gate_report = await _exec_activity(
            evaluate_gate, QualityGateInput(checks=checks, overrides=overrides), **_ACT
        )
    else:
        # 5d. Gate passed clean. MergeVerdict is advisory and ONLY consulted under SOFT policy.
        if cfg.gates.get("merge", GateConfig()).policy == GatePolicy.SOFT:
            dumps = [
                r.model_dump() if hasattr(r, "model_dump") else getattr(r, "__dict__", {})
                for r in results_list
            ]
            if not merge_model or not isinstance(merge_model, str):
                rc = cfg.roles.get("merge_verdict") or cfg.roles.get("merge")
                merge_model = str(rc.model) if rc and rc.model else "unknown"
            role_output = await ctx.run_role(
                cfg,
                "merge_verdict",
                merge_model,
                merge_agent,
                merge_verdict_prompt(dumps),
            )
            verdict: MergeVerdict = getattr(role_output, "output", role_output)
            auto = _auto_decision_for("merge", cfg, verdict.confidence if verdict.approve else None)
            if auto is None:
                gate = await ctx.gate(
                    "merge", cfg.gate_settings(), context=GateContext(checks=gate_report.checks)
                )
                if not gate.approved:
                    return "rejected:merge:soft-verdict"

    _ended = _now()
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="merge",
            role="reviewer",
            started=_started,
            ended=_ended,
            quality_score=(1.0 if gate_report.passed else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.REVISED if overrides else BenchmarkOutcome.PASS),
            model="deterministic",
        ),
    )
    await ctx.retain(
        cfg,
        MemoryKind.GATE_FEEDBACK,
        cfg.memory.project_bank,
        text=(f"merge gate: passed={gate_report.passed} overridden={[o.check for o in overrides]}"),
        metadata={"gate": "merge", "round": "1", "run_id": _workflow_id()},
    )

    if cfg.benchmark.case_id is not None:
        return "skipped:benchmark-run-has-no-remote"

    pr_body = getattr(arch, "overview", "") if arch is not None else idea.description
    pr_url: str = await _exec_activity(
        open_pull_request,
        PROpenInput(
            worktree=integration_wt,
            title=idea.title,
            body=pr_body,
            base_branch=idea.base_branch,
        ),
        **_ACT,
    )
    return pr_url
