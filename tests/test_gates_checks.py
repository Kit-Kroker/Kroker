# tests/test_gates_checks.py
"""FR-917 (E-50 GD3): the two live clauses -- confirmed-vulnerability and
high-criticality testability blocker."""

from __future__ import annotations

import random

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.gates.checks import (
    high_criticality_testability_blockers,
    unaccepted_confirmed_vulnerabilities,
)
from sdlc.assessment.risk.models import (
    CapabilityRisk,
    Criticality,
    CriticalityRating,
    RiskSource,
    Severity,
    StrideCategory,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import testability_identity
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.measurement import Measurement
from tests.helpers_risk import capability, capability_map, capability_risk

MEASURED_JUDGMENT = Measurement.measured(1.0)


def _vuln(
    key="SS1:hardcoded-secret:src/a.py:",
    classification=VulnerabilityClass.CONFIRMED,
    source=RiskSource.BASELINE,
) -> Vulnerability:
    return Vulnerability(
        key=key,
        classification=classification,
        severity=Severity.HIGH,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="src/a.py",
        source=source,
    )


def _disposition(
    key, kind="vulnerability", disposition=Disposition.ACCEPTED_RISK
) -> FindingDisposition:
    from datetime import UTC, datetime

    return FindingDisposition(
        kind=kind,
        key=key,
        disposition=disposition,
        approved_by="maks",
        reason="reviewed",
        decided_at=datetime.now(UTC),
    )


# --- unaccepted_confirmed_vulnerabilities --------------------------------


def test_a_confirmed_unaccepted_vulnerability_fails_the_check():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    check = unaccepted_confirmed_vulnerabilities(m, ())
    assert check is not None
    assert check.passed is False
    assert "SS1:hardcoded-secret:src/a.py:" in check.detail


def test_a_disposition_on_the_same_key_clears_the_check():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    dispositions = (_disposition("SS1:hardcoded-secret:src/a.py:"),)
    check = unaccepted_confirmed_vulnerabilities(m, dispositions)
    assert check.passed is True


def test_a_potential_vulnerability_does_not_fail_the_check():
    m = UnifiedRiskMap(
        capabilities=(
            capability_risk(vulnerabilities=(_vuln(classification=VulnerabilityClass.POTENTIAL),)),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    check = unaccepted_confirmed_vulnerabilities(m, ())
    assert check.passed is True


def test_the_clause_defers_when_judgment_did_not_run():
    """GD3: CONFIRMED is only reachable through the judgment layer, so a map
    that never ran one must not read as a clean PASS -- even when a row is
    already CONFIRMED-shaped. A BASELINE-sourced row is structurally legal
    (nothing couples classification to source at the type), so this pins
    the implementation actually gating on judgment.state rather than
    happening to see no vulnerabilities to check (a weaker map would pass
    the check for the wrong reason)."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=Measurement.not_collected("no risk proposer ran"),
    )
    assert unaccepted_confirmed_vulnerabilities(m, ()) is None


def test_a_disposition_for_a_different_key_is_inert():
    """A stale or unrelated disposition must not clear the real finding
    (failure-modes table: 'inert for this run')."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    stale = (_disposition("SS1:some-other-finding:src/z.py:"),)
    check = unaccepted_confirmed_vulnerabilities(m, stale)
    assert check.passed is False


def test_a_testability_kind_disposition_does_not_clear_a_vulnerability():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    dispositions = (_disposition("SS1:hardcoded-secret:src/a.py:", kind="testability"),)
    check = unaccepted_confirmed_vulnerabilities(m, dispositions)
    assert check.passed is False


def test_vulnerability_clause_is_order_independent():
    """NFR-10."""
    vulns = [_vuln("SS1:a:x:"), _vuln("SS1:b:x:"), _vuln("SS1:c:x:")]
    first = None
    for _ in range(5):
        random.shuffle(vulns)
        m = UnifiedRiskMap(
            capabilities=(capability_risk(vulnerabilities=tuple(vulns)),),
            collected=Measurement.measured(1.0),
            judgment=MEASURED_JUDGMENT,
        )
        out = unaccepted_confirmed_vulnerabilities(m, ()).model_dump_json()
        first = first if first is not None else out
        assert out == first


# --- high_criticality_testability_blockers -------------------------------


def _map_with(bc_id, findings) -> CapabilityMap:
    return capability_map(capability(bc_id=bc_id, testability=tuple(findings)))


def _blocker(path="src/a.py", pattern="singleton-access"):
    from sdlc.assessment.scan.models import TestabilityFinding

    return TestabilityFinding(
        severity="blocks",
        pattern=pattern,
        detail="reaches a global instance",
        recommended_seam="pass the collaborator in",
        path=path,
        line=3,
        evidence="Singleton.getInstance()",
    )


def _high(bc_id="BC-001"):
    return capability_risk(
        bc_id=bc_id,
        criticality=CriticalityRating(level=Criticality.HIGH, collected=Measurement.measured(1.0)),
    )


def test_a_blocker_on_a_high_capability_fails_the_check():
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is False
    assert deferred == ()


def test_a_disposition_on_the_finding_clears_it():
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    key = testability_identity(_blocker())
    dispositions = (_disposition(key, kind="testability"),)
    check, _ = high_criticality_testability_blockers(rmap, cmap, dispositions)
    assert check.passed is True


def test_a_blocker_on_a_measured_medium_capability_does_not_fail_or_defer():
    cmap = _map_with("BC-001", [_blocker()])
    medium = capability_risk(
        bc_id="BC-001",
        criticality=CriticalityRating(
            level=Criticality.MEDIUM, collected=Measurement.measured(1.0)
        ),
    )
    rmap = UnifiedRiskMap(capabilities=(medium,), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True
    assert deferred == ()


def test_an_uncollected_criticality_defers_its_own_blocker_even_with_a_measured_sibling():
    """The mixed-criticality fix: one uncollected capability must not read
    as a silent pass because a DIFFERENT capability happens to be rated."""
    cmap = capability_map(
        capability(bc_id="BC-001", testability=(_blocker(path="src/a.py"),)),
        capability(bc_id="BC-002", testability=()),
    )
    uncollected = capability_risk(bc_id="BC-001")  # default: criticality not_collected
    measured_low = capability_risk(
        bc_id="BC-002",
        criticality=CriticalityRating(level=Criticality.LOW, collected=Measurement.measured(1.0)),
    )
    rmap = UnifiedRiskMap(
        capabilities=(uncollected, measured_low), collected=Measurement.measured(1.0)
    )
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True  # nothing MEASURED high fired
    assert len(deferred) == 1
    assert "BC-001" in deferred[0]


def test_a_blocker_on_a_bc_id_absent_from_the_risk_map_is_deferred_not_skipped():
    """GD3's rationale forbids a silent skip: a capability the discover
    phase carries but the risk phase never scored (an unjoinable bc_id)
    must be visible in `deferred`, not quietly dropped."""
    cmap = capability_map(capability(bc_id="BC-001", testability=(_blocker(),)))
    rmap = UnifiedRiskMap(capabilities=(), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True
    assert len(deferred) == 1
    assert "BC-001" in deferred[0]


def test_a_stale_testability_disposition_is_inert():
    """A disposition for a different finding must not clear this one."""
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    stale = (_disposition("QS3:some-other-pattern:src/z.py:", kind="testability"),)
    check, _ = high_criticality_testability_blockers(rmap, cmap, stale)
    assert check.passed is False


def test_testability_clause_is_order_independent():
    """NFR-10. CapabilityMap enforces no sort on its capabilities (unlike
    UnifiedRiskMap, which forces canonical order at construction) -- the
    genuinely permutable axis here is capability_map's tuple order."""
    caps = [
        capability(bc_id="BC-001", testability=(_blocker("src/a.py", "singleton-access"),)),
        capability(bc_id="BC-002", testability=(_blocker("src/b.py", "sleep-in-production"),)),
    ]
    rmap = UnifiedRiskMap(
        capabilities=(_high("BC-001"), _high("BC-002")), collected=Measurement.measured(1.0)
    )
    first = None
    for _ in range(5):
        random.shuffle(caps)
        cmap = capability_map(*caps)
        check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
        out = check.model_dump_json() + "|" + "|".join(deferred)
        first = first if first is not None else out
        assert out == first


from sdlc.assessment.gates.checks import composite_threshold, evaluate
from sdlc.assessment.gates.models import RiskGateVerdict
from sdlc.assessment.risk.models import Composite, Factor


def _scored(bc_id, value) -> CapabilityRisk:
    from tests.helpers_risk import capability_risk

    return capability_risk(
        bc_id=bc_id,
        unified=Composite(
            value=Measurement.measured(value),
            factors=(Factor(key="x", value=Measurement.measured(value)),),
        ),
    )


# --- composite_threshold --------------------------------------------------


def test_a_measured_capability_at_or_above_0_8_fires_block():
    m = UnifiedRiskMap(capabilities=(_scored("BC-001", 0.85),), collected=Measurement.measured(1.0))
    check, warn, deferred = composite_threshold(m)
    assert check.passed is False
    assert warn is None
    assert deferred == ()


def test_one_block_capability_fires_regardless_of_a_second_partial_one():
    partial = capability_risk("BC-002")  # default unified: not_collected
    m = UnifiedRiskMap(
        capabilities=(_scored("BC-001", 0.9), partial), collected=Measurement.measured(1.0)
    )
    check, warn, deferred = composite_threshold(m)
    assert check.passed is False
    assert "BC-002" in deferred[0]


def test_a_measured_capability_in_the_warn_band_with_no_block_warns():
    m = UnifiedRiskMap(capabilities=(_scored("BC-001", 0.65),), collected=Measurement.measured(1.0))
    check, warn, deferred = composite_threshold(m)
    assert check.passed is True
    assert warn is RiskGateVerdict.WARN


def test_all_capabilities_partial_defers_the_whole_clause():
    """RD3's headline consequence: today's reality until E-56 lands."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk("BC-001"), capability_risk("BC-002")),
        collected=Measurement.measured(1.0),
    )
    check, warn, deferred = composite_threshold(m)
    assert check is None
    assert warn is None
    assert len(deferred) == 2


# NOTE: composite_threshold has no order-independence test of its own.
# UnifiedRiskMap._capabilities_are_sorted forces risk_map.capabilities into
# canonical order at CONSTRUCTION time -- there is no valid way to build an
# UnifiedRiskMap whose capability order differs, so shuffling a list and
# re-sorting it before construction (an earlier version of this test) was
# vacuous: the re-sort silently undid the shuffle. The genuinely free axes
# for this module -- capability_map's tuple order (CapabilityMap enforces
# no sort) and the dispositions tuple order -- are permuted below, at the
# evaluate() level, which is where both axes are actually consumed.


# --- evaluate --------------------------------------------------------------


def _empty_map() -> CapabilityMap:
    return CapabilityMap(collected=Measurement.measured(1.0))


def test_evaluate_passes_when_nothing_fires():
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.PASS


def test_evaluate_blocks_on_a_confirmed_unaccepted_vulnerability():
    rmap = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.BLOCK
    assert "risk_no_unaccepted_confirmed_vuln" in [c.name for c in report.checks]


def test_a_block_clause_wins_over_a_warn_band_composite():
    rmap = UnifiedRiskMap(
        capabilities=(
            capability_risk(bc_id="BC-001", vulnerabilities=(_vuln(),)),
            _scored("BC-002", 0.65),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.BLOCK


def test_evaluate_warns_when_only_the_composite_warn_band_fires():
    rmap = UnifiedRiskMap(
        capabilities=(_scored("BC-001", 0.65),), collected=Measurement.measured(1.0)
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.WARN
    # GD5: detail names every contributing bc_id, even on a PASSED check --
    # a WARN report must not be silent about which capability warned.
    assert any("BC-001" in r for r in report.reasons)


def test_a_pass_with_deferrals_names_them():
    """FR-915: a PASS that skipped a clause must say so."""
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.PASS
    assert any("unified composite" in d for d in report.deferred)
    assert any("judgment layer" in d for d in report.deferred)


def test_no_check_row_is_ever_emitted_for_a_deferred_clause():
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    # judgment not measured -> vuln check absent; composite fully partial -> absent
    assert [c.name for c in report.checks] == ["risk_no_high_criticality_testability_blocker"]


def test_evaluate_is_order_independent():
    """NFR-10. risk_map.capabilities is fixed (the type forces canonical
    order); the genuinely free axes are capability_map's tuple order and
    the dispositions tuple order, both shuffled here across >= 2 elements
    each -- a 1-element list cannot exercise a shuffle at all."""
    rmap = UnifiedRiskMap(
        capabilities=(
            capability_risk(bc_id="BC-001", vulnerabilities=(_vuln("SS1:a:x:"),)),
            _scored("BC-002", 0.7),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    caps = [
        capability(bc_id="BC-001", testability=()),
        capability(bc_id="BC-002", testability=()),
    ]
    dispositions = [
        _disposition("SS1:a:x:", disposition=Disposition.MITIGATED_ELSEWHERE),
        _disposition("QS3:unrelated:src/z.py:", kind="testability"),
    ]
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(dispositions)
        out = evaluate(rmap, capability_map(*caps), tuple(dispositions)).model_dump_json()
        first = first if first is not None else out
        assert out == first
