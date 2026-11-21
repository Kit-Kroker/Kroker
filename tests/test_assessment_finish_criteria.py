# tests/test_assessment_finish_criteria.py
"""FR-918 (E-51): the 14 criteria -- three-state predicates over the typed
artifacts. Owed is a row, never a pass or a fail (FD3/FD11); c07 defers to
E-56 (FD12); c08 records a baseline run instead of failing it (FD17)."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover.map import (
    BlueprintComparison,
    BlueprintStatus,
    CapabilityMap,
    DomainModel,
)
from sdlc.assessment.discover.models import (
    AttributionReport,
    FileBucket,
    OwnershipOutcome,
    ReferenceGraph,
)
from sdlc.assessment.finish.checks import evaluate_criteria
from sdlc.assessment.finish.crossref import xref_domains
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
    Confidence,
    CoverageRecord,
    EvidenceRef,
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
from sdlc.gate import CheckClass, CheckResult
from sdlc.measurement import CollectionState, Measurement
from tests.helpers_risk import capability, capability_risk

DISCOVER_FAMILY = {
    "c01_security_context",
    "c02_qa_context",
    "c03_stride_per_capability",
    "c08_findings_traceable",
    "c10_coverage_floor",
    "c11_blueprint_comparison",
    "c12_domain_model_traceability",
}
RISK_FAMILY = {
    "c03_stride_per_capability",
    "c04_vulnerabilities_mapped",
    "c05_security_scoring",
    "c06_qa_scoring",
    "c07_unified_drivers",
    "c08_findings_traceable",
    "c09_cross_capability_risks",
}
C13_OWED = "c13_five_reports: not collected (E-52)"
C14 = "c14_cross_reference_integrity"


def _measured() -> Measurement:
    return Measurement.measured(1.0)


# --- scan: the honesty registry c01/c02 read --------------------------


def _scan(*, ss: bool = True, qs: bool = True) -> ScanResult:
    """All thirteen signal rows, with the SS/QS families optionally degraded
    to not_collected -- the honest marker that excuses a bare capability."""

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

    return ScanResult(signals=[row(s) for s in SCAN_ORDER])


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


def _bare(bc_id: str):
    """A capability with no context at all -- c01/c02's failure shape."""
    return capability(bc_id)


# --- discover sub-reports ---------------------------------------------


def _attribution(coverage: Measurement | None = None) -> AttributionReport:
    cov = coverage if coverage is not None else Measurement.measured(0.95)
    return AttributionReport(
        counts={bucket: 0 for bucket in FileBucket},
        coverage=cov,
        meets_floor=cov.state is CollectionState.MEASURED
        and cov.value is not None
        and cov.value >= 0.90,
        graph=ReferenceGraph(unresolved_relative_rate=Measurement.measured(0.0)),
    )


def _blueprint(collected: Measurement | None = None) -> BlueprintComparison:
    if collected is not None and collected.state is not CollectionState.MEASURED:
        return BlueprintComparison(collected=collected)
    return BlueprintComparison(
        collected=collected if collected is not None else _measured(),
        counts={status: 0 for status in BlueprintStatus},
    )


def _domain_model(collected: Measurement | None = None) -> DomainModel:
    if collected is not None and collected.state is not CollectionState.MEASURED:
        return DomainModel(collected=collected)
    return DomainModel(
        collected=collected if collected is not None else _measured(),
        counts={outcome: 0 for outcome in OwnershipOutcome},
    )


_CLEAN = object()


def _discover_map(
    *caps,
    attribution=_CLEAN,
    blueprint=_CLEAN,
    domain_model=_CLEAN,
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
    }
    return CapabilityMap(
        capabilities=tuple(caps),
        by_action=actions,
        total_references=total_references,
        collected=_measured(),
        **subs,
    )


# --- risk rows --------------------------------------------------------


def _scored(value: float = 0.5, *, key: str = "a") -> Composite:
    """A MEASURED composite with one collected factor and its driver (the
    post-E-56 shape c07 evaluates)."""
    factor = Factor(key=key, value=Measurement.measured(1.0))
    return Composite(
        value=Measurement.measured(value),
        factors=(factor,),
        drivers=(Driver(factor_key=key, value=1.0, contribution=value),),
    )


