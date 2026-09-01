"""opened_at on the pending variants (spec 4.1). E-9 already proves the value
exists at gate-open time (gates.py:118 passes it into NotifyInput); this
exposes it so a surface can render 'waiting 4h'."""

from datetime import UTC, datetime

from sdlc.models import OpenQuestion
from sdlc.pending import GateContext, clarify_pending, gate_pending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def test_gate_pending_records_opened_at():
    p = gate_pending("architecture", 1, None, opened_at=AT)
    assert p.opened_at == AT


def test_merge_gate_pending_records_opened_at():
    ctx = GateContext(verdict="approve")
    p = gate_pending("merge", 2, ctx, opened_at=AT)
    assert p.opened_at == AT


def test_task_escalation_pending_records_opened_at():
    ctx = GateContext(task_id="T01", analysis="a", attempts=3)
    p = gate_pending("task:T01", 1, ctx, opened_at=AT)
    assert p.opened_at == AT


def test_clarify_pending_records_opened_at_on_every_item():
    qs = [
        OpenQuestion(id="Q1", question="q1", why_it_matters="w"),
        OpenQuestion(id="Q2", question="q2", why_it_matters="w"),
    ]
    out = clarify_pending(qs, set(), opened_at=AT)
    assert [p.opened_at for p in out] == [AT, AT]


def test_opened_at_defaults_to_none_so_existing_callers_are_unaffected():
    assert gate_pending("architecture", 1, None).opened_at is None
    qs = [OpenQuestion(id="Q1", question="q", why_it_matters="w")]
    assert clarify_pending(qs, set())[0].opened_at is None
