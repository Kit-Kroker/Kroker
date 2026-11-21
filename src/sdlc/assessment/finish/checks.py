"""FR-918 (E-51): the 14 acceptance criteria as three-state predicates.

FD11 is the load-bearing rule and `evaluate_criteria` is its only enforcer:
a criterion whose producer phase did not measure is an OWED row in the
pinned format -- never a pass, never a fail (FD3); a measured producer with
a not_collected sub-artifact (attribution coverage, blueprint, domain model,
a system family) is an EVALUATED FAIL carrying the sub-artifact's own
reason; measured inputs are pass/fail by the criterion's predicate.
FD12: c07 defers to E-56 -- `unified` composites cannot exist until QA
factors have a source -- so it is owed statically while any `.unified` is
unmeasured and evaluated only once every composite measures. FD17: c08
never fails a legitimate baseline-only run -- a measured discover phase
already proves the citation guard did not trip (the phase degrades whole
when it does, so that failure arrives as an owed row carrying the guard's
reason verbatim), and zero proposer references is recorded with its mode.

Classifications (FD9): ABSOLUTE = c01-c04, c07, c08, c09, c12, c14;
ADVISORY = c05, c06, c10, c11, c13 -- c13 is always owed today (E-52) and
its classification is declared now so E-52 inherits it. Wire names (FD10)
come from CRITERIA_MANIFEST -- the one declaration; this module never
restates them.

`xref_domains` is called ONCE, by orchestration; `evaluate_criteria` only
RECEIVES its results -- c14 is the derived AND over the four domains.

Pure by design -- the Pydantic models it walks, `...gate`, `...measurement`
and this package's own models.py only. This module must never import
assessment/models.py, activities.py, or temporalio, exactly as crossref.py
must not.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...gate import CheckClass, CheckResult, build_check
from ...measurement import CollectionState, Measurement
from ..discover.map import CapabilityMap
from ..risk.models import SYSTEM_FAMILIES, Composite, UnifiedRiskMap
from ..scan.models import PAYLOAD_FIELD, ScanResult, ScanSignalId
from .models import CRITERIA_MANIFEST

# Wire names (FD10): never renamed once landed -- CRITERIA_MANIFEST is the
# one declaration, and unpacking it positionally pins both count and order.
(C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14) = CRITERIA_MANIFEST

# FD9's classification table: ADVISORY where BrownKit accepts a documented
# shortfall (c05/c06 honesty, the c10 floor, c11); structural presence and
# the derived xref AND are ABSOLUTE. c13's ADVISORY is declared for E-52.
_ADVISORY: frozenset[str] = frozenset({C05, C06, C10, C11, C13})

DETAIL_BUDGET = 300


def _feeding(*fields: str) -> frozenset[ScanSignalId]:
    """The scan signals whose payload lands in `fields` -- inverted from
    scan.models.PAYLOAD_FIELD, which is the one declaration (ADR-6's rule:
    two lists that agree by coincidence are the defect)."""
    return frozenset(s for s, fs in PAYLOAD_FIELD.items() if any(f in fs for f in fields))


# Which scan signals feed each per-capability context criterion: c01 reads
# Capability.security (SS1+SS3) and .sensitivity (SS4); c02 reads
# .testability (QS3) and .coverage (QS2).
_FEEDS: dict[str, frozenset[ScanSignalId]] = {
    C01: _feeding("security", "data_sensitivity"),
    C02: _feeding("testability", "coverage"),
}

# FD11 rule 1's producer map: the phases that must have measured before the
# criterion is evaluable at all, records-side first -- the same precedence
# xref_domains owes in, so a two-phase family names the records side.
_FAMILY: dict[str, tuple[str, ...]] = {
    C01: ("discover",),
    C02: ("discover",),
    C03: ("discover", "risk"),  # the locked set (discover) over the rows (risk)
    C04: ("risk",),
    C05: ("risk",),
    C06: ("risk",),
    C07: ("risk",),
    C08: ("discover", "risk"),  # the reference count (discover), the judgment mode (risk)
    C09: ("risk",),
    C10: ("discover",),
    C11: ("discover",),
    C12: ("discover",),
    # c13 is owed outright (E-52) and c14 follows the walk -- neither has a
    # producer family of its own.
}


def _reason_of(state: Measurement) -> str:
    """A Measurement's reason verbatim -- owed rows carry the producer's own
    words, never a paraphrase (FD11 rule 1)."""
    return state.reason


def _owed(name: str, phase: str, state: Measurement) -> str:
    """The pinned owed format (FD11 rule 1), shared with crossref.py."""
    return f"{name}: not collected ({phase}: {_reason_of(state)})"


def _locked_bcids(discover: CapabilityMap) -> frozenset[str]:
    """The ids the identity lock handed out -- c03's comparison set."""
    return frozenset(c.bc_id for c in discover.capabilities)


