# tests/test_assessment_finish_crossref.py
"""FR-918 (E-51): the cross-reference walk -- four ABSOLUTE domains over the
structured id-typed census (FD15), owed on producer absence (FD11 rule 1)."""

from __future__ import annotations

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.finish.crossref import xref_domains
from sdlc.assessment.risk.models import (
    Cascade,
    RiskSource,
    Severity,
    SharedVulnerability,
    StrideCategory,
    SystemRisk,
    ThreatAssessment,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.capability.models import Advisory, AdvisoryKind
from sdlc.gate import CheckClass
from sdlc.measurement import Measurement
from tests.helpers_risk import capability, capability_map, capability_risk

DISCOVER_REASON = "the discover phase did not run"
RISK_REASON = "the risk phase did not run"


def _measured() -> Measurement:
    return Measurement.measured(1.0)


def _discover(*bc_ids: str) -> CapabilityMap:
    return capability_map(*(capability(bc_id) for bc_id in bc_ids))


def _vuln(key: str) -> Vulnerability:
    return Vulnerability(
        key=key,
        classification=VulnerabilityClass.POTENTIAL,
        severity=Severity.HIGH,
        stride_category=StrideCategory.SPOOFING,
        path="a.py",
        source=RiskSource.BASELINE,
    )


def _threats(spoofing_keys: tuple[str, ...] = ()) -> tuple[ThreatAssessment, ...]:
    """All six categories in declaration order, with the cited keys on
    SPOOFING -- CapabilityRisk._structurally_complete demands all six."""
    return tuple(
        ThreatAssessment(
            category=category,
            applicable=spoofing_keys != () and category is StrideCategory.SPOOFING,
            rationale="no data flow of this shape",
            vulnerability_keys=spoofing_keys if category is StrideCategory.SPOOFING else (),
        )
        for category in StrideCategory
    )


def _risk(*caps, system: SystemRisk | None = None) -> UnifiedRiskMap:
    return UnifiedRiskMap(
        capabilities=tuple(sorted(caps, key=lambda c: c.bc_id)),
        system=system or SystemRisk(),
        collected=_measured(),
    )


def _shared(bc_ids: tuple[str, ...], keys: tuple[str, ...]) -> SharedVulnerability:
    return SharedVulnerability(
        weakness_class="hardcoded-secret",
        signal="SS1",
        rule="ss1_hardcoded_secret",
        bc_ids=bc_ids,
        vulnerability_keys=keys,
        severity=Severity.HIGH,
    )


# --- the four domains over a clean map --------------------------------


def test_clean_map_passes_all_domains():
    """2 capabilities, one shared vuln, one cascade path, one threat citing an
    existing key -> four rows, all passed, all ABSOLUTE (FD9)."""
    risk = _risk(
        capability_risk("BC-001", vulnerabilities=(_vuln("k1"),), threats=_threats(("k1",))),
        capability_risk("BC-002", vulnerabilities=(_vuln("k2"),)),
        system=SystemRisk(
            shared_vulnerabilities=(_shared(("BC-001", "BC-002"), ("k1", "k2")),),
            shared_vulnerabilities_collected=_measured(),
            cascades=(Cascade(origin="BC-001", path=("BC-001", "BC-002")),),
            cascades_collected=_measured(),
        ),
    )
    checks, owed = xref_domains(
        discover=_discover("BC-001", "BC-002"),
        discover_state=_measured(),
        risk=risk,
        risk_state=_measured(),
    )
    assert owed == ()
    assert {c.name for c in checks} == {
        "xref:bc_ids",
        "xref:vulnerability_keys",
        "xref:capability_edges",
        "xref:threat_vulnerability_keys",
    }
    assert all(c.passed for c in checks)
    assert all(c.classification is CheckClass.ABSOLUTE for c in checks)


def test_broken_bc_citation_fails_absolute():
    """A SharedVulnerability citing BC-099 (no such capability) fails the
    bc_ids domain -- ABSOLUTE, naming the dangling citation -- and only it."""
    risk = _risk(
        capability_risk("BC-001", vulnerabilities=(_vuln("k1"),)),
        capability_risk("BC-002", vulnerabilities=(_vuln("k2"),)),
        system=SystemRisk(
            shared_vulnerabilities=(_shared(("BC-001", "BC-099"), ("k1", "k2")),),
            shared_vulnerabilities_collected=_measured(),
        ),
    )
    checks, owed = xref_domains(
        discover=_discover("BC-001", "BC-002"),
        discover_state=_measured(),
        risk=risk,
        risk_state=_measured(),
    )
    assert owed == ()
    assert len(checks) == 4
    by_name = {c.name: c for c in checks}
    broken = by_name["xref:bc_ids"]
    assert broken.passed is False
    assert "BC-099" in broken.detail
    assert broken.classification is CheckClass.ABSOLUTE
    assert by_name["xref:vulnerability_keys"].passed is True
    assert by_name["xref:capability_edges"].passed is True
    assert by_name["xref:threat_vulnerability_keys"].passed is True


def test_zero_citation_sites_under_measured_producer_passes():
    """FD15: a measured risk that cited nothing passes -- cited nothing is
    true, not vacuous, and never reads as owed."""
    checks, owed = xref_domains(
        discover=_discover("BC-001"),
        discover_state=_measured(),
        risk=_risk(),
        risk_state=_measured(),
    )
    assert owed == ()
    assert len(checks) == 4
    assert all(c.passed for c in checks)


# --- FD11 rule 1: producer absence is owed ----------------------------


def test_producer_absent_is_owed():
    """A domain whose records-side producer is absent is owed naming that
    phase with its not_collected reason verbatim; a citing-side-only absence
    is owed naming risk."""
    discover = _discover("BC-001", "BC-002")
    risk = _risk(capability_risk("BC-001"), capability_risk("BC-002"))

    checks, owed = xref_domains(
        discover=None,
        discover_state=Measurement.not_collected(DISCOVER_REASON),
        risk=risk,
        risk_state=_measured(),
    )
    assert owed == (
        f"xref:bc_ids: not collected (discover: {DISCOVER_REASON})",
        f"xref:capability_edges: not collected (discover: {DISCOVER_REASON})",
    )
    # The two domains that live entirely on the risk artifact still evaluate.
    assert {c.name for c in checks} == {"xref:vulnerability_keys", "xref:threat_vulnerability_keys"}
    assert all(c.passed for c in checks)

    checks, owed = xref_domains(
        discover=discover,
        discover_state=_measured(),
        risk=None,
        risk_state=Measurement.not_collected(RISK_REASON),
    )
    assert checks == ()
    assert owed == (
        f"xref:bc_ids: not collected (risk: {RISK_REASON})",
        f"xref:capability_edges: not collected (risk: {RISK_REASON})",
        f"xref:threat_vulnerability_keys: not collected (risk: {RISK_REASON})",
        f"xref:vulnerability_keys: not collected (risk: {RISK_REASON})",
    )


# --- FD15: prose is not a citation site -------------------------------


def test_gate_prose_is_not_walked():
    """An advisory whose prose mentions BC-099 -- an id in no census field --
    must not fail any domain: the module reads structured id-typed fields
    only."""
    caps = (capability("BC-001"), capability("BC-002"))
    by_action: dict = {}
    for c in caps:
        by_action[c.disposition.action] = by_action.get(c.disposition.action, 0) + 1
    discover = CapabilityMap(
        capabilities=caps,
        by_action=by_action,
        advisories=(
            Advisory(
                kind=AdvisoryKind.POSSIBLE_RENAME,
                detail="BC-099 looks like a rename of Payments",
            ),
        ),
        collected=_measured(),
    )
    checks, owed = xref_domains(
        discover=discover,
        discover_state=_measured(),
        risk=_risk(capability_risk("BC-001"), capability_risk("BC-002")),
        risk_state=_measured(),
    )
    assert owed == ()
    assert len(checks) == 4
    assert all(c.passed for c in checks)
