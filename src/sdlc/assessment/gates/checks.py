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
