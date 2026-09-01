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
from typing import Any, Generic, TypeVar

from ...measurement import CollectionState, Measurement
from ..discover.map import Capability, CapabilityMap
from ..scan.models import (
    C_AUTHN_AUTHZ,
    C_DATA_SENSITIVITY,
    EvidenceRef,
    SecurityObservation,
    security_identity,
)
from .models import (
    EDGE_EVIDENCE_MAX,
    FAM_BOUNDARIES,
    FAM_CASCADES,
    FAM_ESCALATIONS,
    FAM_SHARED,
    CapabilityEdge,
    CapabilityRisk,
    Cascade,
    ControlFamily,
    ControlState,
    EscalationPath,
    Severity,
    SharedVulnerability,
    SystemRisk,
    TrustBoundary,
)
from .rules import (
    BOUNDARY_MAX_ROWS,
    CASCADE_MAX_DEPTH,
    CASCADE_MAX_PATHS,
    CASCADE_SOURCE_MIN_SECURITY,
    ESCALATION_MAX_DEPTH,
    ESCALATION_MAX_PATHS,
    SECURITY_CATEGORIES,
    SHARED_MAX_ROWS,
)
from .severity import REACHABLE_KINDS, max_severity

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
    """Truncate to `cap` and record whether the cap bit.

    Order is the CALLER's responsibility: rows must already be sorted so
    truncation drops the tail rather than an arbitrary subset (NFR-10).
    """
    return FamilyResult(
        collected=Measurement.measured(1.0), rows=tuple(rows[:cap]), truncated=len(rows) > cap
    )


def _uncollected(reason: str) -> FamilyResult[R]:
    return FamilyResult(collected=Measurement.not_collected(reason))


def _owners(capabilities: Iterable[Capability]) -> dict[str, tuple[str, ...]]:
    """path -> (bc_id, ...) in sorted order.

    Attribution allows a file to belong to more than one capability, so the
    index maps a path to a tuple of owners rather than a single owner.
    """
    index: dict[str, list[str]] = {}
    for cap in sorted(capabilities, key=lambda c: c.bc_id):
        for path in cap.member_paths:
            index.setdefault(path, []).append(cap.bc_id)
    return {p: tuple(sorted(set(owners))) for p, owners in index.items()}


