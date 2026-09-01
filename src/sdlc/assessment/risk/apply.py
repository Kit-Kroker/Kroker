"""RD1/RD7: the proposer's dispositions stamped onto the deterministic map.

Pure by design -- see the package docstring in models.py.

The proposer NEVER authors. Every function here replaces a FIELD on a row
code already produced, and a disposition naming something the baseline does
not carry is dropped rather than created (ADR-22). The composites are not
reachable from this module at all -- they are copied across untouched, which
is what makes E-50's threshold a gate over a number no model wrote.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from ...measurement import CollectionState, Measurement
from ..scan.models import EvidenceRef
from .models import (
    CapabilityRisk,
    ControlCoverage,
    ControlFamily,
    EscalationPath,
    ProposedBoundary,
    ProposedControl,
    ProposedEscalation,
    ProposedThreat,
    ProposedVulnerability,
    RiskProposal,
    RiskSource,
    StrideCategory,
    SystemRisk,
    ThreatAssessment,
    TrustBoundary,
    UnifiedRiskMap,
    Vulnerability,
)

T = TypeVar("T")
K = TypeVar("K")


def degraded(m: UnifiedRiskMap, reason: str) -> UnifiedRiskMap:
    """RD7: the judgment layer did not collect; the composites survive.

    Constructed rather than model_copy'd so every validator re-runs -- an
    update that bypassed _unjudged_carries_no_proposer_rows could strand
    PROPOSER rows on an unjudged map.
    """
    return UnifiedRiskMap(
        capabilities=m.capabilities,
        system=m.system,
        collected=m.collected,
        judgment=Measurement.not_collected(reason),
    )


def _unique(rows: Iterable[T], key: Callable[[T], K]) -> dict[K, T]:
    """The rows whose key appears exactly once (P2-D5).

    A key dispositioned twice is the proposer contradicting itself; picking
    either is picking at random, and the baseline is the honest answer.
    Matches stamp()'s refusal of a duplicated candidate_id.
    """
    seen: dict[K, T] = {}
    dupes: set[K] = set()
    for row in rows:
        k = key(row)
        if k in seen:
            dupes.add(k)
        seen[k] = row
    return {k: v for k, v in seen.items() if k not in dupes}


def _merged(*groups: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Baseline evidence plus the proposer's VERIFIED refs, deduped on
    (path, lines) and sorted. Keyed on a tuple rather than the model itself
    because EvidenceRef is not hashable."""
    merged = {(e.path, e.lines): e for group in groups for e in group}
    return tuple(merged[k] for k in sorted(merged))


def _threats(
    cap: CapabilityRisk, proposed: dict[tuple[str, StrideCategory], ProposedThreat]
) -> tuple[ThreatAssessment, ...]:
    """All six categories, in declaration order, always."""
    keys = {v.key for v in cap.vulnerabilities}
    out: list[ThreatAssessment] = []
    for row in cap.threats:
        p = proposed.get((cap.bc_id, row.category))
        # FR-918's cross-reference integrity, enforced where the reference is
        # made: a threat linking a vulnerability this capability does not
        # carry is refused whole rather than silently unlinked.
        if p is None or not p.rationale.strip() or any(k not in keys for k in p.vulnerability_keys):
            out.append(row)
            continue
        out.append(
            ThreatAssessment(
                category=row.category,
                applicable=p.applicable,
                rationale=p.rationale,
                vulnerability_keys=tuple(sorted(set(p.vulnerability_keys))),
                source=RiskSource.PROPOSER,
            )
        )
    return tuple(out)


def _vulnerabilities(
    cap: CapabilityRisk, proposed: dict[str, ProposedVulnerability]
) -> tuple[Vulnerability, ...]:
    out: list[Vulnerability] = []
    for row in cap.vulnerabilities:
        p = proposed.get(row.key)
        if p is None or not p.rationale.strip():
            out.append(row)
            continue
        out.append(
            Vulnerability(
                key=row.key,
                classification=p.classification,
                # RD4: severity is f(severity_hint, criticality, confidence) and
                # carries no classification term. A CONFIRMED classification does
                # not move it, and a model field for it would overrule the table.
                severity=row.severity,
                stride_category=p.stride_category,
                path=row.path,
                line=row.line,
                evidence=_merged(row.evidence, p.evidence),
                rationale=p.rationale,
                source=RiskSource.PROPOSER,
            )
        )
    return tuple(out)


def _controls(
    cap: CapabilityRisk, proposed: dict[tuple[str, ControlFamily], ProposedControl]
) -> tuple[ControlCoverage, ...]:
    """All five families, in declaration order, always."""
    out: list[ControlCoverage] = []
    for row in cap.controls:
        p = proposed.get((cap.bc_id, row.family))
        # P2-D4: a family whose scan source did not collect may not be
        # dispositioned. RD5 leaves Authorization and Monitoring sourceless,
        # and laundering "we have no signal for this" into "present" is the
        # most expensive over-claim the artifact admits.
        if (
            p is None
            or not p.rationale.strip()
            or row.collected.state is not CollectionState.MEASURED
        ):
            out.append(row)
            continue
        out.append(
            ControlCoverage(
                family=row.family,
                state=p.state,
                collected=row.collected,
                evidence=_merged(row.evidence, p.evidence),
                rule="proposer_disposition",
                rationale=p.rationale,
                source=RiskSource.PROPOSER,
            )
        )
    return tuple(out)


