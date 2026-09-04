"""Research stage step execution (spec A §3.3).

Executes the research stage (stage 0 / FR-107): fan-out planner -> parallel
sub-questions -> synthesizer, verifies groundedness against fetched pages,
presents to human gate with refine loops, and retains verified findings in episodic memory.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...core.context import StageContext
from ...core.models import (
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ResearchConfig,
    RoleUsage,
)
from ...pricing import PriceUsageInput, price_usage
from .deps import ResearchDeps
from .models import (
    Gap,
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)
from .retain import verified_findings_to_retain
from .stage import (
    PlanInput,
    SubQuestionInput,
    SynthesizeInput,
    plan_research,
    research_subquestion,
    synthesize_brief,
)
from .verify import brief_digest, verify_brief_activity

RESEARCH_PLAN_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5), retry_policy=RetryPolicy(maximum_attempts=3)
)

RESEARCH_SQ_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=20),
    heartbeat_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=60),
        maximum_attempts=6,
        non_retryable_error_types=["BudgetExceeded", "UsageLimitExceeded"],
    ),
)

RESEARCH_SYNTH_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)

VERIFY_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy=RetryPolicy(maximum_attempts=1),
)

PRICE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


class ResearchOutcome(ResearchBrief):
    """Result of the research step, carrying the brief plus stage outcome fields."""

    digest: str = ""
    rejection: str | None = None


def _degraded_research_brief(exc: Exception) -> ResearchBrief:
    """Substitute for the research stage's output when model calls fail."""
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id="research-stage",
                what_is_missing="the research stage did not complete",
                why_it_matters=f"degraded fallback: {exc}",
            )
        ],
        summary=f"Research stopped early: {exc}",
        confidence=0.0,
    )


def _findings_from_results(subs: list[SubQuestion], results: list) -> list[SubQuestionFinding]:
    """Turn gather(..., return_exceptions=True) output into findings."""
    out: list[SubQuestionFinding] = []
    for sub, result in zip(subs, results, strict=False):
        if isinstance(result, BaseException):
            out.append(SubQuestionFinding(sub_question=sub, failed=True, error=str(result)))
        else:
            out.append(result)
    return out


def _should_refine(round_n: int, cfg: ResearchConfig) -> bool:
    return round_n <= cfg.max_refine_rounds


def _refine_seed(brief: ResearchBrief) -> tuple[list, list]:
    return list(brief.gaps), [c for c in brief.contradictions if c.unresolved]


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


async def _fold_research_usage(cfg: PipelineConfig, usage: RoleUsage, into: RoleUsage) -> None:
    """Fold usage from activity returns into stage spend."""
    if not (usage.input_tokens or usage.output_tokens):
        return
    usd: float | None = None
    try:
        usd = await workflow.execute_activity(
            price_usage,
            PriceUsageInput(
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
            ),
            **PRICE_ACT,
        )
    except Exception:
        usd = None
    into.calls += 1
    into.input_tokens += usage.input_tokens
    into.output_tokens += usage.output_tokens
    into.cache_read_tokens += usage.cache_read_tokens
    into.cache_write_tokens += usage.cache_write_tokens
    if usd is not None:
        into.cost_usd = (into.cost_usd or 0.0) + usd


