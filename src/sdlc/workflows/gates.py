"""GateHost -- durable human-in-the-loop gate mechanics (FR-301/302/303).

Extracted from FeatureWorkflow (E-42 D2) so a second workflow can host a gate
without restating "first decision for (gate, round) wins". Duplicating that
rule is the failure shape 2026-07-16-registry-drives-every-role was written
about: an invariant that holds only while two copies happen to agree.

What this owns: policy resolution, (gate, round) identity, the notification
schedule, the timeout decision, and the four HITL handlers. What it does NOT
own: what a workflow *does* with a decided gate. That is three no-op hooks --
FeatureWorkflow emits a RunEvent and retains a memory; TriageWorkflow does
neither, and a base that did either would force this module to import
RunEventKind and the memory activities.

Signals and queries defined here register on every subclass: temporalio
collects them with inspect.getmembers, which walks the MRO
(temporalio/workflow/_definition.py:288). Only @workflow.run must be defined
on the concrete class (_definition.py:128).
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models import (
        GateConfig, GateDecision, GateOutcome, GatePolicy, GateSettings,
        TimeoutAction, gate_key,
    )
    from ..notify.activities import notify
    from ..notify.contract import NotifyInput, NotifyReason, Results
    from ..notify.schedule import build_schedule
    from ..pending import GateContext, PendingDecision, gate_pending

# E-9: delivery is best-effort and must never delay a gate. A single attempt:
# the notify activity already attempts every configured route internally, and
# the short schedule_to_start fails fast when no worker registered notify
# rather than hanging the gate forever.
NOTIFY_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                  schedule_to_start_timeout=timedelta(seconds=5),
                  retry_policy=RetryPolicy(maximum_attempts=1))


class GateHost:
    """Mixin. Subclasses must call super().__init__() and define their own
    @workflow.run."""

    def __init__(self) -> None:
        self._gate_decisions: dict[str, GateDecision] = {}
        # E-6: structured pending-decision registry, keyed by resolution key
        # (question id, or gate_key(gate, round)). Rendered by sdlc.channels.
        self._pending: dict[str, PendingDecision] = {}
        self._status: str = "starting"

    # ------------------------- hooks (no-op) ---------------------------

    async def _on_gate_awaited(self, name: str, round: int) -> None:
        """A gate has opened and is now waiting on a human."""

    async def _on_gate_decided(self, name: str, round: int,
                               policy: GatePolicy, decision: GateDecision,
                               confidence: float | None = None) -> None:
        """A gate has been decided, by a human, a policy, or a timeout.

        `confidence` is a PARAMETER, never instance state: gates interleave.
        Wave mode runs _dev_task concurrently (feature.py's asyncio.gather), so
        a second gate opening while this one awaits a human would overwrite a
        stashed value and silently drop RunSummary.gates[].confidence, which
        SC-6's calibration compare reads.
        """

    async def _on_notified(self, gate: str, reason: NotifyReason,
                           notifier: str, delivered: bool,
                           error: str = "") -> None:
        """One notification route reported its delivery outcome."""

    # -------------------- signals / queries (HITL) ----------------------

    @workflow.signal
    def submit_gate_decision(self, decision: GateDecision) -> None:
        # Idempotent per (gate, round): first decision for a round wins.
        key = gate_key(decision.gate, decision.round)
        if key not in self._gate_decisions:
            decision.decided_at = workflow.now()
            self._gate_decisions[key] = decision
        # _pending means "not yet decided" for every variant (E-7).
        self._pending.pop(key, None)

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def pending_gate(self) -> str | None:
        return self._status if self._status.startswith("awaiting:") else None

    @workflow.query
    def pending_decisions(self) -> list[PendingDecision]:
        """Structured items a human currently owes a decision on (E-6).
        Empty when nothing is awaiting. Rendered by sdlc.channels."""
        return list(self._pending.values())

    # ---------------------------- mechanics -----------------------------

    async def _notify(self, pending, reason, opened_at, deadline) -> None:
        """Fire-and-forget delivery. A transport failure can never block,
        fail, or delay a gate -- but it is reported through _on_notified, not
        swallowed, because a notification that failed to deliver must be
        visible (spec 6, ROADMAP 9.6)."""
        gate = getattr(pending, "gate", None) or pending.key
        try:
            out: Results = await workflow.execute_activity(
                notify,
                NotifyInput(run_id=workflow.info().workflow_id,
                            pending=pending, reason=reason,
                            opened_at=opened_at, now=workflow.now(),
                            deadline=deadline),
                **NOTIFY_ACT)
        except Exception as e:                # noqa: BLE001
            await self._on_notified(gate, reason, "unresolved", False,
                                    str(e)[:200])
            return
        for r in out.results:
            await self._on_notified(gate, reason, r.notifier, r.delivered,
                                    (r.error or "")[:200])

    async def _wait_for_decision(self, key, pending, schedule, expires):
        """Wait for the gate's signal, firing each notification as its
        deadline passes. Returns the decision, or None when the gate expired
        undecided. Exits the instant the signal lands, so there is nothing to
        cancel -- the reason this is a loop rather than a detached
        coroutine."""
        opened_at = schedule[0][0]
        decided = lambda: key in self._gate_decisions      # noqa: E731
        for at, reason in schedule:
            try:
                await workflow.wait_condition(
                    decided, timeout=at - workflow.now())
                return self._gate_decisions[key]
            except TimeoutError:
                await self._notify(pending, reason, opened_at, expires)
        if expires is None:                    # HOLD: wait without a deadline
            await workflow.wait_condition(decided)
            return self._gate_decisions[key]
        return None

    async def _gate(self, name: str, settings: GateSettings,
                    auto_decision: GateDecision | None = None,
                    round: int = 1,
                    context: GateContext | None = None,
                    confidence: float | None = None,
                    default_policy: GatePolicy | None = None) -> GateDecision:
        """Durable HITL gate with policy-based auto-approval."""
        gate_cfg = settings.gates.get(
            name,
            GateConfig(policy=default_policy or settings.default_gate_policy))
        policy = gate_cfg.policy
        key = gate_key(name, round)

        if policy == GatePolicy.OFF:
            decision = GateDecision(gate=name, round=round,
                                    outcome=GateOutcome.APPROVE,
                                    decided_by="policy")
        elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            decision = auto_decision
        else:
            pending = gate_pending(name, round, context)
            self._pending[key] = pending
            self._status = f"awaiting:{name}"
            await self._on_gate_awaited(name, round)
            schedule, expires = build_schedule(
                gate_cfg, settings.gate_timeout_hours, workflow.now())
            try:
                decided = await self._wait_for_decision(
                    key, pending, schedule, expires)
                if decided is not None:
                    decision = decided
                else:
                    # Expired undecided. HOLD never reaches here -- its
                    # schedule has no final deadline, so _wait_for_decision
                    # waits without one.
                    decision = GateDecision(
                        gate=name, round=round, decided_by="timeout",
                        outcome=(GateOutcome.APPROVE
                                 if gate_cfg.on_timeout is TimeoutAction.APPROVE
                                 else GateOutcome.REJECT),
                        comments=f"no decision within "
                                 f"{settings.gate_timeout_hours}h")
            finally:
                self._status = "running"
                self._pending.pop(key, None)

        await self._on_gate_decided(name, round, policy, decision, confidence)
        return decision
