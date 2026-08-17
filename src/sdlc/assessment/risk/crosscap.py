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

from collections.abc import Iterable

from ..discover.map import Capability
from ..scan.models import EvidenceRef
from .models import CapabilityEdge, EDGE_EVIDENCE_MAX


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
