"""Chaos + edge-case characterization for E-74 Task 13 (handler contract).

RED until ``sdlc.workflows.graph_nodes.base`` and ``GraphRunInput`` exist.
Every test imports the missing names IN-FUNCTION, so the file still collects
and each test fails on its own with ``ModuleNotFoundError: No module named
'sdlc.workflows.graph_nodes'`` / ``ImportError: cannot import name
'GraphRunInput'`` -- the plan's own expected RED reasons -- instead of one
whole-file collection error. (Existing names -- core models, ``sdlc.graph``,
``Activation``, ``SeededWork`` -- import at module level.)

Pins the edge behaviour the task specifies:
- RunFacts: the five properties return constructor values and reject
  attribute writes; ``integration``/``base_sha`` are None before
  ``set_integration`` and ``base_sha == handle.head_sha`` after; a second
  ``set_integration`` raises RuntimeError("...write-once")
- NodeContext: ``payload()`` KeyError on an unknown ref; ``carry()`` is
  per-node (the SAME accumulating dict per node_id, independent across
  node_ids); ``connected()`` asserts a topology is attached
- input_model: None for a missing port, a None ref or a non-string ref;
  the stored model for a string ref
- guidance_text: the guidance-or-comments fallback -- comments when guidance
  is None, guidance when comments is None, guidance winning when both exist,
  None when both are empty, when the input is missing, when the payload
  model is None -- and None for a non-GateDecision payload (orchestrator
  coverage; the plan's Step-3 code block had no isinstance guard -- the
  landed base.py added one, resolving the flagged delta)
- project_cfg: a node role fills only an UNOVERRIDDEN spec role (never when
  spec.role is None), the copy semantics of roles/gates, the node-gate
  overlay for every policy, and research_enabled following the
  research_in_graph flag regardless of the cfg's original value
- GraphRunInput: the four core fields required, non-dict roles rejected,
  json round-trip with seeded=None (the default) and a real SeededWork
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
    RoleConfig,
)
from sdlc.graph import NODE_TYPES, GraphNode, PipelineGraph
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


def _facts():
    from sdlc.workflows.graph_nodes.base import RunFacts

    return RunFacts(
        idea=greenfield_idea(),
        repo_path="/fake/repo",
        run_id="wf",
        seeded=None,
        memory_watermark=None,
    )


def _act(inputs):
    return Activation(
        activation_id="architect#1",
        node_id="architect",
        round=1,
        inputs=inputs,
        unavailable_ports={},
    )


def _nc(payloads=None, **kw):
    from sdlc.workflows.graph_nodes.base import NodeContext

    parts = {
        "ctx": None,
        "host": None,
        "facts": _facts(),
        "node": GraphNode(id="architect", type="architect"),
        "spec": NODE_TYPES["architect"],
        "topology": None,
        "payloads": payloads or {},
        "carries": {},
    }
    parts.update(kw)
    return NodeContext(**parts)


def _decision(**kw):
    base = {"gate": "architecture", "outcome": GateOutcome.REVISE, "decided_by": "human"}
    return GateDecision(**{**base, **kw})


def _project(cfg, node, spec_type, *, research_in_graph=False):
    from sdlc.workflows.graph_nodes.base import project_cfg

    return project_cfg(cfg, node, NODE_TYPES[spec_type], research_in_graph=research_in_graph)


def _graph_run_input(**kw):
    from sdlc.workflows.models import GraphRunInput

    base = {
        "idea": greenfield_idea(),
        "cfg": PipelineConfig(),
        "graph": PipelineGraph(schema_version=1, nodes=[], edges=[]),
        "roles": {},
    }
    return GraphRunInput(**{**base, **kw})


# ---- RunFacts: read-only properties + write-once integration -----------------


def test_run_facts_properties_return_constructor_values():
    from sdlc.workflows.graph_nodes.base import RunFacts

    seeded = SeededWork(arch=ARCH, plan=PLAN)
    idea = greenfield_idea()
    facts = RunFacts(
        idea=idea,
        repo_path="/repo",
        run_id="r1",
        seeded=seeded,
        memory_watermark="wm1",
    )

    assert facts.idea is idea
    assert facts.repo_path == "/repo"
    assert facts.run_id == "r1"
    assert facts.seeded is seeded
    assert facts.memory_watermark == "wm1"


@pytest.mark.parametrize("prop", ["idea", "repo_path", "run_id", "seeded", "memory_watermark"])
def test_run_facts_properties_reject_attribute_writes(prop):
    facts = _facts()

    with pytest.raises(AttributeError):
        setattr(facts, prop, None)


def test_integration_and_base_sha_are_none_before_set_integration():
    facts = _facts()

    assert facts.integration is None
    assert facts.base_sha is None


def test_base_sha_matches_handle_head_sha_after_set_integration():
    facts = _facts()
    handle = IntegrationHandle(head_sha="abc123", worktree_path="/wt")

    facts.set_integration(handle)

    assert facts.integration is handle
    assert facts.base_sha == "abc123"


def test_set_integration_is_write_once():
    facts = _facts()
    facts.set_integration(IntegrationHandle(head_sha="h1", worktree_path="/wt"))

    with pytest.raises(RuntimeError, match="write-once"):
        facts.set_integration(IntegrationHandle(head_sha="h2", worktree_path="/wt2"))


# ---- NodeContext: payload boundaries, carry isolation, connected ------------


def test_payload_unknown_ref_raises_key_error():
    from sdlc.workflows.graph_nodes.base import StoredPayload

    nc = _nc({"a#1.spec": StoredPayload(model=ARCH, producer="a#1")})

    with pytest.raises(KeyError, match="ghost"):
        nc.payload("ghost")


def test_carry_is_per_node_and_accumulates_per_node():
    nc = _nc()

    first = nc.carry("architect")
    first["prep"] = 1

    assert nc.carry("architect") is first  # same instance across calls
    assert nc.carry("architect") == {"prep": 1}  # mutations accumulate
    other = nc.carry("planner")
    assert other == {}
    assert other is not first  # independent dicts across node_ids


def test_connected_requires_a_topology():
    nc = _nc(topology=None)

    with pytest.raises(AssertionError):
        nc.connected("spec")


# ---- input_model: ref resolution edges ---------------------------------------


@pytest.mark.parametrize(
    ("inputs", "port"),
    [
        ({}, "requirements"),
        ({"requirements": None}, "requirements"),
        ({"requirements": 42}, "requirements"),
    ],
    ids=["missing-port", "none-ref", "non-string-ref"],
)
def test_input_model_returns_none_without_a_string_ref(inputs, port):
    from sdlc.workflows.graph_nodes.base import input_model

    # real Activation validation only accepts str/tuple refs, so the
    # non-conforming refs are fabricated via model_construct: input_model
    # must still hold the line at runtime
    act = Activation.model_construct(
        activation_id="architect#1",
        node_id="architect",
        round=1,
        inputs=inputs,
        unavailable_ports={},
    )

    assert input_model(_nc(), act, port) is None


def test_input_model_returns_the_stored_model_for_a_string_ref():
    from sdlc.workflows.graph_nodes.base import StoredPayload, input_model

    nc = _nc({"a#1.spec": StoredPayload(model=ARCH, producer="a#1")})

    assert input_model(nc, _act({"requirements": "a#1.spec"}), "requirements") is ARCH


# ---- guidance_text: the guidance-or-comments fallback ------------------------


def test_guidance_text_is_none_without_a_guidance_input():
    from sdlc.workflows.graph_nodes.base import guidance_text

    assert guidance_text(_nc(), _act({})) is None


def test_guidance_text_is_none_for_a_none_payload():
    from sdlc.workflows.graph_nodes.base import StoredPayload, guidance_text

    nc = _nc({"g#1.revise": StoredPayload(model=None, producer="g#1")})

    assert guidance_text(nc, _act({"guidance": "g#1.revise"})) is None


@pytest.mark.parametrize(
    ("guidance", "comments", "expected"),
    [
        (None, "c1", "c1"),
        ("do x", None, "do x"),
        ("do x", "c1", "do x"),
        (None, None, None),
        ("", "c1", "c1"),
        ("", "", None),
    ],
    ids=[
        "comments-fallback",
        "guidance-when-comments-none",
        "guidance-wins",
        "both-none",
        "empty-guidance-falls-through",
        "both-empty",
    ],
)
def test_guidance_text_falls_back_across_guidance_and_comments(guidance, comments, expected):
    from sdlc.workflows.graph_nodes.base import StoredPayload, guidance_text

    nc = _nc(
        {
            "g#1.revise": StoredPayload(
                model=_decision(guidance=guidance, comments=comments), producer="g#1"
            )
        }
    )

    assert guidance_text(nc, _act({"guidance": "g#1.revise"})) == expected


def test_guidance_text_is_none_for_a_non_gate_decision_payload():
    # orchestrator coverage: a non-GateDecision payload must yield None, not
    # crash. The plan's Step-3 code block had no isinstance guard; the landed
    # base.py added one (flagged in the RED report, resolved on landing).
    from sdlc.workflows.graph_nodes.base import StoredPayload, guidance_text

    nc = _nc({"g#1.revise": StoredPayload(model=ARCH, producer="g#1")})

    assert guidance_text(nc, _act({"guidance": "g#1.revise"})) is None


# ---- project_cfg: overlay permutations ---------------------------------------


def test_project_cfg_does_not_inject_a_node_role_when_spec_has_none():
    cfg = PipelineConfig()
    node = GraphNode(
        id="gate_plan", type="gate.plan", role=RoleConfig(kind="proposer", model="node-model")
    )

    out = _project(cfg, node, "gate.plan")

    assert out.roles == cfg.roles  # untouched, despite node.role


def test_project_cfg_is_identity_for_a_plain_node():
    cfg = PipelineConfig()

    out = _project(cfg, GraphNode(id="architect", type="architect"), "architect")

    assert out == cfg


def test_project_cfg_fills_a_missing_spec_role_from_the_node():
    node = GraphNode(
        id="architect", type="architect", role=RoleConfig(kind="proposer", model="node-model")
    )

    out = _project(PipelineConfig(roles={}), node, "architect")
    assert out.roles["architect"].model == "node-model"

    # a populated cfg that merely lacks the spec role fills it too, as a COPY
    cfg = PipelineConfig()
    out2 = _project(cfg, node, "architect")
    assert out2.roles is not cfg.roles
    assert out2.roles["architect"].model == "node-model"
    assert set(out2.roles) == {"architect", *cfg.roles}


def test_project_cfg_run_level_role_override_wins():
    node = GraphNode(
        id="architect", type="architect", role=RoleConfig(kind="proposer", model="node-model")
    )
    run = PipelineConfig()
    run.roles["architect"] = RoleConfig(kind="proposer", model="run-model")

    kept = _project(run, node, "architect")

    assert kept.roles["architect"].model == "run-model"


@pytest.mark.parametrize(
    "policy",
    [GatePolicy.OFF, GatePolicy.HARD, GatePolicy.SOFT],
    ids=["off", "hard", "soft"],
)
def test_project_cfg_overlays_the_node_gate_for_every_policy(policy):
    cfg = PipelineConfig()
    gate = GateConfig(policy=policy)
    node = GraphNode(id="plan", type="gate.plan", gate=gate)

    out = _project(cfg, node, "gate.plan")

    assert out.gates["plan"] is gate
    assert out.gates["plan"].policy is policy


def test_project_cfg_keeps_cfg_gates_when_the_node_has_none():
    cfg = PipelineConfig()

    out = _project(cfg, GraphNode(id="architect", type="architect"), "architect")

    assert out.gates == cfg.gates


@pytest.mark.parametrize(
    ("cfg_enabled", "in_graph", "expected"),
    [(True, False, False), (False, True, True), (True, True, True), (False, False, False)],
    ids=["cfg-on-flag-off", "cfg-off-flag-on", "both-on", "both-off"],
)
def test_project_cfg_research_enabled_follows_the_flag_only(cfg_enabled, in_graph, expected):
    cfg = PipelineConfig(research_enabled=cfg_enabled)

    out = _project(
        cfg, GraphNode(id="architect", type="architect"), "architect", research_in_graph=in_graph
    )

    assert out.research_enabled is expected


# ---- GraphRunInput: validation + round-trips ---------------------------------


@pytest.mark.parametrize("missing", ["idea", "cfg", "graph", "roles"])
def test_graph_run_input_requires_its_core_fields(missing):
    from sdlc.workflows.models import GraphRunInput

    parts = {
        "idea": greenfield_idea(),
        "cfg": PipelineConfig(),
        "graph": PipelineGraph(schema_version=1, nodes=[], edges=[]),
        "roles": {},
    }
    del parts[missing]

    with pytest.raises(ValidationError, match=missing):
        GraphRunInput(**parts)


def test_graph_run_input_rejects_non_dict_roles():
    with pytest.raises(ValidationError, match="roles"):
        _graph_run_input(roles=42)


def test_graph_run_input_round_trips_with_seeded_none():
    from sdlc.workflows.models import GraphRunInput

    inp = _graph_run_input()
    assert inp.seeded is None  # the default

    restored = GraphRunInput.model_validate_json(inp.model_dump_json())

    assert restored == inp


def test_graph_run_input_round_trips_with_a_seeded_work():
    from sdlc.workflows.models import GraphRunInput

    inp = _graph_run_input(seeded=SeededWork(arch=ARCH, plan=PLAN))

    restored = GraphRunInput.model_validate_json(inp.model_dump_json())

    assert restored == inp
    assert restored.seeded.arch == ARCH
    assert restored.seeded is not inp.seeded  # deserialization builds it fresh
