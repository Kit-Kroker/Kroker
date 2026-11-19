"""The shipped nightly-reflect asset (E-13, FR-404; E-25 adds the org half).
Guards the scope boundary: `banks` stays project-only — the org bank reaches
the job via the promotion field (`org_bank`), never via a `banks:` entry,
because nightly promotion is what writes org (E-25)."""

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
    # Scope guard (spec: Findings §3), E-25 shape: `banks` is still
    # project-only. The org bank never rides `banks` — org gets its writers
    # via the nightly promotion below, and consolidating an org entry here
    # before promotion ran would consolidate nothing.
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    for bank in a.action.banks:
        assert bank.startswith("project:"), (
            f"{bank!r} is not project-scoped; org reaches the job via the "
            f"promotion field (org_bank), not via banks"
        )


def test_nightly_reflect_promotes_to_org():
    # E-25: org gets writers via this nightly job. The promotion field is
    # on, so recurring gotchas cross into org and org reflects after.
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    assert a.action.org_bank == "org"


def test_shipped_asset_translates_to_a_temporal_schedule():
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    sched = to_temporal(a)
    assert sched.spec.cron_expressions == [a.spec.cron]
    assert sched.action.workflow == "ReflectWorkflow"
    # The org half must survive translation: the workflow arg carries the
    # promotion target, so the fired job promotes before reflecting org.
    assert sched.action.args[0].org_bank == "org"
