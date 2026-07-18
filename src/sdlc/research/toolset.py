"""Second research entry point (spec §8): the architect consults research
mid-run via a tool, drawing down the SAME per-run budget as the stage would.
One core (the research agent), two callers (the stage and this tool)."""
from __future__ import annotations

from ..models import ResearchBrief
from .deps import ResearchDeps


async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief:
    """Run the research agent on one sub-question with a shared budget. Imported
    lazily so architect/agent.py stays importable without constructing the
    research agent at its own import time.

    NOTE (accepted loss, 2026-07-17 human decision, mirrors Task 8's feature.py
    comment): `deps.budget` accumulates correctly for direct/test invocation
    and within a single non-temporal `agent.run()`, but under `TemporalAgent`
    each tool activity receives a fresh deserialized copy, so the shared-counter
    guarantee is advisory-only when the architect runs temporalized. Restoring
    real per-run enforcement needs a disk-persisted counter (deferred)."""
    from sdlc.agents.roles import t_research
    if t_research is None:
        raise RuntimeError("research agent is not available (agents/research/ "
                           "missing) — cannot service an architect research call")
    return (await t_research.run(question, deps=deps)).output