def _check(name: str, passed: bool, detail: str = "") -> CheckResult:
    """build_check at the criterion's declared classification (FD9)."""
    return build_check(
        name, passed, CheckClass.ADVISORY if name in _ADVISORY else CheckClass.ABSOLUTE, detail
    )


def _bounded(items: Iterable[str]) -> str:
    """Joined, sorted, truncated at the detail budget (crossref.py's rule):
    a census over many named items must stay one readable line."""
    joined = ", ".join(sorted(items))
    if len(joined) <= DETAIL_BUDGET:
        return joined
    return joined[: DETAIL_BUDGET - 3] + "..."


def _honest(scan: ScanResult | None, feeds: frozenset[ScanSignalId]) -> bool:
    """D6's honest marker: every signal feeding the criterion recorded
    not_collected, so the empty context on a capability is a recorded
    absence -- the scan says why it is empty -- and not a bare one.
    ScanResult guarantees the whole signal set, so the row lookup is total."""
    if scan is None:
        return False
    rows = {r.signal: r for r in scan.signals}
    return all(rows[s].collected.state is not CollectionState.MEASURED for s in feeds)


def _scored(composite: Composite) -> bool:
    """MEASURED, or honest partial: some factors collected and the rest carry
    their own recorded reasons (RD3 makes partiality a fact about the
    factors, so "partial-with-reason" is structural here)."""
    return composite.value.state is CollectionState.MEASURED or composite.is_partial


def _explained(composite: Composite) -> bool:
    """FD8's explicitly-unknown shape: not scored, but saying why. The
    Measurement type already enforces a reason on every non-measured state;
    this guard keeps the criterion honest if that ever loosens."""
    return composite.value.state is not CollectionState.MEASURED and bool(
        composite.value.reason.strip()
    )


def _c01(discover: CapabilityMap, scan: ScanResult | None) -> CheckResult:
    """c01_security_context: every capability carries a security observation
    or a sensitivity record (D6), unless the scan honestly could not look."""
    bare = sorted(c.bc_id for c in discover.capabilities if not c.security and not c.sensitivity)
    if bare and not _honest(scan, _FEEDS[C01]):
        return _check(C01, False, f"no security context for: {_bounded(bare)}")
    return _check(C01, True)


def _c02(discover: CapabilityMap, scan: ScanResult | None) -> CheckResult:
    """c02_qa_context: every capability carries a testability finding or a
    coverage record (D6a), unless the QS signals honestly could not look."""
    bare = sorted(c.bc_id for c in discover.capabilities if not c.testability and not c.coverage)
    if bare and not _honest(scan, _FEEDS[C02]):
        return _check(C02, False, f"no qa context for: {_bounded(bare)}")
    return _check(C02, True)


def _c03(discover: CapabilityMap, risk: UnifiedRiskMap) -> CheckResult:
    """c03_stride_per_capability: the risk map covers exactly the locked set
    (CapabilityRisk._structurally_complete already forces the six STRIDE rows
    on every capability, so coverage is the only live question)."""
    locked = _locked_bcids(discover)
    got = {c.bc_id for c in risk.capabilities}
    missing = sorted(locked - got)
    extra = sorted(got - locked)
    parts = []
    if missing:
        parts.append(f"missing {missing}")
    if extra:
        parts.append(f"unexpected {extra}")
    return _check(C03, not parts, "" if not parts else f"locked-set mismatch: {'; '.join(parts)}")


def _c04(risk: UnifiedRiskMap) -> CheckResult:
    """c04_vulnerabilities_mapped: every Vulnerability maps to code -- a
    non-empty `path` and at least one evidence reference. The schema already
    requires `path`; `evidence` is what a row can still omit."""
    unmapped = sorted(
        v.key
        for c in risk.capabilities
        for v in c.vulnerabilities
        if not v.evidence or not v.path.strip()
    )
    return _check(
        C04,
        not unmapped,
        "" if not unmapped else f"vulnerabilities with no code mapping: {_bounded(unmapped)}",
    )


def _c05(risk: UnifiedRiskMap) -> CheckResult:
    """c05_security_scoring: every security composite scored -- MEASURED, or
    partial-with-reason (ADVISORY's documented shortfall, FD8-adjacent). A
    composite with no collected factor at all is a capability nobody scored."""
    unscored = [
        f"{c.bc_id}: {c.security.value.reason}"
        for c in sorted(risk.capabilities, key=lambda c: c.bc_id)
        if not _scored(c.security)
    ]
    return _check(
        C05,
        not unscored,
        "" if not unscored else f"security composite not scored: {_bounded(unscored)}",
    )


