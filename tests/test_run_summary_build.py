from datetime import datetime, timedelta, timezone

from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _ev(seq, kind, stage=None, **data):
    return RunEvent(seq=seq, at=T0 + timedelta(seconds=seq), kind=kind,
                    stage=stage, data={k: str(v) for k, v in data.items()})


def test_clean_deploy_aggregates_stages_and_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1",
            question="scope?"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1",
            answered_by="human"),
        _ev(2, RunEventKind.STAGE_ENDED, stage="clarify", role="clarify",
            outcome="pass", duration_s=2.0, cost_usd=0.10),
        _ev(3, RunEventKind.GATE_DECIDED, gate="architecture", round=1,
            policy="hard", decided_by="human", approved="true", confidence=0.9),
        _ev(4, RunEventKind.STAGE_ENDED, stage="architecture", role="architect",
            outcome="pass", duration_s=3.0, cost_usd=0.20),
        _ev(5, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r1", mode="greenfield",
                          outcome="deployed:http://pr", trace=trace,
                          memory_enabled=False, memory_watermark=None)
    assert s.terminal_stage == "architecture"
    assert [x.stage for x in s.stages] == ["clarify", "architecture"]
    assert s.clarifications[0].answered_by == "human"
    assert s.gates[0].confidence == 0.9 and s.gates[0].approved is True
    assert abs(s.cost_usd_total - 0.30) < 1e-9
    assert s.duration_s == 5.0


def test_unanswered_clarification_and_override_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q9",
            question="deadline?"),
        _ev(1, RunEventKind.GATE_DECIDED, gate="merge", round=1, policy="soft",
            decided_by="human", approved="true", overrides="coverage,traceability"),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r2", mode="greenfield",
                          outcome="rejected:merge:advisory", trace=trace,
                          memory_enabled=True, memory_watermark="4")
    assert s.clarifications[0].answered_by == "unanswered"
    assert s.gates[0].overrides == ["coverage", "traceability"]
    assert s.cost_usd_total is None
    assert s.memory_enabled is True and s.memory_watermark == "4"
