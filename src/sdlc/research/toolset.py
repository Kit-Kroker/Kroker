"""Second research entry point (spec §8): the architect consults research
mid-run via a tool, drawing down the SAME per-run budget as the stage would.
One core (the research agent), two callers (the stage and this tool)."""
from __future__ import annotations

from ..models import Gap, ResearchBrief
from .deps import BudgetExceeded, ResearchDeps


async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief:
    """Run the research agent on one sub-question with a shared budget. Imported
    lazily so architect/agent.py stays importable without constructing the
    research agent at its own import time.

    NOTE (accepted loss, 2026-07-17 human decision, mirrors Task 8's feature.py
    comment): `deps.budget` accumulates correctly for direct/test invocation
    and within a single non-temporal `agent.run()`, but under `TemporalAgent`
    each tool activity receives a fresh deserialized copy, so the shared-counter
    guarantee is advisory-only when the architect runs temporalized. Restoring
    real per-run enforcement needs a disk-persisted counter (deferred).

    Unlike the top-level research stage, this call runs INSIDE the architect's
    own tool-call activity, not workflow code — pydantic_ai's TemporalAgent
    cannot fan the inner agent's tool calls out as further activities from
    there, so it falls back to plain in-process execution and `deps.budget`
    genuinely accumulates and can genuinely raise BudgetExceeded mid-run.
    A raised BudgetExceeded is a plain Exception, so left uncaught it escapes
    this activity's Temporal boundary as an ApplicationFailure that retries
    with no cap (same failure class as the read_repo fix in
    tests/test_research_tools.py — an uncapped Temporal retry storm on a
    deterministic-ish LLM tool-call pattern). Caught here instead, matching
    ResearchConfig's documented contract: exceeding a bound degrades to a
    brief with the shortfall recorded in `gaps`, never a crash."""
    from sdlc.agents.roles import t_research
    if t_research is None:
        raise RuntimeError("research agent is not available (agents/research/ "
                           "missing) — cannot service an architect research call")
    try:
        return (await t_research.run(question, deps=deps)).output
    except BudgetExceeded as exc:
        return ResearchBrief(
            gaps=[Gap(sub_question_id="architect-midrun",
                      what_is_missing=question,
                      why_it_matters=str(exc))],
            summary=f"Research budget exhausted before this sub-question "
                    f"could be answered: {exc}")