def _c06(risk: UnifiedRiskMap) -> CheckResult:
    """c06_qa_scoring: every qa composite scored OR explicitly unknown --
    RD3 makes qa partial on every run until E-56, and an honest partial or a
    reasoned not_collected passes (FD8)."""
    bare = [
        f"{c.bc_id}: {c.qa.value.reason}"
        for c in sorted(risk.capabilities, key=lambda c: c.bc_id)
        if not (_scored(c.qa) or _explained(c.qa))
    ]
    return _check(
        C06,
        not bare,
        "" if not bare else f"qa composite neither scored nor explained: {_bounded(bare)}",
    )


def _c07(risk: UnifiedRiskMap) -> CheckResult:
    """c07_unified_drivers: every unified composite MEASURED with at least
    one named driver (the schema bounds 1-3 -- RD9). The wrapper defers the
    criterion to E-56 while any composite is unmeasured (FD12), so this
    predicate only ever sees measured composites."""
    bare = sorted(c.bc_id for c in risk.capabilities if not c.unified.drivers)
    return _check(
        C07,
        not bare,
        "" if not bare else f"unified composites without drivers: {_bounded(bare)}",
    )


def _c08(discover: CapabilityMap, risk: UnifiedRiskMap) -> CheckResult:
    """c08_findings_traceable (FD17): every proposer reference verified. A
    measured discover phase proves the citation guard did not trip -- the
    phase degrades whole when it does -- so the live question is a zero
    count, which is recorded with its mode (the judgment reason is RD7's own
    baseline-only-vs-degraded distinction and travels verbatim), never
    failed."""
    if discover.total_references == 0:
        mode = (
            "judgment applied and cited no references"
            if risk.judgment.state is CollectionState.MEASURED
            else f"baseline-only or degraded judgment ({risk.judgment.reason})"
        )
        return _check(C08, True, f"no proposer references: {mode}")
    return _check(
        C08,
        True,
        f"{discover.total_references} proposer reference(s) verified; citation guard did not trip",
    )


def _c09(risk: UnifiedRiskMap) -> CheckResult:
    """c09_cross_capability_risks: every system family collected. Rows may
    be empty under a MEASURED family ('computed, and genuinely nothing'); an
    uncollected family is a cross-capability question never asked."""
    uncollected = [
        f"{family}: {risk.system.collected_of(family).reason}"
        for family in SYSTEM_FAMILIES
        if risk.system.collected_of(family).state is not CollectionState.MEASURED
    ]
    return _check(
        C09,
        not uncollected,
        ""
        if not uncollected
        else f"cross-capability families not collected: {_bounded(uncollected)}",
    )


def _c10(discover: CapabilityMap) -> CheckResult:
    """c10_coverage_floor (FD9: ADVISORY -- the floor is a configured target
    and small repositories are legitimately below it, scan D11's ruling).
    FD11 rule 2: discover measured but the attribution report absent, or its
    coverage not_collected, is an EVALUATED FAIL carrying the reason -- a
    real finding, never an owed row."""
    report = discover.attribution
    if report is None:
        return _check(C10, False, "attribution report absent")
    if report.coverage.state is not CollectionState.MEASURED:
        return _check(C10, False, f"coverage not collected ({report.coverage.reason})")
    if report.meets_floor:
        return _check(C10, True)
    return _check(C10, False, f"coverage {report.coverage.value:.2f} below floor {report.floor}")


def _c11(discover: CapabilityMap) -> CheckResult:
    """c11_blueprint_comparison: the comparison collected. MISSING gaps are
    context, not failure (E-48 D8) -- only a comparison that never happened
    fails, carrying its recorded reason (FD11 rule 2)."""
    blueprint = discover.blueprint
    if blueprint is None:
        return _check(C11, False, "blueprint comparison absent")
    if blueprint.collected.state is not CollectionState.MEASURED:
        return _check(C11, False, f"comparison not collected ({blueprint.collected.reason})")
    return _check(C11, True)


def _c12(discover: CapabilityMap) -> CheckResult:
    """c12_domain_model_traceability: the domain model collected and every
    capability traces to code through non-empty member_paths."""
    model = discover.domain_model
    if model is None:
        return _check(C12, False, "domain model absent")
    if model.collected.state is not CollectionState.MEASURED:
        return _check(C12, False, f"domain model not collected ({model.collected.reason})")
    untraced = sorted(c.bc_id for c in discover.capabilities if not c.member_paths)
    return _check(
        C12,
        not untraced,
        "" if not untraced else f"capabilities with no member paths: {_bounded(untraced)}",
    )


