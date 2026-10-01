"""Every proposer agent carries the single-retry capability, and every
provider it can build runs single-layer (004 T010, FR-007).

Three coverage axes, all RED on main:

1. attachment on the durable agents — walk each agent's capability tree and
   require a ResolveModelId beside its TemporalDurability (the capability is
   the framework's only model-id resolution seam, so presence IS the
   mechanism; on main the trees carry durability only);
2. attachment on the two plain research-stage agents (planner / synthesis)
   — built inline inside activities, so the test spies on the
   ``single_retry_layer`` factory the stage must import (004 T013);
3. per-provider behaviour — for every provider name the installed framework
   can construct, the model built through the capability has its SDK retry
   count at 0, or a client with no implicit retry knob at all (opt-in only).
   A constructible provider failing this is stop-guard SG-5, not a test
   tweak.
"""

from __future__ import annotations

import inspect
import re

import pytest
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.models.test import TestModel

from sdlc.agents.roles import ALL_TEMPORAL_AGENTS
from sdlc.stages.research import stage as research_stage
from sdlc.stages.research.models import SubQuestion, SubQuestionFinding


def _capability_tree(agent):
    """Yield every capability reachable from the agent's root, descending
    through CombinedCapability containers."""
    stack = [agent.root_capability]
    while stack:
        cap = stack.pop()
        yield cap
        stack.extend(getattr(cap, "capabilities", ()) or ())


@pytest.mark.parametrize("agent", ALL_TEMPORAL_AGENTS, ids=lambda a: a.name)
def test_every_durable_agent_carries_a_model_id_resolver(agent):
    resolvers = [c for c in _capability_tree(agent) if isinstance(c, ResolveModelId)]
    assert resolvers, (
        f"{agent.name}: no ResolveModelId capability attached — its model "
        f"requests resolve through the default infer_model chain, so the "
        f"provider SDK keeps its own retry layer (FR-007)"
    )


def _require_stage_factory(monkeypatch):
    """The research stage must build its inline agents through the shared
    single_retry_layer factory (004 T013). Returns (wrapped_factory, calls)."""
    factory = getattr(research_stage, "single_retry_layer", None)
    assert factory is not None, (
        "stages/research/stage.py does not import single_retry_layer — its "
        "planner and synthesis agents are plain Agents with no capability, "
        "so their model requests keep SDK retries (FR-007)"
    )
    calls: list[int] = []

    def _recording() -> object:
        calls.append(1)
        return factory()

    monkeypatch.setattr(research_stage, "single_retry_layer", _recording)
    return _recording, calls


@pytest.mark.asyncio
async def test_research_planner_agent_is_built_through_the_factory(monkeypatch):
    _, calls = _require_stage_factory(monkeypatch)
    from sdlc.stages.research.stage import PlanInput, _plan_research_impl

    inp = PlanInput(idea_json="{}", max_sub_questions=2, model="anthropic:glm-5.2")
    await _plan_research_impl(inp, _model=TestModel(custom_output_args={"sub_questions": ["q"]}))
    assert calls, "the planner agent was constructed without the single-retry capability"


@pytest.mark.asyncio
async def test_research_synthesis_agent_is_built_through_the_factory(monkeypatch):
    _, calls = _require_stage_factory(monkeypatch)
    from sdlc.stages.research.stage import SynthesizeInput, _synthesize_brief_impl

    inp = SynthesizeInput(
        idea_json="{}",
        findings=[SubQuestionFinding(sub_question=SubQuestion(id="sq-0", question="q"))],
        model="anthropic:glm-5.2",
    )
    await _synthesize_brief_impl(
        inp,
        _model=TestModel(
            custom_output_args={"summary": "s", "contradictions": [], "confidence": 0.5}
        ),
    )
    assert calls, "the synthesis agent was constructed without the single-retry capability"


def _constructible_provider_names() -> list[str]:
    """Every provider name infer_provider_class knows that this install can
    actually construct (class import + provider instance). Names whose SDK
    extra is not installed raise on import and are not constructible."""
    from pydantic_ai.providers import infer_provider, infer_provider_class

    source = inspect.getsource(infer_provider_class)
    names = sorted(set(re.findall(r"'([a-z0-9][a-z0-9-]*)'", source)))
    # Extraction guard: if the framework rewords its dispatch table the regex
    # must not silently return a stale subset.
    assert {"anthropic", "openai", "google"} <= set(names), (
        f"provider-name extraction from infer_provider_class lost known providers: {names}"
    )
    constructible: list[str] = []
    for name in names:
        try:
            infer_provider(name)
        except Exception:
            continue
        constructible.append(name)
    assert constructible, "no constructible providers found at all — the test is blind"
    return constructible


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", _constructible_provider_names())
async def test_every_constructible_provider_builds_single_layer(provider):
    # Imported here, not at module top: the module is 004's deliverable and
    # the ImportError IS the RED on main.
    from sdlc.agents.model_ids import single_retry_layer

    capability = single_retry_layer()
    model = await capability.resolve_model_id(None, model_id=f"{provider}:stub-model")
    client = getattr(model, "client", None)
    assert client is not None, (
        f"provider {provider!r}: the built model exposes no client to check "
        f"(SG-5 — escalate, do not narrow the test)"
    )
    retries = getattr(client, "max_retries", None)
    if retries is not None:
        assert retries == 0, (
            f"provider {provider!r}: client built with max_retries={retries} "
            f"— the SDK retry layer is still live (FR-007)"
        )
    # A client with no retry knob has no implicit retries: opt-in only, which
    # the contract counts as single-layer.
