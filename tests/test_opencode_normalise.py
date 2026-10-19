"""E-38: opencode --format json event stream -> canonical HarnessSession."""

import json
from pathlib import Path

from sdlc.benchmarks.models import WasteBag
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


# FR-041: the same parser on the REAL captured benchmark stream from the
# passing round-016 R0 smoke (opencode 1.18.35, --format json; todo-api
# T-001 attempt 1, scrubbed: paths, user value, session ids redacted — see
# the fixture). This is the full real event vocabulary: tool_use with
# part.tool, step_finish with tokens+cost per step, and the scrubbed
# `"<worktrees>/..."` write targets. FR-3 expects NO parser change — these
# tests PIN current behaviour; a RED here is a finding, not a fix trigger
# inside this task.
BENCH_CAPTURED = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "opencode"
    / "bench-todo-api-greenfield-1792335476-T-001-a1.jsonl"
).read_text(encoding="utf-8")


def test_normalise_bench_stream_digest_counters():
    d = digest_of(OpenCodeHarness().normalise_session(BENCH_CAPTURED))
    assert d.tool_calls == 7  # 3 write + 4 bash, none dropped
    assert d.file_reads == 0
    assert d.file_rereads == 0
    assert d.files_written == 3
    assert d.rewrite_churn == 0
    assert d.failed_commands == 0  # every bash exit is 0
    assert d.model_turns == 5
    assert d.denials == 0
    assert d.escalations == 0
    assert d.compacted is False
    assert d.capture_rev == 1


def test_normalise_bench_stream_token_cost_summation():
    s = OpenCodeHarness().normalise_session(BENCH_CAPTURED)
    assert s.input_tokens == 3652  # summed across all six step_finish events
    assert s.output_tokens == 875
    # Six step_finish events each carry cost: 0 — a MEASURED zero (saw_cost
    # semantics), never readable as the not-measured None.
    assert s.cost_usd == 0.0
    assert s.cost_usd is not None


def test_normalise_bench_stream_waste_bag_projection():
    d = digest_of(OpenCodeHarness().normalise_session(BENCH_CAPTURED))
    bag = WasteBag.from_digest(d)
    assert bag is not None
    assert bag.tool_calls == 7
    assert bag.file_reads == 0
    assert bag.file_rereads == 0
    assert bag.files_written == 3
    assert bag.rewrite_churn == 0
    assert bag.failed_commands == 0
    assert bag.model_turns == 5
    assert bag.denials == 0
    assert bag.escalations == 0
    assert bag.compacted is False
    assert bag.capture_rev == 1


def test_normalise_bench_stream_write_targets():
    s = OpenCodeHarness().normalise_session(BENCH_CAPTURED)
    targets = [(e.target or "") for e in s.events if e.kind == "file_write"]
    # Scrubbed paths keep their basenames; match on those, not full equality.
    assert sorted(t.split("/")[-1] for t in targets) == [
        ".gitignore",
        "requirements-dev.txt",
        "requirements.txt",
    ]


# FR-041 T2 (spec FR-2, orchestrator ruling): opencode can emit a TOP-LEVEL
# "error" event — an error object (name + data.message + data.ref), NO
# `part` key, fatal, and in the wild the ONLY event of its stream (30
# occurrences in the lost R0 attempt-4 batch). Ruling: an error event
# advances no work and is NOT waste — the parser keeps dropping it, but it
# must not crash nor be reported as parsed text. Verbatim one-line stream
# from runs/ops/raw-stream/01a14ede-c54d-747d-bef0-45f97eeec493/T1-a1.jsonl.
ERROR_ONLY = '{"type":"error","timestamp":1792327419106,"sessionID":"ses_eb0f6013fffeHw7mJg4Ekz5rFA","error":{"name":"UnknownError","data":{"message":"Unexpected server error. Check server logs for details.","ref":"err_395fdec0"}}}'  # noqa: E501


def test_normalise_error_only_stream_drops_the_event():
    s = OpenCodeHarness().normalise_session(ERROR_ONLY)  # must not crash
    assert s.events == []
    # The session is still identified from the event's sessionID field.
    assert s.session_id == "ses_eb0f6013fffeHw7mJg4Ekz5rFA"
    # No text anywhere: the error is never reported as parsed text.
    assert not any(e.text for e in s.events)
    # No step_finish in the stream -> saw_tokens/saw_cost never set -> the
    # not-measured None, exactly like an empty stream.
    assert s.input_tokens is None
    assert s.output_tokens is None
    assert s.cost_usd is None


def test_normalise_error_only_stream_digests_to_a_measured_zero():
    s = OpenCodeHarness().normalise_session(ERROR_ONLY)
    d = digest_of(s)
    # All-zero counters, but stamped capture_rev 1: the stream WAS parsed.
    assert d.tool_calls == 0
    assert d.file_reads == 0
    assert d.file_rereads == 0
    assert d.files_written == 0
    assert d.rewrite_churn == 0
    assert d.failed_commands == 0
    assert d.model_turns == 0
    assert d.denials == 0
    assert d.escalations == 0
    assert d.compacted is False
    assert d.capture_rev == 1
    bag = WasteBag.from_digest(d)
    assert bag is not None
    assert bag.capture_rev == 1
    assert bag.tool_calls == 0
    # The consequence pin: an error-only stream is a MEASURED zero (marked
    # bag), never an unmeasured blank — and the error itself is not waste.
