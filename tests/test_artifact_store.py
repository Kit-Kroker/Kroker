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
    ref = store.put("harness_session", "r", "n.jsonl", b"y")
    assert (tmp_path / "art" / "r" / "sessions" / "n.jsonl").exists()
