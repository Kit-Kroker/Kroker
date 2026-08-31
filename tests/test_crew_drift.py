# tests/test_crew_drift.py
"""E-88 finding 12: drift keys on the activity NAME. A crew turn is a
different activity, and without this drift is silently uncomputed for crew
tasks -- a lost signal, which is the kind nobody notices."""
from __future__ import annotations

from sdlc.benchmarks.drift import CODING_ACTIVITIES, _record_from_event
from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.models import HarnessKind


def test_the_crew_turn_counts_as_a_coding_activity():
    assert "run_coding_task" in CODING_ACTIVITIES
    assert "run_crew_turn" in CODING_ACTIVITIES


def test_a_crew_turn_result_is_unwrapped_to_its_run():
    """run_crew_turn returns CrewTurnOutput {run, record}; the
    shared-contract fields live on .run. Read from the top level and every
    crew turn drifts as claude_code / exit 1 -> FAIL with no cost."""
    rec = _record_from_event("run-1", {
        "event_type": "ActivityTaskCompleted",
        "activity": "run_crew_turn",
        "result": {"run": {"harness": "crew", "exit_code": 0,
                            "cost_usd": 0.5, "input_tokens": 10,
                            "output_tokens": 5},
                    "record": {}},
        "timestamp": "2026-08-31T00:00:00+00:00"}, "bench-1")
    assert rec is not None
    assert rec.harness is HarnessKind.CREW
    assert rec.outcome is BenchmarkOutcome.PASS
    assert rec.cost.usd == 0.5
    assert rec.cost.input_tokens == 10
    assert rec.cost.output_tokens == 5
