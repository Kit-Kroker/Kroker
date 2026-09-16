"""Architecture stage step execution (spec A §3.3).

Executes the architecture stage: recalls prior memories, prepares codebase map grounding
and research tools, runs the architect proposer role with memoization caching and brownfield
delta checks, obtains human gate approval via revisable_stage, judges and records outcome,
retains the architecture summary in memory, and returns (ArchitectureSpec, GateDecision).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

# This module executes inside the workflow sandbox (feature.py's pipeline
# calls architecture.step) and shares model classes with it — without the
# marker the sandbox re-imports them isolated, duplicating classes pydantic
# then rejects (BrownfieldDelta via DeltaCheckInput, first post-B0
# brownfield run, DS12).
with workflow.unsafe.imports_passed_through():
    from ...context.models import CodebaseMap
    from ...context.project import map_digest
    from ...context.render import render_for_prompt
    from ...core.context import StageContext
    from ...core.models import (
        GateDecision,
        IdeaBrief,
        PipelineConfig,
        RoleUsage,
    )
    from ...memory.models import MemoryKind
    from ..clarify.models import ClarifiedRequirements
    from ..context.activities import DeltaCheckInput, check_brownfield_delta
    from .models import ArchitectureSpec
    from .prompts import prompt_digest

_INTAKE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=3),
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
        return "direct-execution"


def _requirements_for_downstream(reqs: ClarifiedRequirements) -> str:
    return reqs.model_dump_json(exclude={"dropped", "dimensions_probed"})


@dataclass
class ArchitecturePrep:
    """The once-per-stage prefix of the architecture stage (E-74 §4.3)."""

    started: datetime
    resolved_model: str
    spend: RoleUsage
    mode_val: str
    snapshot: Any
    map_block: str
    map_key: str
    salt: str


async def prepare(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    codebase_map: CodebaseMap | None = None,
    idea: IdeaBrief | None = None,
    architect_model: str | None = None,
) -> ArchitecturePrep:
    ctx.stage("architecting", "architecture")
    started = _now()
    arch_role = cfg.roles.get("architect")
    resolved_model = (
        architect_model
        or (arch_role.model if arch_role and arch_role.model else None)
        or "claude-3-5-sonnet"
    )
    spend = RoleUsage(role="architect", model=resolved_model)

    title = idea.title if idea else "feature"
    mode_val = idea.mode.value if idea and idea.mode else "greenfield"

    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"architect:{title}",
        filters={"stage": "architect"},
    )

    map_block = ""
    map_key = ""
    if codebase_map is not None:
        rendered_map = render_for_prompt(codebase_map)
        map_key = map_digest(codebase_map)
        map_block = f"\n\nCodebase map at commit {codebase_map.commit_sha[:12]}:\n{rendered_map}"

    return ArchitecturePrep(
        started=started,
        resolved_model=resolved_model,
        spend=spend,
        mode_val=mode_val,
        snapshot=snapshot,
        map_block=map_block,
        map_key=map_key,
        salt=prompt_digest(cfg),
    )


async def produce(
    ctx: StageContext,
    prep: ArchitecturePrep,
    *,
    cfg: PipelineConfig,
    requirements: ClarifiedRequirements,
    codebase_map: CodebaseMap | None = None,
    memory_watermark: str | None = None,
    repo_path: str = "/var/sdlc/repo",
    architect_agent: Any = None,
    guidance: str | None = None,
) -> ArchitectureSpec:
    """One architect round (delta retries included). Verbatim body of the
    former `_run_architect(guidance)` closure."""
    from ..research.deps import ResearchDeps

    research_role = cfg.roles.get("research") if cfg.research_enabled else None
    architect_deps = ResearchDeps(
        run_id=_workflow_id(),
        provider=(research_role.provider or "fake") if research_role else "fake",
        max_searches=cfg.research.max_searches,
        max_fetches=cfg.research.max_fetches,
        max_cost_usd=cfg.research.max_cost_usd,
        memory_backend=cfg.memory.backend,
        memory_base_url=cfg.memory.base_url,
        memory_bank=cfg.memory.project_bank,
        memory_watermark=memory_watermark,
        scope="architect",
    )

    delta_retries = cfg.max_delta_retries
    delta_guidance: str | None = None
    reqs_for_architect = _requirements_for_downstream(requirements)
    snapshot = prep.snapshot
    while True:
        prompt = (
            f"mode={prep.mode_val}\n{reqs_for_architect}"
            + (prep.map_block if codebase_map is not None else "")
            + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items) if snapshot.items else "")
            + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
            + (f"\nDelta correction required:\n{delta_guidance}" if delta_guidance else "")
        )

        async def _produce(prompt: str = prompt) -> ArchitectureSpec:
            res = await ctx.run_role(
                cfg,
                "architect",
                prep.resolved_model,
                architect_agent,
                prompt,
                deps=architect_deps,
                into=prep.spend,
            )
            return res.output

        cache_key = (
            reqs_for_architect
            + (guidance or "")
            + (prep.map_key if codebase_map is not None else "")
            + (delta_guidance or "")
        )
        arch, _ = await ctx.cached_stage(
            cfg, "architect", cache_key, ArchitectureSpec, _produce, prompt_digest=prep.salt
        )

        if codebase_map is None:
            return arch

        delta_check = await workflow.execute_activity(
            check_brownfield_delta,
            DeltaCheckInput(
                repo_dir=repo_path,
                commit_sha=codebase_map.commit_sha,
                delta=arch.delta,
            ),
            **_INTAKE_ACT,
        )
        if delta_check.passed:
            return arch

        if delta_retries <= 0:
            raise ApplicationError(
                f"brownfield architecture delta failed grounding check "
                f"after retries: {delta_check.detail}",
                non_retryable=True,
            )
        delta_retries -= 1
        delta_guidance = (
            f"The proposed delta does not match the repository at "
            f"{codebase_map.commit_sha[:12]}: "
            f"{delta_check.detail}. Update delta.added, delta.modified, "
            f"and delta.removed so every path resolves."
        )


async def finish(
    ctx: StageContext,
    prep: ArchitecturePrep,
    *,
    cfg: PipelineConfig,
    artifact: ArchitectureSpec,
    gate: GateDecision,
) -> None:
    """Post-gate work: judge, record PASS|REVISED, retain."""
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record

    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        artifact.model_dump_json(),
        "architect",
        author_model=prep.resolved_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="architecture",
            role="architect",
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
        text=f"architect: {artifact.overview}",
        metadata={"stage": "architect", "run_id": _workflow_id()},
    )


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    requirements: ClarifiedRequirements,
    codebase_map: CodebaseMap | None = None,
    memory_watermark: str | None = None,
    idea: IdeaBrief | None = None,
    repo_path: str = "/var/sdlc/repo",
    architect_agent: Any = None,
    architect_model: str | None = None,
) -> tuple[ArchitectureSpec, GateDecision]:
    """Execute the architecture stage: prepare, the revisable produce loop,
    finish. Returns (ArchitectureSpec, GateDecision)."""
    prep = await prepare(
        ctx, cfg=cfg, codebase_map=codebase_map, idea=idea, architect_model=architect_model
    )

    async def _run_architect(guidance: str | None) -> ArchitectureSpec:
        return await produce(
            ctx,
            prep,
            cfg=cfg,
            requirements=requirements,
            codebase_map=codebase_map,
            memory_watermark=memory_watermark,
            repo_path=repo_path,
            architect_agent=architect_agent,
            guidance=guidance,
        )

    arch, gate = await ctx.revisable_stage(
        "architecture", cfg, _run_architect, author_model=prep.resolved_model
    )
    await finish(ctx, prep, cfg=cfg, artifact=arch, gate=gate)
    return arch, gate
