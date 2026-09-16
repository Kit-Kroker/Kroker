"""Plan stage step execution (spec A §3.3).

Executes the plan stage: recalls prior memories, runs the planner proposer role with
memoization caching, obtains human gate approval via revisable_stage, judges and records outcome,
retains the plan summary in memory, and returns (ImplementationPlan, GateDecision).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from temporalio import workflow

# This module executes inside the workflow sandbox (feature.py's
# pipeline calls plan.step) and shares model classes with it — without
# the marker the sandbox re-imports them isolated, duplicating classes
# pydantic then rejects (first post-B0 brownfield run, DS12).
with workflow.unsafe.imports_passed_through():
    from ...core.context import StageContext
    from ...core.models import (
        GateDecision,
        IdeaBrief,
        PipelineConfig,
        RoleUsage,
    )
    from ...memory.models import MemoryKind
    from ...prompts import planner_prompt
    from .models import ImplementationPlan
    from .prompts import prompt_digest

if TYPE_CHECKING:
    from ..architecture.models import ArchitectureSpec
    from ..clarify.models import ClarifiedRequirements


def _now() -> datetime:
    try:
        return workflow.now()
    except Exception:
        return datetime.now(UTC)


def _workflow_id() -> str:
    try:
        return workflow.info().workflow_id
    except Exception:
        return "direct-execution"


@dataclass
class PlanPrep:
    """The once-per-stage prefix of the plan stage (E-74 §4.3)."""

    started: datetime
    resolved_model: str
    spend: RoleUsage
    snapshot: Any
    salt: str


async def prepare(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief | None = None,
    planner_model: str | None = None,
) -> PlanPrep:
    started = _now()
    plan_role = cfg.roles.get("plan")
    resolved_model = (
        planner_model
        or (plan_role.model if plan_role and plan_role.model else None)
        or "claude-3-5-sonnet"
    )
    spend = RoleUsage(role="planner", model=resolved_model)
    title = idea.title if idea else "feature"
    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"plan:{title}",
        filters={"stage": "plan"},
    )
    return PlanPrep(
        started=started,
        resolved_model=resolved_model,
        spend=spend,
        snapshot=snapshot,
        salt=prompt_digest(cfg),
    )


async def produce(
    ctx: StageContext,
    prep: PlanPrep,
    *,
    cfg: PipelineConfig,
    architecture: ArchitectureSpec,
    requirements: ClarifiedRequirements | None = None,
    planner_agent: Any = None,
    guidance: str | None = None,
) -> ImplementationPlan:
    """One planner round. Verbatim body of the former `_run_plan(guidance)`."""
    prompt = planner_prompt(architecture.model_dump_json(), prep.snapshot.items, guidance)

    async def _produce() -> ImplementationPlan:
        res = await ctx.run_role(
            cfg,
            "planner",
            prep.resolved_model,
            planner_agent,
            prompt,
            into=prep.spend,
        )
        return res.output

    cache_key = architecture.model_dump_json() + (guidance or "")
    plan_obj, _ = await ctx.cached_stage(
        cfg,
        "plan",
        cache_key,
        ImplementationPlan,
        _produce,
        prompt_digest=prep.salt,
    )
    return plan_obj


async def finish(
    ctx: StageContext,
    prep: PlanPrep,
    *,
    cfg: PipelineConfig,
    artifact: ImplementationPlan,
    gate: GateDecision,
) -> None:
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record

    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        artifact.model_dump_json(),
        "planner",
        author_model=prep.resolved_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="plan",
            role="planner",
            started=prep.started,
            ended=_ended,
            quality_score=_quality.score,
            judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
            model=prep.resolved_model,
            spend=prep.spend,
        ),
    )
    await ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"plan: {len(artifact.tasks)} tasks",
        metadata={"stage": "plan", "run_id": _workflow_id()},
    )


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    architecture: ArchitectureSpec,
    requirements: ClarifiedRequirements | None = None,
    idea: IdeaBrief | None = None,
    planner_agent: Any = None,
    planner_model: str | None = None,
) -> tuple[ImplementationPlan, GateDecision]:
    """Execute the plan stage: prepare, the revisable produce loop, finish."""
    prep = await prepare(ctx, cfg=cfg, idea=idea, planner_model=planner_model)

    async def _run_plan(guidance: str | None) -> ImplementationPlan:
        return await produce(
            ctx,
            prep,
            cfg=cfg,
            architecture=architecture,
            requirements=requirements,
            planner_agent=planner_agent,
            guidance=guidance,
        )

    plan_obj, gate = await ctx.revisable_stage(
        "plan", cfg, _run_plan, author_model=prep.resolved_model
    )
    await finish(ctx, prep, cfg=cfg, artifact=plan_obj, gate=gate)
    return plan_obj, gate
