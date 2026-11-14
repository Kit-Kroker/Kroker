"""The schedules generalisation (023a T026, RED).

Authorship note: both QA seats are quota-blocked again; executor-written
under the degradation ruling — every case transcribes T026's task text
(FR-003, R10). The back-compat pin below was captured against CURRENT
code (pre-generalisation) on 2026-11-14 and is the byte-truth T027 must
not move.

Subject: the discriminated ``ScheduleAction`` (ReflectAction |
MaintenanceKickAction) in sdlc/schedules/models.py and the per-type
dispatch in apply.py (T027 implements).
"""

from __future__ import annotations

import pytest
from temporalio.client import ScheduleActionStartWorkflow

from sdlc.schedules.apply import from_temporal, to_temporal
from sdlc.schedules.loader import ScheduleError, load_schedules
from sdlc.schedules.models import (
    KNOWN_SCHEDULE_WORKFLOWS,
    MaintenanceKickAction,
    ReflectAction,
    ScheduleAsset,
    ScheduleSpecAsset,
)

# --------------------------------------------------------------------------- #
# The back-compat pin: the shipped nightly-reflect asset converts today
# exactly like this, and must convert exactly like this after the
# generalisation (captured pre-change, 2026-11-14).
# --------------------------------------------------------------------------- #


def test_nightly_reflect_to_temporal_is_pinned():
    [asset] = load_schedules("schedules")
    sched = to_temporal(asset)
    assert isinstance(sched.action, ScheduleActionStartWorkflow)
    assert sched.action.workflow == "ReflectWorkflow"
    assert sched.action.id == "sched-nightly-reflect"
    assert sched.action.task_queue == "ai-sdlc"
    from sdlc.workflows.reflect import ReflectScheduleInput

    assert sched.action.args == [
        ReflectScheduleInput(
            banks=["project:default"], backend="hindsight", base_url="http://localhost:8888"
        )
    ]
    assert sched.spec.cron_expressions == ["0 3 * * *"]
    assert sched.spec.time_zone_name == "UTC"


def test_nightly_reflect_round_trips_through_from_temporal():
    [asset] = load_schedules("schedules")
    again = from_temporal(asset.id, to_temporal(asset))
    assert again == asset


# --------------------------------------------------------------------------- #
# The kick asset: loads, converts, round-trips
# --------------------------------------------------------------------------- #


def _kick_asset(cron: str = "0 4 * * *") -> ScheduleAsset:
    return ScheduleAsset(
        id="maint-demo",
        spec=ScheduleSpecAsset(cron=cron),
        action=MaintenanceKickAction(project="demo"),
    )


def test_kick_asset_converts_and_round_trips():
    asset = _kick_asset()
    sched = to_temporal(asset)
    assert sched.action.workflow == "MaintenanceKickWorkflow"
    assert sched.action.id == "sched-maint-demo"
    from sdlc.maintenance.models import MaintenanceKickInput

    assert sched.action.args == [MaintenanceKickInput(project="demo")]
    assert sched.spec.cron_expressions == ["0 4 * * *"]
    again = from_temporal(asset.id, sched)
    assert again == asset


def test_maintenance_kick_workflow_is_known_reflect_unchanged():
    assert KNOWN_SCHEDULE_WORKFLOWS == {"ReflectWorkflow", "MaintenanceKickWorkflow"}


def test_reflect_action_still_carries_banks_backend_base_url():
    action = ReflectAction(banks=["project:default"], backend="hindsight", base_url="http://x:1")
    assert action.banks == ["project:default"]


# --------------------------------------------------------------------------- #
# Cadence: sub-hourly refused for kick assets ONLY
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cron", ["*/15 * * * *", "*/30 * * * *", "0,30 * * * *", "* * * * *"])
def test_sub_hourly_cron_refused_for_kick_assets(cron):
    with pytest.raises(ValueError, match="(?i)hourly|minute"):
        _kick_asset(cron=cron)


@pytest.mark.parametrize("cron", ["0 3 * * *", "30 * * * *", "0 */2 * * *"])
def test_hourly_or_slower_cron_accepted_for_kick_assets(cron):
    assert _kick_asset(cron=cron).spec.cron == cron


def test_reflect_assets_keep_any_five_field_cron():
    # The nightly-reflect asset's cadence rule is untouched: the sub-hourly
    # refusal is a kick-asset rule only.
    ScheduleAsset(
        id="r",
        spec=ScheduleSpecAsset(cron="*/15 * * * *"),
        action=ReflectAction(banks=["project:default"]),
    )


# --------------------------------------------------------------------------- #
# Unknown workflows still refused
# --------------------------------------------------------------------------- #


def test_unknown_workflow_is_still_refused():
    # Refused by the closed union: the tag error names the workflow and the
    # expected tags (T027's mechanism — a discriminated union rather than a
    # name-list validator).
    with pytest.raises(ValueError, match="SomeOtherWorkflow"):
        ScheduleAsset(
            id="x",
            spec=ScheduleSpecAsset(cron="0 3 * * *"),
            action={"workflow": "SomeOtherWorkflow", "project": "demo"},
        )


def test_kick_requires_a_valid_project_slug():
    with pytest.raises(ValueError):
        MaintenanceKickAction(project="Demo")


# --------------------------------------------------------------------------- #
# The reconcile/diff surface for a reflect-only set is unchanged
# --------------------------------------------------------------------------- #


def test_reflect_only_reconcile_unchanged():
    from sdlc.schedules.reconcile import plan_changes

    [asset] = load_schedules("schedules")
    changes = plan_changes([asset], {})
    assert [(c.action, c.id) for c in changes] == [("create", "nightly-reflect")]
    # The same set on both sides is a noop.
    noop = plan_changes([asset], {asset.id: asset})
    assert all(c.action == "noop" for c in noop)


def test_malformed_asset_still_raises_schedule_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("spec:\n  cron: '0 3 * * *'\naction:\n  workflow: Nope\n")
    with pytest.raises(ScheduleError):
        load_schedules(str(tmp_path))
