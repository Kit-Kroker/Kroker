"""Spec section 8. The last line is the one that matters: it is how an
operator sees what the assessment did NOT measure -- FR-915 made visible at
the surface rather than only in the artifact."""
from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_PACKAGES, CATEGORIES, Confidence, CandidateMember, MemberKind,
    SCAN_ORDER, ScanCandidate, ScanResult, ScanSignalId, ScanSignalResult,
    SignalSource, family_of,
)
from sdlc.assessment.scan.summary import render_scan_summary
from sdlc.measurement import Measurement


def _row(sid: ScanSignalId, measured: bool = True) -> ScanSignalResult:
    m = (Measurement.measured(1.0) if measured
         else Measurement.not_collected(f"{sid.value} activity failed"))
    source = (SignalSource.INHERITED if sid is ScanSignalId.SS2
              else SignalSource.COMPUTED)
    producer = None
    if source is SignalSource.INHERITED:
        from sdlc.assessment.scan.models import InheritedProducer
        producer = InheritedProducer(producer="triage:dependencies", version=1)
    return ScanSignalResult(
        signal=sid, family=family_of(sid), version=1, source=source,
        collected=m, categories={k: m for k in CATEGORIES[sid]},
        producer=producer)


def _result(candidates: list[ScanCandidate]) -> ScanResult:
    measured = {ScanSignalId.S1, ScanSignalId.S3, ScanSignalId.S5,
                ScanSignalId.SS2}
    return ScanResult(
        signals=[_row(s, s in measured) for s in SCAN_ORDER],
        candidates=candidates)


def _scan_result(**payload) -> ScanResult:
    """Every row MEASURED, so a payload is representable at all
    (_unmeasured_carries_no_payload), and each test states only the payload it
    is about."""
    return ScanResult(signals=[_row(s, True) for s in SCAN_ORDER], **payload)


def _candidate(cid: str, confidence: Confidence, sources: list[str]):
    return ScanCandidate(
        candidate_id=cid, name=cid.lower(), sources=sources,
        confidence=confidence,
        members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="src/x")])


def test_candidates_are_counted_by_confidence():
    out = render_scan_summary(_result([
        _candidate("C-01", Confidence.MEDIUM, ["S1-a", "S3-a"]),
        _candidate("C-02", Confidence.LOW, ["S1-b"]),
    ]))
    assert "high 0" in out
    assert "medium 1" in out
    assert "low 1" in out


def test_not_collected_categories_are_listed_with_their_reasons():
    out = render_scan_summary(_result([]))
    assert "not collected" in out.lower()
    assert "activity failed" in out   # the reason, carried verbatim
    assert "schema_clusters" in out  # S2's category key


def test_the_candidate_band_is_advisory_and_says_so():
    """D11: never a gate. The word 'advisory' is the contract with the
    operator, and with E-51, which is where a binding version would live."""
    out = render_scan_summary(_result([
        _candidate("C-01", Confidence.LOW, ["S1-a"])]))
    assert "advisory" in out.lower()
    assert "15" in out and "25" in out


def test_a_full_band_draws_no_advisory_line():
    cands = [_candidate(f"C-{i:02d}", Confidence.LOW, [f"S1-{i}"])
             for i in range(1, 17)]
    out = render_scan_summary(_result(cands))
    assert "advisory" not in out.lower()


def test_an_inherited_row_names_its_producer():
    """D2: an inherited row cites, and the operator should see the citation."""
    out = render_scan_summary(_result([]))
    assert "triage:dependencies" in out


# --- plan 3: the counts BrownKit's scan reports -----------------------------

def test_the_summary_reports_the_coverage_source_and_headline():
    """Spec section 8: 'report <tool>' vs 'proxy' is the line that tells an
    operator whether the number is a measurement or an estimate."""
    from sdlc.assessment.scan.models import Confidence, CoverageRecord

    scan = _scan_result(coverage=[
        CoverageRecord(scope="package", path="src/a",
                       covered=Measurement.measured(40.0), source="proxy",
                       confidence=Confidence.LOW),
        CoverageRecord(scope="package", path="src/b",
                       covered=Measurement.measured(60.0), source="proxy",
                       confidence=Confidence.LOW)])
    out = render_scan_summary(scan)
    assert "coverage: proxy" in out
    assert "50.0%" in out


def test_the_summary_counts_security_observations_per_category():
    from sdlc.assessment.scan.models import (
        C_TLS, Confidence, ScanSignalId, SecurityObservation,
    )

    scan = _scan_result(security=[SecurityObservation(
        signal=ScanSignalId.SS1, category=C_TLS, rule="r", detail="d",
        severity_hint="high", path="p", confidence=Confidence.HIGH)])
    out = render_scan_summary(scan)
    assert "tls_enforcement: 1" in out


def test_the_summary_names_drifted_environments():
    from sdlc.assessment.scan.models import EnvironmentRecord

    scan = _scan_result(environments=[
        EnvironmentRecord(name="staging", in_ci=False, in_config=True),
        EnvironmentRecord(name="production", in_ci=True, in_config=True)])
    out = render_scan_summary(scan)
    assert "staging" in out
    assert "environment drift" in out
