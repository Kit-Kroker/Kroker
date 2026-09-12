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
from ...calibration.activities import VerdictInput, calibration_verdict
from ...calibration.decision import auto_decision_for
from ...calibration.models import INSUFFICIENT, LabelSource
from ...calibration.verdict import bucket_key
from ...core.context import StageContext
from ...core.models import (
    GateConfig,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
)
from ...gate import (
    CheckClass,
    CheckResult,
    GateOverride,
    GateReport,
    QualityGateInput,
    build_check,
)
from ...measurement import CollectionState
from ...memory.models import MemoryKind
from ...observability.trace import RunEventKind
from ...pending import GateContext
from ...vcs import BaseWorktree, BaseWorktreeInput, prepare_base_worktree
from ..plan.models import PlanDrift
from ..qa.activities import LintInput, ScopedSecurityScanInput, run_lint, scoped_security_scan
from ..qa.models import ScopedSecurityReport
from ..review.lenses import GATING_LENSES, LensPresence, primary_admits
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
from .models import CoverageReport, MergeVerdict, ScopedLintReport, ScopedTestReport
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


def _plan_drift_flags(drift: PlanDrift) -> bool:
    """E4: per-task threshold. Only unhinted touches count -- hinted_untouched
    (over-hinting) is harmless and files_hint is explicitly a hint, not a
    gate (plan/models.py PlanDrift docstring). Single-file tasks are exempt:
    there is no calibration signal at n=1."""
    if drift.files_touched <= 1:
        return False
    unhinted = len(drift.touched_unhinted)
    return unhinted >= 2 or (unhinted / drift.files_touched) >= 0.5


def _plan_drift_check(results: list) -> CheckResult:
    """E4: run-level aggregation is 'any task fires', not an average or a
    fleet-wide accumulator -- one task past its own threshold fails the
    check regardless of how many other tasks are clean, and many tasks each
    individually under threshold pass (that is the accepted shape of a
    per-task predicate, not a gap). Unfiltered by status: a quarantined
    task's drift counts too, matching the existing review_severity/untraced
    precedent of reading all results."""
    drifted = [
        r.task_id for r in results if r.plan_drift is not None and _plan_drift_flags(r.plan_drift)
    ]
    return build_check(
        "plan_drift",
        not drifted,
        CheckClass.ADVISORY,
        detail=(
            f"{len(drifted)} task(s) touched unhinted files beyond threshold: {drifted[:10]}"
            if drifted
            else "no task exceeded the plan-drift threshold (or drift is unmeasured)"
        ),
    )


