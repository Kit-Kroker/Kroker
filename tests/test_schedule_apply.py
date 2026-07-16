"""Asset↔Temporal translation and plan formatting (E-12). The round-trip test
covers both directions at once; fetch_existing/apply_changes are thin I/O and
are exercised against a live server only in manual runs."""
from __future__ import annotations

import pytest

from temporalio.client import ScheduleActionStartWorkflow

from sdlc.models import ScheduleAsset, ScheduleAction, ScheduleSpecAsset
from sdlc.schedules.apply import (
    apply_changes, format_plan, from_temporal, to_temporal,
)
from sdlc.schedules.reconcile import Change


def asset(sid: str = "nightly-reflect") -> ScheduleAsset:
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(cron="0 3 * * *", timezone="UTC"),
        action=ScheduleAction(workflow="ReflectWorkflow",
                              banks=["project:default"],
                              backend="hindsight",
                              base_url="http://mem:9000"))


def test_round_trip_preserves_the_asset():
    a = asset()
    assert from_temporal(a.id, to_temporal(a)) == a


def test_to_temporal_sets_cron_and_timezone():
    sched = to_temporal(asset())
    assert sched.spec.cron_expressions == ["0 3 * * *"]
    assert sched.spec.time_zone_name == "UTC"


def test_to_temporal_starts_reflect_workflow_with_the_bank_list():
    sched = to_temporal(asset())
    assert isinstance(sched.action, ScheduleActionStartWorkflow)
    assert sched.action.workflow == "ReflectWorkflow"
    assert sched.action.args[0].banks == ["project:default"]
    assert sched.action.args[0].backend == "hindsight"


def test_from_temporal_ignores_schedules_we_do_not_manage():
    # An unrelated schedule in the namespace must not surface as drift.
    sched = to_temporal(asset())
    sched.action.workflow = "SomeoneElsesWorkflow"
    assert from_temporal("theirs", sched) is None


def test_format_plan_lists_every_change():
    out = format_plan([Change("create", "a", "not on server"),
                       Change("drift", "b", "on server, no yaml asset")])
    assert "create" in out and "a" in out
    assert "drift" in out and "b" in out


def test_format_plan_of_empty_plan_says_so():
    assert "no schedules" in format_plan([]).lower()


@pytest.mark.asyncio
async def test_apply_changes_unknown_action_raises():
    # A typo'd action string must surface loudly, not no-op silently.
    with pytest.raises(ValueError, match="bogus"):
        await apply_changes(None, [], [Change("bogus", "x", "never")])
