"""Graph legality -- the single validator (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§7.

Every consumer (interpreter, CLI, canvas via E-75, tests) calls `validate`;
legality is never reimplemented elsewhere. All checks run and accumulate so
the canvas sees every error at once. A clean report carries the `Topology`
the router runs on; this module is its only producer (spec U7).

Pure: no I/O, no clock. `roles` is passed in (a load_registry()-shaped
mapping) because loading it is I/O. The ADR-6 check imports
sdlc.agents.loader INSIDE its body (sdlc/agents/__init__.py is empty, so that
import runs no registry load).

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.{model,node_types,topology} (spec §4; pinned by
tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import RoleConfig
from .model import GraphEdge, GraphNode, PipelineGraph
from .node_types import NODE_TYPES, NodeTypeSpec, find_port, ports_compatible
from .topology import (
    EdgeKey,
    PortWiring,
    Topology,
    edge_id,
    edge_key,
    forward_adjacency,
    forward_cycles,
    forward_reach,
    is_back_edge,
)


class ProblemCode(StrEnum):
    # T1 identity
    DUPLICATE_NODE_ID = "duplicate_node_id"
    DUPLICATE_EDGE = "duplicate_edge"
    # T2 references
    DANGLING_ENDPOINT = "dangling_endpoint"
    UNKNOWN_NODE_TYPE = "unknown_node_type"
    UNKNOWN_PORT = "unknown_port"
    INCOMPATIBLE_PORTS = "incompatible_ports"
    # T3 node configuration
    ROLE_ON_ROLELESS_TYPE = "role_on_roleless_type"
    GATE_ON_NON_GATE = "gate_on_non_gate"
    LOADER_OWNED_FIELD = "loader_owned_field"
    ROLE_NOT_IN_REGISTRY = "role_not_in_registry"
    ROLE_KIND_MISMATCH = "role_kind_mismatch"
    ROLE_HARNESS_MISSING = "role_harness_missing"
    RESEARCH_PROVIDER_MISSING = "research_provider_missing"
    ADR6_VIOLATION = "adr6_violation"
    ADR6_COMBINATIONS_EXCEEDED = "adr6_combinations_exceeded"
    RESERVED_GATE_NAME = "reserved_gate_name"
    # T4 wiring (router preconditions)
    REQUIRED_IN_PORT_UNCONNECTED = "required_in_port_unconnected"
    MIXED_IN_PORT = "mixed_in_port"
    BACK_PORT_NOT_EXCLUSIVE = "back_port_not_exclusive"
    BACK_EDGE_INTO_MANY = "back_edge_into_many"
    ONE_PORT_MULTIPLE_SOURCES = "one_port_multiple_sources"
    # T5 topology
    FORWARD_CYCLE = "forward_cycle"
    BOUNDED_EDGE_NOT_A_LOOP = "bounded_edge_not_a_loop"
    ENTRY_COUNT = "entry_count"
    UNREACHABLE_NODE = "unreachable_node"


# Gate names that handlers use OUTSIDE graphs (spec §3, §7.3). A gate node's
# name is its id (E-72 D7) and shares PipelineConfig.gates[...] and the signal
# namespace with these, so a graph gate may not take one. E-74 removes
# "merge"/"deploy" when those gates become nodes. "research", "architecture"
# and "plan" are deliberately absent: graph gate nodes take them over.
RESERVED_GATE_NAMES: frozenset[str] = frozenset(
    {
        "budget",
        "clarify",
        "crew_question",
        "deploy",
        "deploy_failed",
        "merge",
        "readiness",
        "risk",
        "tidy_up",
        "tool_approval",
    }
)

# Fail closed past this many role->model combinations (spec §7.4).
ADR6_COMBINATION_CAP = 256


class Problem(BaseModel):
    """One legality problem. Tests and the canvas key on `code`, never on
    `message` text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ProblemCode
    message: str
    node: str | None = None
    edge: EdgeKey | None = None
    port: str | None = None

    def sort_key(self) -> tuple[str, str, EdgeKey | tuple[()], str, str]:
        # None-safe: None never meets a str in a comparison.
        return (self.code.value, self.node or "", self.edge or (), self.port or "", self.message)


