import json
import logging

from sdlc.harness.adapters import (
    ClaudeCodeHarness, HarnessRequest, OpenCodeHarness, context_window_for,
)


def test_claude_parse_extracts_tokens_and_cost():
    # E-38: claude now emits stream-json; parse walks lines for the result
    # event. Wrap the old plain-json payload as a one-line result stream.
    payload = {"type": "result", "session_id": "abc",
               "total_cost_usd": 0.12, "result": "done",
               "usage": {"input_tokens": 1234, "output_tokens": 56}}
    res = ClaudeCodeHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "abc"
    assert res.cost_usd == 0.12
    assert res.input_tokens == 1234
    assert res.output_tokens == 56


def test_opencode_parse_extracts_tokens():
    """opencode --format json emits an event stream (one JSON object per
    line): step_start, text..., step_finish. Content lives in part.text on
    text events; tokens/cost live in part on the step_finish event."""
    events = "\n".join([
        json.dumps({"type": "step_start", "sessionID": "ses_abc",
                    "part": {"type": "step-start"}}),
        json.dumps({"type": "text", "sessionID": "ses_abc",
                    "part": {"type": "text", "text": "parsing probe"}}),
        json.dumps({"type": "step_finish", "sessionID": "ses_abc",
                    "part": {"type": "step-finish",
                             "tokens": {"input": 50, "output": 5},
                             "cost": 0}}),
    ])
    res = OpenCodeHarness().parse(events, 0)
    assert res.session_id == "ses_abc"
    assert res.summary == "parsing probe"
    assert res.input_tokens == 50
    assert res.output_tokens == 5
    assert res.cost_usd == 0


def test_opencode_parse_concats_multiple_text_events():
    """A real run emits many text parts; the summary joins them newline-
    separated (each text event is a distinct message block, not a token)."""
    events = "\n".join([
        json.dumps({"type": "text", "sessionID": "s",
                    "part": {"type": "text", "text": "hello"}}),
        json.dumps({"type": "text", "sessionID": "s",
                    "part": {"type": "text", "text": "world"}}),
        json.dumps({"type": "step_finish", "sessionID": "s",
                    "part": {"type": "step-finish", "tokens": {}, "cost": 0.1}}),
    ])
    res = OpenCodeHarness().parse(events, 0)
    assert res.summary == "hello\nworld"
    assert res.cost_usd == 0.1


def test_opencode_parse_raw_fallback_on_non_json():
    """If opencode emits no parseable events (e.g. an error dump), keep the
    raw stdout for diagnosis instead of returning an empty summary."""
    res = OpenCodeHarness().parse("not json at all", 1)
    assert res.summary == "not json at all"


def test_context_window_lookup_by_model():
    assert context_window_for("anthropic:claude-sonnet-4-6") == 200_000
    assert context_window_for("openai/gpt-5.2") == 400_000
    assert context_window_for(None) is None
    assert context_window_for("some-unknown-model") is None


def test_opencode_build_cmd_auto_approves_edits():
    """opencode run is non-interactive; without --auto every Edit/Write/Bash
    tool call blocks on a permission approval that never arrives, so the
    model cannot write anything -> empty diff (the runtime failure).
    Mirrors claude's --permission-mode acceptEdits."""
    cmd = OpenCodeHarness().build_cmd(HarnessRequest(
        prompt="do stuff", cwd="/tmp/wt", model="zai-coding-plan/glm-5.2"))
    assert "--auto" in cmd


def test_opencode_build_cmd_runs_pure():
    """The user's global opencode config loads the superpowers plugin, whose
    brainstorming skill auto-activates on any 'creative work' and makes the
    model ask clarifying questions instead of implementing -> the coding
    activity stalls. Config-level plugin:[] does NOT unload it (opencode
    auto-discovers installed plugins from its cache), so --pure — the only
    mechanism that actually skips plugin loading — is required. It keeps the
    built-in Read/Write/Edit/Bash tools (verified end-to-end)."""
    cmd = OpenCodeHarness().build_cmd(HarnessRequest(
        prompt="do stuff", cwd="/tmp/wt", model="zai-coding-plan/glm-5.2"))
    assert "--pure" in cmd


def test_claude_build_cmd_accept_edits():
    """Regression guard: claude must auto-accept edits for autonomous runs."""
    cmd = ClaudeCodeHarness().build_cmd(HarnessRequest(
        prompt="do stuff", cwd="/tmp/wt"))
    assert "--permission-mode" in cmd and "acceptEdits" in cmd


def test_opencode_parse_logs_debug_on_malformed_line(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    events = "\n".join([
        "not valid json",
        json.dumps({"type": "step_finish", "sessionID": "s",
                    "part": {"tokens": {}, "cost": 0.0}}),
    ])
    OpenCodeHarness().parse(events, 0)
    assert any("not valid json" in r.message for r in caplog.records)


def test_opencode_parse_logs_warning_when_nothing_parses(caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    OpenCodeHarness().parse("not json at all", 1)
    assert any("parsed_any" in r.message or "no events parsed" in r.message
               for r in caplog.records)


def test_claude_parse_logs_warning_on_decode_failure(caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    ClaudeCodeHarness().parse("not json at all", 1)
    assert any("result event" in r.message.lower() or "fallback" in r.message.lower()
               for r in caplog.records)
