"""P3-D4/P3-D5: the typed upstream channel, and the rule that keeps a
degraded upstream out of the memo."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import (
    CATEGORIES,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    TestFileRecord,
    TestLevel,
    family_of,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState, Measurement
from sdlc.workflows.assessment import upstream_for

TREE = 40 * "cd"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _row(sid: ScanSignalId, m: Measurement) -> ScanSignalResult:
    return ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=SignalSource.COMPUTED,
        collected=m,
        categories={k: m for k in CATEGORIES[sid]},
    )


def _candidate(sid: ScanSignalId, local_id: str) -> SourceCandidate:
    return SourceCandidate(
        signal=sid,
        local_id=local_id,
        name=local_id,
        rule="r",
        detail="d",
        confidence_contribution=Confidence.LOW,
        members=[CandidateMember(kind=MemberKind.DB_TABLE, value=local_id)],
    )


def _test_file(path: str) -> TestFileRecord:
    return TestFileRecord(
        path=path,
        level=TestLevel.UNIT,
        rule="r",
        mapping_rule="naming_convention",
        covers=["src/a.py"],
        confidence=Confidence.MEDIUM,
    )


def test_ss4_receives_both_the_signals_it_consumes():
    """P3-D3: accessed_by cites S3, so SS4 must DECLARE S3 -- otherwise
    populating it would read undeclared data and rules_sha would miss S3."""
    assert SCAN_SIGNALS[ScanSignalId.SS4].consumes == (ScanSignalId.S2, ScanSignalId.S3)
    measured = Measurement.measured(1.0)
    outputs = {
        ScanSignalId.S1: SignalOutput(
            row=_row(ScanSignalId.S1, measured), sources=[_candidate(ScanSignalId.S1, "S1-a")]
        ),
        ScanSignalId.S2: SignalOutput(
            row=_row(ScanSignalId.S2, measured), sources=[_candidate(ScanSignalId.S2, "S2-orders")]
        ),
        ScanSignalId.S3: SignalOutput(
            row=_row(ScanSignalId.S3, measured), sources=[_candidate(ScanSignalId.S3, "S3-orders")]
        ),
    }
    up = upstream_for(ScanSignalId.SS4, outputs)
    assert [c.local_id for c in up.sources] == ["S2-orders", "S3-orders"]
    assert set(up.collected) == {ScanSignalId.S2, ScanSignalId.S3}
    assert up.measured(ScanSignalId.S2) is True


def test_qs2_receives_qs1s_test_records_not_candidates():
    """The channel a list[SourceCandidate] could not carry."""
    measured = Measurement.measured(2.0)
    outputs = {
        ScanSignalId.QS1: SignalOutput(
            row=_row(ScanSignalId.QS1, measured), tests=[_test_file("tests/test_a.py")]
        )
    }
    up = upstream_for(ScanSignalId.QS2, outputs)
    assert [t.path for t in up.tests] == ["tests/test_a.py"]
    assert up.sources == []


def test_a_gap_names_the_upstream_and_carries_its_reason():
    nc = Measurement.not_collected("S3 activity failed or timed out")
    up = ScanUpstream(collected={ScanSignalId.S3: nc})
    assert up.measured(ScanSignalId.S3) is False
    gap = up.gap(ScanSignalId.S3, "input_validation")
    assert gap.state is CollectionState.NOT_COLLECTED
    assert "S3" in gap.reason and "timed out" in gap.reason


def test_an_absent_upstream_is_not_a_measured_one():
    """An upstream that never reported is not one that reported nothing."""
    assert ScanUpstream().measured(ScanSignalId.S3) is False


def test_a_measured_row_with_a_degraded_upstream_is_not_cached():
    """P3-D5: SS1 can report MEASURED (a TLS count) while input_validation is
    not_collected because S3 degraded. Caching that serves a permanently
    missing category against a healthy S3, on an unchanged tree, forever."""
    out = SignalOutput(row=_row(ScanSignalId.SS1, Measurement.measured(1.0)))
    degraded = ScanUpstream(collected={ScanSignalId.S3: Measurement.not_collected("S3 failed")})
    assert memo.store(ScanSignalId.SS1, TREE, out, degraded) is False
    assert memo.load(ScanSignalId.SS1, TREE) is None

    healthy = ScanUpstream(collected={ScanSignalId.S3: Measurement.measured(3.0)})
    assert memo.store(ScanSignalId.SS1, TREE, out, healthy) is True
    assert memo.load(ScanSignalId.SS1, TREE) is not None


def test_storing_a_consuming_signal_without_its_upstream_is_a_bug_not_a_silence():
    """Forgetting the argument would quietly reinstate the hazard, so it
    raises -- caught by the activity's own try/except in production, and by
    this test in CI."""
    out = SignalOutput(row=_row(ScanSignalId.QS2, Measurement.measured(1.0)))
    with pytest.raises(ValueError):
        memo.store(ScanSignalId.QS2, TREE, out)


def test_a_wave_one_signal_still_stores_without_an_upstream():
    out = SignalOutput(row=_row(ScanSignalId.S1, Measurement.measured(1.0)))
    assert memo.store(ScanSignalId.S1, TREE, out) is True
