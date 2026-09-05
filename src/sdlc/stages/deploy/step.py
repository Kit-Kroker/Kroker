"""Deploy stage step execution (spec A §3.3).

Executes stage 13 deploy: consults the deploy gate, runs DeploymentWorkflow child workflow,
evaluates smoke checks, handles rollback / failure retries with human-in-the-loop,
records benchmark records, and reports stage transitions.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from temporalio import workflow

from ...agents.roles import resolve_role_model
from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import (
    DeployConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
)
from ...gate import CheckClass, CheckResult
from ...pending import GateContext
from .models import (
    DeployPlan,
    DeployReport,
    SmokeCheck,
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
        return "deploy"


def _task_queue() -> str:
    try:
        return workflow.info().task_queue
    except Exception:
        return "ai-sdlc"


def _deploy_result(report: DeployReport, decision: GateDecision | None, pr_url: str) -> str:
    """Map a DeployReport plus the deploy_failed gate decision onto the run's
    terminal string. Pure, so the mapping is testable without Temporal.

    `decision` is None only when the report says deployed.

    A report whose rollback did NOT happen can never return `rolled-back:` --
    the environment is live and in an unknown state, and flattening that into
    an ordinary failure hides the one outcome needing a human immediately.
    """
    if report.deployed:
        return f"deployed:{pr_url}"
    if not report.rolled_back:
        return f"deploy-broken:{pr_url}"
    if decision is not None and decision.outcome is GateOutcome.REJECT:
        return f"deploy-rejected:{pr_url}"
    return f"rolled-back:{pr_url}"


def _deploy_verdict(report: DeployReport) -> str:
    """What the deploy_failed gate renders. The rollback reason plus, when
    available, the deploy command's own output -- without it the human
    deciding what to do next never sees what the apply actually produced
    (F4: the common smoke-fails case)."""
    if report.apply_detail.strip():
        return f"{report.rollback_reason}\n\nDeploy output:\n{report.apply_detail}"
    return report.rollback_reason


def _sanitize_tag(raw: str) -> str:
    """Turn an arbitrary workflow id into a valid image tag.

    The version becomes IMAGE_TAG for the compose adapter, and a benchmark
    child id is `f"{bench_run_id}/{cell.cell_id}"` -- the '/' (and any other
    char outside [A-Za-z0-9_.-]) is not legal in a docker tag. Replace invalid
    chars with '-', and never let the result start with '.' or '-'.
    """
    tag = re.sub(r"[^A-Za-z0-9_.-]", "-", raw)[:128]
    tag = re.sub(r"^[.-]+", "", tag) or "run"
    return tag


def _deploy_plan(cfg: PipelineConfig, workflow_id: str = "") -> DeployPlan:
    """The frozen DeployPlan for this run.

    TRANSITIONAL: devops_planner authoring this at the planning stage and
    the plan gate freezing it (spec D-2) is the next increment. Until
    then the run deploys with at most one liveness check -- weak but
    honest, and `frozen=True` keeps the contract's shape intact so the
    planner can start filling it without a second code path.

    The http liveness check is emitted ONLY when a base_url is configured:
    a script-adapter deploy has no endpoint, and an http check against an
    empty endpoint errors and would roll back every deploy (D-7 broken).
    With no base_url the plan therefore carries ZERO checks, so a script
    deploy succeeds on a zero exit code alone -- the one case that falls
    short of DeployReport's "deployed is earned by passing smoke checks"
    contract. A command smoke check (the natural fix for the D-7 path)
    lands with devops_planner. The version is sanitized into a valid
    image tag -- a benchmark child id carries a '/', which is not legal
    as a docker tag.
    """
    checks = []
    if cfg.deploy.base_url:
        checks.append(SmokeCheck(name="liveness", kind="http", path="/health"))
    return DeployPlan(
        environment="staging",
        version=_sanitize_tag(workflow_id) if workflow_id else "run",
        smoke_checks=checks,
    )


async def _execute_deployment_workflow(
    plan: DeployPlan,
    cfg: DeployConfig,
    repo_path: str,
    attempt: int,
) -> DeployReport:
    """Run DeploymentWorkflow child workflow. Pure indirection so step tests can patch it."""
    from ...workflows.deployment import DeploymentInput, DeploymentWorkflow

    return await workflow.execute_child_workflow(
        DeploymentWorkflow.run,
        DeploymentInput(plan=plan, cfg=cfg, repo_path=repo_path, attempt=attempt),
        id=f"{_workflow_id()}-deploy-{attempt}",
        task_queue=_task_queue(),
    )


# 6. DEPLOY
async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    deploy_plan: DeployPlan | None = None,
    repo_path: str,
    pr_url: str,
    planner_agent: Any = None,
) -> str:
    """Execute the deploy stage (stage 13).

    Opens the deploy gate, executes DeploymentWorkflow child workflow,
    handles failure and human revise/reject loops, and records benchmark records.
    """
    _started = _now()
    gate = await ctx.gate("deploy", cfg.gate_settings())
    _ended = _now()
    if not gate.approved or not cfg.deploy.enabled:
        # The deploy stage did not run: record the gate decision only.
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="deploy",
                role="devops",
                started=_started,
                ended=_ended,
                quality_score=None,
                judge="llm_judge",
                outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
                model=resolve_role_model(cfg, "devops"),
            ),
        )
        return f"merged-not-deployed:{pr_url}"

    if deploy_plan is None:
        deploy_plan = _deploy_plan(cfg, _workflow_id())

    attempt = 1
    while True:
        report = await _execute_deployment_workflow(deploy_plan, cfg.deploy, repo_path, attempt)
        if report.deployed:
            # One record, reflecting the actual result -- never a
            # premature PASS from the gate. (SC-5 / E-40: a reading must
            # not read as clean when it was not.)
            await ctx.record(
                cfg,
                stage_record(
                    cfg,
                    stage="deploy",
                    role="devops",
                    started=_started,
                    ended=_now(),
                    quality_score=None,
                    judge="contract",
                    outcome=BenchmarkOutcome.PASS,
                    model=resolve_role_model(cfg, "devops"),
                ),
            )
            ctx.stage("deployed", "deploy")
            return _deploy_result(report, None, pr_url)

        # The gate opens even when the rollback itself failed -- that is
        # the case a human most needs to see.
        decision = await ctx.gate(
            "deploy_failed",
            cfg.gate_settings(),
            round=attempt,
            context=GateContext(
                # ABSOLUTE: the human is not waving a check through --
                # the rollback already happened. They are deciding what
                # to do next.
                checks=[
                    CheckResult(
                        name=c.name,
                        passed=c.passed,
                        classification=CheckClass.ABSOLUTE,
                        detail=c.detail,
                    )
                    for c in report.checks
                ],
                verdict=_deploy_verdict(report),
            ),
            default_policy=GatePolicy.HARD,
        )
        if decision.outcome is GateOutcome.REVISE and attempt < cfg.max_gate_rounds:
            attempt += 1
            continue

        # Rolled back or deploy-broken: record FAIL, never the gate's PASS.
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="deploy",
                role="devops",
                started=_started,
                ended=_now(),
                quality_score=None,
                judge="contract",
                outcome=BenchmarkOutcome.FAIL,
                model=resolve_role_model(cfg, "devops"),
            ),
        )
        ctx.stage("deploy_failed", "deploy")
        return _deploy_result(report, decision, pr_url)
