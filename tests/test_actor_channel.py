"""ActorChannel stamps identity on GateDecision.reviewer, never decided_by."""
from sdlc.channels.contract import ActorChannel, Reply
from sdlc.dashboard.channel import DashboardChannel
from sdlc.models import GateOutcome
from sdlc.pending import ClarifyPending, StageGatePending

GATE = StageGatePending(key="architecture#1", gate="architecture", round=1,
                        spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def test_gate_reply_carries_actor_as_reviewer():
    call = ActorChannel(actor="chat:mika").translate(
        GATE, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.reviewer == "chat:mika"


def test_actor_never_reaches_decided_by():
    call = ActorChannel(actor="chat:mika").translate(
        GATE, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.decided_by == "human"


def test_text_reply_has_no_decision_to_stamp():
    call = ActorChannel(actor="chat:mika").translate(Q1, Reply(text="yes"))
    assert call.signal == "answer_question"
    assert call.decision is None


def test_render_delegates_to_the_module_default():
    assert ActorChannel(actor="chat:mika").render(GATE).reply_kind == "gate"


def test_dashboard_channel_is_an_actor_channel():
    assert isinstance(DashboardChannel(actor="human:sam"), ActorChannel)
