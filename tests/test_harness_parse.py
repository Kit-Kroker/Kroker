import json

from sdlc.harness.adapters import (
    ClaudeCodeHarness, OpenCodeHarness, context_window_for,
)


def test_claude_parse_extracts_tokens_and_cost():
    payload = {"session_id": "abc", "total_cost_usd": 0.12, "result": "done",
               "usage": {"input_tokens": 1234, "output_tokens": 56}}
    res = ClaudeCodeHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "abc"
    assert res.cost_usd == 0.12
    assert res.input_tokens == 1234
    assert res.output_tokens == 56


def test_opencode_parse_extracts_tokens():
    payload = {"sessionID": "xyz", "text": "ok",
               "usage": {"input_tokens": 10, "output_tokens": 2}}
    res = OpenCodeHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "xyz"
    assert res.input_tokens == 10


def test_context_window_lookup_by_model():
    assert context_window_for("anthropic:claude-sonnet-4-6") == 200_000
    assert context_window_for("openai/gpt-5.2") == 400_000
    assert context_window_for(None) is None
    assert context_window_for("some-unknown-model") is None