class ValidationReport(BaseModel):
    """`topology` is present iff `problems` is empty, and is excluded from
    the JSON dump (E-75 serialises the problems only)."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    problems: tuple[Problem, ...]
    topology: Topology | None = Field(default=None, exclude=True)

    @property
    def ok(self) -> bool:
        return not self.problems


class InvalidGraph(ValueError):
    """Raised by from_graph() when validate() reports problems."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"{p.code.value}: {p.message}" for p in problems))


def _names(items: Iterable[str]) -> str:
    return ", ".join(repr(i) for i in sorted(items))


def _identity_problems(graph: PipelineGraph) -> list[Problem]:
    problems: list[Problem] = []
    for node_id, count in sorted(Counter(n.id for n in graph.nodes).items()):
        if count > 1:
            problems.append(
                Problem(
                    code=ProblemCode.DUPLICATE_NODE_ID,
                    node=node_id,
                    message=f"node id {node_id!r} is used by {count} nodes",
                )
            )
    for key, count in sorted(Counter(edge_key(e) for e in graph.edges).items()):
        if count > 1:
            problems.append(
                Problem(
                    code=ProblemCode.DUPLICATE_EDGE,
                    edge=key,
                    message=f"edge {key[0]}.{key[1]}->{key[2]}.{key[3]} appears {count} times",
                )
            )
    return problems


def _first_nodes(graph: PipelineGraph) -> dict[str, GraphNode]:
    """id -> the first node with that id (nodes are already sorted, so this
    is deterministic even for an illegal duplicate-id draft)."""
    first: dict[str, GraphNode] = {}
    for n in graph.nodes:
        first.setdefault(n.id, n)
    return first


def _reference_problems(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> list[Problem]:
    problems: list[Problem] = []
    for node_id, n in nodes.items():
        if n.type not in registry:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_NODE_TYPE,
                    node=node_id,
                    message=f"node {node_id!r} has unknown type {n.type!r}",
                )
            )
    for e in graph.edges:
        key = edge_key(e)
        for role, endpoint in (("source", e.source), ("target", e.target)):
            if endpoint not in nodes:
                problems.append(
                    Problem(
                        code=ProblemCode.DANGLING_ENDPOINT,
                        edge=key,
                        message=f"edge {edge_id(e)}: {role} {endpoint!r} names no node",
                    )
                )
        source_spec = _spec_of(nodes, registry, e.source)
        target_spec = _spec_of(nodes, registry, e.target)
        out_port = find_port(source_spec, e.source_port, "out") if source_spec else None
        in_port = find_port(target_spec, e.target_port, "in") if target_spec else None
        if source_spec is not None and out_port is None:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_PORT,
                    edge=key,
                    node=e.source,
                    port=e.source_port,
                    message=f"edge {edge_id(e)}: {source_spec.type!r} has no out-port "
                    f"{e.source_port!r}",
                )
            )
        if target_spec is not None and in_port is None:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_PORT,
                    edge=key,
                    node=e.target,
                    port=e.target_port,
                    message=f"edge {edge_id(e)}: {target_spec.type!r} has no in-port "
                    f"{e.target_port!r}",
                )
            )
        if out_port is not None and in_port is not None and not ports_compatible(out_port, in_port):
            problems.append(
                Problem(
                    code=ProblemCode.INCOMPATIBLE_PORTS,
                    edge=key,
                    message=f"edge {edge_id(e)}: payload {out_port.payload!r} does not "
                    f"connect to {in_port.payload!r}",
                )
            )
    return problems


def _spec_of(
    nodes: Mapping[str, GraphNode], registry: Mapping[str, NodeTypeSpec], node_id: str
) -> NodeTypeSpec | None:
    n = nodes.get(node_id)
    return registry.get(n.type) if n is not None else None


