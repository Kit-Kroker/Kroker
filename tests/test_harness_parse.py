import json

from sdlc.harness.adapters import (
    ClaudeCodeHarness, HarnessRequest, OpenCodeHarness, context_window_for,
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


def test_claude_build_cmd_accept_edits():
    """Regression guard: claude must auto-accept edits for autonomous runs."""
    cmd = ClaudeCodeHarness().build_cmd(HarnessRequest(
        prompt="do stuff", cwd="/tmp/wt"))
    assert "--permission-mode" in cmd and "acceptEdits" in cmd