async def _fan_out_research(
    cfg: PipelineConfig,
    idea: IdeaBrief,
    deps: ResearchDeps,
    spend: RoleUsage,
    id_offset: int = 0,
    guidance: str = "",
    gaps: list | None = None,
    contradictions: list | None = None,
    model: str = "unknown",
) -> list[SubQuestionFinding]:
    """Execute one wave: plan -> N parallel sub-questions."""
    plan: ResearchPlan = await workflow.execute_activity(
        plan_research,
        PlanInput(
            idea_json=idea.model_dump_json(),
            max_sub_questions=cfg.research.max_sub_questions,
            model=model,
            id_offset=id_offset,
            guidance=guidance,
            gaps=gaps or [],
            contradictions=contradictions or [],
        ),
        **RESEARCH_PLAN_ACT,
    )
    await _fold_research_usage(cfg, plan.usage, spend)

    results = await asyncio.gather(
        *[
            workflow.execute_activity(
                research_subquestion,
                SubQuestionInput(
                    sub_question=sq,
                    deps=deps,
                    model=model,
                    max_requests=cfg.research.max_requests,
                    max_run_cost_usd=cfg.research.max_run_cost_usd,
                ),
                **RESEARCH_SQ_ACT,
            )
            for sq in plan.sub_questions
        ],
        return_exceptions=True,
    )

    findings = _findings_from_results(plan.sub_questions, results)
    for f in findings:
        await _fold_research_usage(cfg, f.usage, spend)
    return findings


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    memory_watermark: str | None = "",
    research_agent: Any = None,
    research_model: str = "",
    run_id: str | None = None,
) -> ResearchOutcome:
    """Execute the research stage step."""
    ctx.stage("researching", "research")
    _r_started = _now()

    resolved_model: str = research_model
    if not resolved_model:
        role_cfg = cfg.roles.get("research")
        if role_cfg and role_cfg.model:
            resolved_model = role_cfg.model
        else:
            resolved_model = "unknown"
    run_id_val = run_id or _workflow_id()

    research_role = cfg.roles.get("research")
    deps = ResearchDeps(
        run_id=run_id_val,
        provider=(research_role.provider or "fake") if research_role else "fake",
        max_searches=cfg.research.max_searches,
        max_fetches=cfg.research.max_fetches,
        max_cost_usd=cfg.research.max_cost_usd,
        memory_backend=cfg.memory.backend,
        memory_base_url=cfg.memory.base_url,
        memory_bank=cfg.memory.project_bank,
        memory_watermark=memory_watermark,
    )
    research_spend = RoleUsage(role="research", model=resolved_model)

    try:
        findings = await _fan_out_research(cfg, idea, deps, research_spend, model=resolved_model)
        if all(f.failed for f in findings):
            brief = _degraded_research_brief(RuntimeError("every sub-question failed"))
        else:
            brief, synth_usage = await workflow.execute_activity(
                synthesize_brief,
                SynthesizeInput(
                    idea_json=idea.model_dump_json(),
                    findings=findings,
                    model=resolved_model,
                ),
                **RESEARCH_SYNTH_ACT,
            )
            await _fold_research_usage(cfg, synth_usage, research_spend)
    except Exception as exc:
        brief = _degraded_research_brief(exc)
        findings = []

    violations = await workflow.execute_activity(
        verify_brief_activity, args=[brief, run_id_val], **VERIFY_ACT
    )
    if violations:
        ctx.stage("research_failed", "research")
        err = "; ".join(f"{v.kind}: {v.source}: {v.quote[:80]!r}" for v in violations)
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="research",
                role="research",
                started=_r_started,
                ended=_now(),
                quality_score=None,
                judge="error",
                outcome=BenchmarkOutcome.FAIL,
                model=resolved_model,
                spend=research_spend,
                error=f"rejected:research.grounding: {err}",
            ),
        )
        return ResearchOutcome(**brief.model_dump(), digest="")

    brief_digest_val = brief_digest(brief)
    round_n = 1
    while True:
        gate = await ctx.gate("research", cfg.gate_settings(), round=round_n)
        if gate.outcome == GateOutcome.APPROVE:
            break
        if gate.outcome == GateOutcome.REJECT:
            return ResearchOutcome(**brief.model_dump(), digest="", rejection="rejected:research")
        # REVISE
        if not _should_refine(round_n, cfg.research):
            break
        gaps, conflicts = _refine_seed(brief)
        try:
            findings += await _fan_out_research(
                cfg,
                idea,
                deps,
                research_spend,
                id_offset=len(findings),
                guidance=gate.guidance or "",
                gaps=gaps,
                contradictions=conflicts,
                model=resolved_model,
            )
            brief, synth_usage = await workflow.execute_activity(
                synthesize_brief,
                SynthesizeInput(
                    idea_json=idea.model_dump_json(),
                    findings=findings,
                    model=resolved_model,
                ),
                **RESEARCH_SYNTH_ACT,
            )
            await _fold_research_usage(cfg, synth_usage, research_spend)
        except Exception:
            break
        violations = await workflow.execute_activity(
            verify_brief_activity,
            args=[brief, run_id_val],
            **VERIFY_ACT,
        )
        if violations:
            ctx.stage("research_failed", "research")
            brief_digest_val = ""
            break
        brief_digest_val = brief_digest(brief)
        round_n += 1

    if brief_digest_val:
        for item in verified_findings_to_retain(brief, run_id_val, bank=cfg.memory.project_bank):
            await ctx.retain(cfg, item.kind, item.bank, item.text, item.metadata)
        _r_quality = await ctx.judge(
            cfg,
            brief.model_dump_json(),
            "research",
            author_model=resolved_model,
        )
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="research",
                role="research",
                started=_r_started,
                ended=_now(),
                quality_score=_r_quality.score,
                judge=_r_quality.judge,
                outcome=BenchmarkOutcome.PASS,
                model=resolved_model,
                spend=research_spend,
            ),
        )
    else:
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="research",
                role="research",
                started=_r_started,
                ended=_now(),
                quality_score=None,
                judge="error",
                outcome=BenchmarkOutcome.FAIL,
                model=resolved_model,
                spend=research_spend,
                error="rejected:research.grounding (refine)",
            ),
        )

    return ResearchOutcome(**brief.model_dump(), digest=brief_digest_val)
