"""Second research entry point (spec §8): the architect consults research
mid-run via a tool, drawing down the SAME per-run budget as the stage would.
One core (the research agent), two callers (the stage and this tool).

Since architect-research-surface (plan D2) the tool path also bounds its
inner run with the deps' request limit, degrades BOTH a budget stop and a
request-limit stop to a gap-only brief with a clean text of its own, and
returns the inner run's usage beside the brief as ToolReturn metadata — a
channel the architect model never sees (spike E1/E2; the workflow-side
harvest lives in workflows/role_host.py)."""

from __future__ import annotations

from typing import cast

from pydantic_ai import RunUsage, ToolReturn, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

from ...observability.sub_run_usage import SubRunUsage, from_run_usage, metadata_for
from .deps import BudgetExceeded, ResearchDeps
from .models import (
    Gap,
    ResearchBrief,
)


def _gap_brief(question: str, *, why_it_matters: str, summary: str) -> ResearchBrief:
    """The one gap-only degrade body both stop paths share."""
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id="architect-midrun",
                what_is_missing=question,
                why_it_matters=why_it_matters,
            )
        ],
        summary=summary,
    )


async def research_subquery_reported(
    deps: ResearchDeps, question: str
) -> tuple[ResearchBrief, SubRunUsage | None]:
    """Run the research agent on one sub-question, bounded by the deps'
    request limit, and return `(brief, report)`: the brief the architect
    consumes plus the inner run's usage report (None when the inner run made
    no chargeable request — a refused call stays silent).

    Imported lazily by callers so architect/agent.py stays importable without
    constructing the research agent at its own import time.

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
    prompt before any Temporal retry is spent. Caught here instead, matching
    ResearchConfig's documented contract: exceeding a bound degrades to a
    brief with the shortfall recorded in `gaps`, never a crash. A
    UsageLimitExceeded from the inner run's request limit (N3) degrades the
    same way, with OUR text — never `str(exc)`, which carries the library's
    advice and documentation URL into the architect's context (AM2/R9). Both
    degrades still report the spend made so far; any other exception
    propagates (residual R1)."""
    from sdlc.agents.roles import REGISTRY, t_research

    if t_research is None:
        raise RuntimeError(
            "research agent is not available (agents/research/ "
            "missing) — cannot service an architect research call"
        )
    run_usage = RunUsage()
    usage_limits = UsageLimits(request_limit=deps.max_requests)
    # 004 T033 (D7/FR-001 path c): under a research override the deps carry
    # it; forward it so the model that answers is the override. Without an
    # override the call is made exactly as before, bar the two new kwargs.
    try:
        if deps.research_model is not None:
            result = await t_research.run(
                question,
                deps=deps,
                model=deps.research_model,
                usage_limits=usage_limits,
                usage=run_usage,
            )
        else:
            result = await t_research.run(
                question, deps=deps, usage_limits=usage_limits, usage=run_usage
            )
        brief = cast(ResearchBrief, result.output)
    except BudgetExceeded as exc:
        brief = _gap_brief(
            question,
            why_it_matters=str(exc),
            summary=(
                f"Research budget exhausted before this sub-question could be answered: {exc}"
            ),
        )
    except UsageLimitExceeded:
        reason = f"request limit exhausted ({deps.max_requests} requests)"
        brief = _gap_brief(
            question,
            why_it_matters=reason,
            summary=f"Research stopped before this sub-question could be answered: {reason}",
        )
    # The answering model id: the override when set, else the registry's
    # research model, else the sentinel that prices to no dollars (R3).
    model = deps.research_model or REGISTRY["research"].model or "unknown"
    return brief, from_run_usage(run_usage, model)


async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief:
    """Run the research agent on one sub-question with a shared budget and
    return only the brief. Only tests call this now: the architect's tool
    calls `research_subquery_reported` and returns `tool_return(brief,
    report)` so the inner run's usage rides the tool-return metadata. The
    durability and degrade notes for this path live on
    `research_subquery_reported`."""
    brief, _report = await research_subquery_reported(deps, question)
    return brief


def tool_return(brief: ResearchBrief, report: SubRunUsage | None) -> ResearchBrief | ToolReturn:
    """Pure: the bare brief when there is nothing to report (exactly today's
    code path), else the brief with the report beside it as ToolReturn
    metadata — accepted from a tool annotated `-> ResearchBrief` and never
    serialized to the model (FR-001)."""
    if report is None:
        return brief
    return ToolReturn(return_value=brief, metadata=metadata_for(report))
