"""D8: confidence is derived from distinct source signals, never assigned."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CandidateMember, Confidence, MemberKind, ScanCandidate,
)


def _m(value: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value)


def _candidate(sources: list[str], confidence: Confidence) -> ScanCandidate:
    return ScanCandidate(candidate_id="C-01", name="Payments",
                         sources=sources, confidence=confidence,
                         members=[_m("GET /pay")])


def test_three_distinct_signals_is_high():
    c = _candidate(["S1-pay", "S2-pay", "S3-pay"], Confidence.HIGH)
    assert c.confidence is Confidence.HIGH


def test_two_distinct_signals_is_medium():
    assert _candidate(["S1-pay", "S3-pay"],
                      Confidence.MEDIUM).confidence is Confidence.MEDIUM


def test_two_candidates_from_one_signal_is_low():
    """The load-bearing case: S1 seeing two groupings is one opinion."""
    assert _candidate(["S1-pay", "S1-billing"],
                      Confidence.LOW).confidence is Confidence.LOW


def test_a_disagreeing_confidence_does_not_construct():
    """Derived, never assigned -- a deserialized payload cannot lie about its
    own corroboration, the way Assessment.terminal_status cannot (E-45 D6)."""
    with pytest.raises(ValidationError, match="derived"):
        _candidate(["S1-pay"], Confidence.HIGH)


def test_no_sources_is_refused():
    with pytest.raises(ValidationError, match="at least one source"):
        _candidate([], Confidence.LOW)


def test_a_malformed_source_id_is_refused():
    with pytest.raises(ValidationError, match="malformed"):
        _candidate(["payments"], Confidence.LOW)


def test_candidate_id_is_not_a_bc_id():
    """C-NN is assessment-local. BC-NNN is E-47a's surrogate key, allocated
    after discover; minting one here would create identity two stages early."""
    c = _candidate(["S1-pay", "S2-pay"], Confidence.MEDIUM)
    assert c.candidate_id.startswith("C-")
    assert not c.candidate_id.startswith("BC-")


def test_possible_duplicate_defaults_empty_and_is_sorted():
    c = ScanCandidate(candidate_id="C-02", name="Refunds",
                      sources=["S3-refunds"], confidence=Confidence.LOW,
                      members=[_m("GET /refund")],
                      possible_duplicate_of=["C-09", "C-01"])
    assert c.possible_duplicate_of == ["C-01", "C-09"]
