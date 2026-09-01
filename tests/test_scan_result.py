"""The artifact: a completeness ledger plus typed payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanCandidate,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    family_of,
)
from sdlc.measurement import Measurement


def _row(sid: ScanSignalId, measured: bool = True) -> ScanSignalResult:
    val = Measurement.measured(0.0) if measured else Measurement.not_collected(f"{sid.value} stub")
    return ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=SignalSource.COMPUTED,
        collected=val,
        categories={k: val for k in CATEGORIES[sid]},
    )


def _all_rows(measured: bool = True) -> list[ScanSignalResult]:
    return [_row(s, measured) for s in SCAN_ORDER]


def _candidate() -> ScanCandidate:
    return ScanCandidate(
        candidate_id="C-01",
        name="Payments",
        sources=["S1-pay", "S3-pay"],
        confidence=Confidence.MEDIUM,
        members=[CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /p")],
    )


def test_signals_must_be_the_whole_set_in_order():
    r = ScanResult(
        signals=_all_rows(), sources=[], candidates=[], data_sensitivity=[], testability=[]
    )
    assert [s.signal for s in r.signals] == list(SCAN_ORDER)


def test_a_missing_signal_is_refused():
    with pytest.raises(ValidationError, match="whole set"):
        ScanResult(
            signals=_all_rows()[:-1], sources=[], candidates=[], data_sensitivity=[], testability=[]
        )


def test_out_of_order_signals_are_refused():
    rows = _all_rows()
    rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(ValidationError, match="whole set"):
        ScanResult(signals=rows, sources=[], candidates=[], data_sensitivity=[], testability=[])


def test_a_not_measured_signal_carrying_a_payload_is_refused():
    """Mirrors SignalResult._not_collected_has_no_findings: partial output is
    UNKNOWN, and a signal that did not run has no records."""
    rows = _all_rows()
    rows[SCAN_ORDER.index(ScanSignalId.S5)] = _row(ScanSignalId.S5, measured=False)
    with pytest.raises(ValidationError, match="did not run"):
        ScanResult(
            signals=rows, sources=[], candidates=[_candidate()], data_sensitivity=[], testability=[]
        )


def test_a_measured_signal_may_carry_an_empty_payload():
    """MEASURED with zero records is a real finding: it ran and found none."""
    r = ScanResult(
        signals=_all_rows(), sources=[], candidates=[], data_sensitivity=[], testability=[]
    )
    assert r.candidates == []


def test_signal_output_bundles_the_row_with_its_payload():
    """D10: cached as a unit, so a hit cannot serve a MEASURED row with
    nothing behind it."""
    out = SignalOutput(row=_row(ScanSignalId.S3), sources=[])
    assert out.row.signal is ScanSignalId.S3
    assert out.sources == []
