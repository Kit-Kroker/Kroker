"""Contract & happy-path tests for the RecallSnapshot artifact (round 021, FR-402).

Sections: hash (T002), model (T004), persist (T009), reader (T011).
Failure-path cases (persist failure, backend failure) are covered elsewhere.
Tests import their targets inside the test body so each one fails on its
own, for the expected reason, until the implementation lands.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from sdlc.memory.fake import FakeMemory
from sdlc.memory.models import MemoryKind, RetainItem


def _canonical_expected(bank, watermark, query_hash, items, degraded) -> bytes:
    return json.dumps(
        ["recall_snapshot/v1", bank, watermark, query_hash, items, degraded],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# ---------------------------------------------------------------- hash (T002)


def test_same_inputs_give_the_same_hash():
    import sdlc.memory.query_hash as qh

    a = qh.recall_snapshot_hash("b", "w", "q", ["x", "y"], False)
    b = qh.recall_snapshot_hash("b", "w", "q", ["x", "y"], False)
    assert a == b


def test_swapping_two_items_changes_the_hash():
    import sdlc.memory.query_hash as qh

    assert qh.recall_snapshot_hash("b", "w", "q", ["x", "y"], False) != (
        qh.recall_snapshot_hash("b", "w", "q", ["y", "x"], False)
    )


def test_degraded_flag_changes_the_hash_for_an_otherwise_identical_snapshot():
    import sdlc.memory.query_hash as qh

    assert qh.recall_snapshot_hash("b", "w", "q", [], True) != (
        qh.recall_snapshot_hash("b", "w", "q", [], False)
    )


def test_hash_is_sha256_of_the_canonical_bytes():
    import sdlc.memory.query_hash as qh

    canon = qh.recall_snapshot_canonical("b", "w", "q", ["x"], False)
    assert qh.recall_snapshot_hash("b", "w", "q", ["x"], False) == (
        hashlib.sha256(canon).hexdigest()
    )


def test_canonical_bytes_are_the_versioned_compact_json_array():
    import sdlc.memory.query_hash as qh

    canon = qh.recall_snapshot_canonical("project:default", "3", "01cb", ["é", "y"], False)
    assert canon == _canonical_expected("project:default", "3", "01cb", ["é", "y"], False)
    assert json.loads(canon)[0] == "recall_snapshot/v1"


# --------------------------------------------------------------- model (T004)


def test_healthy_model_gets_a_hash_and_no_ref():
    import sdlc.memory.query_hash as qh
    from sdlc.memory.models import RecallSnapshot

    snap = RecallSnapshot(query_hash="q", bank="b", watermark="w")
    assert snap.snapshot_hash
    assert snap.snapshot_hash == qh.recall_snapshot_hash("b", "w", "q", [], False)
    assert snap.ref is None
    assert snap.persist_failed is False


def test_disabled_shape_keeps_an_empty_hash():
    from sdlc.memory.models import RecallSnapshot

    snap = RecallSnapshot(query_hash="", bank="b", watermark="unknown")
    assert snap.snapshot_hash == ""


def test_degraded_model_with_empty_query_hash_still_gets_a_hash():
    import sdlc.memory.query_hash as qh
    from sdlc.memory.models import RecallSnapshot

    snap = RecallSnapshot(query_hash="", bank="b", watermark="w", degraded=True)
    assert snap.snapshot_hash == qh.recall_snapshot_hash("b", "w", "", [], True)


def test_explicit_snapshot_hash_is_kept():
    from sdlc.memory.models import RecallSnapshot

    snap = RecallSnapshot(query_hash="q", bank="b", watermark="w", snapshot_hash="preset")
    assert snap.snapshot_hash == "preset"


def test_pre_021_recorded_shape_validates_and_gets_a_hash():
    import sdlc.memory.query_hash as qh
    from sdlc.memory.models import RecallSnapshot

    raw = (
        '{"query_hash":"01cb","bank":"project:default","watermark":"0","items":[],"degraded":false}'
    )
    snap = RecallSnapshot.model_validate_json(raw)
    assert snap.items == []
    assert snap.degraded is False
    assert snap.snapshot_hash == qh.recall_snapshot_hash("project:default", "0", "01cb", [], False)


# ------------------------------------------------------------- persist (T009)


@pytest.fixture
def artifact_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_recall_persists_snapshot_at_run_recall_hash_path(monkeypatch, artifact_root):
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:p", text="alpha", metadata={}))

    snap = await recall_snapshot(
        RecallInput(bank="project:p", query="q", backend="fake", watermark="1", run_id="run-1")
    )

    path = artifact_root / "run-1" / "recall" / f"{snap.snapshot_hash}.json"
    assert path.is_file()
    assert snap.ref is not None
    assert snap.ref.kind == "recall_snapshot"
    assert snap.ref.uri == path.resolve().as_uri()
    assert snap.persist_failed is False


@pytest.mark.asyncio
async def test_persisted_bytes_hash_to_snapshot_hash_and_ref_sha(monkeypatch, artifact_root):
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:p", text="alpha", metadata={}))

    snap = await recall_snapshot(
        RecallInput(bank="project:p", query="q", backend="fake", watermark="1", run_id="run-1")
    )

    data = (artifact_root / "run-1" / "recall" / f"{snap.snapshot_hash}.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == snap.snapshot_hash
    assert snap.ref.sha256 == snap.snapshot_hash
    assert data == _canonical_expected("project:p", "1", snap.query_hash, ["alpha"], False)


@pytest.mark.asyncio
async def test_identical_second_call_is_idempotent(monkeypatch, artifact_root):
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:p", text="alpha", metadata={}))
    inp = RecallInput(bank="project:p", query="q", backend="fake", watermark="1", run_id="run-1")

    first = await recall_snapshot(inp)
    first_bytes = (artifact_root / "run-1" / "recall" / f"{first.snapshot_hash}.json").read_bytes()
    second = await recall_snapshot(inp)

    recall_dir = artifact_root / "run-1" / "recall"
    files = sorted(p.name for p in recall_dir.iterdir())
    assert files == [f"{first.snapshot_hash}.json"]
    assert second.snapshot_hash == first.snapshot_hash
    assert (recall_dir / files[0]).read_bytes() == first_bytes


@pytest.mark.asyncio
async def test_empty_run_id_writes_nothing_and_has_no_ref(monkeypatch, artifact_root):
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:p", text="alpha", metadata={}))

    snap = await recall_snapshot(
        RecallInput(bank="project:p", query="q", backend="fake", watermark="1", run_id="")
    )

    assert snap.ref is None
    assert snap.persist_failed is False
    assert not (artifact_root / "recall").exists()
    assert not any(artifact_root.rglob("*.json"))


@pytest.mark.asyncio
async def test_persisted_items_are_scrubbed_not_the_raw_secret(monkeypatch, artifact_root):
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    # Seed the fake directly so the item reaches recall UNscrubbed:
    # the check under test is the recall-side scrub (FR-012), not retain's.
    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank="project:s",
            text="used sk-abcdefghijklmnopqrstuvwx to auth",
            metadata={},
        )
    )

    snap = await recall_snapshot(
        RecallInput(bank="project:s", query="q", backend="fake", watermark="1", run_id="run-s")
    )

    data = (artifact_root / "run-s" / "recall" / f"{snap.snapshot_hash}.json").read_bytes()
    assert b"sk-abcdefghijklmnopqrstuvwx" not in data
    assert "[REDACTED_API_KEY]" in data.decode("utf-8")
    assert snap.items == ["used [REDACTED_API_KEY] to auth"]


# ------------------------------------------------------------- reader (T011)


@pytest.mark.asyncio
async def test_read_round_trips_a_persisted_healthy_snapshot(monkeypatch, artifact_root):
    import sdlc.artifacts.read as read_mod
    import sdlc.memory.activities as activities
    from sdlc.memory.activities import RecallInput, recall_snapshot

    fm = FakeMemory()
    monkeypatch.setattr(activities, "_fake_singleton", fm)
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:r", text="alpha", metadata={}))
    await fm.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:r", text="beta", metadata={}))

    snap = await recall_snapshot(
        RecallInput(bank="project:r", query="q", backend="fake", watermark="2", run_id="run-rt")
    )

    got = read_mod.read_recall_snapshot(snap.ref)
    assert got.items == ["alpha", "beta"]
    assert got.model_dump(exclude={"ref"}) == snap.model_dump(exclude={"ref"})


def test_read_returns_a_degraded_snapshot_written_in_canonical_form(artifact_root):
    import sdlc.memory.query_hash as qh
    from sdlc.artifacts.store import LocalFileStore

    h = qh.recall_snapshot_hash("project:d", "4", "q9", [], True)
    data = qh.recall_snapshot_canonical("project:d", "4", "q9", [], True)
    ref = LocalFileStore(artifact_root).put("recall_snapshot", "run-deg", f"{h}.json", data)

    import sdlc.artifacts.read as read_mod

    got = read_mod.read_recall_snapshot(ref)
    assert got.degraded is True
    assert got.items == []
    assert got.bank == "project:d"
    assert got.watermark == "4"
    assert got.query_hash == "q9"
    assert got.snapshot_hash == h
