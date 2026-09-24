from datetime import UTC, datetime

from sdlc.core.models import (
    ClarificationOutcome,
    GateOutcomeSummary,
    RunSummary,
    StageOutcome,
)
from sdlc.memory.models import MemoryKind


def test_run_summary_round_trips():
    s = RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:http://pr",
        terminal_stage="deploy",
        started_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 7, 22, 12, 30, tzinfo=UTC),
        duration_s=1800.0,
        stages=[StageOutcome(stage="clarify", role="clarify", outcome="pass", duration_s=5.0)],
        clarifications=[
            ClarificationOutcome(question_id="q1", question="scope?", answered_by="human")
        ],
        gates=[
            GateOutcomeSummary(
                gate="architecture",
                round=1,
                policy="hard",
                decided_by="human",
                approved=True,
                confidence=0.9,
                overrides=[],
            )
        ],
        cost_usd_total=1.23,
        memory_enabled=True,
        memory_watermark="7",
        memory_retains=4,
    )
    assert RunSummary.model_validate_json(s.model_dump_json()) == s


def test_memory_kind_has_run_summary():
    assert MemoryKind.RUN_SUMMARY.value == "run_summary"


# --- E-77 T005 (RED): RunSummary.graph_sha (FR-009/FR-024) ------------------


def _summary(**kw):
    base = dict(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:http://pr",
        terminal_stage="deploy",
        started_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 7, 22, 12, 30, tzinfo=UTC),
        duration_s=1800.0,
    )
    base.update(kw)
    return RunSummary(**base)


def test_run_summary_graph_sha_defaults_to_none():
    assert _summary().graph_sha is None


def test_pre_e77_summary_json_without_graph_sha_parses_unchanged():
    """contracts/records-and-store.md: summary.json written before E-77 has
    no graph_sha key; it parses unchanged, reading the field as not recorded."""
    import json

    s = _summary()
    captured = json.loads(s.model_dump_json())
    captured.pop("graph_sha", None)  # a pre-E-77 summary.json has no such key
    s2 = RunSummary.model_validate_json(json.dumps(captured))
    assert s2 == s
    assert s2.graph_sha is None


def test_run_summary_ignores_unknown_keys_and_graph_sha_stays_none():
    """Core envelopes keep pydantic's default extra='ignore' (project
    memory — only graph/ models use forbid)."""
    import json

    payload = json.loads(_summary().model_dump_json())
    payload.pop("graph_sha", None)
    payload["future_e78_field"] = {"anything": [1, 2]}
    s2 = RunSummary.model_validate(payload)
    assert s2.run_id == "r1"  # the unknown key was ignored, not rejected
    assert s2.graph_sha is None


# --- 002 T025 (RED): RunSummary.project_key (FR-020a, G4/R-1) -----------------


def test_run_summary_project_key_defaults_to_none():
    assert _summary().project_key is None


def test_pre_002_summary_json_without_project_key_parses_unchanged():
    """A summary.json written before 002 has no project_key key; it parses
    unchanged, reading the field as not recorded (None, FR-020a). Pins the
    null path at the JSON level per R-1, never "old closed run → banner"."""
    import json

    s = _summary()
    captured = json.loads(s.model_dump_json())
    captured.pop("project_key", None)  # a pre-002 summary.json has no such key
    s2 = RunSummary.model_validate_json(json.dumps(captured))
    assert s2 == s
    assert s2.project_key is None