def _lens_presence_check(results: list) -> CheckResult:
    """C8: a lens that did not run must not be graded as one that approved.

    Ruling OQ2 -- fail only on UNDECLARED_ABSENT (the lens was asked for, was
    reached, and did not deliver) or on a MISSING outcome. The missing-outcome
    clause is what preserves the defense against an empty `lens_outcomes`
    list: a producer that predates the field has no UNDECLARED_ABSENT entry to
    trip on, so without it a task with no tombstones at all would pass. A
    missing tombstone is as severe as a broken one.

    DECLARED_ABSENT (the operator turned it off) and NOT_REACHED (the run site
    was never reached -- routine geometry on quarantined and budget-exhausted
    tasks) both pass, and every state is named in the detail regardless: the
    ruling honours operator intent and pipeline shape without letting either
    go silent.

    Ruling OQ3 -- one uniform check over both lenses; the detail names which.
    Unfiltered by status, matching review_severity and plan_drift.
    """
    failures: list[str] = []
    notes: list[str] = []
    for r in results:
        recorded = {o.lens: o for o in (getattr(r, "lens_outcomes", None) or [])}
        task_id = getattr(r, "task_id", "?")
        for lens in sorted(GATING_LENSES):
            outcome = recorded.get(lens)
            if outcome is None:
                failures.append(f"{task_id}/{lens}: no outcome recorded")
            elif outcome.presence is LensPresence.UNDECLARED_ABSENT:
                failures.append(f"{task_id}/{lens}: {outcome.presence.value} ({outcome.reason})")
            else:
                notes.append(f"{task_id}/{lens}: {outcome.presence.value}")
    return build_check(
        "review_lenses_present",
        not failures,
        CheckClass.ADVISORY,
        detail="; ".join(failures + notes) or "no task results to grade",
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


_M = CollectionState.MEASURED


def _listed(items: list[str], limit: int = 10) -> str:
    return (
        f"; introduced: {items[:limit]}" + (" ..." if len(items) > limit else "") if items else ""
    )


def tests_check(r: ScopedTestReport) -> CheckResult:
    """DS6/DS7: rendered from typed fields, never parsed back."""
    if r.state is not _M:
        return build_check(
            "build_integration_green", False, CheckClass.ABSOLUTE, f"not collected: {r.reason}"
        )
    detail = (
        f"{len(r.introduced)} introduced; {len(r.preexisting)} pre-existing; "
        f"{len(r.preexisting_flaky)} pre-existing flaky" + _listed(r.introduced)
    )
    return build_check("build_integration_green", not r.introduced, CheckClass.ABSOLUTE, detail)


tests_check.__test__ = False  # type: ignore[attr-defined]


def lint_check(r: ScopedLintReport) -> CheckResult:
    if r.state is not _M:
        return build_check("lint_clean", False, CheckClass.ABSOLUTE, f"not collected: {r.reason}")
    detail = (
        f"{len(r.introduced)} introduced; {r.preexisting} pre-existing; {r.resolved} resolved; "
        f"{len(r.policy_paths_changed)} policy path(s) changed; "
        f"{r.suppressions_added} suppression(s) added"
        + _listed([f"{f.rule} {f.path}: {f.line}" for f in r.introduced])
    )
    return build_check("lint_clean", not r.introduced, CheckClass.ABSOLUTE, detail)


def security_checks(r: ScopedSecurityReport) -> list[CheckResult]:
    """security_no_critical passes vacuously on NOT_COLLECTED by design:
    security_scan_collected is the conjunct that fails closed (DS7)."""
    collected = build_check(
        "security_scan_collected",
        r.state is _M,
        CheckClass.ABSOLUTE,
        r.reason or "collected at the base and the head",
    )
    crit = build_check(
        "security_no_critical",
        r.introduced_critical == 0,
        CheckClass.ABSOLUTE,
        f"{r.introduced_critical} introduced critical; {len(r.introduced)} introduced; "
        f"{r.preexisting} pre-existing; {r.resolved} resolved"
        + _listed([f"{f.rule} {f.path}: {f.line}" for f in r.introduced]),
    )
    return [collected, crit]


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
    base_sha: str = "",
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

    renames = (
        [list(p) for p in integration_diff.get("renames", [])]
        if isinstance(integration_diff, dict)
        else []
    )
    base: BaseWorktree = await _exec_activity(
        prepare_base_worktree,
        BaseWorktreeInput(
            integration_wt=integration_wt, run_id=_workflow_id() or "local", base_sha=base_sha
        ),
        **_ACT,
    )
    base_path = base.path if isinstance(getattr(base, "path", None), str) else None
    base_reason = _as_str(getattr(base, "reason", ""), "base worktree unavailable")

    ichecks: IntegrationChecks = await _exec_activity(
        run_integration_checks,
        IntegrationChecksInput(
            worktree=integration_wt,
            changed_files=changed_files,
            base_worktree=base_path,
            base_reason=base_reason,
            base_sha=base_sha,
            renames=renames,
        ),
        **_INTEG_ACT,
    )
    if getattr(ichecks, "toolchain", None) is not None:
        t_rep = getattr(ichecks, "tests", None)
        l_rep = getattr(ichecks, "lint", None)
        absolute = [
            tests_check(
                t_rep
                if isinstance(t_rep, ScopedTestReport)
                else ScopedTestReport(
                    state=CollectionState.NOT_COLLECTED, reason="no scoped test report"
                )
            ),
            lint_check(
                l_rep
                if isinstance(l_rep, ScopedLintReport)
                else ScopedLintReport(
                    state=CollectionState.NOT_COLLECTED, reason="no scoped lint report"
                )
            ),
        ]
    else:
        # No toolchain adapter: today's fallback, unchanged (DS10, named limitation).
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
        absolute = [
            build_check(
                "build_integration_green",
                _merge_evidence_all_green(results_list),
                CheckClass.ABSOLUTE,
                detail="no toolchain adapter: aggregate of per-task QA runs",
            ),
            build_check(
                "lint_clean",
                _as_bool(l_clean, True),
                CheckClass.ABSOLUTE,
                detail=_as_str(l_detail, ""),
            ),
        ]

    cov: CoverageReport = await _exec_activity(
        measure_coverage,
        CoverageInput(worktree=integration_wt, changed_files=changed_files),
        **_ACT,
    )

    sec = await _exec_activity(
        scoped_security_scan,
        ScopedSecurityScanInput(
            worktree=integration_wt,
            base_worktree=base_path,
            renames=renames,
            base_reason=base_reason,
        ),
        **_ACT,
    )
    if not isinstance(sec, ScopedSecurityReport):
        sec = ScopedSecurityReport(
            state=CollectionState.NOT_COLLECTED, reason="no scoped security report"
        )

    cov_obj = getattr(cov, "coverage", None)
    diff_coverage = (
        cov_obj.value
        if cov_obj is not None and getattr(cov_obj, "state", None) is CollectionState.MEASURED
        else None
    )

    checks = [
        *absolute,
        *security_checks(sec),
        build_check(
            "review_severity",
            all(
                primary_admits(o)
                for r in results_list
                for o in (getattr(r, "lens_outcomes", None) or [])
                if o.lens == "reviewer"
            ),
            CheckClass.ADVISORY,
            detail="clean-context reviewer blocking findings (FR-204); "
            "absence is graded by review_lenses_present, not here",
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
        _plan_drift_check(results_list),
        _lens_presence_check(results_list),
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
            confidence = verdict.confidence if verdict.approve else None
            auto = None
            if confidence is not None:
                # Ruling OQ2: merge-gate decisions are simply not sampled --
                # no row is written (outcome_label is NOT NULL, so an
                # unlabelled row cannot exist) -- so this resolves to
                # insufficient_data and the human gate below always fires. No
                # branch on the gate name (SG-3) -- the behaviour comes from
                # the ledger being empty for merge.
                source = (
                    LabelSource.BENCHMARK
                    if cfg.benchmark.case_id is not None
                    else LabelSource.PRODUCTION_PROXY
                )
                try:
                    calibration = await _exec_activity(
                        calibration_verdict,
                        VerdictInput(gate="merge", bucket_key=bucket_key(merge_model, source)),
                        **_ACT,
                    )
                except Exception:
                    calibration = INSUFFICIENT
                auto = auto_decision_for("merge", cfg, confidence, calibration)
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
