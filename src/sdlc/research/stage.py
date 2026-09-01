"""The research fan-out activities: plan -> N sub-questions -> synthesize.

Every model call in the research stage happens HERE, activity-side, which is
why each return type carries a RoleUsage: fan-out moves the call out of
_run_role's reach, and an activity that calls a model must hand its usage back
or the spend is silently lost (E-33 amendment, fan-out design §7).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits
from temporalio import activity

from ..models import (
    Contradiction,
    Gap,
    ResearchBrief,
    ResearchPlan,
    RoleUsage,
    SubQuestion,
    SubQuestionFinding,
)
from .deps import BudgetExceeded, ResearchDeps
from .merge import merge_briefs
from .prompts import PLAN_SYSTEM, SYNTHESIS_SYSTEM, sub_question_prompt


class _PlannerOutput(BaseModel):
    """Structured-output shape for the planner. A flat list of strings: ids
    are assigned by us, not the model, so they stay stable and offsettable."""

    sub_questions: list[str] = Field(default_factory=list)


class PlanInput(BaseModel):
    """Serves BOTH the first plan and a refine replan. A replan is just a plan
    with a seed: the human's guidance plus the machine-readable gaps and
    contradictions round one could not resolve."""

    idea_json: str
    max_sub_questions: int
    model: str
    id_offset: int = 0
    guidance: str = ""
    gaps: list[Gap] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)


def _usage_of(result, model: str) -> RoleUsage:
    """One pydantic-ai run's usage as a RoleUsage. cost_usd stays None: dollars
    are a lookup the WORKFLOW performs via the price_usage activity, because
    pricing must stay replay-safe and must never fail a stage."""
    u = result.usage
    return RoleUsage(
        role="research",
        model=model,
        calls=1,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_tokens or 0,
        cache_write_tokens=u.cache_write_tokens or 0,
        cost_usd=None,
    )


def _plan_prompt(inp: PlanInput) -> str:
    parts = [
        f"Research question / feature idea:\n\n{inp.idea_json}\n",
        f"\nBreak this into at most {inp.max_sub_questions} independent "
        "sub-questions that can be investigated in parallel.\n",
    ]
    if inp.guidance:
        parts.append(f"\nFocus specifically on: {inp.guidance}\n")
    if inp.gaps:
        parts.append("\nA previous round left these questions unanswered — target them:\n")
        parts.extend(f"- {g.what_is_missing} ({g.why_it_matters})\n" for g in inp.gaps)
    if inp.contradictions:
        parts.append("\nA previous round found these unresolved conflicts — target them:\n")
        parts.extend(
            f"- {c.topic}: {' vs '.join(c.positions)}\n" for c in inp.contradictions if c.unresolved
        )
    return "".join(parts)


async def _plan_research_impl(inp: PlanInput, _model=None) -> ResearchPlan:
    """Decompose the idea into independent sub-questions.

    `_model` is a test seam only: production passes None and the activity
    builds an agent on inp.model.

    The slice to max_sub_questions is NOT a formality. Measured behaviour is
    that planners return the top of whatever range they are given, even for a
    yes/no lookup -- so the config value, not the question, decides the width.
    """
    agent = Agent(_model or inp.model, output_type=_PlannerOutput, system_prompt=PLAN_SYSTEM)
    result = await agent.run(_plan_prompt(inp))
    texts = [t.strip() for t in result.output.sub_questions if t and t.strip()]
    texts = texts[: inp.max_sub_questions]

    if not texts:
        # Degrade to exactly today's behaviour: one investigation covering the
        # whole idea. A fan-out failure is never worse than the status quo.
        texts = [inp.idea_json]

    activity.logger.info("planned %d sub-questions", len(texts))
    return ResearchPlan(
        sub_questions=[
            SubQuestion(id=f"sq-{inp.id_offset + i}", question=t) for i, t in enumerate(texts)
        ],
        usage=_usage_of(result, inp.model),
    )


@activity.defn(name="plan_research")
async def plan_research(inp: PlanInput) -> ResearchPlan:
    """Thin activity wrapper around `_plan_research_impl`.

    Temporal derives an activity's arg type hints from its FULL signature,
    then discards ALL of them the moment the payload count sent by the
    caller doesn't match that signature's param count (see
    `_type_hints_from_func` / `worker/_activity.py`'s "only use arg type
    hints if they match the input count"). `_plan_research_impl`'s `_model`
    seam is never passed by `workflow.execute_activity` (only `inp` is), so
    keeping `_model` on the `@activity.defn` function itself silently turned
    off type hints on every real call -- `inp` decoded as a plain dict
    instead of `PlanInput`, crashing on `inp.model`. Splitting the seam out
    into an undecorated impl (called directly by tests, bypassing Temporal
    serialization) keeps the registered activity's signature exactly what
    real callers send.
    """
    return await _plan_research_impl(inp)


# Comfortably below the workflow's heartbeat_timeout (see feature.py's
# RESEARCH_SQ_ACT). The invariant to preserve is:
#   HEARTBEAT_INTERVAL_SECONDS < heartbeat_timeout < start_to_close
HEARTBEAT_INTERVAL_SECONDS = 15.0


class SubQuestionInput(BaseModel):
    sub_question: SubQuestion
    deps: ResearchDeps
    model: str
    max_requests: int
    max_run_cost_usd: float


@contextlib.asynccontextmanager
async def _heartbeating(interval: float | None = None):
    """Heartbeat on a TIMER for as long as the block runs.

    A sub-question legitimately runs for minutes, and the server cannot tell
    "still thinking" from "instance went away". Heartbeating on a timer
    decouples liveness from call duration, so a lost worker is detected in
    ~60s instead of at start_to_close.

    The interval resolves from the module global at CALL time, not as a
    default argument -- otherwise tests cannot shorten it, and an untestable
    heartbeat is one you discover never fired in production."""
    interval = HEARTBEAT_INTERVAL_SECONDS if interval is None else interval

    async def tick() -> None:
        while True:
            await asyncio.sleep(interval)
            activity.heartbeat()

    task = asyncio.create_task(tick())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _degraded(sub: SubQuestion, exc: Exception) -> ResearchBrief:
    """A bound was hit. Conclude with what we have and record the shortfall as
    a gap -- ResearchConfig's documented contract. Never grounded, so
    verify_brief passes it through the ordinary success path."""
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id=sub.id,
                what_is_missing=sub.question,
                why_it_matters=f"research stopped early: {exc}",
            )
        ],
        summary=f"Research stopped early: {exc}",
    )


async def _research_subquestion_impl(
    inp: SubQuestionInput, _model=None, _agent=None
) -> SubQuestionFinding:
    """Research ONE sub-question. The fan-out unit.

    Runs the PLAIN research_agent, not the TemporalAgent: inside an activity
    pydantic-ai falls back to in-process execution, so deps.budget accumulates
    for real within the run while budget_store enforces the persisted caps
    underneath (the pattern research/toolset.py already established for the
    architect's mid-run call).

    `_model` / `_agent` are test seams; production passes neither.
    """
    sub = inp.sub_question
    if _agent is None:
        from sdlc.agents.roles import research_agent

        if research_agent is None:
            raise RuntimeError("research agent is not available (agents/research/ missing)")
        agent = research_agent
    else:
        agent = _agent

    # Each sub-question charges its OWN scope so one cannot drain the run.
    deps = inp.deps.model_copy(
        update={
            "budget": inp.deps.budget.model_copy(),
            "scope": sub.id,
            "max_run_cost_usd": inp.max_run_cost_usd,
        }
    )

    usage = RoleUsage(role="research", model=inp.model)
    try:
        async with _heartbeating():
            usage_limits = UsageLimits(request_limit=inp.max_requests)
            if _model is not None:
                result = await agent.run(
                    sub_question_prompt(sub.question),
                    deps=deps,
                    usage_limits=usage_limits,
                    model=_model,
                )
            else:
                result = await agent.run(
                    sub_question_prompt(sub.question),
                    deps=deps,
                    usage_limits=usage_limits,
                )
    except (BudgetExceeded, UsageLimitExceeded) as exc:
        # Expected exhaustion: degrade. NEVER re-raise -- the counter is
        # persisted, so a retry hits the same exhausted cap and burns six
        # attempts with backoff for a guaranteed failure.
        activity.logger.info("sub-question %s degraded: %s", sub.id, exc)
        return SubQuestionFinding(sub_question=sub, brief=_degraded(sub, exc), usage=usage)
    except asyncio.CancelledError:
        # Graceful shutdown cancels in-flight activities. Heartbeat on the way
        # out so the server learns immediately rather than waiting out
        # start_to_close before rescheduling.
        activity.heartbeat()
        activity.logger.warning("sub-question %s cancelled mid-flight", sub.id)
        raise

    # The research agent's output_type IS ResearchBrief; the generic run()
    # result is untyped, so state the contract here.
    return SubQuestionFinding(
        sub_question=sub,
        brief=cast(ResearchBrief, result.output),
        usage=_usage_of(result, inp.model),
    )


@activity.defn(name="research_subquestion")
async def research_subquestion(inp: SubQuestionInput) -> SubQuestionFinding:
    """Thin activity wrapper -- see `plan_research`'s wrapper docstring for
    why the `_model`/`_agent` test seams cannot live on the registered
    activity's own signature."""
    return await _research_subquestion_impl(inp)


class _SynthesisOutput(BaseModel):
    """EXACTLY the three fields the model is allowed to write. Making this a
    closed type is the enforcement of "synthesis may not author grounded
    findings" -- there is simply nowhere for it to put one.

    Field constraints are enforced HERE, not on ResearchBrief: the brief is
    assembled via model_copy(update=...), which bypasses pydantic validation,
    so ResearchBrief.confidence's ge/le is inert on this path. Putting the
    bound on _SynthesisOutput catches an out-of-range value at the boundary
    where pydantic-ai validates the model's structured output."""

    summary: str = ""
    contradictions: list[Contradiction] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SynthesizeInput(BaseModel):
    idea_json: str
    findings: list[SubQuestionFinding]
    model: str


def _numbered_sources(brief: ResearchBrief) -> str:
    """The numbered source list, built BEFORE the model is prompted.

    Order matters and is the whole reason this is a separate function. Building
    the list after the call makes citation impossible: the model never saw the
    numbers, so it had none to cite. Built first and handed over, the numbers
    the model cites and the numbers the brief carries come from one object and
    cannot drift."""
    return "".join(
        f"[{n}] {s.title or s.url} — {s.url}\n"
        for n, s in enumerate(brief.sources_consulted, start=1)
    )


def _synthesis_prompt(inp: SynthesizeInput, merged: ResearchBrief) -> str:
    parts = [
        f"Original question / feature idea:\n\n{inp.idea_json}\n",
        "\nWhat the analysts found:\n",
    ]
    for f in inp.findings:
        parts.append(f"\n--- On: {f.sub_question.question}\n")
        if f.failed:
            parts.append(f"(this sub-question did not complete: {f.error})\n")
            continue
        parts.append(f"{f.brief.summary}\n")
        for g in f.brief.grounded_findings:
            parts.append(f"  * {g.claim} — {g.source_url}\n")
    sources = _numbered_sources(merged)
    if sources:
        parts.append("\nNumbered sources — cite ONLY these numbers:\n")
        parts.append(sources)
    return "".join(parts)


async def _synthesize_brief_impl(
    inp: SynthesizeInput, _model=None
) -> tuple[ResearchBrief, RoleUsage]:
    """Merge N partial briefs into one ResearchBrief.

    Structure comes from code (merge_briefs), prose from the model. The model
    is handed a closed output type with three fields, so it CANNOT author a
    grounded finding -- a fabricated quote would be caught by verify_brief, but
    only by turning an ordinary run into a fail-closed stage failure.

    Returns the brief AND its model spend. Fan-out moved the model call
    activity-side, out of _run_role's reach, so an activity that calls a model
    must hand its usage back or the spend is silently lost (E-33 amendment,
    spec §7) -- the same rule ResearchPlan and SubQuestionFinding exist to
    enforce. The empty-findings path makes no model call and returns a
    zero-spend RoleUsage.
    """
    merged = merge_briefs(inp.findings)
    if not inp.findings:
        return merged, RoleUsage(role="research", model=inp.model)

    agent = Agent(_model or inp.model, output_type=_SynthesisOutput, system_prompt=SYNTHESIS_SYSTEM)
    result = await agent.run(_synthesis_prompt(inp, merged))
    out = result.output

    return merged.model_copy(
        update={
            "summary": out.summary,
            # Within-sub-question conflicts (already in `merged`) PLUS the
            # cross-sub-question ones only visible now that independent
            # investigations sit side by side. The second kind is unreachable in a
            # single agent turn and is the depth payoff of fanning out.
            "contradictions": merged.contradictions + out.contradictions,
            "confidence": out.confidence,
        }
    ), _usage_of(result, inp.model)


@activity.defn(name="synthesize_brief")
async def synthesize_brief(inp: SynthesizeInput) -> tuple[ResearchBrief, RoleUsage]:
    """Thin activity wrapper -- see `plan_research`'s wrapper docstring for
    why the `_model` test seam cannot live on the registered activity's own
    signature."""
    return await _synthesize_brief_impl(inp)