def _partial() -> Composite:
    """Honest partial (RD3): some factors collected, the rest carry reasons."""
    return Composite(
        value=Measurement.not_collected("factors did not all collect"),
        factors=(
            Factor(key="a", value=Measurement.measured(1.0)),
            Factor(key="b", value=Measurement.not_collected("QS2 did not collect")),
        ),
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


def _risk_row(bc_id: str, *, security=None, qa=None, unified=None, vulnerabilities=()):
    return capability_risk(
        bc_id,
        security=security if security is not None else _scored(),
        qa=qa if qa is not None else _scored(),
        unified=unified if unified is not None else _scored(0.7),
        vulnerabilities=vulnerabilities,
    )


def _system(degrade: str | None = None) -> SystemRisk:
    collected = {family: _measured() for family in SYSTEM_FAMILIES}
    if degrade is not None:
        collected[degrade] = Measurement.not_collected("cross-capability analysis did not run")
    return SystemRisk(**{f"{family}_collected": m for family, m in collected.items()})


def _risk_map(*rows, system: SystemRisk | None = None, judgment: Measurement | None = None):
    kw = {} if judgment is None else {"judgment": judgment}
    return UnifiedRiskMap(
        capabilities=tuple(sorted(rows, key=lambda r: r.bc_id)),
        system=system if system is not None else _system(),
        collected=_measured(),
        **kw,
    )


_JUDGED = Measurement.measured(1.0)


def _clean_risk(*bc_ids, unified=None, judgment=_JUDGED):
    """A measured map over the given capabilities: every composite scored
    (`unified` carries a driver), every vulnerability evidenced, the whole
    system collected, judgment measured. Pass judgment=None to omit the
    field -- the model default not_collected, the baseline-only shape."""
    rows = [
        _risk_row(bc, vulnerabilities=(_vuln(f"k{i}"),), unified=unified)
        for i, bc in enumerate(sorted(bc_ids), 1)
    ]
    kw = {} if judgment is None else {"judgment": judgment}
    return UnifiedRiskMap(
        capabilities=tuple(rows),
        system=_system(),
        collected=_measured(),
        **kw,
    )


def _clean_discover(*bc_ids: str, total_references: int = 3) -> CapabilityMap:
    return _discover_map(
        *(_contexted(bc) for bc in (bc_ids or ("BC-001", "BC-002"))),
        total_references=total_references,
    )


# --- the call ---------------------------------------------------------


def _xref(discover, risk, *, dstate=None, rstate=None):
    """Real xref results, exactly what orchestration hands evaluate_criteria
    (xref_domains is called once, upsteam -- never by checks.py)."""
    checks, owed = xref_domains(
        discover=discover,
        discover_state=dstate if dstate is not None else _measured(),
        risk=risk,
        risk_state=rstate if rstate is not None else _measured(),
    )
    return checks, owed


def _evaluate(
    *,
    discover=None,
    discover_state=None,
    risk=None,
    risk_state=None,
    scan=None,
    scan_state=None,
    xref_checks=(),
    xref_owed=(),
):
    return evaluate_criteria(
        scan=scan,
        scan_state=scan_state if scan_state is not None else _measured(),
        discover=discover,
        discover_state=discover_state if discover_state is not None else _measured(),
        risk=risk,
        risk_state=risk_state if risk_state is not None else _measured(),
        xref_checks=xref_checks,
        xref_owed=xref_owed,
    )


# --- the clean run ----------------------------------------------------


def test_clean_run_evaluates_thirteen_criteria():
    """Clean artifacts: c01-c12 + c14 evaluate and pass; c13 is the only owed
    row; everything is sorted (NFR-10)."""
    discover, risk = _clean_discover(), _clean_risk("BC-001", "BC-002")
    xc, xo = _xref(discover, risk)
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo
    )
    names = [c.name for c in checks]
    assert len(checks) == 13
    assert set(names) == set(CRITERIA_MANIFEST) - {"c13_five_reports"}
    assert names == sorted(names)
    assert all(c.passed for c in checks)
    assert owed == (C13_OWED,)


def test_manifest_pin():
    """FD3: evaluated names plus owed ids total exactly the 14 -- every
    member of the manifest stays addressable in every run shape."""
    discover, risk = _clean_discover(), _clean_risk("BC-001", "BC-002")
    xc, xo = _xref(discover, risk)
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo
    )
    assert {r.name for r in checks} | {o.split(":")[0] for o in owed} == set(CRITERIA_MANIFEST)


