"""Asset↔Temporal translation and plan formatting (E-12; E-25 adds the org
promotion fields). The round-trip test covers both directions at once;
fetch_existing/apply_changes are thin I/O and are exercised against a live
server only in manual runs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec

from sdlc.schedules.apply import (
    apply_changes,
    format_plan,
    from_temporal,
    to_temporal,
)
from sdlc.schedules.models import (
    ReflectAction,
    ScheduleAsset,
    ScheduleSpecAsset,
)
from sdlc.schedules.reconcile import Change


def asset(sid: str = "nightly-reflect") -> ScheduleAsset:
    # promote_min_projects is deliberately non-default (3, not 2): a
    # from_temporal that dropped the field and fell back to the default
    # would still round-trip an asset built with 2 — only a non-default
    # catches the loss.
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(cron="0 3 * * *", timezone="UTC"),
        action=ReflectAction(
            workflow="ReflectWorkflow",
            banks=["project:default"],
            backend="hindsight",
            base_url="http://mem:9000",
            org_bank="org",
            promote_min_projects=3,
        ),
    )


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
    assert sched.action.args[0].org_bank == "org"
    assert sched.action.args[0].promote_min_projects == 3


def test_reflect_action_rejects_min_projects_below_two():
    # ge=2 is the promotion floor: a threshold of 1 would mirror a single
    # project's gotchas into the org bank, which is not cross-project
    # promotion — it must be a validation error, not a silent mirror.
    with pytest.raises(ValidationError):
        ReflectAction(banks=["project:default"], promote_min_projects=1)


def test_from_temporal_tolerates_legacy_args_without_org_fields():
    # Back-compat pin: a pre-E-25 live Schedule recorded args before the org
    # fields existed. Its args are the plain dict the default converter hands
    # back, and from_temporal must still reconstruct a valid asset with the
    # org half off (org_bank None, threshold at its default).
    legacy = Schedule(
        action=ScheduleActionStartWorkflow(
            "ReflectWorkflow",
            args=[
                {
                    "banks": ["project:default"],
                    "backend": "hindsight",
                    "base_url": "http://mem:9000",
                }
            ],
            id="sched-nightly-reflect",
            task_queue="ai-sdlc",
        ),
        spec=ScheduleSpec(cron_expressions=["0 3 * * *"], time_zone_name="UTC"),
    )
    a = from_temporal("nightly-reflect", legacy)
    assert a is not None
    assert isinstance(a.action, ReflectAction)
    assert a.action.org_bank is None
    assert a.action.promote_min_projects == 2


def test_from_temporal_ignores_schedules_we_do_not_manage():
    # An unrelated schedule in the namespace must not surface as drift.
    sched = to_temporal(asset())
    sched.action.workflow = "SomeoneElsesWorkflow"
    assert from_temporal("theirs", sched) is None


def test_format_plan_lists_every_change():
    out = format_plan(
        [Change("create", "a", "not on server"), Change("drift", "b", "on server, no yaml asset")]
    )
    assert "create" in out and "a" in out
    assert "drift" in out and "b" in out


def test_format_plan_of_empty_plan_says_so():
    assert "no schedules" in format_plan([]).lower()


@pytest.mark.asyncio
async def test_apply_changes_unknown_action_raises():
    # A typo'd action string must surface loudly, not no-op silently.
    with pytest.raises(ValueError, match="bogus"):
        await apply_changes(None, [], [Change("bogus", "x", "never")])
