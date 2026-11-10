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

# 020 T007 (plan T014, R-5): the FeatureWorkflow memo-parity keys, frozen
# verbatim from one run of test_memo_key_inputs_match_feature_workflow before
# FeatureWorkflow is deleted. Each tuple is one content_key call:
# (stage, input_json, digest, model, watermark), in call order.
MEMO_PARITY_KEYS: list[tuple] = [
    (
        "clarify",
        '{"title":"Hello service","description":"Add /hello","mode":"greenfield","repo_url":"/fake/repo","base_branch":"main","constraints":[]}',  # noqa: E501
        "26db68a05e6b307a9f372378694db871b374584fd653af10d7d055953f6e8cc9",
        "zai:glm-5.3",
        "wm-e74",
    ),
    (
        "architect",
        '{"summary":"Add a greeting endpoint.","functional_requirements":["GET /hello returns 200"],"non_functional_requirements":["p95 < 100ms"],"out_of_scope":["auth"],"open_questions":[{"id":"q1","question":"Anonymous access ok?","why_it_matters":"scopes auth work","suggested_answer":"yes","answer":"yes","dimension":null,"asked_by":null,"materiality":null,"evidence":null}],"spec_ref":null}',  # noqa: E501
        "21b8cd74f178a7d0830dd0adca58ea699294f8dffcafb7e461db6cdd52f36afd62579cdaf3c2bad333929e3200992b846fff534ac99cd259a94d811c6ac80e99",  # noqa: E501
        "zai:glm-5.3",
        "wm-e74",
    ),
    (
        "plan",
        '{"overview":"Single FastAPI service with one route.","decisions":[{"id":"d1","decision":"Use FastAPI","rationale":"matches team stack","alternatives_considered":[]}],"affected_modules":[],"new_components":["app/main.py"],"risks":[],"spec_ref":null,"confidence":0.95,"delta":null}',  # noqa: E501
        "90bf1e5a44ad50328703903309f55d18e7efc3b81cd74c270321b82d59552d9b4997a572fb2dff55ccb556489ccdbbe2fae207f9b2c5410915262e3cb6fc7a82",  # noqa: E501
        "zai:glm-5.3",
        "wm-e74",
    ),
]


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
    # 020 T007: both live legs equal the frozen FeatureWorkflow keys, so the
    # pin still holds after FeatureWorkflow is gone.
    assert seen["FeatureWorkflow"] == MEMO_PARITY_KEYS
    assert seen["GraphWorkflow"] == MEMO_PARITY_KEYS
    assert all(args[-1] == "wm-e74" for args in seen["GraphWorkflow"])