def _node_config_problems(
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
    roles: Mapping[str, RoleConfig],
) -> list[Problem]:
    """T3 (spec §7.2): E-72 §5's deferred node-configuration list."""
    problems: list[Problem] = []

    def add(code: ProblemCode, node_id: str, message: str) -> None:
        problems.append(Problem(code=code, node=node_id, message=message))

    for node_id, n in nodes.items():
        spec = registry.get(n.type)
        if spec is None:
            continue  # unknown_node_type already reported; nothing to resolve against
        if spec.kind == "gate" and node_id in RESERVED_GATE_NAMES:
            add(
                ProblemCode.RESERVED_GATE_NAME,
                node_id,
                f"gate node id {node_id!r} is a gate name handlers use outside graphs",
            )
        if n.gate is not None and spec.kind != "gate":
            add(ProblemCode.GATE_ON_NON_GATE, node_id, f"{n.type!r} is not a gate type")
        if n.role is not None and (n.role.instructions is not None or n.role.tool_files):
            add(
                ProblemCode.LOADER_OWNED_FIELD,
                node_id,
                "role.instructions and role.tool_files are loaded from agents/<role>/, "
                "never set on a node",
            )
        if spec.role is None:
            if n.role is not None:
                add(ProblemCode.ROLE_ON_ROLELESS_TYPE, node_id, f"{n.type!r} has no role")
            continue
        if spec.role not in roles:
            add(
                ProblemCode.ROLE_NOT_IN_REGISTRY,
                node_id,
                f"{n.type!r} needs role {spec.role!r}, which the loaded registry lacks",
            )
            continue
        if n.role is None:
            continue
        expected = roles[spec.role].kind
        if n.role.kind != expected:
            add(
                ProblemCode.ROLE_KIND_MISMATCH,
                node_id,
                f"role override kind {n.role.kind!r} != registry {spec.role!r} kind "
                f"{expected!r} (an empty `role: {{}}` defaults to 'harness')",
            )
        elif n.role.kind == "harness" and n.role.harness is None:
            add(
                ProblemCode.ROLE_HARNESS_MISSING,
                node_id,
                "a harness-kind role override must name a harness",
            )
        elif n.role.kind == "research" and n.role.provider is None:
            add(
                ProblemCode.RESEARCH_PROVIDER_MISSING,
                node_id,
                "a research-kind role override must name a provider",
            )
    return problems + _adr6_problems(nodes, registry, roles)


def _adr6_problems(
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
    roles: Mapping[str, RoleConfig],
) -> list[Problem]:
    """ADR-6 over graphs (spec U4, §7.4): the registry's role->model map with
    every graph-used role replaced by the SET of its nodes' effective models
    (mirrors cli_roles.build_role_overrides), then the existing
    validate_run_roles over every combination."""
    from ..agents.loader import RegistryError, validate_run_roles

    models: dict[str, set[str]] = {r: {c.model} for r, c in roles.items() if c.model is not None}
    used: dict[str, set[str]] = {}
    for n in nodes.values():
        spec = registry.get(n.type)
        if spec is None or spec.role is None or spec.role not in roles:
            continue
        model = (n.role.model if n.role is not None else None) or roles[spec.role].model
        if model is not None:
            used.setdefault(spec.role, set()).add(model)
    models.update(used)
    names = sorted(models)
    choices = [sorted(models[r]) for r in names]
    total = math.prod(len(c) for c in choices)
    if total > ADR6_COMBINATION_CAP:
        return [
            Problem(
                code=ProblemCode.ADR6_COMBINATIONS_EXCEEDED,
                message=f"{total} role->model combinations exceed the ADR-6 check cap "
                f"of {ADR6_COMBINATION_CAP}",
            )
        ]
    messages: set[str] = set()
    for combo in itertools.product(*choices):
        try:
            validate_run_roles(dict(zip(names, combo, strict=True)))
        except RegistryError as exc:
            messages.add(str(exc))
    return [Problem(code=ProblemCode.ADR6_VIOLATION, message=m) for m in sorted(messages)]


