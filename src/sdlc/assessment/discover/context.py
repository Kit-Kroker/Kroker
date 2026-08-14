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
