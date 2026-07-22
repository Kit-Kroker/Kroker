from datetime import datetime, timezone

from sdlc.models import (
    ClarificationOutcome, GateOutcomeSummary, MemoryKind, RunSummary,
    StageOutcome,
)


def test_run_summary_round_trips():
    s = RunSummary(
        run_id="r1", mode="greenfield", outcome="deployed:http://pr",
        terminal_stage="deploy",
        started_at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc),
        duration_s=1800.0,
        stages=[StageOutcome(stage="clarify", role="clarify",
                             outcome="pass", duration_s=5.0)],
        clarifications=[ClarificationOutcome(
            question_id="q1", question="scope?", answered_by="human")],
        gates=[GateOutcomeSummary(gate="architecture", round=1, policy="hard",
                                  decided_by="human", approved=True,
                                  confidence=0.9, overrides=[])],
        cost_usd_total=1.23,
        memory_enabled=True, memory_watermark="7",
        memory_retains=4,
    )
    assert RunSummary.model_validate_json(s.model_dump_json()) == s


def test_memory_kind_has_run_summary():
    assert MemoryKind.RUN_SUMMARY.value == "run_summary"
