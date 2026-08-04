"""The research fan-out activities: plan -> N sub-questions -> synthesize.

Every model call in the research stage happens HERE, activity-side, which is
why each return type carries a RoleUsage: fan-out moves the call out of
_run_role's reach, and an activity that calls a model must hand its usage back
or the spend is silently lost (E-33 amendment, fan-out design §7).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from temporalio import activity

from ..models import (Contradiction, Gap, ResearchPlan, RoleUsage,
                      SubQuestion)
from .prompts import PLAN_SYSTEM


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
        role="research", model=model, calls=1,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_tokens or 0,
        cache_write_tokens=u.cache_write_tokens or 0,
        cost_usd=None)


def _plan_prompt(inp: PlanInput) -> str:
    parts = [
        f"Research question / feature idea:\n\n{inp.idea_json}\n",
        f"\nBreak this into at most {inp.max_sub_questions} independent "
        "sub-questions that can be investigated in parallel.\n",
    ]
    if inp.guidance:
        parts.append(f"\nFocus specifically on: {inp.guidance}\n")
    if inp.gaps:
        parts.append("\nA previous round left these questions unanswered — "
                     "target them:\n")
        parts.extend(f"- {g.what_is_missing} ({g.why_it_matters})\n"
                     for g in inp.gaps)
    if inp.contradictions:
        parts.append("\nA previous round found these unresolved conflicts — "
                     "target them:\n")
        parts.extend(f"- {c.topic}: {' vs '.join(c.positions)}\n"
                     for c in inp.contradictions
                     if c.unresolved)
    return "".join(parts)


@activity.defn
async def plan_research(inp: PlanInput, _model=None) -> ResearchPlan:
    """Decompose the idea into independent sub-questions.

    `_model` is a test seam only: production passes None and the activity
    builds an agent on inp.model.

    The slice to max_sub_questions is NOT a formality. Measured behaviour is
    that planners return the top of whatever range they are given, even for a
    yes/no lookup -- so the config value, not the question, decides the width.
    """
    agent = Agent(_model or inp.model, output_type=_PlannerOutput,
                  system_prompt=PLAN_SYSTEM)
    result = await agent.run(_plan_prompt(inp))
    texts = [t.strip() for t in result.output.sub_questions if t and t.strip()]
    texts = texts[:inp.max_sub_questions]

    if not texts:
        # Degrade to exactly today's behaviour: one investigation covering the
        # whole idea. A fan-out failure is never worse than the status quo.
        texts = [inp.idea_json]

    activity.logger.info("planned %d sub-questions", len(texts))
    return ResearchPlan(
        sub_questions=[SubQuestion(id=f"sq-{inp.id_offset + i}", question=t)
                       for i, t in enumerate(texts)],
        usage=_usage_of(result, inp.model))
