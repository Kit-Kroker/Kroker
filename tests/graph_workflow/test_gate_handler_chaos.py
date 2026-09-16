"""Chaos + edge-case characterization for E-74 Task 17 (the generic gate handler).

RED until ``sdlc.workflows.graph_nodes.gate`` exists: every test fetches the
module through ``_gate()``, so each test fails on its own with
``ImportError: cannot import name 'gate'`` -- the plan's own expected RED
reason -- while the file still collects.

Pins the edge behaviour the task specifies:
- artifact guards: a missing "artifact" input is a KeyError; a non-string ref
  trips the handler's AssertionError; an unknown ref is a payload KeyError
- an unknown gate type (spec.type not in GATE_FINISH) raises KeyError at the
  finish lookup, AFTER the decision but BEFORE any publish
- a failing gate finish propagates the original exception out of the handler
- the sets_plan_version / publish truth table: the board publish rides
  finalize (nothing is published before it runs) with approved=decision's
  verdict; gate.plan sets host._plan_version on approve AND on reject (only
  sets_plan_version gates the assignment, not the outcome -- pinned as
  coded); gate.architecture never touches it
- author_model absent or empty degrades to "" (the calibration verdict and
  the approve result both carry the empty string)
- a final round ("revise" in unavailable_ports) reads NO calibration even
  under a SOFT policy, passes byte-exact kw (round/context/author_model --
  no auto_decision, no confidence) and maps REVISE to reject
- an in-loop REVISE routes to the revise port only when the port is
  CONNECTED; an edgeless revise port falls through to the reject mapping
  (finish + publish with approved=False)
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError

import pytest

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig
from sdlc.graph import NODE_TYPES, validate
from sdlc.graph.router import Activation
from sdlc.stages.architecture.step import finish as architecture_finish
from sdlc.stages.plan.step import finish as plan_finish
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, PLAN, greenfield_idea
from tests.graph.fixtures.registries import edge, graph, node, roles


def _gate():
    from sdlc.workflows.graph_nodes import gate as gate_module

    return gate_module


class Recorder:
    def __init__(self, outcome: GateOutcome):
        self.outcome = outcome
        self.gate_calls: list[tuple[str, object, dict]] = []

    async def gate(self, name, settings, **kw):
        self.gate_calls.append((name, settings, kw))
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


def _nc(gate_id, producer, artifact, rec, host, *, spec=None, author_model="m-author"):
    graph_ = SHIPPED["default"]
    node_ = next(n for n in graph_.nodes if n.id == gate_id)
    payloads = {
        f"{producer}#1.x": StoredPayload(
            model=artifact, producer=f"{producer}#1", author_model=author_model
        )
    }
    return NodeContext(
        ctx=rec,
        host=host,
        facts=RunFacts(
            idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=None, memory_watermark=None
        ),
        node=node_,
        spec=spec or NODE_TYPES[node_.type],
        topology=validate(graph_, roles=roles()).topology,
        payloads=payloads,
        carries={producer: {"prep": "PREP"}},
    )


def _act(gate_id, ref, round_, final):
    return Activation(
        activation_id=f"{gate_id}#{round_}",
        node_id=gate_id,
        round=round_,
        inputs={"artifact": ref},
        unavailable_ports={"revise": "exhausted"} if final else {},
    )


def _patch_finishes(monkeypatch, gm, *, fail=None):
    """Swap GATE_FINISH for recorders mirroring the real board keys/flags."""
    done: list[tuple[str, object, bool]] = []

    async def fin(ctx, prep, *, cfg, artifact, gate):
        if fail is not None:
            raise fail
        done.append((prep, gate.approved))

    monkeypatch.setattr(
        gm,
        "GATE_FINISH",
        {
            "gate.architecture": gm.GateFinish(
                finish=fin, board_key="architecture", sets_plan_version=False
            ),
            "gate.plan": gm.GateFinish(finish=fin, board_key="plan", sets_plan_version=True),
        },
    )
    return done


def _patch_auto(monkeypatch, gm):
    monkeypatch.setattr(gm, "auto_decision_for", lambda *a, **k: "AUTO")


# ---- artifact input guards -----------------------------------------------------


def test_gate_node_requires_the_artifact_input():
    gm = _gate()
    nc = _nc("plan", "planner", PLAN, Recorder(GateOutcome.APPROVE), Host())
    act = Activation(
        activation_id="plan#1", node_id="plan", round=1, inputs={}, unavailable_ports={}
    )

    with pytest.raises(KeyError, match="artifact"):
        asyncio.run(gm.gate_node(nc, act, PipelineConfig()))


def test_gate_node_requires_a_string_artifact_ref():
    gm = _gate()
    nc = _nc("plan", "planner", PLAN, Recorder(GateOutcome.APPROVE), Host())
    # a tuple of strings PASSES Activation validation but still trips the
    # handler's assert isinstance(ref, str)
    act = Activation(
        activation_id="plan#1",
        node_id="plan",
        round=1,
        inputs={"artifact": ("a", "b")},
        unavailable_ports={},
    )

    with pytest.raises(AssertionError):
        asyncio.run(gm.gate_node(nc, act, PipelineConfig()))


def test_gate_node_rejects_an_unknown_artifact_ref():
    gm = _gate()
    nc = _nc("plan", "planner", PLAN, Recorder(GateOutcome.APPROVE), Host())

    with pytest.raises(KeyError, match="ghost#1.spec"):
        asyncio.run(gm.gate_node(nc, _act("plan", "ghost#1.spec", 1, False), PipelineConfig()))


# ---- unknown gate type ----------------------------------------------------------


def test_gate_node_flags_an_unknown_gate_type_at_the_finish_lookup():
    gm = _gate()
    # the plan node carries spec.type 'gate.research', which has no GATE_FINISH
    # entry: the KeyError fires after the decision, before any finish/publish
    nc = _nc(
        "architecture",
        "architect",
        ARCH,
        Recorder(GateOutcome.APPROVE),
        Host(),
        spec=NODE_TYPES["gate.research"],
    )

    with pytest.raises(KeyError, match="gate.research"):
        asyncio.run(
            gm.gate_node(nc, _act("architecture", "architect#1.x", 1, False), PipelineConfig())
        )


# ---- finish failure propagation --------------------------------------------------


def test_gate_finish_failure_propagates_and_publishes_nothing(monkeypatch):
    gm = _gate()
    boom = RuntimeError("finish exploded")
    done = _patch_finishes(monkeypatch, gm, fail=boom)
    _patch_auto(monkeypatch, gm)
    host = Host()
    nc = _nc("plan", "planner", PLAN, Recorder(GateOutcome.APPROVE), host)

    with pytest.raises(RuntimeError) as err:
        asyncio.run(gm.gate_node(nc, _act("plan", "planner#1.x", 1, False), PipelineConfig()))

    assert err.value is boom
    assert done == []  # the failure IS the finish call
    assert host.published == []


# ---- sets_plan_version / board publish truth table -------------------------------


def test_plan_approve_publishes_approved_and_sets_plan_version(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    _patch_auto(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc = _nc("plan", "planner", PLAN, rec, host)

    out = asyncio.run(gm.gate_node(nc, _act("plan", "planner#1.x", 1, False), PipelineConfig()))

    name, _settings, kw = rec.gate_calls[0]
    assert name == "plan" and host.calibration == [("plan", "m-author")]
    assert kw["auto_decision"] == "AUTO"
    assert kw["confidence"] == PLAN.confidence
    assert kw["round"] == 1
    assert kw["author_model"] == "m-author"
    assert kw["context"].spec_summary == gm._spec_summary(PLAN)
    assert (out.port, out.payload) == ("approve", PLAN)
    assert out.author_model == "m-author"
    assert done == [("PREP", True)]
    assert host.published == []  # the publish rides finalize
    asyncio.run(out.finalize())
    assert host.published == [("plan", True)]
    assert host._plan_version == 11


def test_plan_reject_publishes_unapproved_and_still_sets_plan_version(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    _patch_auto(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.REJECT), Host()
    nc = _nc("plan", "planner", PLAN, rec, host)

    out = asyncio.run(gm.gate_node(nc, _act("plan", "planner#1.x", 1, False), PipelineConfig()))

    assert out.port == "reject"
    assert out.payload is None and out.author_model is None
    assert done == [("PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", False)]
    # sets_plan_version gates the assignment, NOT the outcome: pinned as coded
    assert host._plan_version == 11


def test_architecture_approve_publishes_but_never_sets_plan_version(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc = _nc("architecture", "architect", ARCH, rec, host)

    out = asyncio.run(
        gm.gate_node(nc, _act("architecture", "architect#1.x", 1, False), PipelineConfig())
    )

    # HARD gate: no calibration read, no auto decision
    assert host.calibration == []
    assert rec.gate_calls[0][2]["auto_decision"] is None
    assert (out.port, out.payload) == ("approve", ARCH)
    assert done == [("PREP", True)]
    asyncio.run(out.finalize())
    assert host.published == [("architecture", True)]
    assert host._plan_version is None


def test_architecture_reject_publishes_unapproved_and_never_sets_plan_version(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.REJECT), Host()
    nc = _nc("architecture", "architect", ARCH, rec, host)

    out = asyncio.run(
        gm.gate_node(nc, _act("architecture", "architect#1.x", 1, False), PipelineConfig())
    )

    assert out.port == "reject"
    assert done == [("PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("architecture", False)]
    assert host._plan_version is None


# ---- author_model absent or empty -------------------------------------------------


@pytest.mark.parametrize("author", [None, ""], ids=["absent", "empty"])
def test_author_model_absent_or_empty_degrades_to_the_empty_string(monkeypatch, author):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    _patch_auto(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc = _nc("plan", "planner", PLAN, rec, host, author_model=author)

    out = asyncio.run(gm.gate_node(nc, _act("plan", "planner#1.x", 1, False), PipelineConfig()))

    assert host.calibration == [("plan", "")]  # the SOFT read sees ""
    assert rec.gate_calls[0][2]["author_model"] == ""
    assert out.author_model == ""  # the approve result carries it too
    assert done == [("PREP", True)]


# ---- the final round: revise unavailable in unavailable_ports ----------------------


def test_final_round_reads_no_calibration_and_maps_revise_to_reject(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc = _nc("plan", "planner", PLAN, rec, host)

    out = asyncio.run(gm.gate_node(nc, _act("plan", "planner#1.x", 3, True), PipelineConfig()))

    assert host.calibration == []  # no calibration even under the SOFT plan gate
    name, _settings, kw = rec.gate_calls[0]
    assert name == "plan"
    assert set(kw) == {"round", "context", "author_model"}  # no auto_decision, no confidence
    assert kw["round"] == 3
    assert kw["author_model"] == "m-author"
    assert kw["context"].spec_summary == gm._spec_summary(PLAN)
    assert out.port == "reject"  # REVISE on a final round is a reject
    assert out.payload is None
    assert done == [("PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", False)]


# ---- the revise port's connectivity guard ------------------------------------------


def test_in_loop_revise_on_a_connected_port_emits_the_decision(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc = _nc("architecture", "architect", ARCH, rec, host)

    out = asyncio.run(
        gm.gate_node(nc, _act("architecture", "architect#1.x", 1, False), PipelineConfig())
    )

    assert out.port == "revise"
    assert out.payload.outcome is GateOutcome.REVISE
    assert out.finalize is None  # nothing to publish on a revise loop
    assert done == []
    assert host.published == []


def test_in_loop_revise_on_an_unconnected_port_falls_through_to_reject(monkeypatch):
    gm = _gate()
    done = _patch_finishes(monkeypatch, gm)
    rec, host = Recorder(GateOutcome.REVISE), Host()
    # a gate whose revise port carries no edge: still in-loop, but unconnected
    g = graph(
        [
            node("intake", "intake"),
            node("cl", "clarify"),
            node("arch", "architect"),
            node("garch", "gate.architecture"),
            node("planner", "plan"),
        ],
        [
            edge("intake.ok", "cl.trigger"),
            edge("cl.requirements", "arch.requirements"),
            edge("arch.spec", "garch.artifact"),
            edge("garch.approve", "planner.spec"),
        ],
    )
    report = validate(g, roles=roles())
    assert report.topology is not None, report.problems
    gate_node = next(n for n in g.nodes if n.id == "garch")
    payloads = {
        "arch#1.spec": StoredPayload(model=ARCH, producer="arch#1", author_model="m-author")
    }
    nc = NodeContext(
        ctx=rec,
        host=host,
        facts=RunFacts(
            idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=None, memory_watermark=None
        ),
        node=gate_node,
        spec=NODE_TYPES["gate.architecture"],
        topology=report.topology,
        payloads=payloads,
        carries={"arch": {"prep": "PREP"}},
    )

    out = asyncio.run(gm.gate_node(nc, _act("garch", "arch#1.spec", 1, False), PipelineConfig()))

    assert out.port == "reject"  # REVISE with an edgeless revise port is a reject
    assert done == [("PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("architecture", False)]


# ---- the real GATE_FINISH table ------------------------------------------------------


def test_gate_finish_table_pins_the_real_mapping():
    gm = _gate()

    assert set(gm.GATE_FINISH) == {"gate.architecture", "gate.plan"}
    assert gm.GATE_FINISH["gate.architecture"].finish is architecture_finish
    assert gm.GATE_FINISH["gate.plan"].finish is plan_finish
    assert gm.GATE_FINISH["gate.architecture"].board_key == "architecture"
    assert gm.GATE_FINISH["gate.architecture"].sets_plan_version is False
    assert gm.GATE_FINISH["gate.plan"].board_key == "plan"
    assert gm.GATE_FINISH["gate.plan"].sets_plan_version is True

    with pytest.raises(FrozenInstanceError):
        gm.GATE_FINISH["gate.plan"].board_key = "nope"
