# tests/test_board_stats.py
"""Evidence attachment and board-owned counters."""
import pytest

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore
from sdlc.models import DevTask


@pytest.fixture
def seeded(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3",
                   blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj")
    _, vid = s.publish_artifact_version("proj", "plan", "run-1", b"{}",
                                        actor="workflow:run-1")
    s.sync_plan_tasks("proj", vid, "run-1", [
        DevTask(id="T01", title="a", description="d",
                acceptance_criteria=["x"]),
        DevTask(id="T02", title="b", description="d",
                acceptance_criteria=["x"]),
    ], actor="workflow:run-1")
    return s, vid


def test_evidence_round_trips(seeded):
    store, vid = seeded
    ref = store.attach_task_evidence("proj", vid, "T01", "run-1", "qa",
                                     b'{"passed":true}')
    assert ref_to_path(ref).read_bytes() == b'{"passed":true}'
    ev = store.list_evidence("proj", vid, "T01")
    assert len(ev) == 1
    assert ev[0].kind == "qa"
    assert ev[0].sha256 == ref.sha256


def test_unknown_evidence_kind_is_rejected(seeded):
    store, vid = seeded
    with pytest.raises(ValueError):
        store.attach_task_evidence("proj", vid, "T01", "run-1", "vibes",
                                   b"{}")


def test_stats_count_by_authoritative_status_only(seeded):
    store, vid = seeded
    before = store.get_task("proj", vid, "T01")
    store.set_task_observational("proj", vid, "T01", TaskStatus.IN_PROGRESS,
                                 actor="agent:a",
                                 expect_row_version=before.row_version)
    s = store.stats("proj")
    assert s.tasks_by_status["pending"] == 2, \
        "an agent's observational write must not change the counted status"
    assert s.diverged_tasks == 1


def test_stats_aggregate_fix_attempts_and_errors(seeded):
    store, vid = seeded
    store.set_task_authoritative("proj", vid, "T01", TaskStatus.IN_PROGRESS,
                                 actor="workflow:r")
    store.set_task_authoritative("proj", vid, "T01", TaskStatus.FAILED,
                                 actor="workflow:r", fix_attempts=3,
                                 error="boom")
    s = store.stats("proj")
    assert s.total_fix_attempts == 3
    assert s.tasks_with_error == 1
    assert s.tasks_by_status == {"failed": 1, "pending": 1}


def test_stats_counts_events(seeded):
    store, vid = seeded
    s = store.stats("proj")
    # 1 artifact publish + 2 task creations
    assert s.event_count == 3
