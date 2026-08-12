"""The registry is the one place that says which scan signals exist, what
runs them, what they inherit and what they consume."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, ScanSignalId, SignalSource, family_of,
)
from sdlc.assessment.scan.registry import (
    SCAN_SIGNALS, WAVES, ScanSignalSpec, wave_of,
)


def test_registry_covers_exactly_the_thirteen_signals():
    assert set(SCAN_SIGNALS) == set(SCAN_ORDER)


def test_each_spec_agrees_with_its_id():
    for sid, spec in SCAN_SIGNALS.items():
        assert spec.id is sid
        assert spec.family is family_of(sid)
        assert spec.categories == CATEGORIES[sid]


def test_computed_declares_an_activity_and_no_inherits():
    spec = SCAN_SIGNALS[ScanSignalId.S3]
    assert spec.source is SignalSource.COMPUTED
    assert spec.activity == "scan_entrypoints"
    assert spec.inherits == ()


def test_ss2_is_purely_inherited_and_has_no_activity():
    """D12 cut transitive deps, so SS2 computes nothing."""
    spec = SCAN_SIGNALS[ScanSignalId.SS2]
    assert spec.source is SignalSource.INHERITED
    assert spec.activity == ""
    assert spec.inherits == ("triage:dependencies",)


def test_ss1_is_extended_and_names_both_triage_producers():
    spec = SCAN_SIGNALS[ScanSignalId.SS1]
    assert spec.source is SignalSource.EXTENDED
    assert spec.activity == "scan_security_static"
    assert spec.inherits == ("triage:misconfig", "triage:secrets")


def test_s5_is_computed_in_workflow_and_has_no_activity():
    """S5 is a pure derivation over other signals' output, like
    compute_readiness in TriageWorkflow."""
    spec = SCAN_SIGNALS[ScanSignalId.S5]
    assert spec.activity == ""
    assert spec.in_workflow is True


def test_exactly_eleven_signals_have_an_activity():
    with_activity = [s for s in SCAN_SIGNALS.values() if s.activity]
    assert len(with_activity) == 11
    assert {s.id for s in SCAN_SIGNALS.values() if not s.activity} == {
        ScanSignalId.S5, ScanSignalId.SS2}


def test_wave_is_derived_from_consumes():
    assert wave_of(ScanSignalId.S3) == 1
    assert wave_of(ScanSignalId.SS1) == 2      # consumes S3
    assert wave_of(ScanSignalId.SS4) == 2      # consumes S2
    assert wave_of(ScanSignalId.QS2) == 2      # consumes QS1


def test_waves_partition_the_activity_signals_eight_then_three():
    assert len(WAVES) == 2
    assert len(WAVES[0]) == 8
    assert len(WAVES[1]) == 3
    assert set(WAVES[1]) == {ScanSignalId.SS1, ScanSignalId.SS4,
                             ScanSignalId.QS2}
    assert not set(WAVES[0]) & set(WAVES[1])


def test_a_wave_two_signal_only_consumes_wave_one_signals():
    """Two waves is the whole supported depth; a chain of three would be
    silently truncated."""
    for sid in WAVES[1]:
        for upstream in SCAN_SIGNALS[sid].consumes:
            assert wave_of(upstream) == 1, f"{sid.value} -> {upstream.value}"


def test_computed_spec_without_an_activity_or_in_workflow_is_refused():
    with pytest.raises(ValidationError, match="activity"):
        ScanSignalSpec(id=ScanSignalId.S1, family=family_of(ScanSignalId.S1),
                       version=1, source=SignalSource.COMPUTED,
                       module="sdlc.assessment.scan.signals.packages",
                       categories=CATEGORIES[ScanSignalId.S1])


def test_inherited_spec_declaring_an_activity_is_refused():
    with pytest.raises(ValidationError, match="inherit"):
        ScanSignalSpec(id=ScanSignalId.SS2, family=family_of(ScanSignalId.SS2),
                       version=1, source=SignalSource.INHERITED,
                       activity="scan_deps", inherits=("triage:dependencies",),
                       module="sdlc.assessment.scan.inherit",
                       categories=CATEGORIES[ScanSignalId.SS2])
