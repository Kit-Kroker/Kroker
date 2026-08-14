"""FR-913 (E-48 DD1): the deterministic packet the proposer judges.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio.

Clause D1 (cohesion, coupling, boundary clarity) is computed here rather than
asked of a model, which is ADR-22's whole point: the model disposes over
numbers code produced, and cannot invent a metric.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from ...measurement import Measurement
from ..scan.models import CandidateMember, ScanResult
from . import refgraph
from .map import (
    GUARDRAIL_RULES, CandidateContext, DiscoverContext, GraphSummary,
)

Edges = Sequence[tuple[str, str]]


def _unparsed_reason(member_paths: Collection[str]) -> str:
    return (f"files not parsed: none of this candidate's {len(member_paths)} file(s) "
            f"were parsed by the reference extractor, so an absence of edges is "
            f"not evidence")


def cohesion(member_paths: Collection[str], edges: Edges,
             parsed: Collection[str]) -> Measurement:
    """The share of edges touching this candidate that stay inside it.

    Fails closed twice, for two different absences. Unparsed files yield no
    edges, so a score computed over them would report structure we never
    read. And a parsed candidate that no edge touches may be a set of leaves
    rather than an incoherent boundary -- measured(0.0) would assert the
    second (FR-915).
    """
    if not any(p in parsed for p in member_paths):
        return Measurement.not_collected(_unparsed_reason(member_paths))
    inside = set(member_paths)
    touching = [(a, b) for a, b in edges if a in inside or b in inside]
    if not touching:
        return Measurement.not_collected(
            "no reference-graph edge touches this candidate's files, so its "
            "internal coherence was not measured")
    internal = sum(1 for a, b in touching if a in inside and b in inside)
    return Measurement.measured(internal / len(touching))


def coupling(candidate_id: str, member_paths: Collection[str], edges: Edges,
             owner_of: Mapping[str, Collection[str]],
             parsed: Collection[str]) -> Measurement:
    """How many OTHER candidates this one reaches, or is reached by.

    A count, not a ratio: "payments touches three other capabilities" is the
    sentence clause D1 needs, and normalising it would hide the scale.

    Zero is a real answer once the files parsed -- unlike cohesion, an
    isolated capability is a meaningful finding rather than an absence of
    evidence. The unparsed guard still applies.
    """
    if not any(p in parsed for p in member_paths):
        return Measurement.not_collected(_unparsed_reason(member_paths))
    inside = set(member_paths)
    partners: set[str] = set()
    for a, b in edges:
        if a in inside:
            partners.update(owner_of.get(b, ()))
        if b in inside:
            partners.update(owner_of.get(a, ()))
    partners.discard(candidate_id)
    return Measurement.measured(float(len(partners)))


# S3 and S4 are the entry-point signals; attribute() takes the paths that host
# one so a referenced-by-an-entry-point file is ATTACHED rather than orphaned.
_ENTRY_SIGNALS = ("S3", "S4")


def entry_point_paths(scan: ScanResult) -> tuple[str, ...]:
    """Paths hosting an S3/S4 entry point, for E-47b's attribute()."""
    return tuple(sorted({
        m.path for s in scan.sources if s.signal.value in _ENTRY_SIGNALS
        for m in s.members if m.path}))


def build_context(scan: ScanResult, inventory: Mapping[str, str],
                  skipped: Sequence[str]) -> DiscoverContext:
    """Everything code can compute about the candidate set (DD1).

    The reference graph is built here and DISCARDED: only its summary and the
    metrics derived from it reach the packet, because the packet travels
    through workflow history to the proposer and an edge list there is the
    open FR-702 hazard (DD4).
    """
    graph = refgraph.build(inventory)
    parsed = set(graph.parsed)
    rule_of = {s.local_id: s.rule for s in scan.sources}

    owner_of: dict[str, set[str]] = {}
    for cand in scan.candidates:
        for member in cand.members:
            if member.path:
                owner_of.setdefault(member.path, set()).add(cand.candidate_id)

    contexts: list[CandidateContext] = []
    for cand in sorted(scan.candidates, key=lambda c: c.candidate_id):
        paths = sorted({m.path for m in cand.members if m.path})
        rules = tuple(sorted({rule_of[s] for s in cand.sources
                              if s in rule_of}))
        member_set = set(paths)
        contexts.append(CandidateContext(
            candidate_id=cand.candidate_id,
            name=cand.name,
            confidence=cand.confidence,
            sources=tuple(sorted(cand.sources)),
            source_rules=rules,
            members=tuple(sorted(cand.members,
                                 key=CandidateMember.sort_key)),
            member_paths=tuple(paths),
            cohesion=cohesion(member_set, graph.edges, parsed),
            coupling=coupling(cand.candidate_id, member_set, graph.edges,
                              owner_of, parsed),
            guardrail_only=bool(rules) and all(
                r in GUARDRAIL_RULES for r in rules),
            possible_duplicate_of=tuple(sorted(cand.possible_duplicate_of)),
            security=tuple(o for o in scan.security if o.path in member_set),
            sensitivity=tuple(
                r for r in scan.data_sensitivity
                if any(e.path in member_set for e in r.evidence)),
            testability=tuple(f for f in scan.testability
                              if f.path in member_set),
            coverage=tuple(c for c in scan.coverage if c.path in member_set),
        ))

    return DiscoverContext(
        candidates=tuple(contexts),
        entry_point_paths=entry_point_paths(scan),
        graph=GraphSummary(
            parsed=len(graph.parsed), unparsed=len(graph.unparsed),
            edges=len(graph.edges),
            unresolved_relative_rate=graph.unresolved_relative_rate),
        file_count=len(inventory),
        skipped=tuple(sorted(skipped)),
        collected=Measurement.measured(float(len(contexts))))
