"""FR-913 (E-48 DD1): the deterministic packet the proposer judges.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio.

Clause D1 (cohesion, coupling, boundary clarity) is computed here rather than
asked of a model, which is ADR-22's whole point: the model disposes over
numbers code produced, and cannot invent a metric.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import CandidateMember, ScanResult, ScanSignalId
from . import refgraph
from .map import (
    GUARDRAIL_RULES,
    CandidateContext,
    DiscoverContext,
    GraphSummary,
)

Edges = Sequence[tuple[str, str]]


def _unparsed_reason(member_paths: Collection[str]) -> str:
    return (
        f"files not parsed: none of this candidate's {len(member_paths)} file(s) "
        f"were parsed by the reference extractor, so an absence of edges is "
        f"not evidence"
    )


def cohesion(member_paths: Collection[str], edges: Edges, parsed: Collection[str]) -> Measurement:
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
            "internal coherence was not measured"
        )
    internal = sum(1 for a, b in touching if a in inside and b in inside)
    return Measurement.measured(internal / len(touching))


def coupling(
    candidate_id: str,
    member_paths: Collection[str],
    edges: Edges,
    owner_of: Mapping[str, Collection[str]],
    parsed: Collection[str],
) -> Measurement:
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
_ENTRY_SIGNALS: frozenset[ScanSignalId] = frozenset({ScanSignalId.S3, ScanSignalId.S4})


def entry_point_paths(scan: ScanResult) -> tuple[str, ...]:
    """Paths hosting an S3/S4 entry point, for E-47b's attribute()."""
    return tuple(
        sorted(
            {
                m.path
                for s in scan.sources
                if s.signal in _ENTRY_SIGNALS
                for m in s.members
                if m.path
            }
        )
    )


def build_context(
    scan: ScanResult, inventory: Mapping[str, str], skipped: Sequence[str]
) -> DiscoverContext:
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
        rules = tuple(sorted({rule_of.get(s, "unresolved") for s in cand.sources}))
        member_set = set(paths)
        contexts.append(
            CandidateContext(
                candidate_id=cand.candidate_id,
                name=cand.name,
                confidence=cand.confidence,
                sources=tuple(sorted(cand.sources)),
                source_rules=rules,
                members=tuple(sorted(cand.members, key=CandidateMember.sort_key)),
                member_paths=tuple(paths),
                cohesion=cohesion(member_set, graph.edges, parsed),
                coupling=coupling(cand.candidate_id, member_set, graph.edges, owner_of, parsed),
                guardrail_only=bool(rules) and all(r in GUARDRAIL_RULES for r in rules),
                possible_duplicate_of=tuple(sorted(cand.possible_duplicate_of)),
                security=tuple(o for o in scan.security if o.path in member_set),
                sensitivity=tuple(
                    r
                    for r in scan.data_sensitivity
                    if any(e.path in member_set for e in r.evidence)
                ),
                testability=tuple(f for f in scan.testability if f.path in member_set),
                coverage=tuple(c for c in scan.coverage if c.path in member_set),
            )
        )

    return DiscoverContext(
        candidates=tuple(contexts),
        entry_point_paths=entry_point_paths(scan),
        graph=GraphSummary(
            parsed=len(graph.parsed),
            unparsed=len(graph.unparsed),
            edges=len(graph.edges),
            unresolved_relative_rate=graph.unresolved_relative_rate,
        ),
        file_count=len(inventory) + len(skipped),
        skipped=tuple(sorted(skipped)),
        collected=Measurement.measured(float(len(contexts))),
    )


def _row(scan: ScanResult, signal_id: ScanSignalId) -> Measurement:
    row = next((r for r in scan.signals if r.signal is signal_id), None)
    if row is None:
        return Measurement.not_collected(f"{signal_id.value} has no row in this ScanResult")
    return row.collected


def schema_collected(scan: ScanResult) -> Measurement:
    """S2's row, which is assign()'s `schema_collected` argument."""
    return _row(scan, ScanSignalId.S2)


def contract_collected(scan: ScanResult) -> Measurement:
    """S3 AND S4, as one Measurement (P2-D5).

    decompose() documents its argument as "S3's (and S4's) collection state",
    and CONTRACT_KINDS includes FRONTEND_ROUTE, which only S4 emits. Deriving
    this from S3 alone would let a dead S4 read as a capability that genuinely
    exposes no frontend route -- the FR-915 conflation, one signal removed.
    """
    rows = {sid: _row(scan, sid) for sid in (ScanSignalId.S3, ScanSignalId.S4)}
    degraded = sorted(
        (sid.value, m) for sid, m in rows.items() if m.state is not CollectionState.MEASURED
    )
    if degraded:
        name, measurement = degraded[0]
        return Measurement.not_collected(f"{name} did not collect: {measurement.reason}")
    return Measurement.measured(sum(m.value or 0.0 for m in rows.values()))


def render_discover_prompt(context: DiscoverContext, *, max_members: int = 20) -> str:
    """Bounded, deterministic prompt rendering of DiscoverContext.

    Renders all candidates in the context so no candidate is omitted
    from proposer adjudication, and announces member cuts (NFR-10).
    """
    lines: list[str] = [
        f"# Discover Candidates ({len(context.candidates)})",
        f"Files: {context.file_count} (parsed: {context.graph.parsed}, "
        f"unparsed: {context.graph.unparsed}, edges: {context.graph.edges})",
        "",
    ]
    for c in context.candidates:
        coh_str = (
            f"{c.cohesion.value:.2f}"
            if c.cohesion.state is CollectionState.MEASURED
            else f"({c.cohesion.reason})"
        )
        coup_str = (
            f"{int(c.coupling.value)}"
            if c.coupling.state is CollectionState.MEASURED and c.coupling.value is not None
            else f"({c.coupling.reason})"
        )
        lines.append(f"## Candidate {c.candidate_id}: {c.name}")
        lines.append(f"- Confidence: {c.confidence.value}")
        lines.append(f"- Rules: {', '.join(c.source_rules) or 'none'}")
        lines.append(f"- Cohesion: {coh_str}, Coupling: {coup_str}")
        if c.possible_duplicate_of:
            lines.append(f"- Possible duplicate of: {', '.join(c.possible_duplicate_of)}")
        if c.guardrail_only:
            lines.append("- Guardrail only: true (layer/container naming)")
        if c.security:
            lines.append(
                f"- Security findings ({len(c.security)}): "
                f"{', '.join(f'{s.rule} ({s.severity_hint})' for s in c.security)}"
            )
        if c.sensitivity:
            lines.append(
                f"- Sensitivity records ({len(c.sensitivity)}): "
                f"{', '.join(f'{s.entity}:{s.classification.value}' for s in c.sensitivity)}"
            )
        if c.testability:
            lines.append(
                f"- Testability findings ({len(c.testability)}): "
                f"{', '.join(f'{t.pattern} ({t.severity})' for t in c.testability)}"
            )
        if c.coverage:
            lines.append(f"- Coverage records: {len(c.coverage)}")
        lines.append(f"- Members ({len(c.members)}):")
        for m in c.members[:max_members]:
            loc = f" ({m.path}:{m.line})" if m.line else f" ({m.path})" if m.path else ""
            lines.append(f"  - [{m.kind.value}] {m.value}{loc}")
        if len(c.members) > max_members:
            lines.append(f"  … {len(c.members) - max_members} more member(s)")
        lines.append("")

    return "\n".join(lines)
