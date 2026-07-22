from datetime import datetime, timezone

from sdlc.observability.trace import RunEvent, RunEventKind


def test_run_event_serializes_json_line():
    ev = RunEvent(
        seq=3,
        at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        kind=RunEventKind.GATE_DECIDED,
        stage="architecture",
        data={"decided_by": "human", "approved": "true"},
    )
    dumped = ev.model_dump_json()
    back = RunEvent.model_validate_json(dumped)
    assert back == ev
    assert back.kind is RunEventKind.GATE_DECIDED
    assert back.data["approved"] == "true"


def test_run_event_kind_values_are_stable():
    assert RunEventKind.STAGE_ENDED.value == "stage_ended"
    assert RunEventKind.CLARIFICATION_ANSWERED.value == "clarification_answered"
    assert RunEventKind.RUN_FINISHED.value == "run_finished"
