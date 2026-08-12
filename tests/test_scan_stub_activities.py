"""Plan 1 ships the eleven activities as stubs reporting not_collected and
naming the plan that owes them -- E-45's unbuilt() discipline, one level
down. Plans 2 and 3 replace bodies, not wiring."""
from __future__ import annotations

import pytest

from sdlc.assessment import activities as scan_acts
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, ScanSignalId, SignalSource,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState


def _activity_signals() -> list[ScanSignalId]:
    return [s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity]


def test_every_declared_activity_exists_on_the_module():
    """Registry drift fails here rather than at the first assessment."""
    for sid in _activity_signals():
        name = SCAN_SIGNALS[sid].activity
        assert hasattr(scan_acts, name), f"{sid.value} -> {name}"


def test_no_activity_is_declared_for_the_two_in_workflow_signals():
    for sid in (ScanSignalId.S5, ScanSignalId.SS2):
        assert SCAN_SIGNALS[sid].activity == ""


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_reports_not_collected_naming_the_plan(sid):
    out = scan_acts.unbuilt_signal(sid)
    assert out.row.signal is sid
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "plan" in out.row.collected.reason.lower()
    assert sid.value in out.row.collected.reason


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_reports_every_category_it_owes(sid):
    """A stub must not leave a category unreported -- that would be
    indistinguishable from a category nobody owes."""
    out = scan_acts.unbuilt_signal(sid)
    assert set(out.row.categories) == set(CATEGORIES[sid])
    for m in out.row.categories.values():
        assert m.state is CollectionState.NOT_COLLECTED


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_carries_no_records(sid):
    out = scan_acts.unbuilt_signal(sid)
    assert out.sources == []
    assert out.data_sensitivity == []
    assert out.testability == []


def test_stub_source_matches_its_registry_declaration():
    """An EXTENDED signal's stub still declares EXTENDED; the workflow folds
    the inherited producer in (D7), so the activity's own row is COMPUTED-
    shaped and carries no producer."""
    out = scan_acts.unbuilt_signal(ScanSignalId.SS1)
    assert out.row.source is SignalSource.COMPUTED
    assert out.row.producer is None
    assert SCAN_SIGNALS[ScanSignalId.SS1].source is SignalSource.EXTENDED
