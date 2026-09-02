"""FR-917 (E-50): the risk gate's pure evaluation -- GD3/GD4's clauses.

Pure by design -- see the package docstring in models.py.
"""

from __future__ import annotations

from ...dispositions.models import FindingDisposition
from ...gate import CheckClass, CheckResult
from ...measurement import CollectionState
from ..discover.map import CapabilityMap
from ..risk.models import Criticality, UnifiedRiskMap, VulnerabilityClass
from ..scan.models import testability_identity
from .models import RiskGateReport, RiskGateVerdict


def unaccepted_confirmed_vulnerabilities(
    risk_map: UnifiedRiskMap, dispositions: tuple[FindingDisposition, ...]
) -> CheckResult | None:
    """GD3: defers when the judgment layer did not run -- CONFIRMED is only
    reachable through it (risk/build.py stamps every baseline row
    POTENTIAL), so a map with no judgment layer must not read as clean.
    """
    if risk_map.judgment.state is not CollectionState.MEASURED:
        return None

    accepted = {d.key for d in dispositions if d.kind == "vulnerability"}
    offending = sorted(
        {
            v.key
            for cap in risk_map.capabilities
            for v in cap.vulnerabilities
            if v.classification is VulnerabilityClass.CONFIRMED and v.key not in accepted
        }
    )
    passed = not offending
    return CheckResult(
        name="risk_no_unaccepted_confirmed_vuln",
        passed=passed,
        classification=CheckClass.ABSOLUTE,
        detail="" if passed else f"unaccepted confirmed vulnerabilities: {offending}",
    )


def high_criticality_testability_blockers(
    risk_map: UnifiedRiskMap,
    capability_map: CapabilityMap,
    dispositions: tuple[FindingDisposition, ...],
) -> tuple[CheckResult | None, tuple[str, ...]]:
    """GD3: evaluated per (bc_id, finding) pair. An uncollected criticality
    -- or a bc_id with no matching row in the risk map at all -- defers
    only its own pair, never the whole clause: a sibling capability being
    measured must not silently clear it (the mixed-criticality fix), and a
    bc_id the risk phase never scored must not silently drop its blocker
    either (the same silent-skip shape, one join away).
    """
    testability_by_bc_id = {cap.bc_id: cap.testability for cap in capability_map.capabilities}
    criticality_by_bc_id = {c.bc_id: c.criticality for c in risk_map.capabilities}
    accepted = {d.key for d in dispositions if d.kind == "testability"}

    offending: set[str] = set()
    deferred: list[str] = []
    for bc_id in sorted(testability_by_bc_id):
        blockers = [f for f in testability_by_bc_id[bc_id] if f.severity == "blocks"]
        if not blockers:
            continue
        rating = criticality_by_bc_id.get(bc_id)
        if rating is None:
            deferred.extend(
                f"testability blocker for {bc_id} ({testability_identity(f)}): "
                f"no matching capability in the risk map"
                for f in sorted(blockers, key=testability_identity)
            )
        elif rating.collected.state is not CollectionState.MEASURED:
            deferred.extend(
                f"testability blocker for {bc_id} ({testability_identity(f)}): "
                f"criticality is not_collected"
                for f in sorted(blockers, key=testability_identity)
            )
        elif rating.level is Criticality.HIGH:
            offending.update(
                testability_identity(f) for f in blockers if testability_identity(f) not in accepted
            )

    offending_sorted = sorted(offending)
    check = CheckResult(
        name="risk_no_high_criticality_testability_blocker",
        passed=not offending_sorted,
        classification=CheckClass.ABSOLUTE,
        detail=(
            ""
            if not offending_sorted
            else f"testability blockers on HIGH capabilities: {offending_sorted}"
        ),
    )
    return check, tuple(sorted(deferred))


def composite_threshold(
    risk_map: UnifiedRiskMap,
) -> tuple[CheckResult | None, RiskGateVerdict | None, tuple[str, ...]]:
    """GD4: per capability, worst-instance semantics -- CapabilityRisk.unified
    is the only place a composite exists; there is no single map-level value.
    """
    measured_block: list[str] = []
    measured_warn: list[str] = []
    deferred: list[str] = []
    any_measured = False

    for cap in sorted(risk_map.capabilities, key=lambda c: c.bc_id):
        m = cap.unified.value
        if m.state is not CollectionState.MEASURED:
            deferred.append(f"unified composite for {cap.bc_id}: {m.reason}")
            continue
        any_measured = True
        assert m.value is not None
        if m.value >= 0.8:
            measured_block.append(cap.bc_id)
        elif m.value >= 0.6:
            measured_warn.append(cap.bc_id)

    if not any_measured:
        return None, None, tuple(sorted(deferred))

    # GD5: detail names every contributing bc_id even when the check PASSES
    # -- a WARN-band-only capability must still be visible in the report's
    # `reasons` (evaluate() surfaces every non-empty detail regardless of
    # passed/failed), not just a BLOCK-band one.
    detail_parts = []
    if measured_block:
        detail_parts.append(f"unified composite >= 0.8 for: {sorted(measured_block)}")
    if measured_warn:
        detail_parts.append(f"unified composite in [0.6, 0.8) for: {sorted(measured_warn)}")
    check = CheckResult(
        name="risk_composite_below_threshold",
        passed=not measured_block,
        classification=CheckClass.ABSOLUTE,
        detail="; ".join(detail_parts),
    )
    warn = RiskGateVerdict.WARN if (not measured_block and measured_warn) else None
    return check, warn, tuple(sorted(deferred))


def evaluate(
    risk_map: UnifiedRiskMap,
    capability_map: CapabilityMap,
    dispositions: tuple[FindingDisposition, ...],
) -> RiskGateReport:
    """FR-917: the three clauses, GD4's precedence -- BLOCK > WARN > PASS."""
    vuln_check = unaccepted_confirmed_vulnerabilities(risk_map, dispositions)
    testability_check, testability_deferred = high_criticality_testability_blockers(
        risk_map, capability_map, dispositions
    )
    composite_check, composite_warn, composite_deferred = composite_threshold(risk_map)

    checks = tuple(
        sorted(
            (c for c in (vuln_check, testability_check, composite_check) if c is not None),
            key=lambda c: c.name,
        )
    )

    deferred: list[str] = [*testability_deferred, *composite_deferred]
    if vuln_check is None:
        deferred.append(
            "unaccepted-confirmed-vulnerability clause: judgment layer did not run "
            f"({risk_map.judgment.reason})"
        )

    blocking = [c.name for c in checks if not c.passed]
    if blocking:
        verdict = RiskGateVerdict.BLOCK
    elif composite_warn is RiskGateVerdict.WARN:
        verdict = RiskGateVerdict.WARN
    else:
        verdict = RiskGateVerdict.PASS

    reasons = tuple(sorted({c.detail for c in checks if c.detail}))
    return RiskGateReport(
        verdict=verdict,
        checks=checks,
        deferred=tuple(sorted(set(deferred))),
        reasons=reasons,
    )
