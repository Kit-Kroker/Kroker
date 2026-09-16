"""E-74 §7.3: GraphWorkflow reproduces FeatureWorkflow's golden traces EXACTLY.

Stop-guard SG-3: any difference is a STOP. Never edit a golden file.
"""

from __future__ import annotations

import dataclasses

import pytest
from temporalio import activity

from sdlc.core.models import MemoryConfig
from sdlc.memoization.activities import CacheGetInput, CachePutInput
from tests.fakes.canned import e2e_config
from tests.replay.harness import FEATURE_STARTER, GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import GOLDEN_SCENARIOS, SCENARIOS, A, answer_clarify, decide, wait_for

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


@pytest.mark.asyncio
@pytest.mark.parametrize("sandboxed", [False, True], ids=["unsandboxed", "sandboxed"])
@pytest.mark.parametrize("scenario", GOLDEN_SCENARIOS, ids=[s.name for s in GOLDEN_SCENARIOS])
async def test_graph_workflow_reproduces_the_golden_trace(
    scenario, sandboxed, monkeypatch, tmp_path
):
    """Unsandboxed runs record the stage/gate trace (the recorder patches a class);
    sandboxed runs prove the same commands and close under the production sandbox."""
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=sandboxed)
    golden = load_golden(scenario.name)
    assert captured.golden["commands"] == golden["commands"], "SG-3: command projection differs"
    assert captured.golden["close"] == golden["close"], "SG-3: close differs"
    if not sandboxed:
        assert captured.golden["trace"] == golden["trace"], "SG-3: stage/gate trace differs"


@pytest.mark.asyncio
async def test_live_queries_on_a_sandboxed_graph_workflow(monkeypatch, tmp_path):
    observed: dict = {}

    async def drive(handle, env):
        await answer_clarify(handle)
        await wait_for(handle, "awaiting:architecture")
        observed["state"] = await handle.query("run_state")
        observed["pending"] = await handle.query("pending_decisions")
        for gate in ("architecture", "plan", "deploy"):
            await decide(handle, gate, 1, A)

    scenario = dataclasses.replace(GREENFIELD, name="live_query", drive=drive)
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)
    assert observed["state"]["current_stage"] == "architecture"
    assert observed["pending"], "the architecture gate must be pending"
    golden = load_golden("greenfield_happy")
    assert captured.golden["commands"] == golden["commands"]
    assert captured.golden["close"] == golden["close"]


@activity.defn(name="cache_get")
async def fake_cache_get(inp: CacheGetInput) -> str | None:
    return None


@activity.defn(name="cache_put")
async def fake_cache_put(inp: CachePutInput) -> None:
    return None


@activity.defn(name="reflect")
async def fake_reflect(*args: object) -> None:
    return None  # retro schedules reflect when memory is on (retro/step.py:75-85)


@pytest.mark.asyncio
async def test_memo_key_inputs_match_feature_workflow(monkeypatch, tmp_path):
    """§5.3 host mirrors: with memoization and memory ON, every content_key
    input (incl. the watermark) is identical across the two workflows."""
    import sdlc.workflows.role_host as role_host
    from sdlc.memory.activities import recall_snapshot, retain

    seen: dict[str, list[tuple]] = {"FeatureWorkflow": [], "GraphWorkflow": []}
    current = {"name": ""}
    original = role_host.content_key

    def recording(*args):
        seen[current["name"]].append(args)
        return original(*args)

    monkeypatch.setattr(role_host, "content_key", recording)

    def memo_cfg():
        cfg = e2e_config()
        cfg.deploy.enabled = True
        cfg.memoization_enabled = True
        cfg.memory = MemoryConfig(enabled=True, backend="fake", watermark="wm-e74")
        return cfg

    scenario = dataclasses.replace(
        GREENFIELD,
        name="memo_parity",
        cfg=memo_cfg,
        activities=lambda: [
            *GREENFIELD.activities(),
            fake_cache_get,
            fake_cache_put,
            fake_reflect,
            recall_snapshot,
            retain,
        ],
    )
    for starter in (FEATURE_STARTER, GRAPH_STARTER):
        current["name"] = starter.name
        await capture(scenario, starter, monkeypatch, tmp_path / starter.name)
    assert seen["FeatureWorkflow"], "memoization must have computed keys"
    assert seen["GraphWorkflow"] == seen["FeatureWorkflow"]
    assert all(args[-1] == "wm-e74" for args in seen["GraphWorkflow"])
