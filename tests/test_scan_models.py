"""E-46 contracts. Pure -- no Temporal, no filesystem."""
from __future__ import annotations

import pytest

from sdlc.assessment.scan.models import (
    SCAN_ORDER, Confidence, ScanSignalId, SignalFamily, SignalSource,
    confidence_from, family_of,
)


def test_thirteen_signals_in_declaration_order():
    assert len(SCAN_ORDER) == 13
    assert SCAN_ORDER == tuple(ScanSignalId)
    assert [s.value for s in SCAN_ORDER[:5]] == ["S1", "S2", "S3", "S4", "S5"]
    assert SCAN_ORDER[-1] is ScanSignalId.QS4


def test_family_is_derived_from_the_id_prefix():
    assert family_of(ScanSignalId.S3) is SignalFamily.CAPABILITY
    assert family_of(ScanSignalId.SS1) is SignalFamily.SECURITY
    assert family_of(ScanSignalId.QS2) is SignalFamily.QA


@pytest.mark.parametrize("signals,expected", [
    ([ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3], Confidence.HIGH),
    ([ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.S4],
     Confidence.HIGH),
    ([ScanSignalId.S1, ScanSignalId.S3], Confidence.MEDIUM),
    ([ScanSignalId.S1], Confidence.LOW),
])
def test_confidence_counts_distinct_signals(signals, expected):
    assert confidence_from(signals) is expected


def test_confidence_counts_signals_not_candidates():
    """FR-912: never the depth of one source. Two S1 groupings do not
    corroborate each other."""
    assert confidence_from(
        [ScanSignalId.S1, ScanSignalId.S1, ScanSignalId.S1]) is Confidence.LOW


def test_confidence_from_nothing_is_low_not_an_error():
    """A candidate with no sources cannot be constructed (Task 3 enforces it);
    the scorer stays total so it is never the thing that raises."""
    assert confidence_from([]) is Confidence.LOW


def test_source_has_exactly_three_states():
    assert {s.value for s in SignalSource} == {
        "computed", "inherited", "extended"}
