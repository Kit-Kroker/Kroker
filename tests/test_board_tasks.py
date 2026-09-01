# tests/test_board_tasks.py
"""Task lifecycle: state machine, the two-status split, optimistic locking."""

import threading

import pytest

from sdlc.artifacts.store import LocalFileStore
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore, ConflictError, InvalidTransition, NotFoundError
from sdlc.models import DevTask


def _tasks() -> list[DevTask]:
    return [
        DevTask(id="T01", title="config", description="d", acceptance_criteria=["a"]),
        DevTask(
            id="T02", title="api", description="d", acceptance_criteria=["a"], depends_on=["T01"]
        ),
    ]


@pytest.fixture
def store(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3", blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj")
    return s


@pytest.fixture
def plan_v(store):
    _, vid = store.publish_artifact_version("proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    store.sync_plan_tasks("proj", vid, "run-1", _tasks(), actor="workflow:run-1")
    return vid


def test_sync_creates_pending_tasks(store, plan_v):
    tasks = store.list_tasks("proj", plan_v)
    assert [t.task_id for t in tasks] == ["T01", "T02"]
    assert all(t.status is TaskStatus.PENDING for t in tasks)
    assert all(t.authoritative_status is TaskStatus.PENDING for t in tasks)
    assert all(t.row_version == 1 for t in tasks)


def test_sync_is_idempotent(store, plan_v):
    n = store.sync_plan_tasks("proj", plan_v, "run-1", _tasks(), actor="workflow:run-1")
    assert n == 0, "re-syncing the same plan must insert nothing"
    assert len(store.list_tasks("proj", plan_v)) == 2


def test_workflow_write_moves_both_statuses(store, plan_v):
    t = store.set_task_authoritative(
        "proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:run-1"
    )
    assert t.status is TaskStatus.IN_PROGRESS
    assert t.authoritative_status is TaskStatus.IN_PROGRESS
    assert t.row_version == 2


def test_agent_write_does_not_move_authoritative_status(store, plan_v):
    before = store.get_task("proj", plan_v, "T01")
    t = store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:worker-a",
        expect_row_version=before.row_version,
    )
    assert t.status is TaskStatus.IN_PROGRESS
    assert t.authoritative_status is TaskStatus.PENDING
    assert t.diverged is True


def test_stale_row_version_is_a_conflict(store, plan_v):
    before = store.get_task("proj", plan_v, "T01")
    store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:a",
        expect_row_version=before.row_version,
    )
    with pytest.raises(ConflictError):
        store.set_task_observational(
            "proj",
            plan_v,
            "T01",
            TaskStatus.BLOCKED,
            actor="agent:b",
            expect_row_version=before.row_version,
        )


def test_invalid_transition_is_rejected(store, plan_v):
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:run-1")


def test_done_is_terminal(store, plan_v):
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative(
            "proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r"
        )


def test_rejected_write_appends_no_event(store, plan_v):
    before = len(store.list_events("proj"))
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    assert len(store.list_events("proj")) == before, "the change log records real changes only"


def test_authoritative_validates_against_authoritative_status(store, plan_v):
    """An agent moving `status` must not unlock a workflow transition."""
    before = store.get_task("proj", plan_v, "T01")
    store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:a",
        expect_row_version=before.row_version,
    )
    with pytest.raises(InvalidTransition):
        # authoritative_status is still PENDING, so PENDING -> DONE is invalid
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")


def test_fix_attempts_and_error_are_recorded(store, plan_v):
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    t = store.set_task_authoritative(
        "proj",
        plan_v,
        "T01",
        TaskStatus.FAILED,
        actor="workflow:r",
        fix_attempts=2,
        error="build failed",
        branch="task/T01",
    )
    assert (t.fix_attempts, t.error, t.branch) == (2, "build failed", "task/T01")


def test_unknown_task_raises_not_found(store, plan_v):
    with pytest.raises(NotFoundError):
        store.get_task("proj", plan_v, "T99")


def test_two_threads_claiming_one_task_yield_one_winner(tmp_path):
    """The race the whole design exists to make safe."""
    db = tmp_path / "b.sqlite3"
    setup = BoardStore(db=db, blobs=LocalFileStore(root=tmp_path / "runs"))
    setup.ensure_project("proj")
    _, vid = setup.publish_artifact_version("proj", "plan", "r", b"{}", actor="workflow:r")
    setup.sync_plan_tasks("proj", vid, "r", _tasks(), actor="workflow:r")
    rv = setup.get_task("proj", vid, "T01").row_version

    results: list[str] = []
    lock = threading.Lock()

    def claim(name: str) -> None:
        s = BoardStore(db=db, blobs=LocalFileStore(root=tmp_path / "runs"))
        try:
            s.set_task_observational(
                "proj",
                vid,
                "T01",
                TaskStatus.IN_PROGRESS,
                actor=f"agent:{name}",
                expect_row_version=rv,
            )
            with lock:
                results.append("won")
        except ConflictError:
            with lock:
                results.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=claim, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["conflict", "won"], f"exactly one claim must win, got {results}"


def test_authoritative_re_execution_is_idempotent(store, plan_v):
    """Temporal is at-least-once: an activity that committed but whose
    completion wasn't reported re-executes. A repeated DONE must not raise
    InvalidTransition (which would burn all 5 retry attempts identically and
    permanently fail the run at a task boundary)."""
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    # Re-execution of the same authoritative write: a no-op, not an error.
    t = store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    assert t.authoritative_status is TaskStatus.DONE
    # No event is appended for the no-op re-execution.
    before = len(store.list_events("proj"))
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    assert len(store.list_events("proj")) == before
