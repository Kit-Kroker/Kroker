# tests/test_assessment_finish.py
"""FR-918 (E-51): the per-phase exits and `evaluate_finish`, the single
entry point the workflow wires inline (FD16). FD4: exits carry the
`exit:<phase>:` prefix and the xref walk joins them -- finish's own exits
ARE the 14 criteria plus the walk, no separate rows. FD11's three states
apply to exits verbatim: an absent producer phase is owed, a measured
producer with a not_collected sub-artifact is an evaluated fail, measured
inputs are pass/fail by predicate."""

from __future__ import annotations

from sdlc.assessment.discover.map import (
    BlueprintComparison,
    BlueprintStatus,
    CapabilityMap,
    DomainModel,
)
from sdlc.assessment.discover.models import (
    AttributionReport,
    EntityOwnership,
    FileBucket,
    OwnershipOutcome,
    OwnershipReport,
    OwnershipVerb,
    ReferenceGraph,
)
from sdlc.assessment.finish import evaluate_finish
from sdlc.assessment.finish.crossref import (
    BC_IDS,
    CAPABILITY_EDGES,
    THREAT_VULNERABILITY_KEYS,
    VULNERABILITY_KEYS,
)
from sdlc.assessment.finish.models import CRITERIA_MANIFEST
from sdlc.assessment.risk.models import (
    SYSTEM_FAMILIES,
    Composite,
    Driver,
    Factor,
    RiskSource,
    Severity,
    StrideCategory,
    SystemRisk,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE,
    CATEGORIES,
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    CoverageRecord,
    EvidenceRef,
    MemberKind,
    ScanCandidate,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SecurityObservation,
    Sensitivity,
    SensitivityRecord,
    SignalSource,
    TestabilityFinding,
    family_of,
)
from sdlc.gate import CheckClass
from sdlc.measurement import CollectionState, Measurement
from tests.helpers_risk import capability, capability_risk

C07_DEFERRED = "c07_unified_drivers: deferred (E-56)"
C13_OWED = "c13_five_reports: not collected (E-52)"
REPORT_OWED = "exit:report:reports_emitted: not collected (E-52)"
GENERATE_OWED = "exit:generate:seeds_emitted: not collected (E-52)"
EXIT_NAMES = {
    "exit:scan:signals_measured",
    "exit:scan:candidates_present",
    "exit:discover:identity_lock_held",
    "exit:discover:orphans_classified",
    "exit:discover:ownership_resolved",
    "exit:assess:covers_locked_set",
    "exit:assess:judgment_honest",
}
XREF_NAMES = {BC_IDS, VULNERABILITY_KEYS, CAPABILITY_EDGES, THREAT_VULNERABILITY_KEYS}


def _measured() -> Measurement:
    return Measurement.measured(1.0)


# --- scan: thirteen signal rows, optionally degraded -------------------


def _candidate() -> ScanCandidate:
    return ScanCandidate(
        candidate_id="C-01",
        name="Payments",
        sources=["S1-payments"],
        confidence=Confidence.LOW,  # derived: one distinct source signal (D8)
        members=[CandidateMember(kind=MemberKind.DB_TABLE, value="orders")],
    )


def _scan(*, ss: bool = True, qs: bool = True, candidates: bool = True) -> ScanResult:
    """All thirteen signal rows, with the SS/QS families optionally degraded
    to not_collected -- a row that did not collect did not report."""

    def row(signal: ScanSignalId) -> ScanSignalResult:
        looked = (
            ss if signal.value.startswith("SS") else qs if signal.value.startswith("QS") else True
        )
        collected = (
            _measured() if looked else Measurement.not_collected(f"{signal.value} did not collect")
        )
        return ScanSignalResult(
            signal=signal,
            family=family_of(signal),
            version=1,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={category: collected for category in CATEGORIES[signal]},
        )

    return ScanResult(
        signals=[row(s) for s in SCAN_ORDER],
        candidates=[_candidate()] if candidates else [],
    )


def _security() -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1,
        category=C_CREDENTIAL_STORAGE,
        rule="ss1_hardcoded_secret",
        detail="hardcoded credential",
        severity_hint="high",
        path="a.py",
        confidence=Confidence.HIGH,
    )


def _sensitivity() -> SensitivityRecord:
    return SensitivityRecord(
        classification=Sensitivity.PII,
        entity="users",
        origin="table",
        fields=["email"],
        rule="ss4_pii",
        confidence=Confidence.HIGH,
    )