def _normalize_path_id(pid: str) -> str:
    return pid.replace(" ", "")


def _boundaries(
    system: SystemRisk, proposed: dict[tuple[str, str], ProposedBoundary]
) -> tuple[TrustBoundary, ...]:
    if system.trust_boundaries_collected.state is not CollectionState.MEASURED:
        return system.trust_boundaries
    out: list[TrustBoundary] = []
    for row in system.trust_boundaries:
        p = proposed.get((row.source_bc_id, row.target_bc_id))
        if p is None or not p.rationale.strip():
            out.append(row)
            continue
        out.append(
            TrustBoundary(
                source_bc_id=row.source_bc_id,
                target_bc_id=row.target_bc_id,
                rule=row.rule,
                verdict=p.verdict,
                rationale=p.rationale,
                evidence=_merged(row.evidence, p.evidence),
                source=RiskSource.PROPOSER,
            )
        )
    return tuple(out)


def _escalations(
    system: SystemRisk, proposed: dict[str, ProposedEscalation]
) -> tuple[EscalationPath, ...]:
    if system.escalation_paths_collected.state is not CollectionState.MEASURED:
        return system.escalation_paths
    out: list[EscalationPath] = []
    for row in system.escalation_paths:
        p = proposed.get(_normalize_path_id(row.path_id))
        if p is None or not p.rationale.strip():
            out.append(row)
            continue
        out.append(
            EscalationPath(
                path=row.path,
                rule=row.rule,
                verdict=p.verdict,
                rationale=p.rationale,
                evidence=_merged(row.evidence, p.evidence),
                source=RiskSource.PROPOSER,
            )
        )
    return tuple(out)


def apply_system_judgment(system: SystemRisk, proposal: RiskProposal) -> SystemRisk:
    """Stamp the proposer's verdicts onto the candidates code enumerated."""
    boundaries = _unique(proposal.boundaries, lambda r: (r.source_bc_id, r.target_bc_id))
    escalations = _unique(proposal.escalations, lambda r: _normalize_path_id(r.path_id))
    return SystemRisk(
        shared_vulnerabilities=system.shared_vulnerabilities,
        shared_vulnerabilities_collected=system.shared_vulnerabilities_collected,
        cascades=system.cascades,
        cascades_collected=system.cascades_collected,
        trust_boundaries=_boundaries(system, boundaries),
        trust_boundaries_collected=system.trust_boundaries_collected,
        escalation_paths=_escalations(system, escalations),
        escalation_paths_collected=system.escalation_paths_collected,
        truncated=system.truncated,
    )


def apply_judgment(
    baseline: UnifiedRiskMap, proposal: RiskProposal, *, total_proposed: int | None = None
) -> UnifiedRiskMap:
    """Every disposition that names a row the baseline carries.

    A disposition naming an unknown bc_id, key or family is DROPPED, never
    created. An uncollected baseline is returned untouched: RD8 means no
    empty map is constructed anywhere, including here.

    Degrades when nothing landed (Finding 1), distinguishing an empty proposal
    from one whose rows were all refused, so P2-D3's store guard refuses to
    persist a judgment-free map under a proposer key.
    """
    if baseline.collected.state is not CollectionState.MEASURED:
        return baseline

    known = {c.bc_id for c in baseline.capabilities}
    threats = {
        k: v
        for k, v in _unique(proposal.threats, lambda r: (r.bc_id, r.category)).items()
        if k[0] in known
    }
    # Not filtered on bc_id: a key only matches inside the capability that
    # carries it, so an invented key never lands anywhere.
    vulnerabilities = _unique(proposal.vulnerabilities, lambda r: r.key)
    controls = {
        k: v
        for k, v in _unique(proposal.controls, lambda r: (r.bc_id, r.family)).items()
        if k[0] in known
    }

    rows = tuple(
        CapabilityRisk(
            bc_id=c.bc_id,
            criticality=c.criticality,
            threats=_threats(c, threats),
            vulnerabilities=_vulnerabilities(c, vulnerabilities),
            controls=_controls(c, controls),
            # Copied across untouched. The proposer is downstream of the
            # number, never upstream of it (RD1).
            security=c.security,
            qa=c.qa,
            unified=c.unified,
        )
        for c in baseline.capabilities
    )

    system = apply_system_judgment(baseline.system, proposal)

    applied_count = sum(
        sum(1 for t in c.threats if t.source is RiskSource.PROPOSER)
        + sum(1 for v in c.vulnerabilities if v.source is RiskSource.PROPOSER)
        + sum(1 for ctrl in c.controls if ctrl.source is RiskSource.PROPOSER)
        for c in rows
    )
    applied_count += sum(1 for b in system.trust_boundaries if b.source is RiskSource.PROPOSER)
    applied_count += sum(1 for e in system.escalation_paths if e.source is RiskSource.PROPOSER)

    if applied_count == 0:
        total = len(proposal.rows) if total_proposed is None else total_proposed
        if total == 0:
            return degraded(baseline, "the proposer returned no dispositions")
        return degraded(
            baseline, f"the proposer returned {total} row(s) and none survived verification"
        )

    return UnifiedRiskMap(
        capabilities=rows,
        system=system,
        collected=baseline.collected,
        judgment=Measurement.measured(1.0),
    )
