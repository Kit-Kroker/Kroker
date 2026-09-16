"""E-74 §6.1: the generic gate reproduces _revisable_stage (role_host.py:219-271)."""

from __future__ import annotations

import asyncio

import pytest

from sdlc.core.models import GateDecision, GateOutcome, GatePolicy, PipelineConfig
from sdlc.graph import NODE_TYPES, validate
from sdlc.graph.router import Activation
from sdlc.pending import GateContext
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes import gate as gate_module
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, PLAN, greenfield_idea
from tests.graph.fixtures.registries import roles


class Recorder:
    def __init__(self, outcome: GateOutcome):
        self.outcome = outcome
        self.gate_calls: list[tuple[str, dict]] = []
        self.finished: list[tuple[str, bool]] = []

    async def gate(self, name, settings, **kw):
        self.gate_calls.append((name, kw))
        return GateDecision(
            gate=name, round=kw["round"], outcome=self.outcome, decided_by="human", guidance="g"
        )


class Host:
    def __init__(self):
        self.calibration: list[tuple[str, str]] = []
        self.published: list[tuple[str, bool]] = []
        self._plan_version = None

    async def _calibration_verdict(self, cfg, gate, author_model):
        self.calibration.append((gate, author_model))
        return "verdict"

    async def _board_publish(self, cfg, key, content_json, *, approved=True):
        self.published.append((key, approved))
        return 11


def _nc(gate_id: str, producer: str, artifact, rec: Recorder, host: Host):
    graph = SHIPPED["default"]
    node = next(n for n in graph.nodes if n.id == gate_id)
    payloads = {
        f"{producer}#1.x": StoredPayload(
            model=artifact, producer=f"{producer}#1", author_model="m-author"
        )
    }
    nc = NodeContext(
        ctx=rec,
        host=host,
        facts=RunFacts(
            idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=None, memory_watermark=None
        ),
        node=node,
        spec=NODE_TYPES[node.type],
        topology=validate(graph, roles=roles()).topology,
        payloads=payloads,
        carries={producer: {"prep": "PREP"}},
    )
    return nc, f"{producer}#1.x"


def _act(gate_id: str, ref: str, round_: int, final: bool) -> Activation:
    return Activation(
        activation_id=f"{gate_id}#{round_}",
        node_id=gate_id,
        round=round_,
        inputs={"artifact": ref},
        unavailable_ports={"revise": "exhausted"} if final else {},
    )


@pytest.fixture
def finishes(monkeypatch):
    done: list[tuple[str, object, bool]] = []

    def make(board_key, sets_plan_version):
        async def fin(ctx, prep, *, cfg, artifact, gate):
            done.append((board_key, prep, gate.approved))

        return gate_module.GateFinish(
            finish=fin, board_key=board_key, sets_plan_version=sets_plan_version
        )

    monkeypatch.setattr(
        gate_module,
        "GATE_FINISH",
        {"gate.architecture": make("architecture", False), "gate.plan": make("plan", True)},
    )
    monkeypatch.setattr(
        gate_module, "auto_decision_for", lambda name, cfg, confidence, calibration: "AUTO"
    )
    return done


def test_in_loop_soft_round_reads_calibration_and_passes_confidence(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("plan", "planner", PLAN, rec, host)
    cfg = PipelineConfig()  # plan is SOFT by default
    out = asyncio.run(gate_module.gate_node(nc, _act("plan", ref, 1, final=False), cfg))
    name, kw = rec.gate_calls[0]
    assert name == "plan" and host.calibration == [("plan", "m-author")]
    assert kw == {
        "auto_decision": "AUTO",
        "round": 1,
        "context": GateContext(spec_summary=gate_module._spec_summary(PLAN)),
        "confidence": PLAN.confidence,
        "author_model": "m-author",
    }
    assert (out.port, out.payload) == ("approve", PLAN)
    assert finishes == [("plan", "PREP", True)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", True)] and host._plan_version == 11


def test_hard_round_reads_no_calibration(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    asyncio.run(
        gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), PipelineConfig())
    )
    assert host.calibration == []
    assert rec.gate_calls[0][1]["auto_decision"] is None


def test_default_soft_policy_without_an_entry_reads_no_calibration(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    cfg = PipelineConfig(default_gate_policy=GatePolicy.SOFT)
    cfg.gates.pop("architecture")
    asyncio.run(gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), cfg))
    assert host.calibration == []  # C3: GateConfig().policy is HARD


def test_in_loop_revise_emits_the_decision_without_finish(finishes):
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    out = asyncio.run(
        gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), PipelineConfig())
    )
    assert out.port == "revise" and out.payload.outcome is GateOutcome.REVISE
    assert finishes == [] and out.finalize is None


def test_final_round_skips_calibration_and_maps_revise_to_reject(finishes):
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc, ref = _nc("plan", "planner", PLAN, rec, host)
    out = asyncio.run(gate_module.gate_node(nc, _act("plan", ref, 3, final=True), PipelineConfig()))
    name, kw = rec.gate_calls[0]
    assert host.calibration == []
    assert kw == {
        "round": 3,
        "context": GateContext(spec_summary=gate_module._spec_summary(PLAN)),
        "author_model": "m-author",
    }
    assert out.port == "reject" and finishes == [("plan", "PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", False)]
