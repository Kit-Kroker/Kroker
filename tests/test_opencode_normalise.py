"""E-38: opencode --format json event stream -> canonical HarnessSession."""

import json
from pathlib import Path

from sdlc.harness.opencode import OpenCodeHarness
from sdlc.harness.session import digest_of

STREAM = "\n".join(
    [
        json.dumps({"type": "step_start", "sessionID": "oc1"}),
        json.dumps({"type": "text", "sessionID": "oc1", "part": {"text": "Working on it."}}),
        json.dumps(
            {
                "type": "tool",
                "sessionID": "oc1",
                "part": {
                    "tool": "read",
                    "state": {"input": {"filePath": "src/app.py"}, "status": "completed"},
                },
            }
        ),
        json.dumps(
            {
                "type": "tool",
                "sessionID": "oc1",
                "part": {
                    "tool": "bash",
                    "state": {"input": {"command": "pytest -q"}, "status": "error"},
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "sessionID": "oc1",
                "part": {"tokens": {"input": 10, "output": 5}, "cost": 0.01},
            }
        ),
    ]
)


def test_normalise_maps_stream_onto_canonical_kinds():
    s = OpenCodeHarness().normalise_session(STREAM)
    assert s.session_id == "oc1"
    kinds = [e.kind for e in s.events]
    assert kinds == ["model_turn", "file_read", "command"]
    assert s.events[1].target == "src/app.py"
    assert s.events[2].target == "pytest -q"
    assert s.events[2].exit_code == 1  # status: error -> failed command
    assert s.input_tokens == 10 and s.output_tokens == 5
    assert s.cost_usd == 0.01


def test_normalise_empty_stream_yields_empty_session():
    s = OpenCodeHarness().normalise_session("")
    assert s.events == [] and s.session_id is None


# 014 (contract §10.4, FR-041): the same parser on a REAL captured stream
# (opencode 1.18.35, --format json; PowerShell UTF-16 capture transcoded to
# UTF-8, paths/user/session redacted by text substitution — see the fixture).
# The real stream emits top-level type "tool_use" with the tool name in
# part.tool, and a failed bash call reports state.status "completed" with the
# exit code in state.metadata.exit — neither of which the handwritten stream
# above exercises.
CAPTURED = (
    Path(__file__).resolve().parent / "fixtures" / "opencode" / "session_tools.jsonl"
).read_text(encoding="utf-8")


def test_normalise_captured_stream_counts_tool_events():
    d = digest_of(OpenCodeHarness().normalise_session(CAPTURED))
    assert d.tool_calls == 3  # write + read + bash, none dropped


def test_normalise_captured_stream_file_events_target_hello():
    s = OpenCodeHarness().normalise_session(CAPTURED)
    writes = [e for e in s.events if e.kind == "file_write"]
    reads = [e for e in s.events if e.kind == "file_read"]
    assert any((e.target or "").endswith("hello.txt") for e in writes)
    assert any((e.target or "").endswith("hello.txt") for e in reads)


def test_normalise_captured_stream_failed_command_has_exit_code():
    s = OpenCodeHarness().normalise_session(CAPTURED)
    cmds = [e for e in s.events if e.kind == "command"]
    assert [e.exit_code for e in cmds] == [1]  # status completed, metadata.exit 1


def test_normalise_captured_stream_has_model_turn_text():
    s = OpenCodeHarness().normalise_session(CAPTURED)
    turns = [e for e in s.events if e.kind == "model_turn" and e.text]
    assert any("hello.txt" in (e.text or "") for e in turns)
