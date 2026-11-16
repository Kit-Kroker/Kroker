from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.operator_time import ENGAGEMENT_CAP_S, operator_time
from sdlc.core.models import ClarificationOutcome, GateOutcomeSummary, RunSummary

# --- 025 T005 (RED): operator_time (FR-003/004/005, A.6) ---

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _summary(gates=(), clars=(), instrumented=True):
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T,
        ended_at=T,
        duration_s=0.0,
        gates=list(gates),
        clarifications=list(clars),
        operator_instrumented=instrumented,
    )


def _gate(name="architecture", decided_by="human", raised=None, decided=None, rnd=1):
    return GateOutcomeSummary(
        gate=name,
        round=rnd,
        policy="hard",
        decided_by=decided_by,
        approved=True,
        raised_at=raised,
        decided_at=decided,
    )


def _clar(qid, raised, answered, answered_by="human"):
    return ClarificationOutcome(
        question_id=qid,
        question="q?",
        answered_by=answered_by,
        raised_at=raised,
        answered_at=answered,
    )


def test_cap_constant_is_ten_minutes():
    assert ENGAGEMENT_CAP_S == 600


def test_pre_025_summary_is_not_measured_even_with_human_gate():
    g = _gate(raised=T, decided=T + timedelta(minutes=4))
    r = operator_time(_summary(gates=[g], instrumented=False))
    assert r.state == "not_measured"


def test_instrumented_policy_only_run_is_measured_zero():
    r = operator_time(_summary(gates=[_gate(decided_by="policy", raised=None, decided=T)]))
    assert r.state == "zero"
    assert r.engaged_s == 0


def test_human_gate_under_cap_is_measured():
    g = _gate(raised=T, decided=T + timedelta(minutes=4))
    r = operator_time(_summary(gates=[g]))
    assert r.state == "measured"
    assert r.engaged_s == 240.0
    assert r.wait_s == 240.0
    assert len(r.interactions) == 1


def test_human_gate_over_cap_caps_engaged_but_not_wait():
    g = _gate(raised=T, decided=T + timedelta(hours=9))
    r = operator_time(_summary(gates=[g]))
    assert r.state == "measured"
    assert r.engaged_s == 600.0
    assert r.wait_s == 32400.0


def test_merge_override_with_reviewer_name_counts_as_human():
    g = _gate(name="merge", decided_by="maksim", raised=T, decided=T + timedelta(minutes=2))
    r = operator_time(_summary(gates=[g]))
    assert r.state == "measured"
    assert r.engaged_s == 120.0


def test_policy_and_timeout_gates_are_not_human():
    gates = [
        _gate(name="architecture", decided_by="policy", raised=T, decided=T + timedelta(minutes=1)),
        _gate(name="merge", decided_by="timeout", raised=T, decided=T + timedelta(minutes=9)),
    ]
    r = operator_time(_summary(gates=gates))
    assert r.state == "zero"
    assert r.engaged_s == 0
    assert len(r.interactions) == 0


def test_clarification_batch_counts_as_one_interaction():
    answered = T + timedelta(seconds=700)
    clars = [_clar(f"q{i}", raised=T, answered=answered) for i in range(3)]
    r = operator_time(_summary(clars=clars))
    assert r.state == "measured"
    assert len(r.interactions) == 1
    assert r.engaged_s == 600.0
    assert r.wait_s == 700.0


def test_human_gate_without_raise_time_is_not_measured():
    g = _gate(raised=None, decided=T + timedelta(minutes=4))
    r = operator_time(_summary(gates=[g]))
    assert r.state == "not_measured"


def test_overlapping_gates_sum_as_upper_bound():
    a = _gate(name="architecture", raised=T, decided=T + timedelta(minutes=5))
    b = _gate(name="plan", raised=T + timedelta(minutes=1), decided=T + timedelta(minutes=6))
    r = operator_time(_summary(gates=[a, b]))
    assert r.state == "measured"
    assert len(r.interactions) == 2
    assert r.engaged_s == 600.0
    assert r.wait_s == 600.0


# --- 025 T005 (RED, chaos/edge cases): operator_time ---


def test_mixed_batch_decides_as_one_on_the_latest_answer():
    clars = [
        _clar("q1", raised=T, answered=T + timedelta(seconds=60), answered_by="human"),
        _clar("q2", raised=T, answered=T + timedelta(seconds=90), answered_by="human"),
        _clar("q3", raised=T, answered=T + timedelta(seconds=120), answered_by="suggested"),
    ]
    r = operator_time(_summary(clars=clars))
    assert r.state == "measured"
    assert len(r.interactions) == 1
    assert r.engaged_s == 120.0


def test_batch_with_zero_human_answers_does_not_qualify():
    clars = [
        _clar(f"q{i}", raised=T, answered=T + timedelta(seconds=30), answered_by="suggested")
        for i in range(3)
    ]
    r = operator_time(_summary(clars=clars))
    assert r.state == "zero"
    assert len(r.interactions) == 0
    assert r.engaged_s == 0


def test_engagement_cap_boundary_exactly_at_cap_and_just_over():
    at_cap = operator_time(_summary(gates=[_gate(raised=T, decided=T + timedelta(seconds=600))]))
    assert at_cap.state == "measured"
    assert at_cap.engaged_s == 600.0
    assert at_cap.wait_s == 600.0

    over = operator_time(_summary(gates=[_gate(raised=T, decided=T + timedelta(seconds=601))]))
    assert over.state == "measured"
    assert over.engaged_s == 600.0
    assert over.wait_s == 601.0


def test_human_gate_with_raise_time_but_no_decided_at_is_not_measured():
    r = operator_time(_summary(gates=[_gate(raised=T, decided=None)]))
    assert r.state == "not_measured"


def test_gate_and_clarification_batch_sum_across_kinds():
    g = _gate(raised=T, decided=T + timedelta(seconds=120))
    clars = [
        _clar(
            "q1",
            raised=T + timedelta(seconds=300),
            answered=T + timedelta(seconds=480),
        )
    ]
    r = operator_time(_summary(gates=[g], clars=clars))
    assert r.state == "measured"
    assert len(r.interactions) == 2
    assert r.engaged_s == 300.0
    assert r.wait_s == 300.0


def test_pre_025_marker_outranks_zero_even_with_only_non_human_interactions():
    gates = [_gate(decided_by="policy", raised=T, decided=T + timedelta(seconds=5))]
    clars = [_clar("q1", raised=T, answered=T + timedelta(seconds=5), answered_by="suggested")]
    r = operator_time(_summary(gates=gates, clars=clars, instrumented=False))
    assert r.state == "not_measured"
