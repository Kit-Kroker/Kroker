"""E-33: RoleUsage accumulation semantics + RunSummary/config fields."""

from datetime import UTC

from sdlc.core.models import (
    PipelineConfig,
    RoleUsage,
    RunSummary,
)
from sdlc.observability.usage import merge_usage


def test_role_usage_defaults():
    u = RoleUsage(role="architect", model="anthropic:claude-opus-4-8")
    assert u.calls == 0
    assert u.input_tokens == 0
    assert u.cost_usd is None  # None = no priced call yet


def test_merge_usage_accumulates_tokens_and_calls():
    u = RoleUsage(role="qa", model="m1")
    merge_usage(u, model="m1", input_tokens=100, output_tokens=10)
    merge_usage(
        u, model="m2", input_tokens=50, output_tokens=5, cache_read_tokens=7, cache_write_tokens=3
    )
    assert u.calls == 2
    assert u.input_tokens == 150
    assert u.output_tokens == 15
    assert u.cache_read_tokens == 7
    assert u.cache_write_tokens == 3
    assert u.model == "m2"  # last model seen wins
    assert u.cost_usd is None  # no priced call → stays None


def test_merge_usage_prices_sum_and_none_never_zeroes():
    u = RoleUsage(role="dev", model="m")
    merge_usage(u, model="m", cost_usd=0.5)
    merge_usage(u, model="m", cost_usd=None)  # unpriced call
    merge_usage(u, model="m", cost_usd=0.25)
    assert u.cost_usd == 0.75


def test_pipeline_config_budget_defaults_off():
    assert PipelineConfig().run_budget_usd == 0.0


def test_run_summary_carries_roles_and_budget():
    from datetime import datetime

    now = datetime.now(UTC)
    s = RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:ok",
        terminal_stage="deploy",
        started_at=now,
        ended_at=now,
        duration_s=0.0,
    )
    assert s.roles == []
    assert s.budget_usd is None
    assert s.budget_crossings == 0


def test_cost_bag_from_spend():
    from sdlc.observability.usage import cost_bag_from_spend

    u = RoleUsage(
        role="clarify", model="m", calls=1, input_tokens=100, output_tokens=10, cost_usd=0.5
    )
    bag = cost_bag_from_spend(u)
    assert bag.usd == 0.5
    assert bag.input_tokens == 100
    assert bag.output_tokens == 10


def test_cost_bag_explicit_usd_wins_and_none_spend_degrades():
    from sdlc.observability.usage import cost_bag_from_spend

    u = RoleUsage(role="dev", model="m", input_tokens=100)
    assert cost_bag_from_spend(u, cost_usd=2.0).usd == 2.0  # harness $ wins
    empty = cost_bag_from_spend(None, cost_usd=None)
    assert empty.usd is None and empty.input_tokens is None
    zero = cost_bag_from_spend(RoleUsage(role="x", model="m"))
    assert zero.input_tokens is None  # cache-hit cell: zeros → None


def test_add_spend_adds_counts_and_dollars_but_never_model_or_calls():
    from sdlc.observability.usage import add_spend

    u = RoleUsage(
        role="architect",
        model="architect-model",
        calls=2,
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=5,
        cache_write_tokens=1,
        cost_usd=0.25,
    )
    add_spend(
        u,
        input_tokens=11,
        output_tokens=2,
        cache_read_tokens=3,
        cache_write_tokens=4,
        cost_usd=0.75,
    )
    assert (u.input_tokens, u.output_tokens) == (111, 12)
    assert (u.cache_read_tokens, u.cache_write_tokens) == (8, 5)
    assert u.cost_usd == 1.0
    assert u.calls == 2, "add_spend folds into an existing bag, it records no call"
    assert u.model == "architect-model", "the bag keeps the caller's model label"


def test_add_spend_with_a_none_cost_leaves_the_bag_cost_untouched():
    from sdlc.observability.usage import add_spend

    priced = RoleUsage(role="dev", model="m", cost_usd=0.25)
    add_spend(
        priced,
        input_tokens=1,
        output_tokens=1,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=None,
    )
    assert priced.cost_usd == 0.25  # an unpriced fold never zeroes the sum

    unpriced = RoleUsage(role="dev", model="m")
    add_spend(
        unpriced,
        input_tokens=1,
        output_tokens=1,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=None,
    )
    assert unpriced.cost_usd is None


def test_add_spend_adds_dollars_even_when_the_counts_are_zero():
    # Dollars ride cost_usd alone, never the counts (contrast from_run_usage,
    # whose None-on-zero rule is about reports, not bag folds).
    from sdlc.observability.usage import add_spend

    u = RoleUsage(role="architect", model="m")
    add_spend(
        u,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.5,
    )
    assert u.cost_usd == 0.5
    assert (u.input_tokens, u.output_tokens) == (0, 0)
    assert u.calls == 0
