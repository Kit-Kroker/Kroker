"""RD10: the cross-capability system view (E-49 plan 3).

Pure by design -- see the package docstring in models.py.

Two of the four families are FACTS code proves (shared vulnerabilities,
cascades). Two are CANDIDATES code enumerates and the proposer dispositions
(trust boundaries, privilege-escalation chains). Neither judgment family may
invent an edge: candidates come from the projected graph, which is ADR-22
over a graph instead of over a candidate list.

The projection is a re-index of data already on the CapabilityMap --
`attribution.graph.edges` is file -> file, `Capability.member_paths` is
file -> bc_id. No blob is read and nothing is executed (NFR-9).

Every enumeration is sorted and every traversal bounded: NFR-10 requires
byte-identical output across input order, and an unbounded path search over a
dense graph is not a bounded activity.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..discover.map import Capability, CapabilityMap
from ..scan.models import (
    EvidenceRef, SecurityObservation, security_identity,
)
from ...measurement import CollectionState, Measurement
from .models import (
    BoundaryVerdict, CapabilityEdge, CapabilityRisk, Cascade,
    EDGE_EVIDENCE_MAX, Severity, SharedVulnerability, TrustBoundary,
)
from .rules import (
    BOUNDARY_MAX_ROWS, CASCADE_MAX_DEPTH, CASCADE_MAX_PATHS,
    CASCADE_SOURCE_MIN_SECURITY, SHARED_MAX_ROWS,
)
from .severity import max_severity

R = TypeVar("R")


@dataclass(frozen=True)
class FamilyResult(Generic[R]):
    """One family's Measurement, its rows, and whether its cap bit.

    A dataclass rather than a Pydantic model: it never crosses the Temporal
    boundary (RowVerification's precedent in assessment/verification.py).
    system_view unpacks it onto SystemRisk, which is the typed artifact.

    `truncated` is carried rather than inferred: a consumer cannot tell a set
    that ended at the cap from one that ended naturally, and silently dropping
    rows from an audit is the kind of gap FR-915 exists to make visible.
    """
    collected: Measurement
    rows: tuple[R, ...] = ()
    truncated: bool = False


def _capped(rows: list[R], cap: int) -> FamilyResult[R]:
    return FamilyResult(collected=Measurement.measured(1.0),
                        rows=tuple(rows[:cap]), truncated=len(rows) > cap)


def _uncollected(reason: str) -> FamilyResult:
    return FamilyResult(collected=Measurement.not_collected(reason))


def _owners(capabilities: Iterable[Capability]) -> dict[str, tuple[str, ...]]:
    """path -> the bc_ids that own it, sorted.

    A set per path rather than one owner: attribution lets a file belong to
    more than one capability, and picking one would silently drop an edge.
    """
    index: dict[str, set[str]] = {}
    for cap in capabilities:
        for path in cap.member_paths:
            index.setdefault(path, set()).add(cap.bc_id)
    return {path: tuple(sorted(ids)) for path, ids in index.items()}


def project_edges(capabilities: Iterable[Capability],
                  file_edges: Iterable[tuple[str, str]]
                  ) -> tuple[CapabilityEdge, ...]:
    """The file -> file graph projected onto capability -> capability edges.

    Intra-capability edges and edges touching a file no capability owns are
    dropped: neither is a cross-capability fact.
    """
    owners = _owners(capabilities)
    supporting: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for importer, imported in sorted(set(file_edges)):
        for src in owners.get(importer, ()):
            for dst in owners.get(imported, ()):
                if src == dst:
                    continue
                supporting.setdefault((src, dst), set()).add(
                    (importer, imported))

    out: list[CapabilityEdge] = []
    for (src, dst), pairs in sorted(supporting.items()):
        ordered = sorted(pairs)
        paths: list[str] = []
        for importer, _ in ordered:
            if importer not in paths:
                paths.append(importer)
        out.append(CapabilityEdge(
            source_bc_id=src, target_bc_id=dst, weight=len(ordered),
            evidence=tuple(EvidenceRef(path=p)
                           for p in paths[:EDGE_EVIDENCE_MAX])))
    return tuple(out)


def weakness_class(o: SecurityObservation) -> str:
    """`(signal, rule, key)` -- security_identity with the path removed.

    Computed from the observation rather than parsed out of
    security_identity: a parser over a colon-joined string breaks on the first
    path containing a colon, and two identity schemes derived from each other
    are one scheme with two names.
    """
    return f"{o.signal.value}:{o.rule}:{o.key}"


def shared_vulnerabilities(capabilities: Iterable[Capability],
                           severities: Mapping[str, Severity], *,
                           security_collected: bool
                           ) -> FamilyResult[SharedVulnerability]:
    """Weakness classes carried by two or more capabilities.

    `severities` maps a Vulnerability.key to the severity the RD4 table
    already assigned it: the class inherits the highest of its members rather
    than being rated again, so there is one producer of a severity.
    """
    if not security_collected:
        return _uncollected(
            "no security category collected, so no weakness class could be "
            "seen to recur -- an empty shared set here would read as 'no "
            "shared weakness' (FR-915)")

    groups: dict[str, dict] = {}
    for cap in sorted(capabilities, key=lambda c: c.bc_id):
        for o in cap.security:
            group = groups.setdefault(weakness_class(o), {
                "signal": o.signal.value, "rule": o.rule, "key": o.key,
                "bc_ids": set(), "keys": set()})
            group["bc_ids"].add(cap.bc_id)
            group["keys"].add(security_identity(o))

    rows = [
        SharedVulnerability(
            weakness_class=name, signal=g["signal"], rule=g["rule"],
            key=g["key"], bc_ids=tuple(sorted(g["bc_ids"])),
            vulnerability_keys=tuple(sorted(g["keys"])),
            severity=max_severity(severities[k] for k in sorted(g["keys"])
                                  if k in severities))
        for name, g in sorted(groups.items())
        if len(g["bc_ids"]) >= 2
    ]
    return _capped(rows, SHARED_MAX_ROWS)


def graph_state(cmap: CapabilityMap) -> Measurement:
    """MEASURED when the reference graph is evidence, and the reason when it
    is not.

    A graph that parsed no file has zero edges, and zero edges from an
    extractor that ran on nothing is not evidence that the capabilities are
    independent (FR-915).
    """
    if cmap.attribution is None:
        return Measurement.not_collected(
            "discover produced no AttributionReport, so there is no reference "
            "graph to project capability edges from")
    if not cmap.attribution.graph.parsed:
        return Measurement.not_collected(
            "the reference graph parsed no file, so an absence of edges is "
            "not evidence that the capabilities are independent")
    return Measurement.measured(1.0)


def _adjacency(edges: Iterable[CapabilityEdge]) -> dict[str, tuple[str, ...]]:
    out: dict[str, set[str]] = {}
    for edge in edges:
        out.setdefault(edge.source_bc_id, set()).add(edge.target_bc_id)
    return {src: tuple(sorted(dsts)) for src, dsts in out.items()}


def _shortest_paths(adj: dict[str, tuple[str, ...]], origin: str, *,
                    max_depth: int) -> dict[str, tuple[str, ...]]:
    """BFS over sorted adjacency: each reachable capability appears once, with
    its shortest path, and the origin itself is not a result.

    Bounded by max_depth, and deterministic because the frontier is expanded
    in sorted order (NFR-10).
    """
    seen: dict[str, tuple[str, ...]] = {origin: (origin,)}
    queue: deque[str] = deque([origin])
    while queue:
        node = queue.popleft()
        path = seen[node]
        if len(path) - 1 >= max_depth:
            continue
        for nxt in adj.get(node, ()):
            if nxt in seen:
                continue
            seen[nxt] = path + (nxt,)
            queue.append(nxt)
    return {bc: path for bc, path in seen.items() if bc != origin}


def cascades(risks: Iterable[CapabilityRisk],
             edges: Iterable[CapabilityEdge], *,
             graph: Measurement) -> FamilyResult[Cascade]:
    """What a compromise of a high-security-composite capability reaches."""
    if graph.state is not CollectionState.MEASURED:
        return _uncollected(f"cascades need the reference graph: {graph.reason}")

    rows_in = tuple(risks)
    if not any(r.security.value.state is CollectionState.MEASURED
               for r in rows_in):
        return _uncollected(
            "no capability carries a measured security composite, so no "
            "cascade origin could be identified -- an empty cascade set here "
            "would read as 'nothing propagates' (FR-915)")

    origins = sorted(
        r.bc_id for r in rows_in
        if r.security.value.state is CollectionState.MEASURED
        and r.security.value.value >= CASCADE_SOURCE_MIN_SECURITY)
    adj = _adjacency(edges)

    out: list[Cascade] = []
    for origin in origins:
        for _, path in sorted(
                _shortest_paths(adj, origin,
                                max_depth=CASCADE_MAX_DEPTH).items()):
            out.append(Cascade(origin=origin, path=path))
    out.sort(key=lambda c: (c.origin, c.path))
    return _capped(out, CASCADE_MAX_PATHS)


_NO_JUDGMENT_BOUNDARY = (
    "code enumerated this edge as a trust-boundary candidate; no judgment "
    "was applied -- this is not a finding that the boundary is sound. See "
    "UnifiedRiskMap.judgment for why")


def boundary_candidates(risks: Iterable[CapabilityRisk],
                        capabilities: Iterable[Capability],
                        edges: Iterable[CapabilityEdge], *,
                        sensitivity_collected: bool,
                        graph: Measurement) -> FamilyResult[TrustBoundary]:
    """Edges whose endpoints differ in criticality or sensitivity exposure.

    An edge between endpoints we could not RATE is not a candidate and is not
    a non-candidate either -- when neither input collected, the whole family
    reports not_collected rather than an empty set (FR-915).
    """
    if graph.state is not CollectionState.MEASURED:
        return _uncollected(
            f"trust boundaries need the reference graph: {graph.reason}")

    levels = {r.bc_id: r.criticality.level for r in risks}
    criticality_collected = any(v is not None for v in levels.values())
    if not criticality_collected and not sensitivity_collected:
        return _uncollected(
            "neither criticality nor data sensitivity collected, so no edge "
            "can be seen to cross a trust boundary -- an empty set here would "
            "read as 'every boundary is internal' (FR-915)")

    sensitive = {c.bc_id for c in capabilities
                 if c.sensitivity} if sensitivity_collected else set()

    out: list[TrustBoundary] = []
    for edge in edges:
        src, dst = edge.source_bc_id, edge.target_bc_id
        rule = ""
        if (levels.get(src) is not None and levels.get(dst) is not None
                and levels[src] is not levels[dst]):
            rule = "criticality_differs"
        elif sensitivity_collected and (src in sensitive) != (dst in sensitive):
            rule = "sensitivity_exposure_differs"
        if not rule:
            continue
        out.append(TrustBoundary(
            source_bc_id=src, target_bc_id=dst, rule=rule,
            rationale=_NO_JUDGMENT_BOUNDARY, evidence=edge.evidence))
    out.sort(key=lambda b: (b.source_bc_id, b.target_bc_id))
    return _capped(out, BOUNDARY_MAX_ROWS)

