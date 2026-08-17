"""The dashboard's Channel adapter (E-10).

contract.py states that "a surface MAY override render for richer
presentation"; this uses that extension point to carry operator identity
without adding a parameter to the pure default_translate.

The identity lands on GateDecision.reviewer, NEVER on decided_by:
decided_by is Literal["human","policy","timeout"] and ReadinessOverride
.approved_by carries it verbatim, so a free-string actor there would
destroy the one signal that keeps "policy" legible as non-human.
triage.py:115 sets reviewer for exactly this reason (FR-1004).
"""
from __future__ import annotations

from ..channels.contract import (RenderedDecision, Reply, SignalCall,
                                 default_render, default_translate)
from ..pending import PendingDecision


class DashboardChannel:
    """Channel impl carrying a self-asserted operator identity (OQ-11)."""

    def __init__(self, actor: str) -> None:
        self.actor = actor

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        call = default_translate(d, reply)
        if call.decision is not None:
            call.decision.reviewer = self.actor
        return call