def test_classifications_follow_the_design_table():
    """FD9: structural presence and the derived xref AND are ABSOLUTE; the
    documented-shortfall criteria (c05/c06 honesty, c10 floor, c11) are
    ADVISORY."""
    discover, risk = _clean_discover(), _clean_risk("BC-001", "BC-002")
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    advisory = {
        "c05_security_scoring",
        "c06_qa_scoring",
        "c10_coverage_floor",
        "c11_blueprint_comparison",
    }
    for c in checks:
        expected = CheckClass.ADVISORY if c.name in advisory else CheckClass.ABSOLUTE
        assert c.classification is expected, c.name


# --- the static deferrals ---------------------------------------------


def test_c07_deferred_to_e56():
    """FD12: while any .unified composite is unmeasured (every run until
    E-56), c07 is the deferred row -- evaluated never."""
    discover = _clean_discover("BC-001", "BC-002")
    risk = _clean_risk("BC-001", "BC-002", unified=_NO_SCORE)
    xc, xo = _xref(discover, risk)
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo
    )
    assert "c07_unified_drivers" not in {c.name for c in checks}
    assert owed == (
        "c07_unified_drivers: deferred (E-56)",
        C13_OWED,
    )


def test_c13_owed_to_e52():
    discover, risk = _clean_discover(), _clean_risk("BC-001")
    xc, xo = _xref(discover, risk)
    _, owed = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    assert C13_OWED in owed


# --- the input classes the plan names ---------------------------------


def test_c08_baseline_run_records_not_fails():
    """FD17: propose_discover-off shape -- zero references under a judgment
    layer that never ran is recorded with its mode, never failed."""
    discover = _clean_discover("BC-001", "BC-002", total_references=0)
    risk = _clean_risk("BC-001", "BC-002", judgment=None)
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    c08 = next(c for c in checks if c.name == "c08_findings_traceable")
    assert c08.passed is True
    assert "baseline-only" in c08.detail


def test_c10_subreport_not_collected_fails_not_owed():
    """FD11 rule 2: discover measured, its attribution coverage
    not_collected -- an evaluated fail carrying the reason, never owed."""
    discover = _discover_map(
        _contexted("BC-001"),
        attribution=_attribution(Measurement.not_collected("blobs unreadable")),
    )
    risk = _clean_risk("BC-001")
    xc, xo = _xref(discover, risk)
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo
    )
    c10 = next(c for c in checks if c.name == "c10_coverage_floor")
    assert c10.passed is False
    assert "blobs unreadable" in c10.detail
    assert "c10_coverage_floor" not in {o.split(":")[0] for o in owed}


def test_degraded_subreports_fail_and_carry_reasons():
    """The other FD11 rule 2 shapes: attribution absent, blueprint
    uncollected, domain model absent, one system family uncollected -- each
    an evaluated fail, each saying why."""
    discover = _discover_map(
        _contexted("BC-001"),
        attribution=None,
        blueprint=_blueprint(Measurement.not_collected("no blueprint file")),
        domain_model=None,
    )
    risk = _risk_map(_risk_row("BC-001"), system=_system(degrade="trust_boundaries"))
    xc, xo = _xref(discover, risk)
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo
    )
    by_name = {c.name: c for c in checks}
    assert by_name["c10_coverage_floor"].passed is False
    assert "attribution report absent" in by_name["c10_coverage_floor"].detail
    assert by_name["c11_blueprint_comparison"].passed is False
    assert "no blueprint file" in by_name["c11_blueprint_comparison"].detail
    assert by_name["c12_domain_model_traceability"].passed is False
    assert "domain model absent" in by_name["c12_domain_model_traceability"].detail
    assert by_name["c09_cross_capability_risks"].passed is False
    assert "trust_boundaries" in by_name["c09_cross_capability_risks"].detail
    evaluated_fails = {n for n, c in by_name.items() if not c.passed}
    assert evaluated_fails & {o.split(":")[0] for o in owed} == set()


@pytest.mark.parametrize(
    ("phase", "family"),
    [
        ("discover", DISCOVER_FAMILY),
        ("risk", RISK_FAMILY),
    ],
)
def test_producer_absent_makes_family_owed(phase, family):
    """FD11 rule 1: an absent producer makes every criterion in its family
    an owed row naming the phase and its reason verbatim; the other family
    still evaluates; c14 follows the walk's own owed rows."""
    reason = "lock failed" if phase == "discover" else "assess failed"
    state = Measurement.not_collected(reason)
    dstate = state if phase == "discover" else _measured()
    rstate = state if phase == "risk" else _measured()
    discover = None if phase == "discover" else _clean_discover("BC-001", "BC-002")
    risk = None if phase == "risk" else _clean_risk("BC-001", "BC-002")
    xc, xo = _xref(discover, risk, dstate=dstate, rstate=rstate)
    checks, owed = _evaluate(
        discover=discover,
        discover_state=dstate,
        risk=risk,
        risk_state=rstate,
        scan=_scan(),
        xref_checks=xc,
        xref_owed=xo,
    )
    surviving = set(CRITERIA_MANIFEST) - family - {"c13_five_reports", C14}
    assert {c.name for c in checks} == surviving
    assert all(c.passed for c in checks)
    assert {o.split(":")[0] for o in owed} == family | {"c13_five_reports", C14}
    for o in owed:
        if o.split(":")[0] == "c13_five_reports":
            continue  # static owner (E-52), never the phase
        assert f"({phase}: {reason})" in o, o


