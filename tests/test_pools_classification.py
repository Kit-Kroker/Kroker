"""Classification contract: the harness class vs. what the worker registers (024 T004).

Research R2 (one class authority, ``sdlc.pools.HARNESS_ACTIVITIES``) and R4
(static layer 1 of the no-site-missed guarantee). Everything is imported inside
the fixture/tests so a failure is a failed assertion, not a collection error.

RED today on exactly one assertion: ``check_test_drift`` is in ``vcs.ACTIVITIES``
and scheduled at ``code/step.py:711`` but never registered by
``worker.get_worker_activities()`` (the R2 latent defect). T005 fixes it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def registered_names() -> set[str]:
    from sdlc.worker import get_worker_activities

    return {a.__temporal_activity_definition.name for a in get_worker_activities()}  # type: ignore[attr-defined]


def test_every_harness_name_is_registered(registered_names: set[str]) -> None:
    # R2 / R4 layer 1: HARNESS_ACTIVITIES ⊆ registered. A harness name no worker
    # serves would strand its activity on the harness queue.
    from sdlc.pools import HARNESS_ACTIVITIES

    missing = sorted(HARNESS_ACTIVITIES - registered_names)
    assert not missing, f"harness names not registered by get_worker_activities(): {missing}"


def test_check_test_drift_is_registered(registered_names: set[str]) -> None:
    # R2 "Pre-existing defect": vcs.ACTIVITIES lists it and code/step.py:711
    # schedules it, but worker.py never registered it. RED until T005.
    assert "check_test_drift" in registered_names


def test_check_test_drift_is_in_the_harness_class() -> None:
    # R2 table: check_test_drift is a rule A.1(c) harness activity (worktree write).
    from sdlc.pools import HARNESS_ACTIVITIES

    assert "check_test_drift" in HARNESS_ACTIVITIES


def test_coding_activities_are_harness_class() -> None:
    # R2 Rationale / R4 layer 1: drift.CODING_ACTIVITIES ⊆ HARNESS_ACTIVITIES,
    # asserted here rather than imported by pools (pools stays a leaf).
    from sdlc.benchmarks.drift import CODING_ACTIVITIES
    from sdlc.pools import HARNESS_ACTIVITIES

    assert CODING_ACTIVITIES <= HARNESS_ACTIVITIES, sorted(CODING_ACTIVITIES - HARNESS_ACTIVITIES)


def test_every_vcs_activity_is_registered(registered_names: set[str]) -> None:
    # R2 defect, generalised: nothing in vcs.ACTIVITIES may be left unserved.
    from sdlc import vcs

    vcs_names = {a.__temporal_activity_definition.name for a in vcs.ACTIVITIES}  # type: ignore[attr-defined]
    missing = sorted(vcs_names - registered_names)
    assert not missing, f"vcs.ACTIVITIES not registered by get_worker_activities(): {missing}"


def test_janitor_is_not_an_activity(registered_names: set[str]) -> None:
    # R2 "The janitor": worktree_janitor is a plain worker-lifetime coroutine,
    # not an activity. It is placed by boot plan (all/harness only), never routed.
    from sdlc.vcs.janitor import worktree_janitor

    assert not hasattr(worktree_janitor, "__temporal_activity_definition")
    assert "worktree_janitor" not in registered_names


# ------------------------------------------------- chaos pass (024 T004, anti-vacuous / drift)


def test_harness_activities_has_exactly_28_names() -> None:
    # R2: the harness rows are 28 names. A name added or dropped without a
    # matching research update must fail loudly, not slide through the subset checks.
    from sdlc.pools import HARNESS_ACTIVITIES

    assert len(HARNESS_ACTIVITIES) == 28, sorted(HARNESS_ACTIVITIES)


def test_harness_activities_names_are_clean_strings() -> None:
    # No test-only junk: every element is a non-empty str in the queue-name-safe charset.
    import re

    from sdlc.pools import HARNESS_ACTIVITIES

    safe = re.compile(r"[A-Za-z0-9._-]{1,200}")
    bad = sorted(
        repr(n) for n in HARNESS_ACTIVITIES if not (isinstance(n, str) and safe.fullmatch(n))
    )
    assert not bad, f"harness names that are not non-empty queue-safe strings: {bad}"


def test_coding_activities_is_non_empty_before_the_subset_check() -> None:
    # Anti-vacuous guard: an accidentally-emptied CODING_ACTIVITIES would make
    # ``test_coding_activities_are_harness_class`` pass trivially (empty set <= anything).
    from sdlc.benchmarks.drift import CODING_ACTIVITIES

    assert len(CODING_ACTIVITIES) > 0


def test_get_worker_activities_registers_no_name_twice() -> None:
    # Duplicate registration: the defn-name set must be as long as the sequence.
    from sdlc.worker import get_worker_activities

    names = [a.__temporal_activity_definition.name for a in get_worker_activities()]  # type: ignore[attr-defined]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"activity names registered more than once: {dupes}"
    assert len(set(names)) == len(names)
