"""Plan 1 shipped the eleven activities as stubs reporting not_collected and
naming the plan that owes them -- E-45's unbuilt() discipline, one level
down. Plans 2 and 3 replaced every stub body, so OWED_BY is empty and no scan
row can name a plan."""

from __future__ import annotations

import pytest

from sdlc.assessment import activities as scan_acts
from sdlc.assessment.scan.models import SCAN_ORDER, ScanSignalId
from sdlc.assessment.scan.registry import SCAN_SIGNALS


def test_every_declared_activity_exists_on_the_module():
    """Registry drift fails here rather than at the first assessment."""
    for sid in (s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity):
        name = SCAN_SIGNALS[sid].activity
        assert hasattr(scan_acts, name), f"{sid.value} -> {name}"


def test_no_activity_is_declared_for_the_two_in_workflow_signals():
    for sid in (ScanSignalId.S5, ScanSignalId.SS2):
        assert SCAN_SIGNALS[sid].activity == ""


def test_nothing_is_owed_any_more():
    """Plan 3's headline: OWED_BY is empty, so no scan row can name a plan.
    unbuilt_signal survives as the mechanism a FUTURE signal would use."""
    assert scan_acts.OWED_BY == {}
    assert scan_acts.BUILT == {s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity}


def test_unbuilt_signal_still_works_for_a_future_signal():
    """The discipline outlives its current users: a fourteenth signal added
    later reports not_collected naming its owner rather than a zero."""
    with pytest.raises(KeyError):
        scan_acts.unbuilt_signal(ScanSignalId.S1)  # nothing owes S1
