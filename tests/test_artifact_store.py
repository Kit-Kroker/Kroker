"""E-38: first real claim-check store (file:// backend behind a seam)."""

import hashlib

from sdlc.artifacts.store import LocalFileStore, ref_to_path


def test_put_writes_under_run_sessions_dir(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("harness_session", "run-1", "t1-a1.jsonl", b"hello\n")
    assert ref.kind == "harness_session"
    assert ref.uri.startswith("file://")
    p = tmp_path / "run-1" / "sessions" / "t1-a1.jsonl"
    assert p.read_bytes() == b"hello\n"
    assert ref.sha256 == hashlib.sha256(b"hello\n").hexdigest()


def test_digest_kind_lands_beside_full(tmp_path):
    store = LocalFileStore(root=tmp_path)
    store.put("harness_session_digest", "run-1", "t1-a1.digest.json", b"{}")
    assert (tmp_path / "run-1" / "sessions" / "t1-a1.digest.json").exists()


def test_ref_round_trips_to_path_and_delete(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("harness_session", "run-1", "t1-a1.jsonl", b"x")
    assert ref_to_path(ref).read_bytes() == b"x"
    store.delete(ref)
    assert not ref_to_path(ref).exists()
    store.delete(ref)  # idempotent — second delete is a no-op


def test_env_root_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "art"))
    store = LocalFileStore()
    store.put("harness_session", "r", "n.jsonl", b"y")
    assert (tmp_path / "art" / "r" / "sessions" / "n.jsonl").exists()


def test_export_root_fallback_is_runs_pipeline(tmp_path, monkeypatch):
    """Layout contract: no env at all -> artifacts ride beside the E-32
    exports under runs/pipeline/."""
    monkeypatch.delenv("SDLC_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SDLC_EXPORT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    store = LocalFileStore()
    store.put("harness_session", "run-1", "s.jsonl", b"x")
    assert (tmp_path / "runs" / "pipeline" / "run-1" / "sessions" / "s.jsonl").exists()
