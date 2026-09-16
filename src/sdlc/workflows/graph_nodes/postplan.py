"""Post-plan node handlers (E-74 spec §6; coarse `code` per U1)."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ...agents.roles import STAGE_MODELS, resolve_role_model, t_analyst, t_merge_verdict
    from ...core.models import PipelineConfig
    from ...graph.router import Activation
    from ...stages import analyze, deploy, merge
    from ...stages.analyze.models import untraced_criteria
    from ...stages.plan.validation import validate_task_graph
    from ...vcs import DiffInput, get_task_diff
    from ..build import run_tasks
    from ..models import AnalyzeResult, BuildResult, PullRequest
    from .base import NodeContext, NodeResult, input_model

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


async def plan_check_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    plan = input_model(nc, act, "plan")
    assert plan is not None
    graph_error = validate_task_graph(plan.tasks)
    if graph_error:
        return NodeResult(port="halt", result=f"failed:plan-validation:{graph_error}")
    # Sync only after the graph is valid (feature.py:614-617).
    await nc.host._board_sync_tasks(cfg, nc.host._plan_version, plan.tasks)
    return NodeResult(port="ok", payload=plan)


async def seed_spec_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError(f"{nc.node.id} activated on a run without SeededWork")
    return NodeResult(port="spec", payload=seeded.arch)


async def seed_plan_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError(f"{nc.node.id} activated on a run without SeededWork")
    nc.host._stage("coding", "code")  # feature.py:518 -- the seeded path's only stage event here
    return NodeResult(port="plan", payload=seeded.plan)


async def code_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    plan = input_model(nc, act, "plan")
    assert plan is not None
    done, failure = await run_tasks(nc.host, cfg=cfg, plan=plan, repo_path=nc.facts.repo_path)
    if failure is not None:
        return NodeResult(port="halt", result=failure)
    return NodeResult(port="results", payload=BuildResult(task_results=list(done.values())))


async def analyze_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    assert results is not None
    plan = input_model(nc, act, "plan")
    assert plan is not None
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    integration_diff = await workflow.execute_activity(
        get_task_diff,
        DiffInput(worktree=integration.worktree_path, branch_point=nc.facts.base_sha or ""),
        **ACT,
    )
    done = {r.task_id: r for r in results.task_results}
    authoritative: list[tuple[str, str]] = [
        (t.id, c) for t in plan.tasks for c in t.acceptance_criteria
    ]
    analysis = await analyze.step(
        nc.ctx,
        cfg=cfg,
        plan=plan,
        task_results=done,
        diff=integration_diff,
        integration_wt=integration.worktree_path,
        base_branch=nc.facts.idea.base_branch,
        analyst_agent=t_analyst,
        analyst_model=resolve_role_model(cfg, "analyze"),
    )
    return NodeResult(
        port="analysis",
        payload=AnalyzeResult(
            report=analysis,
            untraced=untraced_criteria(authoritative, analysis),
            integration_diff=integration_diff,
        ),
    )


async def merge_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    assert results is not None
    analysis = input_model(nc, act, "analysis")
    assert analysis is not None
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    pr_url = await merge.step(
        nc.ctx,
        cfg=cfg,
        task_results=list(results.task_results),
        integration_wt=integration.worktree_path,
        idea=nc.facts.idea,
        arch=input_model(nc, act, "spec"),
        plan=input_model(nc, act, "plan"),
        base_sha=nc.facts.base_sha or "",
        integration_diff=analysis.integration_diff,
        untraced=analysis.untraced,
        merge_agent=t_merge_verdict,
        merge_model=STAGE_MODELS.get("merge_verdict", "unknown"),
    )
    if pr_url.startswith("rejected:"):
        return NodeResult(port="reject", result=pr_url)
    return NodeResult(port="pr", payload=PullRequest(url=pr_url))


async def deploy_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    pr = input_model(nc, act, "pr")
    assert pr is not None
    out = await deploy.step(
        nc.ctx,
        cfg=cfg,
        deploy_plan=deploy._deploy_plan(cfg, nc.facts.run_id),
        repo_path=nc.facts.repo_path,
        pr_url=pr.url,
    )
    return NodeResult(port="done", result=out)
