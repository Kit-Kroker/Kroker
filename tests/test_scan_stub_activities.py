"""Plan 1 shipped the eleven activities as stubs reporting not_collected and
naming the plan that owes them -- E-45's unbuilt() discipline, one level
down. Plan 2 replaced S1's and S3's bodies; the remaining nine are still
stubs, and OWED_BY is what says so."""
from __future__ import annotations

import pytest

from sdlc.assessment import activities as scan_acts
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, ScanSignalId,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState


def _activity_signals() -> list[ScanSignalId]:
    """Every signal the registry says has an activity -- built or not."""
    return [s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity]


def _stub_signals() -> list[ScanSignalId]:
    """The ones still owed a body. S1 and S3 landed in plan 2, so
    unbuilt_signal would KeyError on them."""
    return [s for s in SCAN_ORDER if s in scan_acts.OWED_BY]


def test_every_declared_activity_exists_on_the_module():
    """Registry drift fails here rather than at the first assessment."""
    for sid in _activity_signals():
        name = SCAN_SIGNALS[sid].activity
        assert hasattr(scan_acts, name), f"{sid.value} -> {name}"


def test_no_activity_is_declared_for_the_two_in_workflow_signals():
    for sid in (ScanSignalId.S5, ScanSignalId.SS2):
        assert SCAN_SIGNALS[sid].activity == ""


@pytest.mark.parametrize("sid", _stub_signals(), ids=lambda s: s.value)
def test_stub_reports_not_collected_naming_the_plan(sid):
    out = scan_acts.unbuilt_signal(sid)
    assert out.row.signal is sid
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "plan" in out.row.collected.reason.lower()
    assert sid.value in out.row.collected.reason


@pytest.mark.parametrize("sid", _stub_signals(), ids=lambda s: s.value)
def test_stub_reports_every_category_it_owes(sid):
    """A stub must not leave a category unreported -- that would be
    indistinguishable from a category nobody owes."""
    out = scan_acts.unbuilt_signal(sid)
    assert set(out.row.categories) == set(CATEGORIES[sid])
    for m in out.row.categories.values():
        assert m.state is CollectionState.NOT_COLLECTED


@pytest.mark.parametrize("sid", _stub_signals(), ids=lambda s: s.value)
def test_stub_carries_no_records(sid):
    """Generic over SignalOutput's payload fields: a new payload type added
    in a later plan is covered without editing this test."""
    out = scan_acts.unbuilt_signal(sid)
    for name in (f for f in type(out).model_fields if f != "row"):
        assert getattr(out, name) == [], name
