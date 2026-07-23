"""E-38: opencode --format json event stream -> canonical HarnessSession."""
import json

from sdlc.harness.adapters import OpenCodeHarness

STREAM = "\n".join([
    json.dumps({"type": "step_start", "sessionID": "oc1"}),
    json.dumps({"type": "text", "sessionID": "oc1",
                "part": {"text": "Working on it."}}),
    json.dumps({"type": "tool", "sessionID": "oc1",
                "part": {"tool": "read", "state": {
                    "input": {"filePath": "src/app.py"}, "status": "completed"}}}),
    json.dumps({"type": "tool", "sessionID": "oc1",
                "part": {"tool": "bash", "state": {
                    "input": {"command": "pytest -q"}, "status": "error"}}}),
    json.dumps({"type": "step_finish", "sessionID": "oc1",
                "part": {"tokens": {"input": 10, "output": 5}, "cost": 0.01}}),
])


def test_normalise_maps_stream_onto_canonical_kinds():
    s = OpenCodeHarness().normalise_session(STREAM)
    assert s.session_id == "oc1"
    kinds = [e.kind for e in s.events]
    assert kinds == ["model_turn", "file_read", "command"]
    assert s.events[1].target == "src/app.py"
    assert s.events[2].target == "pytest -q"
    assert s.events[2].exit_code == 1     # status: error -> failed command
    assert s.input_tokens == 10 and s.output_tokens == 5
    assert s.cost_usd == 0.01


def test_normalise_empty_stream_yields_empty_session():
    s = OpenCodeHarness().normalise_session("")
    assert s.events == [] and s.session_id is None
