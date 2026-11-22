"""US1 contract: the ``choose_starts`` start-selection policy (023b T036, RED).

Split out of ``test_execution.py`` on 2026-11-22 to stay under the 1000-line
ceiling (AGENTS.md): that file pinned five pure subjects of
``sdlc.maintenance.execution``, and this is the last of them. The three
builders below are copies of the ones in ``test_execution.py``, kept local so
neither file imports the other.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from sdlc.maintenance.models import Incident, MaintenanceConfig, RepairAction, RepairPlan
from sdlc.triage.models import FixClass, TriageFinding

# --------------------------------------------------------------------------- builders


def _finding(fix_class: FixClass) -> TriageFinding:
    return TriageFinding(
        signal="secrets",
        rule="env_file_tracked",
        severity="high",
        detail=".env is tracked; add it to .gitignore and remove it from the index.",
        path=".gitignore",
        fix_class=fix_class,
    )


def _incident(
    fix_class: FixClass = FixClass.MECHANICAL,
    *,
    consecutive_seen: int = 2,
    reopens: int = 0,
) -> Incident:
    return Incident(
        no=1,
        key="secrets:env_file_tracked:.gitignore",
        kind="finding",
        finding=_finding(fix_class),
        commit_sha="a" * 40,
        first_seen_cycle=1,
        last_seen_cycle=2,
        consecutive_seen=consecutive_seen,
        reopens=reopens,
    )


def _plan(actions: list[RepairAction], *, floor: float, self_confidence: float = 0.9) -> RepairPlan:
    # RepairPlan requires effective == min(self_confidence, floor) (023a FR-010).
    return RepairPlan(
        analysis="The .env file is tracked and holds a live token.",
        actions=actions,
        self_confidence=self_confidence,
        floor=floor,
        effective=min(self_confidence, floor),
        author_model="claude-sonnet-5-5",
    )


# =========================================================================== #
# T036 (023b, RED): the start-selection policy (R10, B-FR-010/011, SC-B06).
#
# Subject: ``choose_starts(incidents, exec_starts, cfg, now) -> StartPlan`` in
# ``sdlc.maintenance.execution``. The interim in maintenance_execute.py has the
# same arguments but returns a plain list. This one returns a frozen StartPlan.
#
# SHAPE CHOSEN (pinned by test_start_plan_shape_is_pinned):
#   StartPlan(starts, queued, exec_starts, notice), all frozen and PURE:
#   - starts / queued: tuples of incident numbers, in number order.
#   - exec_starts: the window AFTER pruning to 7 days. The caller stamps the
#     new starts itself, so choose_starts never appends.
#   - notice: one string when anything was queued, else None. One per call.
#
# Gate order (R10): 1 path overlap (live EXECUTING/VERIFYING on the same path),
# 2 per-cycle cap, 3 window cap. may_execute is NOT part of this function.
#
# Each test imports choose_starts / StartPlan inside its body, so before T037
# each case fails per test on ImportError.
# =========================================================================== #

_NOW_DAY = 15


def _now():
    from datetime import UTC, datetime

    return datetime(2026, 11, _NOW_DAY, 12, tzinfo=UTC)


def _caps_cfg(*, per_cycle: int = 1, window: int = 3) -> MaintenanceConfig:
    return MaintenanceConfig(
        project="demo",
        repo_dir="/srv/repos/demo",
        build_probe=False,
        max_starts_per_cycle=per_cycle,
        max_starts_per_window=window,
    )


def _caps_incident(no: int, state: str = "approved", paths=(".gitignore",)):
    """An incident numbered ``no`` in ``state``, whose one code_fix touches ``paths``."""
    from sdlc.maintenance.models import IncidentState

    actions = [RepairAction(kind="code_fix", summary=f"fix {no}", target_paths=list(paths))]
    return _incident(FixClass.MECHANICAL).model_copy(
        update={
            "no": no,
            "key": f"caps-{no}",
            "state": IncidentState(state),
            "plan": _plan(actions, floor=0.95),
        }
    )


def test_start_plan_shape_is_pinned():
    from dataclasses import fields

    from sdlc.maintenance.execution import StartPlan

    assert [f.name for f in fields(StartPlan)] == ["starts", "queued", "exec_starts", "notice"]


def test_one_cap_starts_the_lowest_number_and_queues_the_rest():
    from sdlc.maintenance.execution import choose_starts

    incidents = [
        _caps_incident(1, paths=(".gitignore",)),
        _caps_incident(2, paths=("config/a.ini",)),
        _caps_incident(3, paths=("docs/b.md",)),
    ]
    plan = choose_starts(incidents, [], _caps_cfg(per_cycle=1), _now())
    assert plan.starts == (1,)
    assert plan.queued == (2, 3)
    assert isinstance(plan.notice, str), "a held incident notifies the operator once"


def test_the_window_cap_queues_everything_and_notifies_once():
    from sdlc.maintenance.execution import choose_starts

    recent = [_now() - timedelta(days=d) for d in (1, 2, 3)]
    incidents = [_caps_incident(1), _caps_incident(2, paths=("config/a.ini",))]
    plan = choose_starts(incidents, recent, _caps_cfg(per_cycle=3, window=3), _now())
    assert plan.starts == ()
    assert plan.queued == (1, 2)
    assert isinstance(plan.notice, str)


def test_stamps_older_than_seven_days_do_not_count_toward_the_window():
    from sdlc.maintenance.execution import choose_starts

    old = [_now() - timedelta(days=8, hours=d) for d in (1, 2, 3)]
    plan = choose_starts([_caps_incident(1)], old, _caps_cfg(per_cycle=1, window=3), _now())
    assert plan.starts == (1,), "an 8-day-old stamp is outside the rolling window"
    assert plan.exec_starts == (), "the returned window excludes the pruned stamps"


@pytest.mark.parametrize("live_state", ["executing", "verifying"])
def test_a_path_overlap_with_a_live_incident_queues_without_consuming_a_start(live_state):
    from sdlc.maintenance.execution import choose_starts

    incidents = [
        _caps_incident(1, state=live_state, paths=("src/a.py",)),
        _caps_incident(2, paths=("src/a.py",)),  # overlaps the live one
        _caps_incident(3, paths=("src/b.py",)),  # different path: starts beside it
    ]
    plan = choose_starts(incidents, [], _caps_cfg(per_cycle=1), _now())
    assert plan.starts == (3,), "the overlapping incident must not take the cycle's start"
    assert plan.queued == (2,)


def test_incidents_are_walked_in_number_order_regardless_of_list_order():
    from sdlc.maintenance.execution import choose_starts

    incidents = [_caps_incident(5), _caps_incident(2, paths=("config/a.ini",))]
    plan = choose_starts(incidents, [], _caps_cfg(per_cycle=1), _now())
    assert plan.starts == (2,)
    assert plan.queued == (5,)


def test_no_cap_and_no_overlap_means_no_notice():
    from sdlc.maintenance.execution import choose_starts

    plan = choose_starts([_caps_incident(1)], [], _caps_cfg(per_cycle=3, window=3), _now())
    assert plan.starts == (1,)
    assert plan.queued == ()
    assert plan.notice is None


def test_choose_starts_is_pure_and_never_mutates_its_inputs():
    from sdlc.maintenance.execution import choose_starts

    incidents = [_caps_incident(1), _caps_incident(2, paths=("config/a.ini",))]
    stamps = [_now() - timedelta(days=1)]
    snap_inc = [i.model_dump_json() for i in incidents]
    snap_stamps = list(stamps)
    first = choose_starts(incidents, stamps, _caps_cfg(per_cycle=1), _now())
    second = choose_starts(incidents, stamps, _caps_cfg(per_cycle=1), _now())
    assert first == second
    assert [i.model_dump_json() for i in incidents] == snap_inc
    assert stamps == snap_stamps


def test_starts_chosen_earlier_in_the_same_cycle_count_toward_the_window():
    """R10: the window cap is a rolling 7-day cap, so it must hold WITHIN a cycle.
    With window 1 and no prior stamps, the per-cycle cap of 3 must not let two
    incidents start in one cycle."""
    from sdlc.maintenance.execution import choose_starts

    incidents = [_caps_incident(1), _caps_incident(2, paths=("config/a.ini",))]
    plan = choose_starts(incidents, [], _caps_cfg(per_cycle=3, window=1), _now())
    assert plan.starts == (1,)
    assert plan.queued == (2,)


# -------------------------------------------------------- EDGE (023b T036) -- qa-chaos
#
# Convention pinned here, so T037 cannot guess it: a start stamp is inside the
# rolling window iff ``now - stamp <= 7 days`` (inclusive). A stamp exactly 7 days
# old still counts. A stamp 7 days plus one microsecond old does not.


def test_the_seven_day_window_is_inclusive_at_seven_days_and_exclusive_one_microsecond_past():
    """Edge, RED until T037 (ImportError). Both sides of the 7-day boundary."""
    from datetime import timedelta

    from sdlc.maintenance.execution import choose_starts

    cfg = _caps_cfg(per_cycle=1, window=1)

    held = choose_starts([_caps_incident(1)], [_now() - timedelta(days=7)], cfg, _now())
    assert held.starts == (), "a stamp exactly 7 days old is inside the window"
    assert held.queued == (1,)

    freed = choose_starts(
        [_caps_incident(1)],
        [_now() - timedelta(days=7, microseconds=1)],
        cfg,
        _now(),
    )
    assert freed.starts == (1,), "a stamp 7 days plus 1 microsecond old is outside the window"
    assert freed.exec_starts == (), "the pruned window excludes it"


def test_a_queued_incident_starts_on_the_next_call_and_call_one_stamp_counts_toward_it():
    """Edge, RED until T037 (ImportError). The two-call rhythm the e2e suite drives:
    call 1 starts incident 1 and queues incident 2. The caller stamps the start.
    Call 2 starts incident 2 when the window has room. The same call with window
    1 starts nothing, because the call-1 stamp fills it."""
    from sdlc.maintenance.execution import choose_starts

    first = choose_starts(
        [_caps_incident(1), _caps_incident(2, paths=("config/a.ini",))],
        [],
        _caps_cfg(per_cycle=1, window=2),
        _now(),
    )
    assert first.starts == (1,)
    assert first.queued == (2,)
    stamps = [*first.exec_starts, _now()]  # the caller stamps the new start

    def _second_call_inputs():
        return [
            _caps_incident(1, state="executing"),
            _caps_incident(2, state="queued", paths=("config/a.ini",)),
        ]

    second = choose_starts(_second_call_inputs(), stamps, _caps_cfg(per_cycle=1, window=2), _now())
    assert second.starts == (2,), "the held incident starts once the window has room"
    assert second.queued == ()

    blocked = choose_starts(_second_call_inputs(), stamps, _caps_cfg(per_cycle=1, window=1), _now())
    assert blocked.starts == (), "the call-1 stamp consumes the only window slot"
    assert blocked.queued == (2,)
