# tests/test_board_artifacts.py
"""Artifact publish: version numbering, lineage, pointer movement."""

import pytest

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.models import ArtifactStatus
from sdlc.board.store import BoardStore, NotFoundError


@pytest.fixture
def store(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3", blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj", repo="git@example:acme/x")
    return s


def test_first_publish_is_v1_and_becomes_current(store):
    ref, vid = store.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"a"}', actor="workflow:run-1"
    )
    art = store.get_artifact("proj", "architecture")
    assert art.status is ArtifactStatus.CURRENT
    assert art.current_version == vid
    versions = store.list_versions("proj", "architecture")
    assert [v.n for v in versions] == [1]
    assert versions[0].supersedes is None
    assert ref.sha256 == versions[0].sha256


def test_blob_lands_in_claim_check_store_and_round_trips(store):
    body = b'{"overview":"a"}'
    ref, _ = store.publish_artifact_version(
        "proj", "architecture", "run-1", body, actor="workflow:run-1"
    )
    assert ref_to_path(ref).read_bytes() == body
    assert "artifacts" in ref.uri


def test_second_publish_supersedes_the_first(store):
    _, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b"1", actor="workflow:run-1"
    )
    _, v2 = store.publish_artifact_version(
        "proj", "architecture", "run-2", b"2", actor="workflow:run-2"
    )
    art = store.get_artifact("proj", "architecture")
    assert art.current_version == v2
    by_id = {v.id: v for v in store.list_versions("proj", "architecture")}
    assert by_id[v2].supersedes == v1
    assert by_id[v2].n == 2


def test_rejected_publish_records_version_but_does_not_move_pointer(store):
    _, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b"1", actor="workflow:run-1"
    )
    _, v2 = store.publish_artifact_version(
        "proj",
        "architecture",
        "run-2",
        b"bad",
        status=ArtifactStatus.REJECTED,
        actor="workflow:run-2",
    )
    art = store.get_artifact("proj", "architecture")
    assert art.current_version == v1, "rejected design must not become current"
    assert len(store.list_versions("proj", "architecture")) == 2
    assert store.get_version("proj", v2).n == 2


def test_publish_appends_exactly_one_event(store):
    store.publish_artifact_version("proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    events = store.list_events("proj")
    assert len(events) == 1
    assert events[0].subject == "artifact:plan"
    assert events[0].actor == "workflow:run-1"
    assert events[0].to_status == "current"


def test_unknown_artifact_raises_not_found(store):
    with pytest.raises(NotFoundError):
        store.get_artifact("proj", "architecture")


def test_versions_are_independent_per_key(store):
    store.publish_artifact_version("proj", "plan", "r", b"1", actor="workflow:r")
    store.publish_artifact_version("proj", "architecture", "r", b"1", actor="workflow:r")
    assert store.list_versions("proj", "plan")[0].n == 1
    assert store.list_versions("proj", "architecture")[0].n == 1


def test_publish_re_execution_is_idempotent_on_identical_content(store):
    """Temporal re-executes an activity whose completion wasn't reported.
    A repeated publish of byte-identical content must return the existing
    version — not create a duplicate with a bogus supersedes link, and not
    append a second event."""
    ref1, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"same"}', actor="workflow:run-1"
    )
    ref2, v2 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"same"}', actor="workflow:run-1"
    )
    assert v1 == v2, "re-execution must return the same version id"
    assert ref1.sha256 == ref2.sha256
    versions = store.list_versions("proj", "architecture")
    assert [x.n for x in versions] == [1], "no duplicate version row"
    events = [e for e in store.list_events("proj") if e.subject == "artifact:architecture"]
    assert len(events) == 1, "no duplicate event for the re-execution"


def test_publish_different_content_still_versions(store):
    """Idempotency keys on content (sha256), so genuinely new content
    still produces a new version — the dedupe is retry-safety, not a cap."""
    _, v1 = store.publish_artifact_version("proj", "architecture", "r", b"a", actor="workflow:r")
    _, v2 = store.publish_artifact_version("proj", "architecture", "r", b"b", actor="workflow:r")
    assert v2 != v1
    assert [x.n for x in store.list_versions("proj", "architecture")] == [1, 2]


def test_cross_run_republish_with_identical_content_is_distinct(store):
    """Dedupe is scoped to run_id: Temporal re-execution is always within one
    workflow run, so (project, key, run_id, sha256) catches retries. A second
    RUN publishing byte-identical content (the common case under
    _cached_stage memoization) must still append its own version — each run
    is visible on the board, with its own event and run_id."""
    _, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"same"}', actor="workflow:run-1"
    )
    _, v2 = store.publish_artifact_version(
        "proj", "architecture", "run-2", b'{"overview":"same"}', actor="workflow:run-2"
    )
    assert v1 != v2, "a different run must get its own version"
    versions = store.list_versions("proj", "architecture")
    assert [x.n for x in versions] == [1, 2]
    assert {x.run_id for x in versions} == {"run-1", "run-2"}
    art = store.get_artifact("proj", "architecture")
    assert art.current_version == v2  # run-2's version is now current
    events = [e for e in store.list_events("proj") if e.subject == "artifact:architecture"]
    assert len(events) == 2, "each run appends its own event"
