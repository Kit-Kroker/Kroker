"""Plan 1's payoff: _scan produces a real thirteen-row ScanResult and
terminal_status derives assessed:partial with no edit to E-45's derivation."""
from __future__ import annotations

import pytest

from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.assessment.scan.inherit import inherited_halves
from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE, C_TLS, CATEGORIES, SCAN_ORDER, CandidateMember,
    Confidence, MemberKind, ScanSignalId, ScanSignalResult, SignalOutput,
    SignalSource, SourceCandidate, family_of,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    FixClass, Readiness, RepoTriage, SignalResult, TriageFinding, Verdict,
)
from sdlc.workflows.assessment import (
    ScanOutcome, _collected_from_categories, _inherited_row, _upstream_for,
    fold_row, skipped_scan_signal,
)


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    f = TriageFinding(signal="secrets", rule="aws_key", severity="critical",
                      detail="d", path=".env", fix_class=FixClass.MECHANICAL,
                      key="k")
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40, toolchain="python",
        readiness=Readiness(buildable=ok, runnable=ok, tests_present=ok,
                            structure_discernible=ok, verdict=Verdict.READY),
        signals=[SignalResult(signal="secrets", version=2,
                              collected=Measurement.measured(1.0),
                              findings=[f])])


def test_skipped_scan_signal_reports_every_owed_category():
    row = skipped_scan_signal(ScanSignalId.QS3, "activity failed")
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert set(row.categories) == set(CATEGORIES[ScanSignalId.QS3])
    assert "activity failed" in row.collected.reason


def test_fold_row_unions_categories_and_promotes_source_to_extended():
    """D7: the activity computed one half, inherit.py derived the other."""
    nc = Measurement.not_collected("plan 3")
    activity_row = ScanSignalResult(
        signal=ScanSignalId.SS1, family=family_of(ScanSignalId.SS1),
        version=1, source=SignalSource.COMPUTED, collected=nc,
        categories={k: nc for k in CATEGORIES[ScanSignalId.SS1]})
    half = inherited_halves(_triage())[ScanSignalId.SS1]

    folded = fold_row(activity_row, half)
    assert folded.source is SignalSource.EXTENDED
    assert folded.producer is not None
    # the inherited half wins its own categories
    assert folded.categories[C_CREDENTIAL_STORAGE].state is \
        CollectionState.MEASURED
    # and the computed ones stay the activity's
    assert folded.categories[C_TLS].state is CollectionState.NOT_COLLECTED
    assert set(folded.categories) == set(CATEGORIES[ScanSignalId.SS1])


def test_fold_row_without_a_half_leaves_the_row_computed():
    nc = Measurement.not_collected("plan 2")
    row = ScanSignalResult(
        signal=ScanSignalId.S1, family=family_of(ScanSignalId.S1), version=1,
        source=SignalSource.COMPUTED, collected=nc,
        categories={k: nc for k in CATEGORIES[ScanSignalId.S1]})
    folded = fold_row(row, None)
    assert folded.source is SignalSource.COMPUTED
    assert folded.producer is None


def test_ss2_is_built_from_its_half_alone():
    """SS2 has no activity at all (D12), so the workflow must synthesize its
    row from the inherited half rather than from an activity result."""
    assert SCAN_SIGNALS[ScanSignalId.SS2].activity == ""
    half = inherited_halves(_triage())[ScanSignalId.SS2]
    assert set(half.categories) == set(CATEGORIES[ScanSignalId.SS2])


# --- review fixes: SS2 from its half, consumes-driven upstream, reasons -----

def _measured_row(sid: ScanSignalId) -> ScanSignalResult:
    val = Measurement.measured(0.0)
    return ScanSignalResult(signal=sid, family=family_of(sid), version=1,
                            source=SignalSource.COMPUTED, collected=val,
                            categories={k: val for k in CATEGORIES[sid]})


def test_collected_from_categories_is_measured_with_record_count_when_all_measured():
    cats = {"a": Measurement.measured(2.0), "b": Measurement.measured(3.0)}
    m = _collected_from_categories(cats)
    assert m.state is CollectionState.MEASURED
    assert m.value == 5.0


def test_collected_from_categories_is_not_collected_when_any_category_unmeasured():
    cats = {"a": Measurement.measured(1.0),
            "b": Measurement.not_collected("triage timed out")}
    m = _collected_from_categories(cats)
    assert m.state is CollectionState.NOT_COLLECTED
    assert "timed out" in m.reason


