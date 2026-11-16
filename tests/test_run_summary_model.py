from datetime import UTC, datetime

from sdlc.core.models import (
    ClarificationOutcome,
    GateOutcome,
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


# --- 011 T002 (RED): old summaries load without budget_counted_usd ------------


def test_pre_011_summary_json_without_budget_counted_usd_parses_unchanged():
    """data-model §2.1: a summary.json written before 011 has no
    budget_counted_usd key; it loads with the field None (no budget, or a
    summary from before this change) and equals the original summary."""
    import json

    s = _summary()
    captured = json.loads(s.model_dump_json())
    captured.pop("budget_counted_usd", None)  # a pre-011 summary.json has no such key
    s2 = RunSummary.model_validate_json(json.dumps(captured))
    assert s2 == s
    assert s2.budget_counted_usd is None


def test_run_summary_budget_counted_usd_round_trips():
    """data-model §2.1: the additive wire carries a real counted value —
    RunSummary.budget_counted_usd survives a model_dump_json round-trip."""
    s = _summary(budget_counted_usd=2.5)
    assert RunSummary.model_validate_json(s.model_dump_json()) == s


# --- FR-304 (RED): GateOutcomeSummary full decision field set ------------------


def test_gate_outcome_summary_new_fields_default_none():
    """The FR-304 fields are additive: absent means a pre-FR-304 record,
    never a fabricated value."""
    g = GateOutcomeSummary(gate="merge", round=1, policy="soft", decided_by="human", approved=True)
    assert g.outcome is None
    assert g.comments is None
    assert g.reviewer is None
    assert g.decided_at is None


def test_gate_outcome_summary_parses_pre_change_json():
    """A summary.json written before this change has no new keys on its
    gates rows; they parse unchanged, reading the fields as not recorded."""
    g = GateOutcomeSummary.model_validate(
        {"gate": "merge", "round": 1, "policy": "soft", "decided_by": "human", "approved": True}
    )
    assert g.outcome is None


def test_gate_outcome_summary_round_trips_full_fields():
    """The full FR-304 record survives a model_dump_json round-trip."""
    g = GateOutcomeSummary(
        gate="merge",
        round=2,
        policy="hard",
        decided_by="human",
        approved=False,
        outcome=GateOutcome.REVISE,
        comments="narrow the scope",
        reviewer="maksim",
        decided_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
    )
    assert GateOutcomeSummary.model_validate_json(g.model_dump_json()) == g


# --- 025 T002 (RED): clarification times + operator_instrumented (FR-001/005/010, AS4) ---


def test_legacy_pre_025_summary_json_loads_with_defaults():
    """A summary.json written before 025 carries none of the new keys; it
    loads unchanged with the new fields at their defaults."""
    import json

    raised = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    answered = datetime(2026, 7, 22, 12, 5, tzinfo=UTC)
    full = _summary(
        operator_instrumented=True,
        clarifications=[
            ClarificationOutcome(
                question_id="q1",
                question="scope?",
                answered_by="human",
                raised_at=raised,
                answered_at=answered,
            )
        ],
        gates=[
            GateOutcomeSummary(
                gate="architecture",
                round=1,
                policy="hard",
                decided_by="human",
                approved=True,
                raised_at=raised,
            )
        ],
    )
    raw = json.loads(full.model_dump_json())
    raw.pop("operator_instrumented")
    for row in raw["gates"]:
        row.pop("raised_at")
    for row in raw["clarifications"]:
        row.pop("raised_at")
        row.pop("answered_at")

    legacy = RunSummary.model_validate(raw)

    expected = _summary(
        operator_instrumented=False,
        clarifications=[
            ClarificationOutcome(
                question_id="q1",
                question="scope?",
                answered_by="human",
                raised_at=None,
                answered_at=None,
            )
        ],
        gates=[
            GateOutcomeSummary(
                gate="architecture",
                round=1,
                policy="hard",
                decided_by="human",
                approved=True,
                raised_at=None,
            )
        ],
    )
    assert legacy == expected
    assert legacy.operator_instrumented is False
    assert legacy.gates[0].raised_at is None
    assert legacy.clarifications[0].raised_at is None
    assert legacy.clarifications[0].answered_at is None


def test_pre_025_summary_without_rows_loads_with_operator_instrumented_false():
    """The marker is a top-level default, not derived from rows being present."""
    import json

    raw = json.loads(_summary(operator_instrumented=True).model_dump_json())
    raw.pop("operator_instrumented", None)
    assert raw["gates"] == [] and raw["clarifications"] == []

    legacy = RunSummary.model_validate(raw)

    assert legacy.operator_instrumented is False


def test_legacy_gate_row_without_raised_at_validates_with_none():
    import json

    row = json.loads(
        GateOutcomeSummary(
            gate="architecture",
            round=1,
            policy="hard",
            decided_by="human",
            approved=True,
            raised_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        ).model_dump_json()
    )
    row.pop("raised_at", None)

    legacy = GateOutcomeSummary.model_validate(row)

    assert legacy.raised_at is None
