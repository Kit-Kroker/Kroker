"""Runtime deps for the research agent's tools. Serializable (crosses the
Temporal activity boundary via pydantic_data_converter), so it carries CONFIG
and COUNTERS — never a live provider handle or a filesystem path.

The `budget` counter is a mutable pydantic model on `ResearchDeps`. It
accumulates correctly when tools are called directly (unit tests) or within a
single non-temporal `agent.run()` (the same deps instance is threaded through
every `ctx.deps`). Under `TemporalAgent` (Task 8 wires this), each tool call is
a SEPARATE activity that receives its own deserialized copy of `deps`, so
mutations do NOT flow back to the workflow. Per-run budget enforcement under
TemporalAgent is a Task 8 concern (likely a disk-persisted counter at
runs/<run_id>/research/budget.json), NOT a Task 6 concern.

(Task 1 spike finding B + the 2026-07-17 human-authorised fallback: CodeMode
was the original mechanism for keeping this counter in-process across the
fan-out; CodeMode is untestable via TestModel under TemporalAgent and has been
dropped in favour of plain sequential tools. See task-6-brief-amended.md.)"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Per-call cost estimates (spec §3). The fake provider is free; these bound a
# real Tavily run. Kept as constants, not config, so the budget math is auditable.
SEARCH_COST_USD = 0.01
FETCH_COST_USD = 0.02


class BudgetExceeded(Exception):
    """A stage-scoped bound was hit. Surfaces to the model as an ordinary error;
    the agent concludes with what it has and records the shortfall in gaps."""


class Budget(BaseModel):
    searches: int = 0
    fetches: int = 0
    cost_usd: float = 0.0


class ResearchDeps(BaseModel):
    run_id: str
    provider: Literal["tavily", "fake"]
    max_searches: int
    max_fetches: int
    max_cost_usd: float
    memory_backend: str = "fake"
    memory_base_url: str = "http://localhost:8888"
    memory_bank: str = "project:default"
    memory_watermark: str | None = None
    scope: str = "run"
    """Which persisted budget counter this call charges. The fan-out sets it
    to "sq-<id>" so one sub-question's spending cannot drain its siblings'
    allowance; "run" is the shared whole-run counter."""

    max_run_cost_usd: float = 4.0
    """The whole-run ceiling, charged alongside `scope` on every call. Carried
    on deps because the toolset charges activity-side and has no other route
    to the config."""
    budget: Budget = Field(default_factory=Budget)


def charge(deps: ResearchDeps, *, search: int = 0, fetch: int = 0) -> None:
    """Enforce the bounds BEFORE the work, then account for it. Raises
    BudgetExceeded if a cap (count or cost) would be crossed."""
    b = deps.budget
    if search and b.searches + search > deps.max_searches:
        raise BudgetExceeded(
            f"search budget exhausted ({deps.max_searches} searches)")
    if fetch and b.fetches + fetch > deps.max_fetches:
        raise BudgetExceeded(
            f"fetch budget exhausted ({deps.max_fetches} fetches)")
    projected = b.cost_usd + search * SEARCH_COST_USD + fetch * FETCH_COST_USD
    if projected > deps.max_cost_usd:
        raise BudgetExceeded(
            f"cost budget exhausted (${deps.max_cost_usd:.2f})")
    b.searches += search
    b.fetches += fetch
    b.cost_usd = projected
