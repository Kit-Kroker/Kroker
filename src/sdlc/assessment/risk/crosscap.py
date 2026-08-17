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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..discover.map import Capability
from ..scan.models import (
    EvidenceRef, SecurityObservation, security_identity,
)
from ...measurement import Measurement
from .models import (
    CapabilityEdge, EDGE_EVIDENCE_MAX, Severity, SharedVulnerability,
)
from .rules import SHARED_MAX_ROWS
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
