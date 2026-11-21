"""FR-918 (E-51): the cross-reference walk -- c14's audit over the typed ids
the final artifacts cite.

FD15: the census covers structured, id-typed fields ONLY. Gate-report prose
(detail/deferred/reasons) and FindingDisposition are out of scope by
construction -- walking prose would mean parsing strings, the "reading prose
back" anti-goal -- and advisories are prose. FD4/FD9: one ABSOLUTE
CheckResult per domain under a `xref:` wire name, because a citation that
resolves to nothing is a broken artifact, not overridable judgment (FD6: no
repair -- the detail names what it refuses).

`risk/apply.py:87` already enforces this rule where references are CREATED
(a proposer disposition naming a key its capability does not carry is refused
whole); this walk is the belt-and-suspenders audit over the final artifact --
what BrownKit Part B is. FD11 rule 1: a domain whose producer phase did not
measure is an owed row, never a pass and never a fail; zero citation sites
under a measured producer passes -- cited nothing is true, not vacuous.

Pure by design -- the Pydantic models it walks, `...measurement` and
`...gate` only. This module must never import assessment/models.py,
activities.py, or temporalio, exactly as gates/checks.py must not.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...gate import CheckClass, CheckResult, build_check
from ...measurement import CollectionState, Measurement
from ..discover.map import CapabilityMap
from ..risk.models import UnifiedRiskMap

# Wire names (FD10): never renamed once landed -- the GUARD_PATCH_ID rule.
BC_IDS = "xref:bc_ids"
VULNERABILITY_KEYS = "xref:vulnerability_keys"
CAPABILITY_EDGES = "xref:capability_edges"
THREAT_VULNERABILITY_KEYS = "xref:threat_vulnerability_keys"

# Bounded detail -- the house rule (gates/checks.py): a census over many
# dangling citations must stay one readable line.
DETAIL_BUDGET = 300


def _bc_id_records(discover: CapabilityMap) -> frozenset[str]:
    """Records for both bc-id domains: the locked Capability.bc_id set -- the
    ids the identity lock handed out."""
    return frozenset(c.bc_id for c in discover.capabilities)


def _bc_id_cites(risk: UnifiedRiskMap) -> list[str]:
    """Every id-typed field on the risk artifact: CapabilityRisk.bc_id,
    SharedVulnerability.bc_ids, Cascade.path entries, TrustBoundary
    source/target, EscalationPath.path entries."""
    return (
        [c.bc_id for c in risk.capabilities]
        + [bc for s in risk.system.shared_vulnerabilities for bc in s.bc_ids]
        + [bc for c in risk.system.cascades for bc in c.path]
        + [bc for b in risk.system.trust_boundaries for bc in (b.source_bc_id, b.target_bc_id)]
        + [bc for p in risk.system.escalation_paths for bc in p.path]
    )


def _edge_endpoint_cites(risk: UnifiedRiskMap) -> list[str]:
    """Both endpoints of every stored projection of CapabilityEdge -- Cascade
    paths, TrustBoundary endpoints, EscalationPath paths. The edge model
    itself is deliberately not stored (RD10); its projections are."""
    return (
        [bc for c in risk.system.cascades for bc in c.path]
        + [bc for b in risk.system.trust_boundaries for bc in (b.source_bc_id, b.target_bc_id)]
        + [bc for p in risk.system.escalation_paths for bc in p.path]
    )


def _vulnerability_key_records(risk: UnifiedRiskMap) -> frozenset[str]:
    """The union of CapabilityRisk.vulnerabilities[].key across the map."""
    return frozenset(v.key for c in risk.capabilities for v in c.vulnerabilities)


def _vulnerability_key_cites(risk: UnifiedRiskMap) -> list[str]:
    """ThreatAssessment.vulnerability_keys and
    SharedVulnerability.vulnerability_keys members."""
    return [k for c in risk.capabilities for t in c.threats for k in t.vulnerability_keys] + [
        k for s in risk.system.shared_vulnerabilities for k in s.vulnerability_keys
    ]


def _threat_locality_records(risk: UnifiedRiskMap) -> dict[str, frozenset[str]]:
    """Per CapabilityRisk row: the vulnerability keys THAT row carries --
    locality, not the global key union."""
    return {c.bc_id: frozenset(v.key for v in c.vulnerabilities) for c in risk.capabilities}


def _threat_locality_cites(risk: UnifiedRiskMap) -> dict[str, tuple[str, ...]]:
    """Per CapabilityRisk row: the keys its own threats cite."""
    return {
        c.bc_id: tuple(k for t in c.threats for k in t.vulnerability_keys)
        for c in risk.capabilities
    }


def _broken(records: frozenset[str], cites: Iterable[str]) -> list[str]:
    """The citing sites that resolve to no record."""
    return [c for c in cites if c not in records]


def _bounded(sorted_unique: list[str]) -> str:
    """The joined citations, truncated at the detail budget."""
    joined = ", ".join(sorted_unique)
    if len(joined) <= DETAIL_BUDGET:
        return joined
    return joined[: DETAIL_BUDGET - 3] + "..."


def _absolute(name: str, label: str, broken: Iterable[str]) -> CheckResult:
    """One build_check per domain: ABSOLUTE (FD9), detail naming every broken
    citation sorted and bounded (FD6 -- it names what it refuses)."""
    unresolved = sorted(set(broken))
    return build_check(
        name=name,
        passed=not unresolved,
        requested=CheckClass.ABSOLUTE,
        detail="" if not unresolved else f"{label}: {_bounded(unresolved)}",
    )


def _owed(domain: str, phase: str, state: Measurement) -> str:
    """The pinned owed format (FD11 rule 1): the phase's not_collected reason
    verbatim."""
    return f"{domain}: not collected ({phase}: {state.reason})"


def _bc_ids_domain(discover: CapabilityMap, risk: UnifiedRiskMap) -> CheckResult:
    """xref:bc_ids (FD9): every id-typed field on the risk artifact cites a
    capability the identity lock created."""
    return _absolute(
        BC_IDS,
        "unresolved bc_id citations",
        _broken(_bc_id_records(discover), _bc_id_cites(risk)),
    )


def _vulnerability_keys_domain(risk: UnifiedRiskMap) -> CheckResult:
    """xref:vulnerability_keys (FD9): every cited vulnerability key resolves
    to a vulnerability some CapabilityRisk row carries."""
    return _absolute(
        VULNERABILITY_KEYS,
        "unresolved vulnerability key citations",
        _broken(_vulnerability_key_records(risk), _vulnerability_key_cites(risk)),
    )


def _capability_edges_domain(discover: CapabilityMap, risk: UnifiedRiskMap) -> CheckResult:
    """xref:capability_edges (FD9): every bc_id in the stored projections of
    CapabilityEdge resolves to a locked capability, both endpoints."""
    return _absolute(
        CAPABILITY_EDGES,
        "unresolved capability edge endpoints",
        _broken(_bc_id_records(discover), _edge_endpoint_cites(risk)),
    )


def _threat_vulnerability_keys_domain(risk: UnifiedRiskMap) -> CheckResult:
    """xref:threat_vulnerability_keys (FD9): a threat may only cite
    vulnerabilities its OWN CapabilityRisk carries -- the post-hoc audit of
    the rule risk/apply.py:87 enforces where proposer links are created."""
    records = _threat_locality_records(risk)
    broken = [
        f"{bc_id}:{key}"
        for bc_id, keys in _threat_locality_cites(risk).items()
        for key in keys
        if key not in records[bc_id]
    ]
    return _absolute(
        THREAT_VULNERABILITY_KEYS,
        "threat citations outside their own capability",
        broken,
    )


def xref_domains(
    *,
    discover: CapabilityMap | None,
    discover_state: Measurement,
    risk: UnifiedRiskMap | None,
    risk_state: Measurement,
) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]:
    """The four citation domains: (evaluated checks, owed rows), both sorted
    so the caller can slot them straight into FinishReport.

    `discover_state`/`risk_state` are the PHASE-level collection states
    (FD11 rule 1): a domain whose producer phase did not measure is an owed
    row in the pinned format. The records side is checked first -- without
    discover's locked set the census is undefined however many citations
    exist. `xref:bc_ids` and `xref:capability_edges` read both phases;
    `xref:vulnerability_keys` and `xref:threat_vulnerability_keys` live
    entirely on the risk artifact and evaluate even when discover is absent.
    """
    discover_ok = discover_state.state is CollectionState.MEASURED
    risk_ok = risk_state.state is CollectionState.MEASURED
    checks: list[CheckResult] = []
    owed: list[str] = []

    # xref:bc_ids -- records on discover, every id-typed field on risk.
    if not discover_ok:
        owed.append(_owed(BC_IDS, "discover", discover_state))
    elif not risk_ok:
        owed.append(_owed(BC_IDS, "risk", risk_state))
    else:
        assert discover is not None and risk is not None  # measured producers carry their artifact
        checks.append(_bc_ids_domain(discover, risk))

    # xref:vulnerability_keys -- records and cites both live on risk.
    if not risk_ok:
        owed.append(_owed(VULNERABILITY_KEYS, "risk", risk_state))
    else:
        assert risk is not None
        checks.append(_vulnerability_keys_domain(risk))

    # xref:capability_edges -- records on discover, stored projections on risk.
    if not discover_ok:
        owed.append(_owed(CAPABILITY_EDGES, "discover", discover_state))
    elif not risk_ok:
        owed.append(_owed(CAPABILITY_EDGES, "risk", risk_state))
    else:
        assert discover is not None and risk is not None
        checks.append(_capability_edges_domain(discover, risk))

    # xref:threat_vulnerability_keys -- locality, both sides on risk.
    if not risk_ok:
        owed.append(_owed(THREAT_VULNERABILITY_KEYS, "risk", risk_state))
    else:
        assert risk is not None
        checks.append(_threat_vulnerability_keys_domain(risk))

    return tuple(sorted(checks, key=lambda c: c.name)), tuple(sorted(owed))
