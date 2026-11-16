from datetime import UTC, datetime, timedelta

from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _ev(seq, kind, stage=None, **data):
    return RunEvent(
        seq=seq,
        at=T0 + timedelta(seconds=seq),
        kind=kind,
        stage=stage,
        data={k: str(v) for k, v in data.items()},
    )


def test_clean_deploy_aggregates_stages_and_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1", question="scope?"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1", answered_by="human"),
        _ev(
            2,
            RunEventKind.STAGE_ENDED,
            stage="clarify",
            role="clarify",
            outcome="pass",
            duration_s=2.0,
            cost_usd=0.10,
        ),
        _ev(
            3,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="hard",
            decided_by="human",
            approved="true",
            confidence=0.9,
        ),
        _ev(
            4,
            RunEventKind.STAGE_ENDED,
            stage="architecture",
            role="architect",
            outcome="pass",
            duration_s=3.0,
            cost_usd=0.20,
        ),
        _usage_event(6, "clarify", "m", 100, 10, usd=0.10),
        _usage_event(7, "architect", "m", 200, 20, usd=0.20),
        _ev(5, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:http://pr",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.terminal_stage == "architecture"
    assert [x.stage for x in s.stages] == ["clarify", "architecture"]
    assert s.clarifications[0].answered_by == "human"
    assert s.gates[0].confidence == 0.9 and s.gates[0].approved is True
    assert abs(s.cost_usd_total - 0.30) < 1e-9
    assert s.duration_s == 5.0


def test_unanswered_clarification_and_override_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q9", question="deadline?"),
        _ev(
            1,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="soft",
            decided_by="human",
            approved="true",
            overrides="coverage,traceability",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r2",
        mode="greenfield",
        outcome="rejected:merge:advisory",
        trace=trace,
        memory_enabled=True,
        memory_watermark="4",
    )
    assert s.clarifications[0].answered_by == "unanswered"
    assert s.gates[0].overrides == ["coverage", "traceability"]
    assert s.cost_usd_total is None
    assert s.memory_enabled is True and s.memory_watermark == "4"


def _usage_event(seq, role, model, in_t, out_t, usd=None):
    from datetime import datetime

    from sdlc.observability.trace import RunEvent, RunEventKind

    data = {
        "role": role,
        "model": model,
        "calls": "1",
        "input_tokens": str(in_t),
        "output_tokens": str(out_t),
        "cache_read_tokens": "0",
        "cache_write_tokens": "0",
    }
    if usd is not None:
        data["cost_usd"] = str(usd)
    return RunEvent(seq=seq, at=datetime.now(UTC), kind=RunEventKind.MODEL_USAGE, data=data)


def test_role_rollup_aggregates_model_usage_events():
    trace = [
        _usage_event(0, "clarify", "m1", 100, 10, usd=0.5),
        _usage_event(1, "clarify", "m1", 50, 5),  # unpriced call
        _usage_event(2, "dev", "m2", 1000, 200, usd=2.0),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
        budget_usd=5.0,
    )
    roles = {u.role: u for u in s.roles}
    assert roles["clarify"].calls == 2
    assert roles["clarify"].input_tokens == 150
    assert roles["clarify"].cost_usd == 0.5  # None call didn't zero it
    assert roles["dev"].cost_usd == 2.0
    assert s.cost_usd_total == 2.5  # rollup sum, not stage sum
    assert s.budget_usd == 5.0


def test_budget_crossings_counted_from_gate_events():
    now = datetime.now(UTC)
    trace = [
        RunEvent(
            seq=0,
            at=now,
            kind=RunEventKind.GATE_DECIDED,
            data={
                "gate": "budget",
                "round": "1",
                "policy": "hard",
                "decided_by": "human",
                "approved": "true",
            },
        ),
        RunEvent(
            seq=1,
            at=now,
            kind=RunEventKind.GATE_DECIDED,
            data={
                "gate": "budget",
                "round": "2",
                "policy": "hard",
                "decided_by": "human",
                "approved": "false",
            },
        ),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="rejected:budget",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.budget_crossings == 2
    assert s.budget_usd is None  # not passed → off


# --- E-77 T017 (RED): build_run_summary graph_sha (FR-009, R-3/U6) ----------


def test_graph_sha_keyword_sets_the_field():
    trace = [
        _ev(0, RunEventKind.STAGE_ENDED, stage="code", role="dev", outcome="pass", duration_s=4.0),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r9",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
        graph_sha="a" * 64,
    )
    assert s.graph_sha == "a" * 64


def test_without_graph_sha_the_summary_is_unchanged_and_graph_sha_is_none():
    """Pre-change output, field for field: the hand-built RunSummary below is
    the committed expectation (this file pins outputs by direct construction,
    not committed dicts); both sides carry graph_sha=None."""
    from sdlc.core.models import RunSummary, StageOutcome

    trace = [
        _ev(
            0,
            RunEventKind.STAGE_ENDED,
            stage="code",
            role="dev",
            outcome="pass",
            duration_s=4.0,
            cost_usd=1.5,
        ),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r9",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    expected = RunSummary(
        run_id="r9",
        mode="greenfield",
        outcome="done",
        terminal_stage="code",
        started_at=T0,
        ended_at=T0 + timedelta(seconds=1),
        duration_s=1.0,
        stages=[
            StageOutcome(stage="code", role="dev", outcome="pass", duration_s=4.0, cost_usd=1.5)
        ],
        # 025: the builder now stamps the instrument marker on every
        # summary (FR-005) — still field-for-field, with the new field.
        operator_instrumented=True,
    )
    assert s == expected
    assert s.graph_sha is None


# --- 002 T025 (RED): build_run_summary project_key (FR-020a, R-1) ----------


def test_project_key_keyword_sets_the_field():
    trace = [
        _ev(0, RunEventKind.STAGE_ENDED, stage="code", role="dev", outcome="pass", duration_s=4.0),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r10",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
        project_key="kroker",
    )
    assert s.project_key == "kroker"


def test_without_project_key_the_field_is_none():
    trace = [
        _ev(0, RunEventKind.STAGE_ENDED, stage="code", role="dev", outcome="pass", duration_s=4.0),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r10",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.project_key is None


# --- 011 T002 (RED): build_run_summary budget_counted_usd --------------------
# data-model §2.1: the same priced-dollars figure RunState carries live, at
# close; None = no budget or a summary built before this change.


def test_budget_counted_usd_keyword_sets_the_field():
    trace = [
        _ev(0, RunEventKind.STAGE_ENDED, stage="code", role="dev", outcome="pass", duration_s=4.0),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r11",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
        budget_counted_usd=1.5,
    )
    assert s.budget_counted_usd == 1.5


def test_without_budget_counted_usd_the_field_is_none():
    trace = [
        _ev(0, RunEventKind.STAGE_ENDED, stage="code", role="dev", outcome="pass", duration_s=4.0),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r11",
        mode="greenfield",
        outcome="done",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.budget_counted_usd is None


# --- FR-304 (RED): full decision fields reach the summary; dedup enriches ------


def test_gate_decided_full_fields_reach_summary():
    from sdlc.core.models import GateOutcome

    trace = [
        _ev(
            0,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="hard",
            decided_by="human",
            approved="false",
            outcome="reject",
            reviewer="maksim",
            comments="not ready",
            decided_at="2026-11-15T09:00:00+00:00",
        ),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="rejected",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    g = s.gates[0]
    assert g.outcome is GateOutcome.REJECT
    assert g.reviewer == "maksim"
    assert g.comments == "not ready"
    assert g.decided_at == datetime(2026, 11, 15, 9, 0, tzinfo=UTC)


def test_gate_dedup_enriches_instead_of_replacing():
    """The merge-gate shape: RunHost's full emit, then merge's overrides-only
    re-emit. Field-wise merge, not last-wins replace."""
    from sdlc.core.models import GateOutcome

    trace = [
        _ev(
            0,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="soft",
            decided_by="human",
            approved="true",
            outcome="approve",
            reviewer="maksim",
            comments="accepted risk",
            decided_at="2026-11-15T09:00:00+00:00",
        ),
        _ev(
            1,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="soft",
            decided_by="maksim",
            approved="true",
            overrides="coverage,lint",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    g = s.gates[0]
    assert g.outcome is GateOutcome.APPROVE and g.comments == "accepted risk"  # kept
    assert g.decided_by == "maksim" and g.overrides == ["coverage", "lint"]  # later wins


def test_pre_change_events_parse_to_none_fields():
    """A GATE_DECIDED event emitted before this change carries none of the
    new keys; its summary row reads them as not recorded."""
    trace = [
        _ev(
            0,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="hard",
            decided_by="human",
            approved="true",
            confidence=0.9,
        ),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    g = s.gates[0]
    assert g.outcome is None and g.comments is None
    assert g.reviewer is None and g.decided_at is None


# --- 025 T001 (RED): GateOutcomeSummary.raised_at (FR-001/002, US-A1 AS1) ---


def test_raised_at_is_stamped_from_gate_awaited_event():
    trace = [
        _ev(2, RunEventKind.GATE_AWAITED, gate="architecture", round=1),
        _ev(
            5,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="hard",
            decided_by="human",
            approved="true",
        ),
        _ev(6, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert len(s.gates) == 1
    assert s.gates[0].raised_at == T0 + timedelta(seconds=2)


def test_raised_at_survives_gate_dedup_enrich():
    trace = [
        _ev(1, RunEventKind.GATE_AWAITED, gate="merge", round=1),
        _ev(
            2,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="soft",
            decided_by="human",
            approved="true",
        ),
        _ev(
            3,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="soft",
            decided_by="maksim",
            approved="true",
            overrides="coverage,lint",
        ),
        _ev(4, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert len(s.gates) == 1
    assert s.gates[0].raised_at == T0 + timedelta(seconds=1)


def test_raised_at_is_none_when_gate_never_opened_for_a_human():
    trace = [
        _ev(
            1,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="soft",
            decided_by="policy",
            approved="true",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.gates[0].raised_at is None


def _build_gates(trace):
    return build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome="deployed",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    ).gates


def test_raised_at_records_the_open_even_when_policy_auto_decides():
    trace = [
        _ev(1, RunEventKind.GATE_AWAITED, gate="architecture", round=1),
        _ev(
            3,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="soft",
            decided_by="policy",
            approved="true",
        ),
        _ev(4, RunEventKind.RUN_FINISHED),
    ]
    gates = _build_gates(trace)
    assert len(gates) == 1
    assert gates[0].raised_at == T0 + timedelta(seconds=1)


def test_raised_at_is_keyed_per_round_of_the_same_gate():
    trace = [
        _ev(1, RunEventKind.GATE_AWAITED, gate="architecture", round=1),
        _ev(
            2,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="hard",
            decided_by="human",
            approved="false",
        ),
        _ev(5, RunEventKind.GATE_AWAITED, gate="architecture", round=2),
        _ev(
            6,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=2,
            policy="hard",
            decided_by="human",
            approved="true",
        ),
        _ev(7, RunEventKind.RUN_FINISHED),
    ]
    gates = _build_gates(trace)
    assert len(gates) == 2
    by_round = {g.round: g for g in gates}
    assert by_round[1].raised_at == T0 + timedelta(seconds=1)
    assert by_round[2].raised_at == T0 + timedelta(seconds=5)


def test_raised_at_does_not_leak_across_gates():
    trace = [
        _ev(1, RunEventKind.GATE_AWAITED, gate="merge", round=1),
        _ev(
            2,
            RunEventKind.GATE_DECIDED,
            gate="merge",
            round=1,
            policy="hard",
            decided_by="human",
            approved="true",
        ),
        _ev(
            3,
            RunEventKind.GATE_DECIDED,
            gate="deploy",
            round=1,
            policy="soft",
            decided_by="policy",
            approved="true",
        ),
        _ev(4, RunEventKind.RUN_FINISHED),
    ]
    gates = _build_gates(trace)
    by_gate = {g.gate: g for g in gates}
    assert by_gate["merge"].raised_at == T0 + timedelta(seconds=1)
    assert by_gate["deploy"].raised_at is None


# --- 025 T002 (RED): clarification times + operator_instrumented (FR-001/005/010, AS4) ---


def _build_025(trace, outcome="deployed"):
    return build_run_summary(
        run_id="r",
        mode="greenfield",
        outcome=outcome,
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )


def test_clarification_answered_at_and_raised_at_are_stamped():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1", question="scope?"),
        _ev(4, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1", answered_by="human"),
        _ev(5, RunEventKind.RUN_FINISHED),
    ]
    s = _build_025(trace)
    c = s.clarifications[0]
    assert c.raised_at == T0 + timedelta(seconds=0)
    assert c.answered_at == T0 + timedelta(seconds=4)
    assert s.operator_instrumented is True


def test_unanswered_clarification_has_raised_at_but_no_answered_at():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1", question="scope?"),
        _ev(9, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1", answered_by="unanswered"),
        _ev(10, RunEventKind.RUN_FINISHED),
    ]
    s = _build_025(trace)
    c = s.clarifications[0]
    assert c.answered_by == "unanswered"
    assert c.raised_at == T0 + timedelta(seconds=0)
    assert c.answered_at is None


def test_builder_marks_every_summary_operator_instrumented():
    s = _build_025([_ev(0, RunEventKind.RUN_FINISHED)])
    assert s.operator_instrumented is True


def test_suggested_answer_still_records_its_answered_at():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1", question="scope?"),
        _ev(3, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1", answered_by="suggested"),
        _ev(4, RunEventKind.RUN_FINISHED),
    ]
    c = _build_025(trace).clarifications[0]
    assert c.answered_by == "suggested"
    assert c.raised_at == T0 + timedelta(seconds=0)
    assert c.answered_at == T0 + timedelta(seconds=3)


def test_clarification_batch_shares_raised_at_with_per_question_answered_at():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1", question="a?"),
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q2", question="b?"),
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q3", question="c?"),
        _ev(2, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1", answered_by="human"),
        _ev(4, RunEventKind.CLARIFICATION_ANSWERED, question_id="q3", answered_by="human"),
        _ev(5, RunEventKind.RUN_FINISHED),
    ]
    by_id = {c.question_id: c for c in _build_025(trace).clarifications}
    assert set(by_id) == {"q1", "q2", "q3"}
    assert all(c.raised_at == T0 for c in by_id.values())
    assert by_id["q1"].answered_at == T0 + timedelta(seconds=2)
    assert by_id["q2"].answered_at is None
    assert by_id["q3"].answered_at == T0 + timedelta(seconds=4)


def test_operator_instrumented_is_true_on_an_interaction_free_trace():
    trace = [
        _ev(
            1,
            RunEventKind.STAGE_ENDED,
            stage="clarify",
            role="clarify",
            outcome="pass",
            duration_s=1.0,
            cost_usd=0.0,
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = _build_025(trace)
    assert s.gates == [] and s.clarifications == []
    assert s.operator_instrumented is True
