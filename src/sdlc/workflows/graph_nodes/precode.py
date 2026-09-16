"""Pre-code node handlers (E-74 spec §6): adapters over the stage steps.

Each handler reproduces the matching `_pipeline` section's commands in order
(golden command projection, spec §7.3). Host attribute mirrors follow §5.3.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ...agents.roles import (
        resolve_role_model,
        t_architect,
        t_clarify,
        t_clarify_probe,
        t_clarify_route,
        t_planner,
        t_research,
    )
    from ...core.models import PipelineConfig, ProjectMode
    from ...graph.router import Activation
    from ...memory.models import MemoryKind
    from ...stages import clarify, context, intake, research
    from ...stages.architecture.step import prepare as arch_prepare
    from ...stages.architecture.step import produce as arch_produce
    from ...stages.plan.step import prepare as plan_prepare
    from ...stages.plan.step import produce as plan_produce
    from ...stages.research.models import ResearchBrief
    from ...vcs import IntegrationInput, setup_integration_branch
    from .base import NodeContext, NodeResult, guidance_text, input_model

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


async def intake_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    idea = nc.facts.idea
    err = await intake.step(nc.ctx, cfg=cfg, idea=idea, repo_path=nc.facts.repo_path)
    if err is not None:
        return NodeResult(port="reject", result=err)
    brownfield = idea.mode is ProjectMode.BROWNFIELD
    port = "brownfield" if brownfield else "ok"
    if not nc.connected(port):
        mode = "brownfield" if brownfield else "greenfield"
        return NodeResult(port="reject", result=f"rejected:intake (graph has no {mode} path)")
    # ADR-14: the branch is cut only after intake passes (feature.py:490-510) --
    # never more reachable for the stale-branch defect than today (spec §11).
    integration = await workflow.execute_activity(
        setup_integration_branch,
        IntegrationInput(
            repo_path=nc.facts.repo_path, run_id=nc.facts.run_id, base_branch=idea.base_branch
        ),
        **ACT,
    )
    nc.facts.set_integration(integration)
    nc.host._integration_head = integration.head_sha
    nc.host._base_sha = integration.head_sha
    nc.host._integration_wt = integration.worktree_path
    return NodeResult(port=port)


async def context_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    res = await context.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        repo_path=nc.facts.repo_path,
        commit_sha=nc.host._integration_head,
    )
    if isinstance(res, str):
        return NodeResult(port="reject", result=res)
    if res is None:
        return NodeResult(
            port="reject", result="rejected:context (greenfield run has no codebase to map)"
        )
    nc.host._codebase_map = res
    return NodeResult(port="map", payload=res)


async def research_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    if t_research is None:
        raise RuntimeError(
            "research node on a worker without agents/research (select_graph guards this)"
        )
    out = await research.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        memory_watermark=nc.host._memory_watermark,
        research_agent=t_research,
        research_model=resolve_role_model(cfg, "research"),
    )
    if out.rejection:
        return NodeResult(port="reject", result=out.rejection)
    brief = ResearchBrief.model_validate(out.model_dump(exclude={"digest", "rejection"}))
    return NodeResult(port="brief", payload=brief, meta={"digest": out.digest})


async def clarify_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    research_ref = act.inputs.get("research")
    digest = (
        nc.payload(research_ref).meta.get("digest", "") if isinstance(research_ref, str) else ""
    )
    reqs = await clarify.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        codebase_map=input_model(nc, act, "codebase_map"),
        brief_digest=digest,
        clarify_agent=t_clarify,
        route_agent=t_clarify_route,
        probe_agent=t_clarify_probe,
        clarify_model=resolve_role_model(cfg, "clarify"),
    )
    await nc.host._board_publish(cfg, "requirements", reqs.model_dump_json())
    await nc.ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"clarify: {reqs.summary}",
        metadata={"stage": "clarify", "run_id": nc.facts.run_id},
    )
    return NodeResult(port="requirements", payload=reqs)


async def architect_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    carry = nc.carry(nc.node.id)
    codebase_map = input_model(nc, act, "codebase_map")
    if "prep" not in carry:  # once per stage (§7.2, C1)
        carry["prep"] = await arch_prepare(
            nc.ctx,
            cfg=cfg,
            codebase_map=codebase_map,
            idea=nc.facts.idea,
            architect_model=resolve_role_model(cfg, "architect"),
        )
    prep = carry["prep"]
    reqs = input_model(nc, act, "requirements")
    assert reqs is not None
    spec = await arch_produce(
        nc.ctx,
        prep,
        cfg=cfg,
        requirements=reqs,
        codebase_map=codebase_map,
        memory_watermark=nc.host._memory_watermark,
        repo_path=nc.facts.repo_path,
        architect_agent=t_architect,
        guidance=guidance_text(nc, act),
    )
    return NodeResult(port="spec", payload=spec, author_model=prep.resolved_model)


async def plan_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    carry = nc.carry(nc.node.id)
    if "prep" not in carry:
        carry["prep"] = await plan_prepare(
            nc.ctx, cfg=cfg, idea=nc.facts.idea, planner_model=resolve_role_model(cfg, "plan")
        )
    prep = carry["prep"]
    arch = input_model(nc, act, "spec")
    assert arch is not None
    plan = await plan_produce(
        nc.ctx,
        prep,
        cfg=cfg,
        architecture=arch,
        requirements=input_model(nc, act, "requirements"),
        planner_agent=t_planner,
        guidance=guidance_text(nc, act),
    )
    return NodeResult(port="plan", payload=plan, author_model=prep.resolved_model)
