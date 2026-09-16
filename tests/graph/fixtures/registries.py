"""Test-only registries, roles and graph builders for E-73 (spec §8).

Injected through `registry=` / `roles=` -- never through the seed catalog.
Payload names here are fixture strings: validate.py compares payload names
with `ports_compatible` and never resolves them through PAYLOAD_TYPES.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sdlc.core.models import HarnessKind, RoleConfig
from sdlc.graph.model import GraphEdge, GraphNode, NodePort, PipelineGraph
from sdlc.graph.node_types import NodeTypeSpec


def port_in(
    name: str, payload: str | None, *, required: bool = True, many: bool = False
) -> NodePort:
    return NodePort(
        name=name,
        direction="in",
        payload=payload,
        required=required,
        multiplicity="many" if many else "one",
    )


def port_out(name: str, payload: str | None, *, terminal: str | None = None) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)  # type: ignore[arg-type]


def stage(type_: str, *ports: NodePort, role: str | None = None) -> NodeTypeSpec:
    return NodeTypeSpec(type=type_, kind="stage", role=role, canonical_stage=None, ports=ports)


def gate(type_: str, payload: str) -> NodeTypeSpec:
    return NodeTypeSpec(
        type=type_,
        kind="gate",
        role=None,
        canonical_stage=None,
        ports=(
            port_in("artifact", payload),
            port_out("approve", payload),
            port_out("revise", "GateDecision"),
            port_out("reject", None, terminal="rejected"),
        ),
    )


def registry(*specs: NodeTypeSpec) -> Mapping[str, NodeTypeSpec]:
    return MappingProxyType({s.type: s for s in specs})


def node(id_: str, type_: str, **kw: object) -> GraphNode:
    return GraphNode.model_validate({"id": id_, "type": type_, **kw})


def edge(source: str, target: str, bound: int | None = None) -> GraphEdge:
    """edge("a.out", "b.in", bound=2)"""
    s, sp = source.split(".")
    t, tp = target.split(".")
    return GraphEdge(source=s, source_port=sp, target=t, target_port=tp, max_traversals=bound)


def graph(nodes: list[GraphNode], edges: list[GraphEdge]) -> PipelineGraph:
    return PipelineGraph(schema_version=1, nodes=nodes, edges=edges)


def roles(**overrides: RoleConfig | None) -> dict[str, RoleConfig]:
    """A minimal load_registry()-shaped mapping that passes ADR-6: dev and
    reviewer in different model families. `name=None` removes a role."""
    base: dict[str, RoleConfig] = {
        "architect": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "clarify": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "dev": RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"
        ),
        "planner": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "research": RoleConfig(kind="research", model="anthropic:glm-5.2", provider="fake"),
        "reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
    }
    for name, cfg in overrides.items():
        if cfg is None:
            base.pop(name, None)
        else:
            base[name] = cfg
    return dict(sorted(base.items()))


# GENERIC: small composable types for validator and router tables.
GENERIC = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_in("guidance", "GateDecision", required=False),
        port_out("out", "Art"),
    ),
    stage("sink", port_in("art", "Art"), port_out("done", None)),
    stage("collect", port_in("items", "Art", many=True), port_out("done", None)),
    stage("brancher", port_in("trigger", None), port_out("left", "Art"), port_out("right", "Art")),
    stage(
        "opt2",
        port_in("a", "Art", required=False),
        port_in("b", "Art", required=False),
        port_out("done", None),
    ),
    stage(
        "retry",
        port_in("trigger", None),
        port_in("again", "GateDecision", required=False),
        port_out("out", "Art"),
        port_out("redo", "GateDecision"),
    ),
    stage(
        "refine",
        port_in("art", "Art"),
        port_in("guidance", "GateDecision", required=False),
        port_out("out", "Art"),
    ),
    stage(
        "join",
        port_in("req", "Art"),
        port_in("opt", "Art", required=False),
        port_out("out", "Art"),
    ),
    stage(
        "fixer",
        port_in("trigger", None),
        port_in("opt", "Art", required=False),
        port_out("fix", "GateDecision"),
    ),
    stage("builder", port_in("trigger", None), port_out("out", "Art"), role="dev"),
    stage("critic", port_in("art", "Art"), port_out("done", None), role="reviewer"),
    gate("gate.art", "Art"),
)

# FIX_LOOP: the code stage's fix loop as topology (spec §8, router table 3).
FIX_LOOP = registry(
    stage("start", port_out("ok", None)),
    stage(
        "coder",
        port_in("task", None),
        port_in("guidance", "GateDecision", required=False),
        port_out("patch", "Patch"),
    ),
    stage(
        "qa",
        port_in("patch", "Patch"),
        port_out("pass", "Patch"),
        port_out("fail", "GateDecision"),
        port_out("escalate", "Patch"),
    ),
    gate("gate.task", "Patch"),
)


def fix_loop_graph(max_fix_attempts: int, max_gate_rounds: int) -> PipelineGraph:
    """start -> coder -> qa; qa.fail -> coder (bound M); qa.escalate ->
    task gate; gate.revise -> coder (bound R). qa.pass and gate.approve are
    sinks; gate.reject is unconnected (REJECTED)."""
    return graph(
        [
            node("start", "start"),
            node("coder", "coder"),
            node("qa", "qa"),
            node("task", "gate.task"),
        ],
        [
            edge("start.ok", "coder.task"),
            edge("coder.patch", "qa.patch"),
            edge("qa.fail", "coder.guidance", bound=max_fix_attempts),
            edge("qa.escalate", "task.artifact"),
            edge("task.revise", "coder.guidance", bound=max_gate_rounds),
        ],
    )
