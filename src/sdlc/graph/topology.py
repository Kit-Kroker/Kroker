"""Loop structure of a pipeline graph (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§4-§5.

Pure graph algorithms over node ids and edge endpoints -- no registry, no
roles. A BACK edge is exactly an edge carrying `max_traversals` (spec U3);
every other edge is FORWARD. `Topology` is the precomputed structure the
router runs on. Its only producer is validate.py (spec U7), so a router is
only ever built over a legal graph.

No set types are stored: every collection is a sorted tuple or a mapping
built in sorted-key order (NFR-10, skeptic F8).

Edge ids are "source.source_port->target.target_port". Ids and port names
match ^[a-z][a-z0-9_]*$, and '-' and '.' sort below every character an id
can contain, so sorting edge ids as strings sorts their endpoint 4-tuples.

Module-level imports stay within stdlib and sdlc.graph.model (spec §4;
pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from .model import GraphEdge

EdgeKey = tuple[str, str, str, str]


def edge_key(edge: GraphEdge) -> EdgeKey:
    return (edge.source, edge.source_port, edge.target, edge.target_port)


def edge_id(edge: GraphEdge) -> str:
    return f"{edge.source}.{edge.source_port}->{edge.target}.{edge.target_port}"


def is_back_edge(edge: GraphEdge) -> bool:
    """Spec U3: an edge is a back (loop) edge iff it carries a bound."""
    return edge.max_traversals is not None


def forward_adjacency(
    node_ids: Iterable[str], edges: Iterable[GraphEdge]
) -> dict[str, tuple[str, ...]]:
    """node -> sorted distinct forward successors. Bounded edges and edges
    whose endpoints are not in `node_ids` are ignored."""
    targets: dict[str, set[str]] = {n: set() for n in sorted(set(node_ids))}
    for edge in edges:
        if not is_back_edge(edge) and edge.source in targets and edge.target in targets:
            targets[edge.source].add(edge.target)
    return {n: tuple(sorted(succ)) for n, succ in targets.items()}


def forward_reach(adjacency: Mapping[str, tuple[str, ...]], start: str) -> tuple[str, ...]:
    """`start` plus every node reachable from it, sorted."""
    seen = {start}
    stack = [start]
    while stack:
        for succ in adjacency.get(stack.pop(), ()):
            if succ not in seen:
                seen.add(succ)
                stack.append(succ)
    return tuple(sorted(seen))


def forward_cycles(adjacency: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Non-trivial strongly connected components (size > 1, or one node with
    a self edge): members sorted, components sorted. Iterative Tarjan over
    sorted roots, so the result never depends on dict or DFS order."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[tuple[str, ...]] = []
    counter = 0

    for root in sorted(adjacency):
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(adjacency.get(root, ())))]
        while work:
            node, successors = work[-1]
            descended = False
            for succ in successors:
                if succ not in index:
                    index[succ] = low[succ] = counter
                    counter += 1
                    stack.append(succ)
                    on_stack.add(succ)
                    work.append((succ, iter(adjacency.get(succ, ()))))
                    descended = True
                    break
                if succ in on_stack:
                    low[node] = min(low[node], index[succ])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, ()):
                    components.append(tuple(sorted(component)))
    return tuple(sorted(components))


@dataclass(frozen=True)
class PortWiring:
    """One CONNECTED in-port of one node, resolved against the registry."""

    required: bool
    multiplicity: Literal["one", "many"]
    forward_edges: tuple[str, ...]  # edge ids, sorted
    back_edges: tuple[str, ...]  # edge ids, sorted


@dataclass(frozen=True)
class Topology:
    """Everything the router needs, resolved once from a LEGAL graph.

    Built only by sdlc.graph.validate (spec U7). Mappings are built in
    sorted-key order; tuples are sorted."""

    entry: str
    node_ids: tuple[str, ...]
    gate_nodes: tuple[str, ...]  # nodes whose type kind is "gate"
    edges: Mapping[str, EdgeKey]  # edge id -> endpoints
    bounds: Mapping[str, int]  # back edge id -> max_traversals
    out_ports: Mapping[str, Mapping[str, tuple[str, ...]]]  # node -> EVERY out-port -> edge ids
    in_ports: Mapping[str, Mapping[str, PortWiring]]  # node -> connected in-port -> wiring
    regions: Mapping[str, tuple[str, ...]]  # back-edge target v -> REGION(v)
    # node -> terminal out-port -> outcome
    terminal_ports: Mapping[str, Mapping[str, Literal["rejected", "failed"]]]
