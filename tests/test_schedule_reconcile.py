"""Pure yaml→server diff (E-12). No Temporal client involved: plan_changes is
a function of desired vs existing, so every reconcile rule is testable here."""

from __future__ import annotations

from sdlc.schedules.models import (
    ScheduleAction,
    ScheduleAsset,
    ScheduleSpecAsset,
)
from sdlc.schedules.reconcile import plan_changes


def asset(
    sid: str = "nightly-reflect", cron: str = "0 3 * * *", banks: list[str] | None = None
) -> ScheduleAsset:
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(cron=cron),
        action=ScheduleAction(workflow="ReflectWorkflow", banks=banks or ["project:default"]),
    )


def _by_id(changes):
    return {c.id: c.action for c in changes}


def test_absent_on_server_is_create():
    assert _by_id(plan_changes([asset()], {})) == {"nightly-reflect": "create"}


def test_identical_is_noop():
    existing = {"nightly-reflect": asset()}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "noop"}


def test_changed_cron_is_update():
    existing = {"nightly-reflect": asset(cron="0 4 * * *")}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "update"}


def test_changed_banks_is_update():
    existing = {"nightly-reflect": asset(banks=["project:old"])}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "update"}


def test_server_schedule_with_no_yaml_is_drift_not_delete():
    # Delete-by-default would turn "checked out an old branch and ran apply"
    # into an outage. Drift is reported; --prune (Task 4) deletes.
    existing = {"orphan": asset(sid="orphan")}
    changes = plan_changes([], existing)
    assert _by_id(changes) == {"orphan": "drift"}
    assert all(c.action != "delete" for c in changes)


def test_mixed_plan_covers_every_case():
    desired = [asset(sid="keep"), asset(sid="change", cron="0 5 * * *"), asset(sid="new")]
    existing = {
        "keep": asset(sid="keep"),
        "change": asset(sid="change", cron="0 9 * * *"),
        "gone": asset(sid="gone"),
    }
    assert _by_id(plan_changes(desired, existing)) == {
        "keep": "noop",
        "change": "update",
        "new": "create",
        "gone": "drift",
    }


def test_empty_both_sides_is_empty_plan():
    assert plan_changes([], {}) == []


def test_change_carries_a_human_reason():
    assert plan_changes([asset()], {})[0].reason


def test_plan_is_deterministically_ordered():
    desired = [asset(sid="b"), asset(sid="a")]
    existing = {"z": asset(sid="z"), "y": asset(sid="y")}
    ids = [c.id for c in plan_changes(desired, existing)]
    # desired order preserved, then drift sorted
    assert ids == ["b", "a", "y", "z"]