def _testability() -> TestabilityFinding:
    return TestabilityFinding(
        severity="smell",
        pattern="static-clock-access",
        detail="clock read at module scope",
        recommended_seam="inject a clock",
        path="a.py",
    )


def _coverage() -> CoverageRecord:
    return CoverageRecord(
        scope="file",
        path="a.py",
        covered=Measurement.measured(50.0),
        source="proxy",
        confidence=Confidence.LOW,
    )


def _contexted(bc_id: str):
    """A capability carrying every context field, so c01/c02/c12 pass."""
    return capability(
        bc_id,
        member_paths=("a.py",),
        security=(_security(),),
        sensitivity=(_sensitivity(),),
        testability=(_testability(),),
        coverage=(_coverage(),),
    )


# --- discover sub-reports ---------------------------------------------


def _attribution() -> AttributionReport:
    cov = Measurement.measured(0.95)
    return AttributionReport(
        counts={bucket: 0 for bucket in FileBucket},
        coverage=cov,
        meets_floor=cov.value is not None and cov.value >= 0.90,
        graph=ReferenceGraph(unresolved_relative_rate=Measurement.measured(0.0)),
    )


def _blueprint() -> BlueprintComparison:
    return BlueprintComparison(
        collected=_measured(),
        counts={status: 0 for status in BlueprintStatus},
    )


def _domain_model() -> DomainModel:
    return DomainModel(
        collected=_measured(),
        counts={outcome: 0 for outcome in OwnershipOutcome},
    )


def _ownership() -> OwnershipReport:
    rows = (
        EntityOwnership(
            entity="orders",
            outcome=OwnershipOutcome.OWNED,
            owner="BC-001",
            verb=OwnershipVerb.OWNS,
            rule="declaration",
            claimants=("BC-001",),
        ),
    )
    return OwnershipReport(
        entities=rows,
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=_measured(),
    )


_CLEAN = object()


def _discover_map(
    *caps,
    attribution=_CLEAN,
    blueprint=_CLEAN,
    domain_model=_CLEAN,
    ownership=_CLEAN,
    total_references: int = 0,
) -> CapabilityMap:
    """A measured map. `_CLEAN` builds the measured sub-report; pass None to
    omit it (a measured discover whose sub-report never landed -- FD11 rule
    2's shape)."""
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    subs = {
        "attribution": attribution if attribution is not _CLEAN else _attribution(),
        "blueprint": blueprint if blueprint is not _CLEAN else _blueprint(),
        "domain_model": domain_model if domain_model is not _CLEAN else _domain_model(),
        "ownership": ownership if ownership is not _CLEAN else _ownership(),
    }
    return CapabilityMap(
        capabilities=tuple(caps),
        by_action=actions,
        total_references=total_references,
        collected=_measured(),
        **subs,
    )


def _clean_discover(*bc_ids: str, total_references: int = 3) -> CapabilityMap:
    return _discover_map(
        *(_contexted(bc) for bc in (bc_ids or ("BC-001", "BC-002"))),
        total_references=total_references,
    )


# --- risk rows --------------------------------------------------------


def _scored(value: float = 0.5, *, key: str = "a") -> Composite:
    factor = Factor(key=key, value=Measurement.measured(1.0))
    return Composite(
        value=Measurement.measured(value),
        factors=(factor,),
        drivers=(Driver(factor_key=key, value=1.0, contribution=value),),
    )


_NO_SCORE = Composite(value=Measurement.not_collected("no factors collected"))


def _vuln(key: str, *, evidence: bool = True) -> Vulnerability:
    return Vulnerability(
        key=key,
        classification=VulnerabilityClass.POTENTIAL,
        severity=Severity.HIGH,
        stride_category=StrideCategory.SPOOFING,
        path="a.py",
        evidence=(EvidenceRef(path="a.py", lines="1-2"),) if evidence else (),
        source=RiskSource.BASELINE,
    )


def _system() -> SystemRisk:
    collected = {family: _measured() for family in SYSTEM_FAMILIES}
    return SystemRisk(**{f"{family}_collected": m for family, m in collected.items()})


_JUDGED = Measurement.measured(1.0)


def _clean_risk(*bc_ids, judgment=_JUDGED) -> UnifiedRiskMap:
    """A measured map: security/qa scored, every vulnerability evidenced, the
    whole system collected, judgment measured. `unified` carries no drivers'
    source until E-56 (RD3), so c07 defers -- the honest every-run shape the
    orchestration composes."""
    rows = [
        capability_risk(
            bc,
            security=_scored(),
            qa=_scored(),
            unified=_NO_SCORE,
            vulnerabilities=(_vuln(f"k{i}"),),
        )
        for i, bc in enumerate(sorted(bc_ids), 1)
    ]
    return UnifiedRiskMap(
        capabilities=tuple(rows),
        system=_system(),
        collected=_measured(),
        judgment=judgment,
    )


