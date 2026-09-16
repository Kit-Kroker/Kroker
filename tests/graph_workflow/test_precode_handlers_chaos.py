"""Chaos + edge-case characterization for E-74 Task 16 (pre-code handlers).

RED until ``sdlc.workflows.graph_nodes.precode`` exists: every test fetches
the module through ``_precode()``, so each test fails on its own with
``ImportError: cannot import name 'precode'`` -- the plan's own expected RED
reason -- while the file still collects (everything else it needs is landed:
the base contract, SHIPPED graphs, core models, canned fakes, fixtures).

Pins the edge behaviour the task specifies:
- context_node: a None step result rejects greenfield with the exact wire
  string "rejected:context (greenfield run has no codebase to map)"; a str
  result passes through verbatim as the rejection; a mapped result is stored
  on the host mirror and forwarded as the payload, with commit_sha threaded
  from the host's _integration_head
- research_node: without t_research it raises RuntimeError("research node on
  a worker without agents/research (select_graph guards this)") BEFORE
  touching research.step; a truthy out.rejection passes through as
  port='reject'; a clean run builds the brief via model_validate excluding
  digest/rejection and pins meta={'digest': ...}, forwarding the host's
  memory watermark and the resolved research model
- plan_node: prepare runs ONCE via carry (the same prep object feeds every
  round), produce runs per round with guidance_text forwarded (None then the
  gate's guidance), architecture re-read per round, and author_model set
  from prep.resolved_model on every result
- carry: the plan prep persists across rounds on the node's own carry dict
  and no other node's carry is touched
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig
from sdlc.graph import NODE_TYPES, validate
from sdlc.graph.router import Activation
from sdlc.stages.research.models import ResearchBrief
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, CLARIFIED, PLAN, greenfield_idea
from tests.graph.fixtures.registries import roles


def _precode():
    from sdlc.workflows.graph_nodes import precode

    return precode


class Host:
    """The §5.3 host mirrors the handlers read and write."""

    def __init__(self):
        self._integration_head = ""
        self._base_sha = ""
        self._integration_wt = ""
        self._codebase_map = None
        self._memory_watermark = "wm"
        self.published: list[tuple[str, bool]] = []

    async def _board_publish(self, cfg, key, content_json, *, approved=True):
        self.published.append((key, approved))
        return 7


class _FakeResearchOut:
    """research.step's output shape: rejection + digest + model_dump."""

    def __init__(self, dump, *, digest="d1", rejection=None):
        self.rejection = rejection
        self.digest = digest
        self._dump = dump

    def model_dump(self, *, exclude=None):
        drop = exclude or set()
        return {k: v for k, v in self._dump.items() if k not in drop}


BRIEF_DUMP = {
    "summary": "findings",
    "confidence": 0.9,
    "gaps": [{"sub_question_id": "q1", "what_is_missing": "g1"}],
}


def _nc(node_id, *, graph=None, payloads=None, host=None, services=None):
    graph = graph or SHIPPED["default"]
    topology = validate(graph, roles=roles()).topology
    assert topology is not None
    node = next(n for n in graph.nodes if n.id == node_id)
    facts = RunFacts(
        idea=greenfield_idea(),
        repo_path="/fake/repo",
        run_id="wf-1",
        seeded=None,
        memory_watermark="wm",
    )
    return NodeContext(
        ctx=services or SimpleNamespace(),
        host=host or Host(),
        facts=facts,
        node=node,
        spec=NODE_TYPES[node.type],
        topology=topology,
        payloads=payloads or {},
        carries={},
    )


def _act(node_id, round_=1, inputs=None):
    return Activation(
        activation_id=f"{node_id}#{round_}",
        node_id=node_id,
        round=round_,
        inputs=inputs or {},
        unavailable_ports={},
    )


# ---- context_node --------------------------------------------------------------


def test_context_node_rejects_a_greenfield_run_with_no_codebase(monkeypatch):
    precode = _precode()

    async def fake_step(ctx, **kw):
        return None

    monkeypatch.setattr(precode, "context", SimpleNamespace(step=fake_step))

    out = asyncio.run(precode.context_node(_nc("context"), _act("context"), PipelineConfig()))

    assert (out.port, out.result) == (
        "reject",
        "rejected:context (greenfield run has no codebase to map)",
    )
    assert out.payload is None


def test_context_node_passes_a_string_rejection_through_verbatim(monkeypatch):
    precode = _precode()

    async def fake_step(ctx, **kw):
        return "rejected:context (git remote unreachable)"

    monkeypatch.setattr(precode, "context", SimpleNamespace(step=fake_step))

    out = asyncio.run(precode.context_node(_nc("context"), _act("context"), PipelineConfig()))

    assert (out.port, out.result) == ("reject", "rejected:context (git remote unreachable)")


def test_context_node_maps_mirrors_the_host_and_threads_the_commit(monkeypatch):
    precode = _precode()
    seen = {}
    codebase_map = SimpleNamespace(files=["a.py"])

    async def fake_step(ctx, **kw):
        seen.update(kw)
        return codebase_map

    monkeypatch.setattr(precode, "context", SimpleNamespace(step=fake_step))
    host = Host()
    host._integration_head = "h1"

    nc = _nc("context", host=host)
    out = asyncio.run(precode.context_node(nc, _act("context"), PipelineConfig()))

    assert out.port == "map" and out.payload is codebase_map
    assert nc.host._codebase_map is codebase_map  # the host mirror
    assert seen["commit_sha"] == "h1"  # threaded from the host mirror
    assert seen["repo_path"] == "/fake/repo"
    assert seen["idea"] is nc.facts.idea


