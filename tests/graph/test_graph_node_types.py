"""E-72 node-type registry, payload allowlist and compatibility rule (spec §6)."""

from __future__ import annotations

import itertools
from pathlib import Path
from types import MappingProxyType

import pytest

from sdlc.graph import (
    NODE_TYPES,
    PAYLOAD_TYPES,
    NodePort,
    NodeTypeSpec,
    check_node_types,
    find_port,
    from_yaml,
    ports_compatible,
)
from sdlc.graph import node_types as node_types_module

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _in(name, payload, **kw):
    return NodePort(name=name, direction="in", payload=payload, **kw)


def _out(name, payload, *, terminal=None):
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)


def _stage(type_, *ports, role=None, canonical_stage="architecture"):
    return NodeTypeSpec(
        type=type_, kind="stage", role=role, canonical_stage=canonical_stage, ports=ports
    )


def test_seed_registry_is_healthy():
    assert check_node_types() == []


def test_seed_catalog_types():
    assert sorted(NODE_TYPES) == [
        "architect",
        "clarify",
        "context",
        "gate.architecture",
        "gate.plan",
        "gate.research",
        "intake",
        "plan",
        "research",
    ]
    assert "gate.clarify" not in NODE_TYPES  # clarify's HITL is handler-internal (spec §6.4)


@pytest.mark.parametrize(
    ("type_", "kind", "role", "canonical_stage"),
    [
        ("intake", "stage", None, "intake"),
        ("context", "stage", None, "context"),
        ("research", "stage", "research", "research"),
        ("clarify", "stage", "clarify", "clarify"),
        ("architect", "stage", "architect", "architecture"),
        ("plan", "stage", "planner", "planning"),
        ("gate.research", "gate", None, "research"),
        ("gate.architecture", "gate", None, "architecture"),
        ("gate.plan", "gate", None, "planning"),
    ],
)
def test_seed_catalog_metadata(type_, kind, role, canonical_stage):
    spec = NODE_TYPES[type_]
    assert (spec.kind, spec.role, spec.canonical_stage) == (kind, role, canonical_stage)


def _port_table(type_):
    return {
        (p.direction, p.name): (p.payload, p.required, p.multiplicity)
        for p in NODE_TYPES[type_].ports
    }


def test_seed_catalog_ports():
    gd = "GateDecision"
    assert _port_table("intake") == {("out", "ok"): (None, True, "one")}
    assert _port_table("context") == {
        ("in", "trigger"): (None, True, "one"),
        ("out", "map"): ("CodebaseMap", True, "one"),
    }
    assert _port_table("research") == {
        ("in", "trigger"): (None, True, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "brief"): ("ResearchBrief", True, "one"),
    }
    assert _port_table("clarify") == {
        ("in", "trigger"): (None, False, "one"),
        ("in", "codebase_map"): ("CodebaseMap", False, "one"),
        ("in", "research"): ("ResearchBrief", False, "one"),
        ("out", "requirements"): ("ClarifiedRequirements", True, "one"),
    }
    assert _port_table("architect") == {
        ("in", "requirements"): ("ClarifiedRequirements", True, "one"),
        ("in", "codebase_map"): ("CodebaseMap", False, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "spec"): ("ArchitectureSpec", True, "one"),
    }
    assert _port_table("plan") == {
        ("in", "spec"): ("ArchitectureSpec", True, "one"),
        ("in", "requirements"): ("ClarifiedRequirements", False, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "plan"): ("ImplementationPlan", True, "one"),
    }
    for gate, payload in [
        ("gate.research", "ResearchBrief"),
        ("gate.architecture", "ArchitectureSpec"),
        ("gate.plan", "ImplementationPlan"),
    ]:
        assert _port_table(gate) == {
            ("in", "artifact"): (payload, True, "one"),
            ("out", "approve"): (payload, True, "one"),
            ("out", "revise"): (gd, True, "one"),
            ("out", "reject"): (None, True, "one"),
        }