def _xref_owner(discover_state: Measurement, risk_state: Measurement) -> str:
    """The walk's records-side-first owner, recomputed from the same phase
    states xref_domains owed on -- never parsed back out of the owed strings
    (grading by reading the artifact's prose back is the anti-goal). Called
    only when the walk reported owed rows, which only happens when a
    producer state is not MEASURED."""
    if discover_state.state is not CollectionState.MEASURED:
        return f"discover: {_reason_of(discover_state)}"
    return f"risk: {_reason_of(risk_state)}"


def _c14(xref_checks: tuple[CheckResult, ...]) -> CheckResult:
    """c14_cross_reference_integrity: the derived AND over the four xref
    domains -- all evaluated and passed is a pass; a failure names the
    broken domains (FD6: it names what it refuses). The wrapper owes the
    criterion while the walk reports owed rows: an unevaluated domain never
    reads as a failure (FD3)."""
    failed = sorted(c.name for c in xref_checks if not c.passed)
    return _check(C14, not failed, "" if not failed else f"xref domains failed: {_bounded(failed)}")


def evaluate_criteria(
    *,
    scan: ScanResult | None,
    scan_state: Measurement,
    discover: CapabilityMap | None,
    discover_state: Measurement,
    risk: UnifiedRiskMap | None,
    risk_state: Measurement,
    xref_checks: tuple[CheckResult, ...],
    xref_owed: tuple[str, ...],
) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]:
    """The 14 criteria: (evaluated checks, owed rows), both sorted by name so
    the caller can slot them straight into FinishReport (NFR-10).

    FD11's three states, in order: a producer phase absent (state not
    MEASURED) makes the criterion an owed row in the pinned format --
    c07/c13's owners are static (E-56/E-52); a measured producer with a
    not_collected sub-artifact is an evaluated fail; measured inputs are
    pass/fail by the predicate. FD12: c07 is owed to E-56 while any
    `.unified` composite is unmeasured. FD3: c14 is owed while the walk
    reports owed rows. FD13's short-circuit (nothing measured at all)
    happens above this call, which is why `scan_state` rides the signature
    without a criterion reading it -- the honesty markers c01/c02 consult
    live on the scan artifact itself.
    """
    phase_state = {"discover": discover_state, "risk": risk_state}
    measured = {phase: s.state is CollectionState.MEASURED for phase, s in phase_state.items()}
    checks: list[CheckResult] = []
    owed: list[str] = []

    for name in CRITERIA_MANIFEST:
        if name == C13:
            owed.append(f"{C13}: not collected (E-52)")
            continue
        if name == C14:
            if xref_owed:
                owed.append(f"{C14}: not collected ({_xref_owner(discover_state, risk_state)})")
            else:
                checks.append(_c14(xref_checks))
            continue
        absent = next((phase for phase in _FAMILY[name] if not measured[phase]), None)
        if absent is not None:
            owed.append(_owed(name, absent, phase_state[absent]))
            continue
        if name == C01:
            assert discover is not None  # measured producers carry their artifact
            checks.append(_c01(discover, scan))
        elif name == C02:
            assert discover is not None
            checks.append(_c02(discover, scan))
        elif name == C03:
            assert discover is not None and risk is not None
            checks.append(_c03(discover, risk))
        elif name == C04:
            assert risk is not None
            checks.append(_c04(risk))
        elif name == C05:
            assert risk is not None
            checks.append(_c05(risk))
        elif name == C06:
            assert risk is not None
            checks.append(_c06(risk))
        elif name == C07:
            assert risk is not None
            # FD12: the deferral, not the predicate, while the composites the
            # drivers would name cannot exist. E-56 gives qa its source.
            if any(
                c.unified.value.state is not CollectionState.MEASURED for c in risk.capabilities
            ):
                owed.append(f"{C07}: deferred (E-56)")
            else:
                checks.append(_c07(risk))
        elif name == C08:
            assert discover is not None and risk is not None
            checks.append(_c08(discover, risk))
        elif name == C09:
            assert risk is not None
            checks.append(_c09(risk))
        elif name == C10:
            assert discover is not None
            checks.append(_c10(discover))
        elif name == C11:
            assert discover is not None
            checks.append(_c11(discover))
        elif name == C12:
            assert discover is not None
            checks.append(_c12(discover))

    return tuple(sorted(checks, key=lambda c: c.name)), tuple(sorted(owed))
