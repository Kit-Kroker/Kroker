"""E-38: canonical HarnessSession / SessionDigest models + pure helpers."""

import json

from sdlc.harness.session import (
    SKELETON_MAX,
    digest_of,
    scrub_session,
    session_text_from_jsonl,
    session_to_jsonl,
    session_to_text,
)
from sdlc.models import (
    HarnessKind,
    HarnessRunResult,
    HarnessSession,
    SessionEvent,
)


def _session(events):
    return HarnessSession(
        harness=HarnessKind.CLAUDE_CODE, session_id="s1", model="opus", events=events
    )


def test_run_result_gains_session_fields_defaulting_none():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok")
    assert r.session_ref is None
    assert r.session_digest is None


def test_raw_stdout_private_attr_never_serialized():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok")
    r._raw_stdout = "SECRET STREAM"
    assert "_raw_stdout" not in r.model_dump()
    assert "SECRET STREAM" not in r.model_dump_json()


def test_digest_counts_waste_aggregates():
    ev = [
        SessionEvent(kind="model_turn", text="thinking"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),  # re-read
        SessionEvent(kind="file_write", tool="Write", target="b.py"),
        SessionEvent(kind="file_write", tool="Edit", target="b.py"),  # churn
        SessionEvent(kind="command", tool="Bash", target="pytest", exit_code=1),
        SessionEvent(kind="command", tool="Bash", target="pytest", exit_code=0),
        SessionEvent(kind="compaction"),
    ]
    d = digest_of(_session(ev))
    assert d.tool_calls == 6  # every tool-bearing event
    assert d.file_reads == 2
    assert d.file_rereads == 1  # a.py read twice -> 1 extra read
    assert d.files_written == 1  # distinct paths written
    assert d.rewrite_churn == 1  # b.py written twice
    assert d.failed_commands == 1
    assert d.model_turns == 1
    assert d.compacted is True
    assert d.decision_skeleton[0] == "Read a.py"
    assert len(d.decision_skeleton) == 6  # only tool-bearing events, in order


def test_digest_skeleton_capped():
    ev = [
        SessionEvent(kind="file_read", tool="Read", target=f"f{i}.py")
        for i in range(SKELETON_MAX + 50)
    ]
    d = digest_of(_session(ev))
    assert len(d.decision_skeleton) == SKELETON_MAX


def test_scrub_session_redacts_text_and_target():
    ev = [
        SessionEvent(
            kind="command",
            tool="Bash",
            target="export KEY=sk-abcdefghijklmnopqrstuv",
            text="password: hunter2hunter2",
        )
    ]
    s = scrub_session(_session(ev))
    assert "sk-abcdefghijklmnop" not in (s.events[0].target or "")
    assert "hunter2" not in (s.events[0].text or "")


def test_session_to_jsonl_header_plus_one_line_per_event():
    ev = [
        SessionEvent(kind="model_turn", text="hi"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),
    ]
    lines = session_to_jsonl(_session(ev)).strip().splitlines()
    assert len(lines) == 3
    head = json.loads(lines[0])
    assert head["session_id"] == "s1" and "events" not in head
    assert json.loads(lines[1])["kind"] == "model_turn"


def test_session_to_text_renders_one_line_per_event_in_prose_style():
    """The plain-text view the handoff/deep_review prompts describe and the
    grounding verifier checks against (code review #1). A faithful quote is
    a substring: '<kind> <target>' matches the prompts' worked examples."""
    text = session_to_text(
        _session(
            [
                SessionEvent(kind="file_read", target="oracle/test_app.py"),
                SessionEvent(kind="command", target="pytest", exit_code=0),
                SessionEvent(kind="model_turn", text="I'll use cookies here"),
            ]
        )
    )
    assert "file_read oracle/test_app.py" in text
    assert "command pytest (exit 0)" in text
    assert "I'll use cookies here" in text


def test_session_text_from_jsonl_round_trips_the_stored_format():
    """load_session returns the raw JSONL the store holds; the verifier must
    see the same prose view the rendered prompt shows, derived from it."""
    s = _session([SessionEvent(kind="file_read", target="oracle/test_app.py")])
    assert "file_read oracle/test_app.py" in session_text_from_jsonl(session_to_jsonl(s))


def test_session_text_from_jsonl_skips_a_partial_trailing_line():
    """load_session byte-caps at 512KB; the last line can be truncated
    mid-JSON. A partial event line must be skipped, not crash the render."""
    full = session_to_jsonl(
        _session(
            [
                SessionEvent(kind="file_read", target="a.py"),
                SessionEvent(kind="file_write", target="b.py"),
            ]
        )
    )
    cut = full.rfind('"file_write"')  # inside the last event line
    truncated = full[:cut] + '{"kind":"file_write","target":"b'  # partial
    text = session_text_from_jsonl(truncated)
    assert "file_read a.py" in text
    assert "file_write" not in text  # partial line dropped