def test_payload_allowlist_seed():
    assert dict(PAYLOAD_TYPES) == {
        "AnalyzeResult": "sdlc.workflows.models:AnalyzeResult",
        "ArchitectureSpec": "sdlc.stages.architecture.models:ArchitectureSpec",
        "BuildResult": "sdlc.workflows.models:BuildResult",
        "ClarifiedRequirements": "sdlc.stages.clarify.models:ClarifiedRequirements",
        "CodebaseMap": "sdlc.context.models:CodebaseMap",
        "GateDecision": "sdlc.core.models:GateDecision",
        "ImplementationPlan": "sdlc.stages.plan.models:ImplementationPlan",
        "NodeFailure": "sdlc.core.models:NodeFailure",
        "PullRequest": "sdlc.workflows.models:PullRequest",
        "ResearchBrief": "sdlc.stages.research.models:ResearchBrief",
    }


def test_registries_are_read_only():
    with pytest.raises(TypeError):
        NODE_TYPES["x"] = NODE_TYPES["intake"]  # type: ignore[index]
    with pytest.raises(TypeError):
        PAYLOAD_TYPES["x"] = "y"  # type: ignore[index]


def test_find_port():
    spec = NODE_TYPES["architect"]
    assert find_port(spec, "spec", "out") is not None
    assert find_port(spec, "spec", "in") is None
    assert find_port(spec, "nope", "out") is None


@pytest.mark.parametrize(
    ("out_port", "in_port", "expected"),
    [
        (_out("spec", "ArchitectureSpec"), _in("spec", "ArchitectureSpec"), True),
        (_out("spec", "ArchitectureSpec"), _in("plan", "ImplementationPlan"), False),
        (_out("ok", None), _in("trigger", None), True),
        (_out("spec", "ArchitectureSpec"), _in("trigger", None), False),
        (_out("ok", None), _in("spec", "ArchitectureSpec"), False),
        (_in("spec", "ArchitectureSpec"), _in("spec", "ArchitectureSpec"), False),
        (_out("spec", "ArchitectureSpec"), _out("spec", "ArchitectureSpec"), False),
        (_in("spec", "ArchitectureSpec"), _out("spec", "ArchitectureSpec"), False),
    ],
)
def test_ports_compatible_truth_table(out_port, in_port, expected):
    assert ports_compatible(out_port, in_port) is expected


def test_fixture_graph_is_port_compatible_against_seed():
    """Cross-check the fixture against the registry with the E-72 predicate.
    Not validate.py (E-73) -- only types exist and every edge's ports match."""
    graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    types = {n.id: n.type for n in graph.nodes}
    assert set(types.values()) <= set(NODE_TYPES)
    for edge in graph.edges:
        out_port = find_port(NODE_TYPES[types[edge.source]], edge.source_port, "out")
        in_port = find_port(NODE_TYPES[types[edge.target]], edge.target_port, "in")
        assert out_port is not None and in_port is not None, edge
        assert ports_compatible(out_port, in_port), edge


def _broken_registry() -> dict[str, NodeTypeSpec]:
    return {
        "bad_key": _stage("architect", _out("spec", "ArchitectureSpec"), role="architect"),
        "dup": _stage("dup", _in("x", None), _out("x", None)),
        "unknown_payload": _stage("unknown_payload", _out("y", "NoSuchModel")),
        "bad_stage": _stage("bad_stage", _out("ok", None), canonical_stage="plan"),
        "bad_role": _stage("bad_role", _out("ok", None), role="architecht"),
        "gate.bad": NodeTypeSpec(
            type="gate.bad",
            kind="gate",
            role="reviewer",
            canonical_stage="planning",
            ports=(
                _in("artifact", "ImplementationPlan"),
                _out("approve", "ArchitectureSpec"),
                _out("revise", "ImplementationPlan"),
                _out("escalate", None),
            ),
        ),
        "gate.no_artifact": NodeTypeSpec(
            type="gate.no_artifact",
            kind="gate",
            role=None,
            canonical_stage=None,
            ports=(_in("input", None), _out("approve", None)),
        ),
    }


