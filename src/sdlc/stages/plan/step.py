"""Plan stage step execution (spec A §3.3).

Executes the plan stage: recalls prior memories, runs the planner proposer role with
memoization caching, obtains human gate approval via revisable_stage, judges and records outcome,
retains the plan summary in memory, and returns (ImplementationPlan, GateDecision).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from temporalio import workflow

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
    """Execute the plan stage.

    Runs the planner agent with memoization and revisable review loops,
    records benchmark telemetry and memory summary, and returns
    (ImplementationPlan, GateDecision).
    """
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record

    _started = _now()
    plan_role = cfg.roles.get("plan")
    resolved_model = (
        planner_model
        or (plan_role.model if plan_role and plan_role.model else None)
        or "claude-3-5-sonnet"
    )
    plan_spend = RoleUsage(role="planner", model=resolved_model)

    title = idea.title if idea else "feature"
    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"plan:{title}",
        filters={"stage": "plan"},
    )

    _salt = prompt_digest(cfg)

    async def _run_plan(guidance: str | None) -> ImplementationPlan:
        prompt = planner_prompt(architecture.model_dump_json(), snapshot.items, guidance)

        async def _produce() -> ImplementationPlan:
            res = await ctx.run_role(
                cfg,
                "planner",
                resolved_model,
                planner_agent,
                prompt,
                into=plan_spend,
            )
            return res.output

        cache_key = architecture.model_dump_json() + (guidance or "")
        plan_obj, _ = await ctx.cached_stage(
            cfg,
            "plan",
            cache_key,
            ImplementationPlan,
            _produce,
            prompt_digest=_salt,
        )
        return plan_obj

    plan_obj, gate = await ctx.revisable_stage("plan", cfg, _run_plan)
    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        plan_obj.model_dump_json(),
        "planner",
        author_model=resolved_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="plan",
            role="planner",
            started=_started,
            ended=_ended,
            quality_score=_quality.score,
            judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
            model=resolved_model,
            spend=plan_spend,
        ),
    )
    await ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"plan: {len(plan_obj.tasks)} tasks",
        metadata={"stage": "plan", "run_id": _workflow_id()},
    )
    return plan_obj, gate
