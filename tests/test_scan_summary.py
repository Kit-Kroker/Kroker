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
         else Measurement.not_collected(f"{sid.value} not implemented (plan 3)"))
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
    assert "plan 3" in out          # the reason, carried verbatim
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
