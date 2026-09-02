# tests/test_dispositions_store.py
"""FR-304 (E-50): finding-disposition persistence, mirroring E-47a's
BoardIdentityStore discipline exactly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import (
    BoardFindingDispositionStore,
    FindingDispositionConflictError,
)


@pytest.fixture()
def store(tmp_path):
    s = BoardFindingDispositionStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fd(kind="vulnerability", key="SS1:hardcoded-secret:src/a.py:", **kw) -> FindingDisposition:
    base = dict(
        kind=kind,
        key=key,
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


def test_empty_project_loads_empty_at_version_zero(store):
    assert store.load("p") == []
    assert store.registry_version("p") == 0


def test_apply_round_trips_a_disposition(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    (got,) = store.load("p")
    assert got.key == "SS1:hardcoded-secret:src/a.py:"
    assert got.disposition is Disposition.ACCEPTED_RISK


def test_apply_bumps_registry_version(store):
    assert store.apply("p", _fd(), expected_version=0, actor="maks") == 1
    assert store.apply("p", _fd(key="SS1:x:src/b.py:"), expected_version=1, actor="maks") == 2


def test_stale_expected_version_conflicts(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    with pytest.raises(FindingDispositionConflictError):
        store.apply("p", _fd(key="SS1:x:src/b.py:"), expected_version=0, actor="maks")


def test_a_second_apply_on_the_same_kind_and_key_revises_it_not_accumulates(store):
    """A human revising a prior call, not a growing history of live rows."""
    store.apply("p", _fd(disposition=Disposition.FALSE_POSITIVE), expected_version=0, actor="maks")
    store.apply(
        "p",
        _fd(disposition=Disposition.ACCEPTED_RISK, reason="changed my mind"),
        expected_version=1,
        actor="maks",
    )
    rows = store.load("p")
    assert len(rows) == 1
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_two_applies_to_the_same_kind_and_key_leave_two_event_rows(store):
    """The spec's testing bullet: revising a disposition updates the live
    row but the audit trail keeps both events (mirrors capability_event)."""
    store.apply("p", _fd(disposition=Disposition.FALSE_POSITIVE), expected_version=0, actor="maks")
    store.apply(
        "p",
        _fd(disposition=Disposition.ACCEPTED_RISK, reason="changed my mind"),
        expected_version=1,
        actor="maks",
    )
    ops = store.events("p", "vulnerability", "SS1:hardcoded-secret:src/a.py:")
    assert ops == ["dispose", "dispose"]


def test_vulnerability_and_testability_dispositions_on_the_same_key_do_not_collide(store):
    """The (kind, key) composite primary key, not prefix sniffing, keeps
    the two finding families apart (GD7)."""
    store.apply("p", _fd(kind="vulnerability", key="SHARED"), expected_version=0, actor="maks")
    store.apply("p", _fd(kind="testability", key="SHARED"), expected_version=1, actor="maks")
    rows = {(r.kind, r.key): r for r in store.load("p")}
    assert len(rows) == 2


def test_projects_are_isolated(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    assert store.load("other") == []


def test_load_returns_rows_sorted_by_kind_then_key(store):
    store.apply("p", _fd(kind="vulnerability", key="b"), expected_version=0, actor="maks")
    store.apply("p", _fd(kind="testability", key="a"), expected_version=1, actor="maks")
    store.apply("p", _fd(kind="vulnerability", key="a"), expected_version=2, actor="maks")
    assert [(r.kind, r.key) for r in store.load("p")] == [
        ("testability", "a"),
        ("vulnerability", "a"),
        ("vulnerability", "b"),
    ]


def test_reopening_the_same_db_sees_prior_state(tmp_path):
    db = tmp_path / "board.sqlite3"
    first = BoardFindingDispositionStore(db=db)
    first.apply("p", _fd(), expected_version=0, actor="maks")
    first.close()
    second = BoardFindingDispositionStore(db=db)
    assert [r.key for r in second.load("p")] == ["SS1:hardcoded-secret:src/a.py:"]
    second.close()
