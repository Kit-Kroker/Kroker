"""E-38: capture -> scrub (fail-closed) -> digest -> store."""
import json

import pytest

from sdlc.artifacts.capture import capture_session
from sdlc.artifacts.store import ref_to_path
from sdlc.harness.adapters import ClaudeCodeHarness

STREAM = "\n".join([
    json.dumps({"type": "assistant", "session_id": "abc", "message": {
        "content": [{"type": "tool_use", "name": "Bash",
                     "input": {"command":
                               "export K=sk-abcdefghijklmnopqrstuv"}}]}}),
    json.dumps({"type": "result", "session_id": "abc", "result": "done",
                "usage": {"input_tokens": 1, "output_tokens": 1}}),
])


def test_capture_stores_scrubbed_jsonl_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM,
                               run_id="r1", task_id="t1", attempt=1)
    assert ref is not None and ref.kind == "harness_session"
    stored = ref_to_path(ref).read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in stored          # scrub effectiveness
    assert "[REDACTED_API_KEY]" in stored
    assert dig.tool_calls == 1
    assert (tmp_path / "r1" / "sessions" / "t1-a1.digest.json").exists()


def test_capture_fail_closed_stores_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr("sdlc.artifacts.capture.scrub_session",
                        lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM,
                               run_id="r1", task_id="t1", attempt=1)
    assert ref is None and dig is None
    assert not (tmp_path / "r1").exists()               # nothing on disk


def test_capture_sanitizes_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, _ = capture_session(ClaudeCodeHarness(), STREAM,
                             run_id="r1", task_id="T/1: setup", attempt=2)
    assert ref_to_path(ref).name == "T_1__setup-a2.jsonl"
