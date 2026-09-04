"""E-38: claude stream-json -> canonical HarnessSession."""

import json

from sdlc.harness.base import HarnessRequest
from sdlc.harness.claude_code import ClaudeCodeHarness

STREAM = "\n".join(
    [
        json.dumps(
            {"type": "system", "subtype": "init", "session_id": "abc", "model": "claude-opus-4-8"}
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {"content": [{"type": "text", "text": "I'll read the file."}]},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "src/app.py"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "session_id": "abc",
                "message": {"content": [{"type": "tool_result", "content": "def app(): ..."}]},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Write", "input": {"file_path": "src/out.py"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "session_id": "abc",
                "message": {
                    "content": [{"type": "tool_result", "content": "1 failed", "is_error": True}]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "abc",
                "total_cost_usd": 0.12,
                "result": "done",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        ),
    ]
)


def test_build_cmd_uses_stream_json_with_verbose():
    cmd = ClaudeCodeHarness().build_cmd(HarnessRequest(prompt="p", cwd="."))
    assert "stream-json" in cmd
    assert "--verbose" in cmd
    assert "json" not in [a for a in cmd if a == "json"]  # plain json gone


def test_parse_reads_result_event_from_stream():
    r = ClaudeCodeHarness().parse(STREAM, 0)
    assert r.session_id == "abc"
    assert r.cost_usd == 0.12
    assert r.input_tokens == 100 and r.output_tokens == 50
    assert r.summary == "done"


def test_normalise_maps_tools_onto_canonical_kinds():
    s = ClaudeCodeHarness().normalise_session(STREAM)
    kinds = [e.kind for e in s.events]
    assert s.session_id == "abc" and s.model == "claude-opus-4-8"
    assert kinds == [
        "model_turn",
        "file_read",
        "tool_result",
        "file_write",
        "command",
        "tool_result",
        "result",
    ]
    read = s.events[1]
    assert read.tool == "Read" and read.target == "src/app.py"
    bash = s.events[4]
    assert bash.tool == "Bash" and bash.target == "pytest -q"
    err = s.events[5]
    assert err.exit_code == 1  # is_error -> exit_code 1
    assert s.cost_usd == 0.12


def test_normalise_tolerates_garbage_lines():
    s = ClaudeCodeHarness().normalise_session("not json\n" + STREAM)
    assert len(s.events) == 7
