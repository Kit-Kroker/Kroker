"""Second research entry point (spec §8): the architect consults research
mid-run via a tool, drawing down the SAME per-run budget as the stage would.
One core (the research agent), two callers (the stage and this tool)."""

from __future__ import annotations

from typing import cast

from .deps import BudgetExceeded, ResearchDeps
from .models import (
    Gap,
    ResearchBrief,
)


async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief:
    """Run the research agent on one sub-question with a shared budget. Imported
    lazily so architect/agent.py stays importable without constructing the
    research agent at its own import time.

    NOTE (2026-07-17 human decision, wording updated): `deps.budget`
    accumulates correctly for direct/test invocation and within a single
    non-temporal `agent.run()`, but under durable execution each tool
    activity receives a fresh deserialized copy, so the in-memory counter
    alone cannot hold a cross-activity cap. It does not have to: the
    research tools charge `budget_store.py`'s disk-persisted counters
    (this call runs under `scope="architect"` plus the shared run
    ceiling), which is what actually enforces the budget here.

    Unlike the top-level research stage, this call runs INSIDE the architect's
    own tool-call activity, not workflow code — pydantic_ai's durable execution
    cannot fan the inner agent's tool calls out as further activities from
    there, so it falls back to plain in-process execution and `deps.budget`
    genuinely accumulates and can genuinely raise BudgetExceeded mid-run.
    A raised BudgetExceeded is a plain Exception, so left uncaught it escapes
    this activity's Temporal boundary as an ApplicationFailure and is retried
    — bounded, not uncapped: agent activities cap at 3 attempts (`roles.py`),
    and under CodeMode a tool-side timeout surfaces to the model as a retry
    prompt before any Temporal retry is spent (same failure class as the
    read_repo fix in tests/test_research_tools.py). Caught here instead,
    matching ResearchConfig's documented contract: exceeding a bound degrades
    to a brief with the shortfall recorded in `gaps`, never a crash."""
    from sdlc.agents.roles import t_research

    if t_research is None:
        raise RuntimeError(
            "research agent is not available (agents/research/ "
            "missing) — cannot service an architect research call"
        )
    try:
        # 004 T033 (D7/FR-001 path c): under a research override the deps
        # carry it; forward it so the model that answers is the override
        # (the string crosses the durable boundary as the model id). Without
        # an override the call is made exactly as before.
        if deps.research_model is not None:
            result = await t_research.run(question, deps=deps, model=deps.research_model)
        else:
            result = await t_research.run(question, deps=deps)
        return cast(ResearchBrief, result.output)
    except BudgetExceeded as exc:
        return ResearchBrief(
            gaps=[
                Gap(
                    sub_question_id="architect-midrun",
                    what_is_missing=question,
                    why_it_matters=str(exc),
                )
            ],
            summary=f"Research budget exhausted before this sub-question could be answered: {exc}",
        )
