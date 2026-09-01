"""Pure render/translate for the channel contract (E-6).

render(PendingDecision) -> RenderedDecision   : surface-neutral presentation.
translate(PendingDecision, Reply) -> SignalCall: map a reply to ONE of the two
                                                 FR-302 signals.

No I/O. Delivery is a separate opt-in PushChannel capability. The module-level
default_render/default_translate are the reference behavior every surface
reuses; a surface MAY override render for richer presentation.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..models import GateDecision, GateOutcome
from ..pending import (
    ClarifyPending,
    MergeGatePending,
    PendingDecision,
    StageGatePending,
    TaskEscalationPending,
)


class RenderedDecision(BaseModel):
    """What a surface displays. reply_kind tells the surface which affordance
    to offer: 'text' = free-text answer; 'gate' = approve/revise/reject."""

    key: str
    title: str
    body: str
    reply_kind: Literal["text", "gate"]
    suggested: str | None = None
    rows: list[tuple[str, str]] = Field(default_factory=list)


class Reply(BaseModel):
    """What a surface collects from the operator, surface-neutral."""

    outcome: GateOutcome | None = None  # gate replies
    text: str | None = None  # answer text, or comment/guidance


class SignalCall(BaseModel):
    """translate's output. Transport code invokes the named signal with these
    args on the workflow handle. Only ever one of the two FR-302 signals."""

    signal: Literal["answer_question", "submit_gate_decision"]
    question_id: str | None = None  # answer_question
    answer: str | None = None  # answer_question
    decision: GateDecision | None = None  # submit_gate_decision


def default_render(d: PendingDecision) -> RenderedDecision:
    if isinstance(d, ClarifyPending):
        return RenderedDecision(
            key=d.key,
            title=f"Clarify: {d.question}",
            body=d.why_it_matters,
            reply_kind="text",
            suggested=d.suggested_answer,
        )
    if isinstance(d, StageGatePending):
        return RenderedDecision(
            key=d.key,
            title=f"Gate: {d.gate} (round {d.round})",
            body=d.spec_summary,
            reply_kind="gate",
        )
    if isinstance(d, TaskEscalationPending):
        return RenderedDecision(
            key=d.key,
            title=f"Task escalation: {d.task_id} (attempt {d.attempts})",
            body=d.analysis,
            reply_kind="gate",
        )
    if isinstance(d, MergeGatePending):
        return RenderedDecision(
            key=d.key,
            title=f"Merge gate (round {d.round})",
            body=d.verdict or "Deterministic quality gate result",
            reply_kind="gate",
            rows=[
                (
                    c.name,
                    f"{'ok' if c.passed else 'FAIL'} "
                    f"[{c.classification.value}] {c.detail}".rstrip(),
                )
                for c in d.checks
            ],
        )
    raise TypeError(f"unhandled pending decision: {type(d)!r}")


def default_translate(d: PendingDecision, reply: Reply) -> SignalCall:
    if isinstance(d, ClarifyPending):
        return SignalCall(signal="answer_question", question_id=d.key, answer=reply.text)
    if isinstance(d, (StageGatePending, TaskEscalationPending, MergeGatePending)):
        # every gate variant -> submit_gate_decision; gate/round come from the
        # pending item, so a reply can never land on the wrong round. A gate
        # reply carries an outcome by contract -- a bare-text reply is a
        # ClarifyPending, which took the branch above.
        assert reply.outcome is not None
        guidance = reply.text if reply.outcome is GateOutcome.REVISE else None
        return SignalCall(
            signal="submit_gate_decision",
            decision=GateDecision(
                gate=d.gate,
                round=d.round,
                outcome=reply.outcome,
                decided_by="human",
                comments=reply.text,
                guidance=guidance,
            ),
        )
    raise TypeError(f"unhandled pending decision: {type(d)!r}")


@runtime_checkable
class Channel(Protocol):
    """Every surface adapter: present a pending decision, map a reply to a
    signal. Both pure; delivery is a separate concern (see PushChannel)."""

    def render(self, d: PendingDecision) -> RenderedDecision: ...
    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall: ...


@runtime_checkable
class PushChannel(Channel, Protocol):
    """A surface that actively delivers (Slack notify, dashboard push).
    Pull surfaces (CLI, MCP) implement only Channel."""

    async def deliver(self, r: RenderedDecision) -> None: ...


class ReferenceChannel:
    """Minimal Channel — the test double and the pattern E-7's CLI refit
    follows. Delegates to the module defaults."""

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        return default_translate(d, reply)


class ActorChannel:
    """A Channel carrying a self-asserted operator identity (OQ-11).

    contract.py states that "a surface MAY override render for richer
    presentation"; this uses that extension point to carry identity without
    adding a parameter to the pure default_translate.

    The identity lands on GateDecision.reviewer, NEVER on decided_by:
    decided_by is Literal["human","policy","timeout"] and
    ReadinessOverride.approved_by carries it verbatim, so a free-string actor
    there would destroy the one signal that keeps "policy" legible as
    non-human. triage.py:115 sets reviewer for exactly this reason (FR-1004).

    Shared by every identity-bearing surface: the dashboard (E-10) and the
    chat surface (E-86) differ only in the actor string they pass.
    """

    def __init__(self, actor: str) -> None:
        self.actor = actor

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        call = default_translate(d, reply)
        if call.decision is not None:
            call.decision.reviewer = self.actor
        return call
