"""DashboardChannel stamps operator identity onto GateDecision.reviewer.

NOT decided_by: that is Literal["human","policy","timeout"] (models.py:818)
and ReadinessOverride.approved_by carries it verbatim so "policy" and
"timeout" stay legible as non-human. reviewer is the established home for a
self-asserted identity-- triage.py:115 does exactly this.
"""

from sdlc.channels.contract import Reply
from sdlc.core.models import (
    GateOutcome,
)
from sdlc.dashboard.channel import DashboardChannel
from sdlc.pending import ClarifyPending, StageGatePending

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def test_translate_stamps_the_actor_onto_reviewer():
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.APPROVE, text="ok"))
    assert call.decision.reviewer == "human:mika"


def test_translate_leaves_decided_by_as_human():
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.decided_by == "human"


def test_translate_preserves_gate_and_round_from_the_pending_item():
    ch = DashboardChannel(actor="human:sam")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.REVISE, text="split"))
    assert (call.decision.gate, call.decision.round) == ("architecture", 1)
    assert call.decision.guidance == "split"


def test_translate_of_a_clarify_reply_is_untouched_by_the_actor():
    """answer_question carries no identity field; stamping must not crash."""
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(Q1, Reply(text="OIDC"))
    assert call.signal == "answer_question"
    assert call.question_id == "Q1"
    assert call.answer == "OIDC"


def test_render_delegates_to_the_default():
    ch = DashboardChannel(actor="human:mika")
    assert ch.render(ARCH).reply_kind == "gate"
    assert ch.render(Q1).reply_kind == "text"