EXPECTED_BROKEN = sorted(
    [
        "bad_key: registry key does not match spec.type 'architect'",
        "dup: duplicate port name 'x'",
        "unknown_payload.y: payload 'NoSuchModel' is not in PAYLOAD_TYPES",
        "bad_stage: canonical_stage 'plan' is not canonical",
        "bad_role: role 'architecht' is not a known registry role",
        "gate.bad: gate type must be role-less",
        "gate.bad: gate out-port 'approve' must carry the artifact payload 'ImplementationPlan'",
        "gate.bad: gate out-port 'reject' must be a signal port",
        "gate.bad: gate out-port 'revise' must carry 'GateDecision'",
        "gate.bad: gate type has unexpected out-port(s): escalate",
        "gate.no_artifact: gate type must have exactly one in-port 'artifact' with a payload",
    ]
)


def test_check_node_types_reports_every_problem_sorted():
    assert check_node_types(_broken_registry()) == EXPECTED_BROKEN


def test_check_node_types_is_order_independent():
    """NFR-10, per-module pattern: identical across registry insertion order."""
    items = list(_broken_registry().items())
    for perm in itertools.permutations(items):
        assert check_node_types(MappingProxyType(dict(perm))) == EXPECTED_BROKEN


def test_payload_resolution_failures(monkeypatch):
    monkeypatch.setattr(
        node_types_module,
        "PAYLOAD_TYPES",
        {
            "Renamed": "sdlc.stages.plan.models:ImplementationPlan",
            "Missing": "sdlc.no_such_module:Thing",
            "NotAModel": "sdlc.core.models:gate_key",
            "NoAttr": "sdlc.core.models:NoSuchClass",
        },
    )
    registry = {
        "t": _stage(
            "t",
            _out("a", "Renamed"),
            _out("b", "Missing"),
            _out("c", "NotAModel"),
            _out("d", "NoAttr"),
        )
    }
    problems = check_node_types(registry)
    assert problems[0] == "t.a: payload 'Renamed' resolves to class 'ImplementationPlan'"
    assert problems[1].startswith("t.b: payload 'Missing' does not resolve (sdlc.no_such_module:")
    assert (
        problems[2]
        == "t.c: payload 'NotAModel' (sdlc.core.models:gate_key) is not a pydantic model"
    )
    assert problems[3].startswith("t.d: payload 'NoAttr' does not resolve (sdlc.core.models:")
    assert len(problems) == 4


def test_gate_reject_must_be_terminal_rejected():
    from sdlc.graph.node_types import NodeTypeSpec as Spec

    bad = Spec(
        type="gate.x",
        kind="gate",
        role=None,
        canonical_stage="architecture",
        ports=(
            NodePort(name="artifact", direction="in", payload="ArchitectureSpec"),
            NodePort(name="approve", direction="out", payload="ArchitectureSpec"),
            NodePort(name="reject", direction="out", payload=None),
        ),
    )
    problems = check_node_types(MappingProxyType({"gate.x": bad}))
    assert "gate.x: gate out-port 'reject' must be terminal='rejected'" in problems


def test_seed_gate_rejects_are_terminal():
    for gate in ("gate.research", "gate.architecture", "gate.plan"):
        reject = find_port(NODE_TYPES[gate], "reject", "out")
        assert reject is not None and reject.terminal == "rejected"


def test_new_payloads_resolve():
    for name in ("AnalyzeResult", "BuildResult", "NodeFailure", "PullRequest"):
        assert node_types_module._resolve_payload(name) is None, name


def test_budget_after_defaults_to_none():
    assert _stage("x.y", _out("o", None)).budget_after == "none"