def project_edges(
    capabilities: Iterable[Capability], file_edges: Iterable[tuple[str, str]]
) -> tuple[CapabilityEdge, ...]:
    """Project file -> file reference edges into capability -> capability edges.

    Deterministic: input order is ignored, output is sorted by (source_bc_id,
    target_bc_id). Supporting file edges are kept up to EDGE_EVIDENCE_MAX per
    capability edge, deterministically sorted.

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
                supporting.setdefault((src, dst), set()).add((importer, imported))

    out: list[CapabilityEdge] = []
    for (src, dst), pairs in sorted(supporting.items()):
        ordered = sorted(pairs)
        paths: list[str] = []
        for importer, _ in ordered:
            if importer not in paths:
                paths.append(importer)
                if len(paths) == EDGE_EVIDENCE_MAX:
                    break
        out.append(
            CapabilityEdge(
                source_bc_id=src,
                target_bc_id=dst,
                weight=len(ordered),
                evidence=tuple(EvidenceRef(path=p) for p in paths[:EDGE_EVIDENCE_MAX]),
            )
        )
    return tuple(out)


def weakness_class(o: SecurityObservation) -> str:
    """`(signal, rule, key)` -- security_identity with the path removed.

    Computed from the observation rather than parsed out of
    security_identity: a parser over a colon-joined string breaks on the first
    path containing a colon, and two identity schemes derived from each other
    are one scheme with two names.
    """
    return f"{o.signal.value}:{o.rule}:{o.key}"


def shared_vulnerabilities(
    capabilities: Iterable[Capability],
    severities: Mapping[str, Severity],
    *,
    security_collected: bool,
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
            "shared weakness' (FR-915)"
        )

    groups: dict[str, dict] = {}
    for cap in sorted(capabilities, key=lambda c: c.bc_id):
        for o in cap.security:
            group = groups.setdefault(
                weakness_class(o),
                {
                    "signal": o.signal.value,
                    "rule": o.rule,
                    "key": o.key,
                    "bc_ids": set(),
                    "keys": set(),
                },
            )
            group["bc_ids"].add(cap.bc_id)
            group["keys"].add(security_identity(o))

    rows = [
        SharedVulnerability(
            weakness_class=name,
            signal=g["signal"],
            rule=g["rule"],
            key=g["key"],
            bc_ids=tuple(sorted(g["bc_ids"])),
            vulnerability_keys=tuple(sorted(g["keys"])),
            severity=max_severity(severities[k] for k in sorted(g["keys"]) if k in severities),
        )
        for name, g in sorted(groups.items())
        if len(g["bc_ids"]) >= 2 and len(g["keys"]) >= 2
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
            "graph to project capability edges from"
        )
    if not cmap.attribution.graph.parsed:
        return Measurement.not_collected(
            "the reference graph parsed no file, so an absence of edges is "
            "not evidence that the capabilities are independent"
        )
    return Measurement.measured(1.0)


def _adjacency(edges: Iterable[CapabilityEdge]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.source_bc_id, []).append(e.target_bc_id)
    return {k: sorted(set(v)) for k, v in adj.items()}


def _shortest_paths(
    adj: dict[str, list[str]], origin: str, *, max_depth: int
) -> dict[str, tuple[str, ...]]:
    """BFS for shortest paths from `origin`, up to `max_depth` hops.

    Deterministic: adj lists are sorted, so paths of equal length break ties
    lexicographically by node id.
    """
    best: dict[str, tuple[str, ...]] = {}
    queue: deque[tuple[str, ...]] = deque([(origin,)])
    while queue:
        path = queue.popleft()
        node = path[-1]
        if len(path) - 1 >= max_depth:
            continue
        for neighbor in adj.get(node, ()):
            if neighbor in path:  # cycle
                continue
            extended = (*path, neighbor)
            if neighbor not in best or len(extended) < len(best[neighbor]):
                best[neighbor] = extended
                queue.append(extended)
    return best


def cascades(
    risks: Iterable[CapabilityRisk], edges: Iterable[CapabilityEdge], *, graph: Measurement
) -> FamilyResult[Cascade]:
    """Shortest paths from high-security-composite capabilities to all
    reachable capabilities.

    Origins are capabilities with security composite >= CASCADE_SOURCE_MIN_SECURITY.
    """
    if graph.state is not CollectionState.MEASURED:
        return _uncollected(f"cascades need the reference graph: {graph.reason}")

    origins = sorted(
        r.bc_id
        for r in risks
        if (
            r.security.value.state is CollectionState.MEASURED
            and r.security.value.value is not None
            and r.security.value.value >= CASCADE_SOURCE_MIN_SECURITY
        )
    )
    if not origins:
        # If no security composite was MEASURED, cascades did not collect; if
        # composites were measured and none cleared the threshold, that is a
        # measured zero (empty list).
        any_measured = any(r.security.value.state is CollectionState.MEASURED for r in risks)
        if not any_measured:
            return _uncollected(
                "no capability has a MEASURED security composite, so cascade "
                "origins cannot be identified (FR-915)"
            )
        return FamilyResult(collected=Measurement.measured(1.0), rows=())

    adj = _adjacency(edges)
    out: list[Cascade] = []
    for origin in origins:
        paths = _shortest_paths(adj, origin, max_depth=CASCADE_MAX_DEPTH)
        for _target, path in sorted(paths.items()):
            out.append(Cascade(origin=origin, path=path))
    out.sort(key=lambda c: (c.origin, c.impacted))
    return _capped(out, CASCADE_MAX_PATHS)


_NO_JUDGMENT_BOUNDARY = (
    "deterministic baseline: criticality or data sensitivity exposure "
    "differs across this edge; trust boundary verdict is the risk proposer's "
    "judgment, and this row records that no judgment was applied. See "
    "UnifiedRiskMap.judgment for why"
)


def boundary_candidates(
    risks: Iterable[CapabilityRisk],
    capabilities: Iterable[Capability],
    edges: Iterable[CapabilityEdge],
    *,
    sensitivity_collected: bool,
    graph: Measurement,
) -> FamilyResult[TrustBoundary]:
    """Candidate trust boundaries from criticality or sensitivity differences."""
    if graph.state is not CollectionState.MEASURED:
        return _uncollected(f"trust boundaries need the reference graph: {graph.reason}")

    levels = {r.bc_id: r.criticality.level for r in risks}
    criticality_collected = any(r.criticality.level is not None for r in risks)
    if not criticality_collected and not sensitivity_collected:
        return _uncollected(
            "neither criticality nor data sensitivity collected, so no edge "
            "can be seen to cross a trust boundary -- an empty set here would "
            "read as 'every boundary is internal' (FR-915)"
        )

    sensitive = {c.bc_id for c in capabilities if c.sensitivity} if sensitivity_collected else set()

    out: list[TrustBoundary] = []
    for edge in edges:
        src, dst = edge.source_bc_id, edge.target_bc_id
        rule = ""
        if (
            levels.get(src) is not None
            and levels.get(dst) is not None
            and levels[src] is not levels[dst]
        ):
            rule = "criticality_differs"
        elif sensitivity_collected and (src in sensitive) != (dst in sensitive):
            rule = "sensitivity_exposure_differs"
        if not rule:
            continue
        out.append(
            TrustBoundary(
                source_bc_id=src,
                target_bc_id=dst,
                rule=rule,
                rationale=_NO_JUDGMENT_BOUNDARY,
                evidence=edge.evidence,
            )
        )
    out.sort(key=lambda b: (b.source_bc_id, b.target_bc_id))
    return _capped(out, BOUNDARY_MAX_ROWS)


_NO_JUDGMENT_CHAIN = (
    "code enumerated this path as a privilege-escalation candidate; no "
    "judgment was applied -- this is not a finding that the chain is "
    "exploitable. See UnifiedRiskMap.judgment for why"
)


def escalation_candidates(
    risks: Iterable[CapabilityRisk],
    capabilities: Iterable[Capability],
    edges: Iterable[CapabilityEdge],
    *,
    authn_collected: bool = True,
    sensitivity_collected: bool,
    graph: Measurement,
) -> FamilyResult[EscalationPath]:
    """Bounded paths from an unauthenticated entry point to sensitive data.

    KNOWN LIMIT (RD10): authentication-gated, not authorization-gated. RD5
    leaves Authorization with no scan source, so a capability whose
    authentication control reads PRESENT is excluded even though nothing
    collected says whether it authorizes the caller.
    """
    if graph.state is not CollectionState.MEASURED:
        return _uncollected(f"escalation chains need the reference graph: {graph.reason}")
    if not authn_collected:
        return _uncollected(
            "C_AUTHN_AUTHZ did not collect, so no entry point can be "
            "identified as unauthenticated vs authenticated -- an empty set "
            "here would read as 'no escalation path exists' (FR-915)"
        )
    if not sensitivity_collected:
        return _uncollected(
            "SS4 did not collect, so no capability can be identified as "
            "handling sensitive entities and no chain has an end -- an empty "
            "set here would read as 'no escalation path exists' (FR-915)"
        )

    caps = {c.bc_id: c for c in capabilities}
    auth = {
        r.bc_id: next(c for c in r.controls if c.family is ControlFamily.AUTHENTICATION)
        for r in risks
    }
    targets = {bc for bc, cap in caps.items() if cap.sensitivity}

    entries: list[str] = []
    for bc_id in sorted(auth):
        cap = caps.get(bc_id)
        if cap is None or not any(m.kind in REACHABLE_KINDS for m in cap.members):
            continue
        # PRESENT is the one state that disqualifies: ABSENT is a weakness.
        # Only a measured ABSENT control qualifies as an unauthenticated entry.
        if (
            auth[bc_id].collected.state is not CollectionState.MEASURED
            or auth[bc_id].state is not ControlState.ABSENT
        ):
            continue
        entries.append(bc_id)

    adj = _adjacency(edges)
    out: list[EscalationPath] = []
    for entry in entries:
        rule = "entry_authentication_absent"
        for target, path in sorted(
            _shortest_paths(adj, entry, max_depth=ESCALATION_MAX_DEPTH).items()
        ):
            if target not in targets:
                continue
            out.append(EscalationPath(path=path, rule=rule, rationale=_NO_JUDGMENT_CHAIN))
    out.sort(key=lambda p: p.path)
    return _capped(out, ESCALATION_MAX_PATHS)


def system_view(
    cmap: CapabilityMap, risks: tuple[CapabilityRisk, ...], *, collected_categories: frozenset[str]
) -> SystemRisk:
    """RD10 assembled: the projection once, then the four families over it.

    Each family degrades on its OWN inputs -- a missing reference graph costs
    three families and leaves shared vulnerabilities measured. That is the
    per-report degradation E-48's BlueprintComparison already established,
    applied one artifact down.
    """
    graph = graph_state(cmap)
    edges = (
        project_edges(cmap.capabilities, cmap.attribution.graph.edges)
        if graph.state is CollectionState.MEASURED and cmap.attribution is not None
        else ()
    )
    severities = {v.key: v.severity for r in risks for v in r.vulnerabilities}
    sensitivity_collected = C_DATA_SENSITIVITY in collected_categories
    authn_collected = C_AUTHN_AUTHZ in collected_categories

    shared = shared_vulnerabilities(
        cmap.capabilities,
        severities,
        security_collected=bool(SECURITY_CATEGORIES & collected_categories),
    )
    cascade = cascades(risks, edges, graph=graph)
    boundaries = boundary_candidates(
        risks, cmap.capabilities, edges, sensitivity_collected=sensitivity_collected, graph=graph
    )
    chains = escalation_candidates(
        risks,
        cmap.capabilities,
        edges,
        authn_collected=authn_collected,
        sensitivity_collected=sensitivity_collected,
        graph=graph,
    )

    families: dict[str, FamilyResult[Any]] = {
        FAM_SHARED: shared,
        FAM_CASCADES: cascade,
        FAM_BOUNDARIES: boundaries,
        FAM_ESCALATIONS: chains,
    }
    return SystemRisk(
        shared_vulnerabilities=shared.rows,
        shared_vulnerabilities_collected=shared.collected,
        cascades=cascade.rows,
        cascades_collected=cascade.collected,
        trust_boundaries=boundaries.rows,
        trust_boundaries_collected=boundaries.collected,
        escalation_paths=chains.rows,
        escalation_paths_collected=chains.collected,
        truncated=tuple(sorted(name for name, fam in families.items() if fam.truncated)),
    )