def test_ss2_row_is_built_from_its_half_as_inherited_and_measured():
    """D12 + FR-915: SS2's computed half is cut, so the inherited half IS the
    signal. Its row reads INHERITED (not EXTENDED) and collected when the
    producing triage signal collected -- the reverse-FR-915 conflation the
    first review found."""
    tri = RepoTriage(
        repo_dir="/r", commit_sha="a" * 40, toolchain="python",
        readiness=Readiness(buildable=Measurement.measured(1.0),
                            runnable=Measurement.measured(1.0),
                            tests_present=Measurement.measured(1.0),
                            structure_discernible=Measurement.measured(1.0),
                            verdict=Verdict.READY),
        signals=[SignalResult(
            signal="dependencies", version=1,
            collected=Measurement.measured(1.0),
            findings=[TriageFinding(
                signal="dependencies", rule="known_vulnerable",
                severity="high", detail="d", path="p.lock",
                fix_class=FixClass.MECHANICAL, key="k")])])
    half = inherited_halves(tri)[ScanSignalId.SS2]
    row = _inherited_row(ScanSignalId.SS2, half)
    assert row.source is SignalSource.INHERITED
    assert row.collected.state is CollectionState.MEASURED
    assert row.producer is half.producer
    assert set(row.categories) == set(CATEGORIES[ScanSignalId.SS2])


def test_ss2_row_is_not_collected_when_its_triage_source_did_not_collect():
    """An absent triage signal propagates as not_collected, not measured(0)."""
    half = inherited_halves(
        RepoTriage(repo_dir="/r", commit_sha="a" * 40, toolchain="python",
                   readiness=Readiness(
                       buildable=Measurement.measured(1.0),
                       runnable=Measurement.measured(1.0),
                       tests_present=Measurement.measured(1.0),
                       structure_discernible=Measurement.measured(1.0),
                       verdict=Verdict.READY),
                   signals=[]))[ScanSignalId.SS2]
    row = _inherited_row(ScanSignalId.SS2, half)
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert row.source is SignalSource.INHERITED


def _candidate(signal: ScanSignalId, local_id: str) -> SourceCandidate:
    kind = MemberKind.PACKAGE_PATH if signal is ScanSignalId.S1 \
        else MemberKind.HTTP_ROUTE
    return SourceCandidate(
        signal=signal, local_id=local_id, name=local_id, rule="r", detail="d",
        confidence_contribution=Confidence.LOW,
        members=[CandidateMember(kind=kind, value=local_id)])


def test_upstream_for_returns_only_declared_consumes_candidates():
    """D10: a wave-2 signal receives candidates ONLY from signals it declares
    in consumes, so reading undeclared data is impossible and rules_sha (which
    walks the same consumes) cannot miss a real input."""
    outputs = {
        ScanSignalId.S1: SignalOutput(row=_measured_row(ScanSignalId.S1),
                                      sources=[_candidate(ScanSignalId.S1, "S1-pay")]),
        ScanSignalId.S2: SignalOutput(row=_measured_row(ScanSignalId.S2),
                                      sources=[_candidate(ScanSignalId.S2, "S2-orders")]),
        ScanSignalId.S3: SignalOutput(row=_measured_row(ScanSignalId.S3),
                                      sources=[_candidate(ScanSignalId.S3, "S3-pay")]),
        ScanSignalId.S4: SignalOutput(row=_measured_row(ScanSignalId.S4),
                                      sources=[_candidate(ScanSignalId.S4, "S4-shop")]),
    }
    # SS1 consumes only S3.
    assert [c.local_id for c in _upstream_for(ScanSignalId.SS1, outputs)] \
        == ["S3-pay"]
    # SS4 consumes only S2.
    assert [c.local_id for c in _upstream_for(ScanSignalId.SS4, outputs)] \
        == ["S2-orders"]


def test_upstream_for_a_wave_one_signal_is_empty():
    """Wave-1 signals consume nothing, so the build is deterministic and the
    consumes/wave derivation cannot disagree."""
    outputs = {ScanSignalId.S1: SignalOutput(
        row=_measured_row(ScanSignalId.S1),
        sources=[_candidate(ScanSignalId.S1, "S1-pay")])}
    assert _upstream_for(ScanSignalId.S3, outputs) == []


def test_s5_row_is_built_from_the_merge_not_from_a_stub():
    """E-45 D6's derivation was the plan-1 claim; this is the plan-2 one:
    S5's row comes from merge(), so nothing in the artifact names a plan."""
    from sdlc.assessment.scan.merge import merge
    from sdlc.assessment.scan.models import C_MERGE
    from sdlc.workflows.assessment import _merged_row

    out = merge([_candidate(ScanSignalId.S1, "S1-payments"),
                 _candidate(ScanSignalId.S3, "S3-payments")],
                {ScanSignalId.S1: Measurement.measured(1.0),
                 ScanSignalId.S3: Measurement.measured(1.0)})
    row = _merged_row(out)
    assert row.signal is ScanSignalId.S5
    assert row.source is SignalSource.COMPUTED
    assert row.producer is None
    assert set(row.categories) == {C_MERGE}
    assert row.collected.state is CollectionState.MEASURED
    assert "plan" not in (row.collected.reason or "").lower()


def test_s5_reports_a_gap_when_every_source_signal_failed():
    from sdlc.assessment.scan.merge import merge
    from sdlc.workflows.assessment import _merged_row

    nc = Measurement.not_collected("S1 activity failed or timed out")
    row = _merged_row(merge([], {ScanSignalId.S1: nc, ScanSignalId.S3: nc}))
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert "S1" in row.collected.reason
