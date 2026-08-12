"""Plan 1's payoff: _scan produces a real thirteen-row ScanResult and
terminal_status derives assessed:partial with no edit to E-45's derivation."""
from __future__ import annotations

import pytest

from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.assessment.scan.inherit import inherited_halves
from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE, C_TLS, CATEGORIES, SCAN_ORDER, ScanSignalId,
    ScanSignalResult, SignalSource, family_of,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    FixClass, Readiness, RepoTriage, SignalResult, TriageFinding, Verdict,
)
from sdlc.workflows.assessment import (
    ScanOutcome, fold_row, skipped_scan_signal,
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
