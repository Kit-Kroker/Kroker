import asyncio

import pytest

from sdlc.artifacts.read import (
    DEEP_REVIEW_MAX_BYTES, LoadSessionInput, LoadSessionResult, load_session,
)
from sdlc.artifacts.store import LocalFileStore
from sdlc.models import ArtifactRef


def test_load_session_round_trips_scrubbed_jsonl(tmp_path):
    store = LocalFileStore(tmp_path)
    ref = store.put("harness_session", "run1", "t1-a1.jsonl",
                    b'{"kind":"file_read","target":"app.py"}\n')
    out = asyncio.run(load_session(LoadSessionInput(ref=ref)))
    assert isinstance(out, LoadSessionResult)
    assert out.truncated is False
    assert "file_read" in out.text


def test_load_session_rejects_non_session_ref():
    ref = ArtifactRef(kind="diff", uri="file:///x", sha256=None)
    with pytest.raises(AssertionError):
        asyncio.run(load_session(LoadSessionInput(ref=ref)))


def test_load_session_truncates_oversized(tmp_path):
    store = LocalFileStore(tmp_path)
    big = b"x" * (DEEP_REVIEW_MAX_BYTES + 100)
    ref = store.put("harness_session", "run1", "t1-a1.jsonl", big)
    out = asyncio.run(load_session(LoadSessionInput(ref=ref)))
    assert out.truncated is True
    assert len(out.text) <= DEEP_REVIEW_MAX_BYTES
