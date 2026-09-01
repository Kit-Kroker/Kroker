"""Pure RoleUsage accumulation (E-33). No I/O, no temporalio: shared by the
workflow's in-state accumulator and the retro-stage trace rollup, and unit-
testable outside the workflow sandbox."""

from __future__ import annotations

from ..models import RoleUsage


def merge_usage(
    bag: RoleUsage,
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float | None = None,
) -> None:
    """Fold one model call into a role's bag. cost_usd=None (unpriced call)
    leaves bag.cost_usd untouched — never zeroes an existing sum."""
    bag.model = model or bag.model
    bag.calls += 1
    bag.input_tokens += input_tokens
    bag.output_tokens += output_tokens
    bag.cache_read_tokens += cache_read_tokens
    bag.cache_write_tokens += cache_write_tokens
    if cost_usd is not None:
        bag.cost_usd = (bag.cost_usd or 0.0) + cost_usd


def cost_bag_from_spend(spend: RoleUsage | None, cost_usd: float | None = None):
    """CostBag for a stage's BenchmarkRecord (E-33, spec §2). Explicit
    cost_usd (harness-reported dollars) wins over the spend's priced sum.
    A zero-token spend (memoization cache hit — the closure never ran)
    degrades to None fields, matching pre-E-33 records."""
    from ..benchmarks.models import CostBag

    if spend is None:
        return CostBag(usd=cost_usd)
    return CostBag(
        usd=cost_usd if cost_usd is not None else spend.cost_usd,
        input_tokens=spend.input_tokens or None,
        output_tokens=spend.output_tokens or None,
    )