# --- the call ---------------------------------------------------------


def _finish(**kw):
    """evaluate_finish with the clean defaults, overridden per test."""
    defaults = {
        "scan": _scan(),
        "scan_state": _measured(),
        "discover": _clean_discover("BC-001", "BC-002"),
        "discover_state": _measured(),
        "risk": _clean_risk("BC-001", "BC-002"),
        "risk_state": _measured(),
    }
    return evaluate_finish(**{**defaults, **kw})


def _ratio(report) -> float:
    """The composer's formula, recomputed independently: passed ABSOLUTE rows
    over total ABSOLUTE rows across criteria + exits."""
    absolutes = [
        r for r in (*report.criteria, *report.exits) if r.classification is CheckClass.ABSOLUTE
    ]
    return sum(1 for r in absolutes if r.passed) / len(absolutes)


# --- orchestration ----------------------------------------------------


def test_orchestration_composes_all_three():
    """Clean artifacts: criteria carry the twelve evaluable members, exits
    carry the seven per-phase rows plus the four xref domains, and owed is
    exactly the four static rows (c07/c13/report/generate)."""
    report = _finish()
    criteria_names = {c.name for c in report.criteria}
    assert criteria_names == set(CRITERIA_MANIFEST) - {"c07_unified_drivers", "c13_five_reports"}
    assert all(c.passed for c in report.criteria)
    exit_names = {c.name for c in report.exits}
    assert EXIT_NAMES <= exit_names
    assert XREF_NAMES <= exit_names
    assert all(c.passed for c in report.exits)
    assert report.owed == (C07_DEFERRED, C13_OWED, GENERATE_OWED, REPORT_OWED)
    assert report.collected.state is CollectionState.MEASURED
    assert report.collected.value == _ratio(report)
    assert report.passed is True


def test_ratio_when_scan_only():
    """Only scan measured: every producer family is owed, only the scan exits
    evaluate -- and a degraded signal row makes the honest ratio < 1."""
    report = _finish(
        scan=_scan(qs=False),
        discover=None,
        discover_state=Measurement.not_collected("lock failed"),
        risk=None,
        risk_state=Measurement.not_collected("assess failed"),
    )
    assert report.criteria == ()  # every criterion's producer family is owed
    assert {o.split(":")[0] for o in report.owed} >= set(CRITERIA_MANIFEST)
    scan_rows = {c.name: c for c in report.exits}
    assert set(scan_rows) == {"exit:scan:signals_measured", "exit:scan:candidates_present"}
    assert scan_rows["exit:scan:signals_measured"].passed is False
    assert "QS2" in scan_rows["exit:scan:signals_measured"].detail
    assert scan_rows["exit:scan:candidates_present"].passed is True
    for name, phase, reason in (
        ("exit:discover:identity_lock_held", "discover", "lock failed"),
        ("exit:discover:orphans_classified", "discover", "lock failed"),
        ("exit:discover:ownership_resolved", "discover", "lock failed"),
        ("exit:assess:covers_locked_set", "risk", "assess failed"),
        ("exit:assess:judgment_honest", "risk", "assess failed"),
    ):
        assert f"{name}: not collected ({phase}: {reason})" in report.owed, name
    assert report.collected.state is CollectionState.MEASURED
    assert report.collected.value == _ratio(report)
    assert report.collected.value < 1.0


def test_exits_owed_for_unbuilt_phases():
    """report/generate are unbuilt (E-52): their exits are the two pinned
    owed rows on every run -- never CheckResults in `exits` (FD14)."""
    report = _finish()
    assert REPORT_OWED in report.owed
    assert GENERATE_OWED in report.owed
    names = {c.name for c in report.exits}
    assert "exit:report:reports_emitted" not in names
    assert "exit:generate:seeds_emitted" not in names


def test_sorted_everything():
    """NFR-10: the orchestrator's output constructs FinishReport without
    raising -- the sorted/dedup validators ran and the merges stayed sorted."""
    report = _finish(scan=_scan(ss=False))  # a degraded SS family still composes
    criteria_names = [c.name for c in report.criteria]
    exit_names = [c.name for c in report.exits]
    assert criteria_names == sorted(criteria_names)
    assert exit_names == sorted(exit_names)
    assert list(report.owed) == sorted(set(report.owed))
    assert len(set(exit_names)) == len(exit_names)
