"""E-38/OQ-B7: full transcript deleted only on clean-green non-benchmark."""

import pytest

from sdlc.artifacts.retention import RetentionInput, apply_session_retention, keep_full_transcripts
from sdlc.artifacts.store import LocalFileStore, ref_to_path


@pytest.mark.parametrize(
    "outcome,had_fix,is_bench,expected",
    [
        ("deployed:staging", False, False, False),  # clean-green -> downgrade
        ("deployed:staging", True, False, True),  # green after retry -> keep
        ("deployed:staging", False, True, True),  # benchmark -> keep
        ("rejected:merge", False, False, True),  # failed -> keep
        ("rejected:merge", True, True, True),
    ],
)
def test_keep_full_transcripts_matrix(outcome, had_fix, is_bench, expected):
    assert keep_full_transcripts(outcome, had_fix, is_bench) is expected


@pytest.mark.asyncio
async def test_retention_deletes_full_keeps_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    store = LocalFileStore()
    ref = store.put("harness_session", "r1", "t1-a1.jsonl", b"full")
    store.put("harness_session_digest", "r1", "t1-a1.digest.json", b"{}")
    out = await apply_session_retention(RetentionInput(refs=[ref], keep_full=False))
    assert not ref_to_path(ref).exists()
    assert (tmp_path / "r1" / "sessions" / "t1-a1.digest.json").exists()
    assert out == "downgraded:1"


@pytest.mark.asyncio
async def test_retention_keep_full_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    store = LocalFileStore()
    ref = store.put("harness_session", "r1", "t1-a1.jsonl", b"full")
    out = await apply_session_retention(RetentionInput(refs=[ref], keep_full=True))
    assert ref_to_path(ref).exists()
    assert out == "kept:1"
