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

from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum

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
    # T5 topology
    FORWARD_CYCLE = "forward_cycle"
    BOUNDED_EDGE_NOT_A_LOOP = "bounded_edge_not_a_loop"
    ENTRY_COUNT = "entry_count"
    UNREACHABLE_NODE = "unreachable_node"


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
    problems = identity + references
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
