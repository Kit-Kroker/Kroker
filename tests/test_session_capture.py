"""E-38: capture -> scrub (fail-closed) -> digest -> store."""

import json

from sdlc.artifacts.capture import capture_session
from sdlc.artifacts.store import ref_to_path
from sdlc.harness.claude_code import ClaudeCodeHarness

STREAM = "\n".join(
    [
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "export K=sk-abcdefghijklmnopqrstuv"},
                        }
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "session_id": "abc",
                "result": "done",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ),
    ]
)


def test_capture_stores_scrubbed_jsonl_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert ref is not None and ref.kind == "harness_session"
    stored = ref_to_path(ref).read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in stored  # scrub effectiveness
    assert "[REDACTED_API_KEY]" in stored
    assert dig.tool_calls == 1
    assert (tmp_path / "r1" / "sessions" / "t1-a1.digest.json").exists()


def test_capture_fail_closed_stores_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "sdlc.artifacts.capture.scrub_session",
        lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert ref is None and dig is None
    assert not (tmp_path / "r1").exists()  # nothing on disk


def test_capture_sanitizes_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, _ = capture_session(
        ClaudeCodeHarness(), STREAM, run_id="r1", task_id="T/1: setup", attempt=2
    )
    assert ref_to_path(ref).name == "T_1__setup-a2.jsonl"


def test_capture_digest_carries_capture_rev_for_every_harness(tmp_path, monkeypatch):
    """Contract 10.3: capture goes through digest_of for every harness, so
    both the claude and the opencode stream yield a marked digest."""
    from sdlc.harness.opencode import OpenCodeHarness

    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    _, claude_dig = capture_session(
        ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1
    )
    assert claude_dig is not None and claude_dig.capture_rev == 1

    oc_stream = "\n".join(
        [
            json.dumps({"type": "step_start", "sessionID": "oc1"}),
            json.dumps(
                {
                    "type": "step_finish",
                    "sessionID": "oc1",
                    "part": {"tokens": {"input": 2, "output": 1}, "cost": 0.01},
                }
            ),
        ]
    )
    _, oc_dig = capture_session(OpenCodeHarness(), oc_stream, run_id="r2", task_id="t1", attempt=1)
    assert oc_dig is not None and oc_dig.capture_rev == 1


# --- 016 T009 (RED): the opt-in raw stream (R4, D-9) ---------------------------
#
# Names: RAW_STREAM_ENV = "SDLC_RAW_STREAM_DIR". When set, capture_session
# ALSO writes raw_stdout unchanged to <dir>/<safe run_id>/<safe
# task_id>-a<attempt>.jsonl (the module's _safe()), inside its own
# try/except, before normalising, and logs one INFO line. Default off.


def test_capture_without_raw_stream_env_stores_exactly_two_files(tmp_path, monkeypatch):
    """Default off: with SDLC_RAW_STREAM_DIR unset the store holds exactly
    today's two artifacts and nothing else anywhere under the store root."""
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.delenv("SDLC_RAW_STREAM_DIR", raising=False)
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert ref is not None and dig is not None
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert files == [
        "r1/sessions/t1-a1.digest.json",
        "r1/sessions/t1-a1.jsonl",
    ]


def test_capture_with_raw_stream_env_writes_unmodified_raw_stdout(tmp_path, monkeypatch):
    """When the env is set the raw stdout bytes are ALSO written, unchanged
    (unscrubbed -- the secret is still in them), under the env dir with the
    module's _safe() names, while the normal capture still happens in the
    store."""
    store_root = tmp_path / "store"
    raw_dir = tmp_path / "raw"
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(store_root))
    monkeypatch.setenv("SDLC_RAW_STREAM_DIR", str(raw_dir))
    ref, dig = capture_session(
        ClaudeCodeHarness(), STREAM, run_id="r1", task_id="T/1: setup", attempt=2
    )
    # the normal capture still happened
    assert ref is not None and dig is not None
    raw_file = raw_dir / "r1" / "T_1__setup-a2.jsonl"  # _safe() names, as today's store uses
    assert raw_file.is_file()
    assert raw_file.read_text(encoding="utf-8") == STREAM  # unmodified raw stdout
    # the raw copy lives under the env dir; the store keeps exactly its two files
    stored = sorted(
        p.relative_to(store_root).as_posix() for p in store_root.rglob("*") if p.is_file()
    )
    assert stored == [
        "r1/sessions/T_1__setup-a2.digest.json",
        "r1/sessions/T_1__setup-a2.jsonl",
    ]


def test_capture_logs_raw_stream_captured_line(tmp_path, monkeypatch, caplog):
    """Names: one INFO line, 'raw stream captured: <path>'."""
    import logging

    store_root = tmp_path / "store"
    raw_dir = tmp_path / "raw"
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(store_root))
    monkeypatch.setenv("SDLC_RAW_STREAM_DIR", str(raw_dir))
    with caplog.at_level(logging.INFO, logger="sdlc.artifacts.capture"):
        capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert f"raw stream captured: {raw_dir / 'r1' / 't1-a1.jsonl'}" in caplog.text


# --- 016 T009 (RED, chaos): the raw stream never breaks the normal capture -----


def _stored_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_capture_survives_an_unwritable_raw_stream_dir_exactly_as_with_the_env_unset(
    tmp_path, monkeypatch
):
    """Names (Raw stream): the raw write sits inside its own try/except; a
    failure stores nothing extra and changes nothing else. PIN-style: it
    passes today (the env var is ignored) and must keep passing once the
    raw write exists. SDLC_RAW_STREAM_DIR points BELOW a regular file, so
    its mkdir cannot succeed."""
    # control: env unset
    control_root = tmp_path / "control-store"
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(control_root))
    monkeypatch.delenv("SDLC_RAW_STREAM_DIR", raising=False)
    c_ref, c_dig = capture_session(
        ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1
    )
    assert c_ref is not None and c_dig is not None

    # subject: env set to <file>/deeper
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a regular file", encoding="utf-8")
    bad_dir = blocker / "deeper"
    subject_root = tmp_path / "subject-store"
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(subject_root))
    monkeypatch.setenv("SDLC_RAW_STREAM_DIR", str(bad_dir))
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)

    # same pair as the control, no raise
    assert ref is not None and dig is not None
    assert ref.kind == c_ref.kind
    assert ref_to_path(ref).name == ref_to_path(c_ref).name
    assert dig == c_dig
    assert ref_to_path(ref).read_text(encoding="utf-8") == ref_to_path(c_ref).read_text(
        encoding="utf-8"
    )

    # the two normal artifacts, identical to the control's file set
    assert _stored_files(subject_root) == _stored_files(control_root)
    assert _stored_files(subject_root) == [
        "r1/sessions/t1-a1.digest.json",
        "r1/sessions/t1-a1.jsonl",
    ]

    # no raw stream anywhere: the blocker is untouched, nothing appeared
    assert blocker.is_file()
    assert blocker.read_text(encoding="utf-8") == "i am a regular file"
    assert not bad_dir.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "control-store",
        "not-a-dir",
        "subject-store",
    ]


def test_capture_module_exposes_the_raw_stream_env_name():
    """Names: RAW_STREAM_ENV = "SDLC_RAW_STREAM_DIR"."""
    from sdlc.artifacts import capture as capture_mod

    assert capture_mod.RAW_STREAM_ENV == "SDLC_RAW_STREAM_DIR"