def test_c14_follows_xref():
    """c14 is the derived AND over the walk: one failed domain fails it
    naming the domain; any owed row owes it with the same owner (FD3)."""
    discover, risk = _clean_discover(), _clean_risk("BC-001", "BC-002")
    good, _ = _xref(discover, risk)
    failing = (
        CheckResult(
            name="xref:bc_ids",
            passed=False,
            classification=CheckClass.ABSOLUTE,
            detail="unresolved bc_id citations: BC-099",
        ),
        *good[1:],
    )
    checks, owed = _evaluate(
        discover=discover, risk=risk, scan=_scan(), xref_checks=failing, xref_owed=()
    )
    c14 = next(c for c in checks if c.name == C14)
    assert c14.passed is False
    assert "xref:bc_ids" in c14.detail
    assert c14.classification is CheckClass.ABSOLUTE

    checks, owed = _evaluate(
        discover=None,
        discover_state=Measurement.not_collected("lock failed"),
        risk=risk,
        scan=_scan(),
        xref_checks=failing,
        xref_owed=("xref:bc_ids: not collected (discover: lock failed)",),
    )
    assert f"{C14}: not collected (discover: lock failed)" in owed
    assert C14 not in {c.name for c in checks}


# --- predicate details the wrapper hides ------------------------------


def test_bare_capabilities_fail_and_honest_scan_passes_them():
    """c01/c02: a capability with no context fails, named -- unless the scan
    recorded not_collected for every signal feeding that context (D6's
    honest marker)."""
    discover = _discover_map(_bare("BC-001"))
    risk = _clean_risk("BC-001")
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    by_name = {c.name: c for c in checks}
    assert by_name["c01_security_context"].passed is False
    assert "BC-001" in by_name["c01_security_context"].detail
    assert by_name["c02_qa_context"].passed is False
    assert "BC-001" in by_name["c02_qa_context"].detail

    checks, _ = _evaluate(
        discover=discover,
        risk=risk,
        scan=_scan(ss=False, qs=False),
        xref_checks=xc,
        xref_owed=xo,
    )
    by_name = {c.name: c for c in checks}
    assert by_name["c01_security_context"].passed is True
    assert by_name["c02_qa_context"].passed is True


def test_c03_names_missing_capabilities():
    discover = _discover_map(_contexted("BC-001"), _contexted("BC-002"))
    risk = _clean_risk("BC-001")
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    c03 = next(c for c in checks if c.name == "c03_stride_per_capability")
    assert c03.passed is False
    assert "BC-002" in c03.detail


def test_c04_names_unverified_vulnerabilities():
    discover = _discover_map(_contexted("BC-001"))
    risk = _risk_map(_risk_row("BC-001", vulnerabilities=(_vuln("k1", evidence=False),)))
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    c04 = next(c for c in checks if c.name == "c04_vulnerabilities_mapped")
    assert c04.passed is False
    assert "k1" in c04.detail


def test_c05_fails_unscored_security_while_c06_passes_honest_partial():
    """c05 fails a security composite that never scored; c06 passes the honest
    partial -- RD3 makes qa partial on every run until E-56 (FD8)."""
    discover = _discover_map(_contexted("BC-001"))
    risk = _risk_map(_risk_row("BC-001", security=_NO_SCORE, qa=_partial(), unified=_scored(0.7)))
    xc, xo = _xref(discover, risk)
    checks, _ = _evaluate(discover=discover, risk=risk, scan=_scan(), xref_checks=xc, xref_owed=xo)
    by_name = {c.name: c for c in checks}
    assert by_name["c05_security_scoring"].passed is False
    assert "BC-001" in by_name["c05_security_scoring"].detail
    assert by_name["c06_qa_scoring"].passed is True
    assert by_name["c07_unified_drivers"].passed is True
