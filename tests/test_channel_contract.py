from __future__ import annotations

from sdlc.channels.contract import (
    Channel, ReferenceChannel, Reply, default_render, default_translate,
)
from sdlc.gate import CheckClass, CheckResult
from sdlc.models import GateOutcome
from sdlc.pending import (
    ClarifyPending, MergeGatePending, StageGatePending, TaskEscalationPending,
)


def test_render_clarify_is_text_reply_with_suggestion():
    r = default_render(ClarifyPending(key="Q1", question="OIDC?",
                                      why_it_matters="auth", suggested_answer="yes"))
    assert r.reply_kind == "text" and r.key == "Q1"
    assert "OIDC?" in r.title and r.body == "auth" and r.suggested == "yes"


def test_render_merge_gate_tabulates_checks():
    r = default_render(MergeGatePending(
        key="merge#1", gate="merge", round=1,
        checks=[CheckResult(name="lint_clean", passed=False,
                            classification=CheckClass.ABSOLUTE, detail="3 errs")]))
    assert r.reply_kind == "gate"
    assert r.rows and r.rows[0][0] == "lint_clean" and "FAIL" in r.rows[0][1]


def test_translate_clarify_maps_to_answer_question():
    d = ClarifyPending(key="Q1", question="q", why_it_matters="w")
    call = default_translate(d, Reply(text="Use OIDC"))
    assert call.signal == "answer_question"
    assert call.question_id == "Q1" and call.answer == "Use OIDC"
    assert call.decision is None


def test_translate_stage_gate_approve_maps_to_gate_decision():
    d = StageGatePending(key="architecture#2", gate="architecture", round=2,
                         spec_summary="s")
    call = default_translate(d, Reply(outcome=GateOutcome.APPROVE, text="lgtm"))
    assert call.signal == "submit_gate_decision"
    dec = call.decision
    assert dec.gate == "architecture" and dec.round == 2
    assert dec.outcome is GateOutcome.APPROVE and dec.decided_by == "human"
    assert dec.comments == "lgtm" and dec.guidance is None


def test_translate_revise_carries_guidance():
    d = TaskEscalationPending(key="task:t1#1", gate="task:t1", round=1,
                              task_id="t1", analysis="a", attempts=2)
    call = default_translate(d, Reply(outcome=GateOutcome.REVISE, text="try X"))
    assert call.decision.outcome is GateOutcome.REVISE
    assert call.decision.guidance == "try X"


def test_reference_channel_satisfies_protocol_and_round_trips():
    ch = ReferenceChannel()
    assert isinstance(ch, Channel)
    d = StageGatePending(key="planning#1", gate="planning", round=1,
                         spec_summary="p")
    assert ch.render(d).reply_kind == "gate"
    assert ch.translate(d, Reply(outcome=GateOutcome.REJECT)).signal \
        == "submit_gate_decision"


def test_translate_rejects_unknown_type():
    import pytest
    with pytest.raises(TypeError):
        default_translate(object(), Reply(text="x"))
