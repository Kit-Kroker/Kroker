"""E-74 §6: pre-code handlers adapt the stage steps; host mirrors and carry (§5.3, D4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from sdlc.graph import NODE_TYPES, from_yaml, validate
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle, IntegrationInput
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes import precode
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, CLARIFIED, greenfield_idea
from tests.graph.fixtures.registries import roles

PRE_CODE = Path(__file__).resolve().parents[1] / "graph" / "fixtures" / "pre_code.graph.yaml"


class Host:
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


def _nc(
    node_id: str,
    *,
    graph=None,
    idea: IdeaBrief | None = None,
    payloads=None,
    host=None,
    services=None,
):
    graph = graph or SHIPPED["default"]
    topology = validate(graph, roles=roles()).topology
    node = next(n for n in graph.nodes if n.id == node_id)
    facts = RunFacts(
        idea=idea or greenfield_idea(),
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


def _act(node_id: str, round_: int = 1, inputs=None) -> Activation:
    return Activation(
        activation_id=f"{node_id}#{round_}",
        node_id=node_id,
        round=round_,
        inputs=inputs or {},
        unavailable_ports={},
    )


def test_intake_sets_up_integration_after_passing_and_mirrors_the_host(monkeypatch):
    calls = []

    async def fake_step(ctx, *, cfg, idea, repo_path):
        calls.append(("intake", repo_path))
        return None

    async def fake_activity(fn, arg, **kw):
        calls.append(("activity", fn.__name__, arg))
        return IntegrationHandle(head_sha="h1", worktree_path="/wt")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", fake_activity)
    nc = _nc("intake")
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.port == "ok"
    assert calls[0] == ("intake", "/fake/repo")
    assert calls[1][2] == IntegrationInput(
        repo_path="/fake/repo", run_id="wf-1", base_branch="main"
    )
    assert (nc.host._integration_head, nc.host._base_sha, nc.host._integration_wt) == (
        "h1",
        "h1",
        "/wt",
    )
    assert nc.facts.base_sha == "h1"


def test_intake_rejection_creates_no_branch(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return "rejected:intake (not a git repository)"

    async def no_activity(*a, **k):
        raise AssertionError("no branch on a rejected intake")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    out = asyncio.run(precode.intake_node(_nc("intake"), _act("intake"), PipelineConfig()))
    assert (out.port, out.result) == ("reject", "rejected:intake (not a git repository)")


def test_intake_rejects_a_mode_the_graph_has_no_path_for(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return None

    async def no_activity(*a, **k):
        raise AssertionError("no branch without a path")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    brown = IdeaBrief(title="t", description="d", mode=ProjectMode.BROWNFIELD, repo_url="/r")
    nc = _nc("intake", graph=from_yaml(PRE_CODE.read_text(encoding="utf-8")), idea=brown)
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.result == "rejected:intake (graph has no brownfield path)"


def test_clarify_passes_the_research_digest_publishes_and_retains(monkeypatch):
    seen = {}

    async def fake_step(ctx, **kw):
        seen.update(kw)
        return CLARIFIED

    retained = []

    async def retain(cfg, kind, bank, text, metadata):
        retained.append((text, metadata))

    monkeypatch.setattr(precode, "clarify", SimpleNamespace(step=fake_step))
    graph = SHIPPED["default-research"]
    payloads = {
        "research#1.brief": StoredPayload(model=None, producer="research#1", meta={"digest": "d1"})
    }
    nc = _nc("clarify", graph=graph, payloads=payloads, services=SimpleNamespace(retain=retain))
    act = _act("clarify", inputs={"research": "research#1.brief"})
    out = asyncio.run(precode.clarify_node(nc, act, PipelineConfig()))
    assert out.payload is CLARIFIED
    assert seen["brief_digest"] == "d1" and seen["codebase_map"] is None
    assert nc.host.published == [("requirements", True)]
    assert retained == [(f"clarify: {CLARIFIED.summary}", {"stage": "clarify", "run_id": "wf-1"})]


def test_architect_prepares_once_and_reads_guidance(monkeypatch):
    prepared, produced = [], []

    async def fake_prepare(ctx, **kw):
        prepared.append(kw)
        return SimpleNamespace(resolved_model="m-arch")

    async def fake_produce(ctx, prep, **kw):
        produced.append(kw["guidance"])
        return ARCH

    monkeypatch.setattr(precode, "arch_prepare", fake_prepare)
    monkeypatch.setattr(precode, "arch_produce", fake_produce)
    monkeypatch.setattr(precode, "resolve_role_model", lambda cfg, stage: f"model-{stage}")
    decision = GateDecision(
        gate="architecture", outcome=GateOutcome.REVISE, decided_by="human", guidance="g1"
    )
    payloads = {
        "clarify#1.requirements": StoredPayload(model=CLARIFIED, producer="clarify#1"),
        "architecture#1.revise": StoredPayload(model=decision, producer="architecture#1"),
    }
    nc = _nc("architect", payloads=payloads)
    first = asyncio.run(
        precode.architect_node(
            nc, _act("architect", 1, {"requirements": "clarify#1.requirements"}), PipelineConfig()
        )
    )
    second = asyncio.run(
        precode.architect_node(
            nc,
            _act(
                "architect",
                2,
                {"requirements": "clarify#1.requirements", "guidance": "architecture#1.revise"},
            ),
            PipelineConfig(),
        )
    )
    assert len(prepared) == 1 and prepared[0]["architect_model"] == "model-architect"
    assert produced == [None, "g1"]
    assert (first.port, first.author_model, second.payload) == ("spec", "m-arch", ARCH)