# ---- research_node ---------------------------------------------------------------


def test_research_node_raises_without_a_research_agent(monkeypatch):
    precode = _precode()

    async def no_step(*a, **k):
        raise AssertionError("research.step must not run without an agent")

    monkeypatch.setattr(precode, "research", SimpleNamespace(step=no_step))
    monkeypatch.setattr(precode, "t_research", None)

    with pytest.raises(RuntimeError, match="without agents/research"):
        asyncio.run(
            precode.research_node(
                _nc("research", graph=SHIPPED["default-research"]),
                _act("research"),
                PipelineConfig(),
            )
        )


def test_research_node_passes_a_rejection_through(monkeypatch):
    precode = _precode()

    async def fake_step(ctx, **kw):
        return SimpleNamespace(rejection="rejected:research (budget exhausted)")

    monkeypatch.setattr(precode, "research", SimpleNamespace(step=fake_step))

    out = asyncio.run(
        precode.research_node(
            _nc("research", graph=SHIPPED["default-research"]), _act("research"), PipelineConfig()
        )
    )

    assert (out.port, out.result) == ("reject", "rejected:research (budget exhausted)")


def test_research_node_builds_the_brief_pins_the_digest_and_threads_the_host(monkeypatch):
    precode = _precode()
    seen = {}
    agent = object()

    async def fake_step(ctx, **kw):
        seen.update(kw)
        return _FakeResearchOut(BRIEF_DUMP, digest="d1")

    monkeypatch.setattr(precode, "research", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode, "t_research", agent)
    monkeypatch.setattr(precode, "resolve_role_model", lambda cfg, stage: f"model-{stage}")

    out = asyncio.run(
        precode.research_node(
            _nc("research", graph=SHIPPED["default-research"]), _act("research"), PipelineConfig()
        )
    )

    assert out.port == "brief"
    assert out.payload == ResearchBrief.model_validate(BRIEF_DUMP)
    assert out.meta == {"digest": "d1"}
    assert seen["memory_watermark"] == "wm"  # the host watermark
    assert seen["research_agent"] is agent
    assert seen["research_model"] == "model-research"


# ---- plan_node -------------------------------------------------------------------


def _patched_plan(monkeypatch, prep):
    """Wire fake prepare/produce; returns (prepared, produced) recorders."""
    precode = _precode()
    prepared, produced = [], []

    async def fake_prepare(ctx, **kw):
        prepared.append(kw)
        return prep

    async def fake_produce(ctx, p, **kw):
        produced.append((p, kw["guidance"], kw["architecture"]))
        return PLAN

    monkeypatch.setattr(precode, "plan_prepare", fake_prepare)
    monkeypatch.setattr(precode, "plan_produce", fake_produce)
    monkeypatch.setattr(precode, "resolve_role_model", lambda cfg, stage: f"model-{stage}")
    return prepared, produced


_PLAN_INPUTS = {"spec": "arch#1.spec", "requirements": "clarify#1.requirements"}


def _plan_payloads():
    decision = GateDecision(
        gate="plan", outcome=GateOutcome.REVISE, decided_by="human", guidance="g1"
    )
    return {
        "arch#1.spec": StoredPayload(model=ARCH, producer="arch#1"),
        "clarify#1.requirements": StoredPayload(model=CLARIFIED, producer="clarify#1"),
        "plan#1.revise": StoredPayload(model=decision, producer="plan#1"),
    }


def _plan_call(nc, round_, *, guidance=False):
    precode = _precode()
    inputs = {**_PLAN_INPUTS, "guidance": "plan#1.revise"} if guidance else _PLAN_INPUTS
    return precode.plan_node(nc, _act("planner", round_, inputs), PipelineConfig())


def test_plan_node_prepares_once_produces_per_round_and_forwards_guidance(monkeypatch):
    prep = SimpleNamespace(resolved_model="m-plan")
    prepared, produced = _patched_plan(monkeypatch, prep)
    nc = _nc("planner", payloads=_plan_payloads())

    first = asyncio.run(_plan_call(nc, 1))
    second = asyncio.run(_plan_call(nc, 2, guidance=True))

    assert len(prepared) == 1  # prepare ONCE per stage, not per round
    assert prepared[0]["planner_model"] == "model-plan"
    assert [g for (_, g, _) in produced] == [None, "g1"]  # guidance_text forwarding
    assert all(p is prep for p, _, _ in produced)  # the carried prep feeds produce
    assert [a for (_, _, a) in produced] == [ARCH, ARCH]  # architecture re-read per round
    assert (first.port, first.author_model) == ("plan", "m-plan")
    assert second.payload is PLAN
    assert second.author_model == "m-plan"


def test_plan_carry_persists_across_rounds_and_stays_node_isolated(monkeypatch):
    prep = SimpleNamespace(resolved_model="m-plan")
    prepared, _produced = _patched_plan(monkeypatch, prep)
    nc = _nc("planner", payloads=_plan_payloads())

    for round_ in (1, 2, 3):
        out = asyncio.run(_plan_call(nc, round_))
        assert out.author_model == "m-plan"

    assert len(prepared) == 1  # still exactly one prepare after three rounds
    assert nc.carry("planner")["prep"] is prep  # persisted on the node's carry
    assert nc.carry("architect") == {}  # no other node's carry was touched
