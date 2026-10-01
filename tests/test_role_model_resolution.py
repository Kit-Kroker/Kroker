from sdlc.agents.roles import resolve_role_model
from sdlc.core.models import (
    PipelineConfig,
    RoleConfig,
)
from sdlc.memoization.cache import content_key


def test_resolver_falls_back_to_registry_default():
    cfg = PipelineConfig()  # no proposer overrides
    # architect stage default comes from STAGE_MODELS (registry)
    from sdlc.agents.roles import STAGE_MODELS

    assert resolve_role_model(cfg, "architect") == STAGE_MODELS["architect"]


def test_resolver_prefers_per_run_override():
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(kind="proposer", model="openai:gpt-5.2")
    assert resolve_role_model(cfg, "architect") == "openai:gpt-5.2"


def test_resolver_maps_stage_to_role_name():
    # stage 'plan' resolves through role 'planner'
    cfg = PipelineConfig()
    cfg.roles["planner"] = RoleConfig(kind="proposer", model="openai:gpt-5.2")
    assert resolve_role_model(cfg, "plan") == "openai:gpt-5.2"


def test_memo_key_moves_with_per_role_model():
    base = PipelineConfig()
    override = PipelineConfig()
    override.roles["architect"] = RoleConfig(kind="proposer", model="openai:gpt-5.2")
    k_base = content_key("architect", "{}", "sha", resolve_role_model(base, "architect"), "none")
    k_over = content_key(
        "architect", "{}", "sha", resolve_role_model(override, "architect"), "none"
    )
    assert k_base != k_over


import re
from pathlib import Path


def test_no_raw_stage_models_lookup_in_feature_workflow():
    """Every proposer model reference must go through resolve_role_model so
    per-run overrides and the memo key stay consistent. The only allowed raw
    STAGE_MODELS[...] is inside resolve_role_model itself."""
    src = Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    # strip the resolver body (the one legitimate raw lookup)
    src_wo_resolver = re.sub(
        r"def resolve_role_model.*?return STAGE_MODELS\[stage\]", "", src, flags=re.DOTALL
    )
    assert "STAGE_MODELS[" not in src_wo_resolver


# --- 004 T027: the memo key under a forwarding override (FR-003, E3) ---

import inspect

import pytest
from pydantic import BaseModel

from sdlc.agents.roles import PROMPT_SHAS, STAGE_MODELS
from sdlc.workflows import role_host


class _Out(BaseModel):
    text: str = "ok"


async def _recorded_put_key(cfg: PipelineConfig, monkeypatch) -> str:
    """Run one memoized stage and return the key its cache_put wrote. The
    memo activities are stubbed at the workflow boundary so the key
    _cached_stage computes is observable without a workflow environment."""
    puts: list[str] = []

    async def fake_execute_activity(activity, arg=None, **kwargs):
        if activity is role_host.cache_get:
            return None  # always a miss — we want the put
        if activity is role_host.cache_put:
            puts.append(arg.key)
            return None
        raise AssertionError(f"unexpected activity {activity!r}")

    monkeypatch.setattr(role_host.workflow, "execute_activity", fake_execute_activity)
    host = role_host.RoleHost()

    async def run_fn() -> _Out:
        return _Out()

    await host._cached_stage(cfg, "architect", '{"idea": "x"}', _Out, run_fn)
    assert len(puts) == 1, "a miss must run the stage and put exactly once"
    return puts[0]


@pytest.mark.asyncio
async def test_override_memo_key_carries_the_forwarded_salt(monkeypatch):
    """D6/E3: a memo entry written pre-fix under an override key (raw model
    string in the slot) was produced by the REGISTRY model — it must never
    be served as the override's output. RED on main: the key written is the
    raw pre-fix key."""
    override = PipelineConfig(memoization_enabled=True)
    override.roles["architect"] = RoleConfig(kind="proposer", model="openai:gpt-5.2")
    key = await _recorded_put_key(override, monkeypatch)

    raw = content_key(
        "architect", '{"idea": "x"}', PROMPT_SHAS["architect"], "openai:gpt-5.2", "none"
    )
    salted = content_key(
        "architect", '{"idea": "x"}', PROMPT_SHAS["architect"], "fwd1:openai:gpt-5.2", "none"
    )
    assert key != raw, "the pre-fix override key (raw model string) must not be written"
    assert key == salted


@pytest.mark.asyncio
async def test_no_override_memo_key_is_byte_identical_to_today(monkeypatch):
    cfg = PipelineConfig(memoization_enabled=True)
    key = await _recorded_put_key(cfg, monkeypatch)
    assert key == content_key(
        "architect", '{"idea": "x"}', PROMPT_SHAS["architect"], STAGE_MODELS["architect"], "none"
    )


def test_content_key_still_takes_five_positional_arguments():
    params = list(inspect.signature(content_key).parameters.values())
    assert len(params) == 5
    assert all(
        p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in params
    )