def _wiring_problems(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> list[Problem]:
    """T4 (spec §7.2): the preconditions the router's semantics rely on.

    An edge takes part on a side only where that side's port resolves.
    Duplicated 4-tuples (already `duplicate_edge`) never take part in the
    classification rules -- their bounds may disagree -- but they still
    count as connecting a required in-port, so a duplicate is reported once."""
    counts = Counter(edge_key(e) for e in graph.edges)
    duplicated = {k for k, c in counts.items() if c > 1}

    def resolves(node_id: str, port: str, direction: Literal["in", "out"]) -> bool:
        spec = _spec_of(nodes, registry, node_id)
        return spec is not None and find_port(spec, port, direction) is not None

    problems: list[Problem] = []
    for node_id, n in nodes.items():
        spec = registry.get(n.type)
        if spec is None:
            continue
        for port in sorted((p for p in spec.ports if p.direction == "in"), key=lambda p: p.name):
            incoming = [
                e for e in graph.edges if e.target == node_id and e.target_port == port.name
            ]
            classified = [e for e in incoming if edge_key(e) not in duplicated]
            forward = [e for e in classified if not is_back_edge(e)]
            back = [e for e in classified if is_back_edge(e)]
            connected_by_duplicate = len(classified) < len(incoming)
            if port.required and not forward and not connected_by_duplicate:
                problems.append(
                    Problem(
                        code=ProblemCode.REQUIRED_IN_PORT_UNCONNECTED,
                        node=node_id,
                        port=port.name,
                        message=f"required in-port {node_id}.{port.name} has no forward "
                        f"(unbounded) in-edge",
                    )
                )
            if forward and back:
                problems.append(
                    Problem(
                        code=ProblemCode.MIXED_IN_PORT,
                        node=node_id,
                        port=port.name,
                        message=f"in-port {node_id}.{port.name} mixes forward and loop in-edges",
                    )
                )
            if port.multiplicity == "many":
                for e in back:
                    problems.append(
                        Problem(
                            code=ProblemCode.BACK_EDGE_INTO_MANY,
                            edge=edge_key(e),
                            message=f"loop edge {edge_id(e)} targets a collect (many) port",
                        )
                    )
            elif len({e.source for e in forward}) > 1:
                problems.append(
                    Problem(
                        code=ProblemCode.ONE_PORT_MULTIPLE_SOURCES,
                        node=node_id,
                        port=port.name,
                        message=f"in-port {node_id}.{port.name} takes one token but is fed by "
                        f"{_names({e.source for e in forward})}; only distinct out-ports of "
                        f"ONE node are mutually exclusive",
                    )
                )
    by_out_port: dict[tuple[str, str], list[GraphEdge]] = {}
    for e in graph.edges:
        if edge_key(e) not in duplicated and resolves(e.source, e.source_port, "out"):
            by_out_port.setdefault((e.source, e.source_port), []).append(e)
    for (source, source_port), edges in sorted(by_out_port.items()):
        if len(edges) > 1 and any(is_back_edge(e) for e in edges):
            problems.append(
                Problem(
                    code=ProblemCode.BACK_PORT_NOT_EXCLUSIVE,
                    node=source,
                    port=source_port,
                    message=f"out-port {source}.{source_port} carries a loop edge, so it must "
                    f"carry no other edge",
                )
            )
    return problems


def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
    problems: list[Problem] = []
    adjacency = forward_adjacency(node_ids, graph.edges)
    for component in forward_cycles(adjacency):
        problems.append(
            Problem(
                code=ProblemCode.FORWARD_CYCLE,
                node=component[0],
                message=f"unbounded cycle through {_names(component)}; "
                f"set max_traversals on the loop edge",
            )
        )
    for e in graph.edges:
        if is_back_edge(e) and e.source not in forward_reach(adjacency, e.target):
            problems.append(
                Problem(
                    code=ProblemCode.BOUNDED_EDGE_NOT_A_LOOP,
                    edge=edge_key(e),
                    message=f"edge {edge_id(e)} carries max_traversals but closes no cycle",
                )
            )
    has_forward_in = {e.target for e in graph.edges if not is_back_edge(e)}
    entries = [n for n in node_ids if n not in has_forward_in]
    if len(entries) != 1:
        problems.append(
            Problem(
                code=ProblemCode.ENTRY_COUNT,
                message=f"a graph needs exactly one entry node (no forward in-edge); "
                f"found {len(entries)}: {_names(entries)}",
            )
        )
    else:
        reached = set(forward_reach(adjacency, entries[0]))
        for n in node_ids:
            if n not in reached:
                problems.append(
                    Problem(
                        code=ProblemCode.UNREACHABLE_NODE,
                        node=n,
                        message=f"node {n!r} is not reachable from entry {entries[0]!r}",
                    )
                )
    return problems


def _build_topology(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> Topology:
    """Called only on a clean graph: every lookup below is known to succeed."""
    node_ids = sorted(nodes)
    adjacency = forward_adjacency(node_ids, graph.edges)
    entry = next(
        n for n in node_ids if n not in {e.target for e in graph.edges if not is_back_edge(e)}
    )
    by_id: dict[str, GraphEdge] = {edge_id(e): e for e in graph.edges}
    out_ports: dict[str, dict[str, tuple[str, ...]]] = {}
    in_ports: dict[str, dict[str, PortWiring]] = {}
    for node_id in node_ids:
        spec = registry[nodes[node_id].type]
        outs: dict[str, tuple[str, ...]] = {}
        ins: dict[str, PortWiring] = {}
        for port in sorted(spec.ports, key=lambda p: (p.direction, p.name)):
            if port.direction == "out":
                outs[port.name] = tuple(
                    i
                    for i, e in sorted(by_id.items())
                    if e.source == node_id and e.source_port == port.name
                )
                continue
            incoming = [
                (i, e)
                for i, e in sorted(by_id.items())
                if e.target == node_id and e.target_port == port.name
            ]
            if incoming:
                ins[port.name] = PortWiring(
                    required=port.required,
                    multiplicity=port.multiplicity,
                    forward_edges=tuple(i for i, e in incoming if not is_back_edge(e)),
                    back_edges=tuple(i for i, e in incoming if is_back_edge(e)),
                )
        out_ports[node_id] = dict(sorted(outs.items()))
        in_ports[node_id] = dict(sorted(ins.items()))
    bounds = {i: e.max_traversals for i, e in sorted(by_id.items()) if e.max_traversals is not None}
    targets = sorted({by_id[i].target for i in bounds})
    return Topology(
        entry=entry,
        node_ids=tuple(node_ids),
        gate_nodes=tuple(n for n in node_ids if registry[nodes[n].type].kind == "gate"),
        edges={i: edge_key(e) for i, e in sorted(by_id.items())},
        bounds=bounds,
        out_ports=out_ports,
        in_ports=in_ports,
        regions={v: forward_reach(adjacency, v) for v in targets},
    )


def validate(
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
    *,
    roles: Mapping[str, RoleConfig],
) -> ValidationReport:
    """Every legality problem of `graph`, sorted; plus its Topology iff none."""
    nodes = _first_nodes(graph)
    identity = _identity_problems(graph)
    references = _reference_problems(graph, nodes, registry)
    problems = (
        identity
        + references
        + _node_config_problems(nodes, registry, roles)
        + _wiring_problems(graph, nodes, registry)
    )
    suppress_topology = any(
        p.code
        in (
            ProblemCode.DUPLICATE_NODE_ID,
            ProblemCode.DUPLICATE_EDGE,
            ProblemCode.DANGLING_ENDPOINT,
        )
        for p in problems
    )
    if not suppress_topology:
        problems += _topology_problems(graph, sorted(nodes))
    ordered = tuple(sorted(problems, key=Problem.sort_key))
    if ordered:
        return ValidationReport(problems=ordered)
    return ValidationReport(problems=(), topology=_build_topology(graph, nodes, registry))
