"""E-74 §5.2/§5.3/§7.2: the handler contract."""

from __future__ import annotations

import pytest

from sdlc.core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
    RoleConfig,
)
from sdlc.graph import NODE_TYPES, GraphNode
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle
from sdlc.workflows.graph_nodes.base import (
    NodeContext,
    NodeResult,
    RunFacts,
    StoredPayload,
    guidance_text,
    input_model,
    project_cfg,
)
from sdlc.workflows.models import GraphRunInput
from tests.fakes.canned import ARCH, greenfield_idea


def _facts() -> RunFacts:
    return RunFacts(
        idea=greenfield_idea(),
        repo_path="/fake/repo",
        run_id="wf",
        seeded=None,
        memory_watermark=None,
    )


def test_run_facts_integration_is_write_once():
    facts = _facts()
    assert facts.integration is None and facts.base_sha is None
    facts.set_integration(IntegrationHandle(head_sha="h1", worktree_path="/wt"))
    assert (facts.integration.worktree_path, facts.base_sha) == ("/wt", "h1")
    with pytest.raises(RuntimeError, match="write-once"):
        facts.set_integration(IntegrationHandle(head_sha="h2", worktree_path="/wt2"))


def test_node_result_defaults():
    r = NodeResult(port="ok")
    assert (r.payload, r.author_model, dict(r.meta), r.result, r.finalize) == (
        None,
        None,
        {},
        None,
        None,
    )


def _nc(payloads) -> NodeContext:
    return NodeContext(
        ctx=None,
        host=None,
        facts=_facts(),
        node=GraphNode(id="architect", type="architect"),
        spec=NODE_TYPES["architect"],
        topology=None,
        payloads=payloads,
        carries={},
    )


def test_input_model_and_guidance_text():
    decision = GateDecision(
        gate="architecture", outcome=GateOutcome.REVISE, decided_by="human", comments="c1"
    )
    payloads = {
        "a#1.spec": StoredPayload(model=ARCH, producer="a#1"),
        "g#1.revise": StoredPayload(model=decision, producer="g#1"),
    }
    act = Activation(
        activation_id="architect#2",
        node_id="architect",
        round=2,
        inputs={"requirements": "a#1.spec", "guidance": "g#1.revise"},
        unavailable_ports={},
    )
    nc = _nc(payloads)
    assert input_model(nc, act, "requirements") is ARCH
    assert input_model(nc, act, "codebase_map") is None
    assert guidance_text(nc, act) == "c1"
    no_guidance = act.model_copy(update={"inputs": {"requirements": "a#1.spec"}})
    assert guidance_text(nc, no_guidance) is None


def test_carry_is_per_node_and_persistent():
    nc = _nc({})
    nc.carry("architect")["prep"] = 1
    assert nc.carry("architect") == {"prep": 1}
    assert nc.carry("planner") == {}


def test_project_cfg_is_identity_without_node_config():
    cfg = PipelineConfig()
    out = project_cfg(
        cfg,
        GraphNode(id="architect", type="architect"),
        NODE_TYPES["architect"],
        research_in_graph=False,
    )
    assert out == cfg


def test_project_cfg_node_role_fills_only_an_unoverridden_role():
    node = GraphNode(
        id="architect", type="architect", role=RoleConfig(kind="proposer", model="node-model")
    )
    filled = project_cfg(PipelineConfig(), node, NODE_TYPES["architect"], research_in_graph=False)
    assert filled.roles["architect"].model == "node-model"
    run = PipelineConfig()
    run.roles["architect"] = RoleConfig(kind="proposer", model="run-model")
    kept = project_cfg(run, node, NODE_TYPES["architect"], research_in_graph=False)
    assert kept.roles["architect"].model == "run-model"  # U5: run-level override wins


def test_project_cfg_gate_and_research():
    node = GraphNode(id="plan", type="gate.plan", gate=GateConfig(policy=GatePolicy.OFF))
    out = project_cfg(
        PipelineConfig(research_enabled=True),
        node,
        NODE_TYPES["gate.plan"],
        research_in_graph=False,
    )
    assert out.gates["plan"].policy is GatePolicy.OFF
    assert out.research_enabled is False


def test_graph_run_input_round_trips():
    from sdlc.graph import PipelineGraph

    inp = GraphRunInput(
        idea=greenfield_idea(),
        cfg=PipelineConfig(),
        graph=PipelineGraph(schema_version=1, nodes=[], edges=[]),
        roles={},
    )
    assert GraphRunInput.model_validate_json(inp.model_dump_json()) == inp
