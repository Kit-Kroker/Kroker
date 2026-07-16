"""The shipped nightly-reflect asset (E-13, FR-404). Guards the scope
boundary: project banks only — org_bank has no writers, so an org schedule
would be a permanent no-op behind a checked box."""
from __future__ import annotations

from pathlib import Path

from sdlc.schedules.apply import to_temporal
from sdlc.schedules.loader import DEFAULT_SCHEDULES_DIR, load_schedules

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_default_schedules_dir_points_at_the_repo_schedules_folder():
    assert DEFAULT_SCHEDULES_DIR == REPO_ROOT / "schedules"


def test_nightly_reflect_asset_ships_and_loads():
    assets = {a.id: a for a in load_schedules(DEFAULT_SCHEDULES_DIR)}
    assert "nightly-reflect" in assets


def test_nightly_reflect_targets_reflect_workflow_nightly():
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    assert a.action.workflow == "ReflectWorkflow"
    assert len(a.spec.cron.split()) == 5
    assert a.action.banks


def test_nightly_reflect_is_project_scoped_only():
    # Scope guard (spec: Findings §3). org_bank has no writers — every
    # _retain call site in feature.py passes project_bank — so an org bank
    # here would consolidate nothing, nightly, forever.
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    for bank in a.action.banks:
        assert bank.startswith("project:"), (
            f"{bank!r} is not project-scoped; org reflect is out of scope "
            f"until something retains to org_bank")


def test_shipped_asset_translates_to_a_temporal_schedule():
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    sched = to_temporal(a)
    assert sched.spec.cron_expressions == [a.spec.cron]
    assert sched.action.workflow == "ReflectWorkflow"
