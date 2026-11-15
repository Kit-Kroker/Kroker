"""The execution authority guard (023b T016, R6, B-FR-002/017).

Pure domain: no I/O, no Temporal, order-independent (NFR-10).
``may_execute`` is the ONLY gate between an approved incident and a
child start; ``executable_actions`` is the code_fix subset a child is
seeded with. Ops actions are never executed (B-FR-017, GATE 2 ruling):
the loop records them as proposals, whatever decided the gate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..core.models import GateDecision, GateOutcome
from ..triage.delta import FindingDelta, FindingState, compute_delta
from ..triage.models import FixClass, RepoTriage
from .models import Incident, MaintenanceConfig, RepairAction, RepairPlan

#: The recorded outcome for any ops action, verbatim on the wire (SC-B03,
#: GATE 1 Q6): ops proposals are never executed, by policy or by hand.
OPS_REFUSAL_OUTCOME = "not executed — ops proposal only"


class Refusal(BaseModel):
    """Why an approved plan did not start a child. The outcome text is
    recorded on the incident and rendered for the operator."""

    model_config = ConfigDict(extra="forbid")

    outcome: str


def executable_actions(plan: RepairPlan) -> list[RepairAction]:
    """The plan's ``code_fix`` actions, in order: everything a child may be
    seeded with."""
    return [action for action in plan.actions if action.kind == "code_fix"]


def merge_reject_decision(round: int, verdict: str) -> GateDecision:
    """The ONLY decision the loop ever sends a repair child (023b R5,
    SC-B10): a merge-gate REJECT decided by policy, the verdict line in
    comments. No other outcome is buildable in this module — the
    annotation-driven scan in ``T/maintenance/test_execution.py`` keeps
    that property load-bearing as later builders land (T029/T033)."""
    return GateDecision(
        gate="merge",
        round=round,
        outcome=GateOutcome.REJECT,
        decided_by="policy",
        comments=verdict,
    )


def classify_verification(
    base_triage: RepoTriage,
    verify_triage: RepoTriage,
    identity: str,
    conflicted: bool,
) -> str:
    """One identity's verification verdict (023b R4, B-FR-007): the
    ``VerificationResult.verdict`` literal.

    ``compute_delta(base, verify)`` is the single classifier — a
    not-collected signal on either side arrives as UNVERIFIABLE already, so
    an absence caused by a blind cycle can never masquerade as a resolved
    fix. A conflicted merge overrides everything (R5: the branch did not
    land, whatever the triage says). An identity the delta has no opinion
    on — collected on both sides but present in NEITHER triage — is
    ``absent_at_base``: the fault the incident recorded does not exist at
    the verification base, so nothing was verified (data-model §transitions
    sends such an incident to ``resolved_externally`` — stale, not proven
    fixed)."""
    if conflicted:
        return "conflicted"
    delta: list[FindingDelta] = compute_delta(base_triage, verify_triage)
    for d in delta:
        if d.identity != identity:
            continue
        if d.state is FindingState.UNVERIFIABLE:
            return "unverifiable"
        if d.state is FindingState.RESOLVED:
            return "resolved"
        if d.state is FindingState.PERSISTED:
            return "persisted"
        return "new"  # FindingState.NEW
    return "absent_at_base"


def may_execute(
    incident: Incident,
    plan: RepairPlan,
    decision: GateDecision,
    cfg: MaintenanceConfig,
) -> Refusal | None:
    """R6: ``None`` only when the plan may start exactly one seeded child.

    Policy path (auto-approval) requires ALL of: the finding is MECHANICAL,
    every action is ``code_fix``, ``consecutive_seen >= 2``, ``reopens ==
    0``, and ``effective > threshold`` (strict). The human path requires
    only one ``code_fix`` action -- human authority spans fix classes.
    A timeout decision never executes, and ops actions never do."""
    if decision.decided_by == "timeout":
        return Refusal(outcome="a timeout decision never executes a repair")

    if decision.decided_by == "human":
        if not executable_actions(plan):
            return Refusal(outcome=OPS_REFUSAL_OUTCOME)
        return None

    # -- policy path -----------------------------------------------------
    actions = executable_actions(plan)
    if not actions:
        return Refusal(outcome="an empty plan executes nothing")
    if len(actions) != len(plan.actions):
        return Refusal(outcome=OPS_REFUSAL_OUTCOME)
    finding = incident.finding
    if finding is None or finding.fix_class != FixClass.MECHANICAL:
        return Refusal(outcome="policy executes only mechanical findings; this plan needs a human")
    if incident.reopens != 0:
        return Refusal(outcome="policy never re-executes a reopened incident")
    if incident.consecutive_seen < 2:
        return Refusal(outcome="the fault has not reproduced on consecutive cycles")
    if not plan.effective > cfg.threshold:
        return Refusal(
            outcome=f"effective {plan.effective:.2f} does not clear the "
            f"threshold {cfg.threshold:.2f} (strict)"
        )
    return None
