"""E-33: RoleUsage accumulation semantics + RunSummary/config fields."""
from sdlc.models import PipelineConfig, RoleUsage, RunSummary
from sdlc.observability.usage import merge_usage


def test_role_usage_defaults():
    u = RoleUsage(role="architect", model="anthropic:claude-opus-4-8")
    assert u.calls == 0
    assert u.input_tokens == 0
    assert u.cost_usd is None       # None = no priced call yet


def test_merge_usage_accumulates_tokens_and_calls():
    u = RoleUsage(role="qa", model="m1")
    merge_usage(u, model="m1", input_tokens=100, output_tokens=10)
    merge_usage(u, model="m2", input_tokens=50, output_tokens=5,
                cache_read_tokens=7, cache_write_tokens=3)
    assert u.calls == 2
    assert u.input_tokens == 150
    assert u.output_tokens == 15
    assert u.cache_read_tokens == 7
    assert u.cache_write_tokens == 3
    assert u.model == "m2"          # last model seen wins
    assert u.cost_usd is None       # no priced call → stays None


def test_merge_usage_prices_sum_and_none_never_zeroes():
    u = RoleUsage(role="dev", model="m")
    merge_usage(u, model="m", cost_usd=0.5)
    merge_usage(u, model="m", cost_usd=None)   # unpriced call
    merge_usage(u, model="m", cost_usd=0.25)
    assert u.cost_usd == 0.75


def test_pipeline_config_budget_defaults_off():
    assert PipelineConfig().run_budget_usd == 0.0


def test_run_summary_carries_roles_and_budget():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    s = RunSummary(run_id="r1", mode="greenfield", outcome="deployed:ok",
                   terminal_stage="deploy", started_at=now, ended_at=now,
                   duration_s=0.0)
    assert s.roles == []
    assert s.budget_usd is None
    assert s.budget_crossings == 0
