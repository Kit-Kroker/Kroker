"""The execution authority guard (023b T016, R6, B-FR-002/017).

Pure domain: no I/O, no Temporal, order-independent (NFR-10).
``may_execute`` is the ONLY gate between an approved incident and a
child start; ``executable_actions`` is the code_fix subset a child is
seeded with. Ops actions are never executed (B-FR-017, GATE 2 ruling):
the loop records them as proposals, whatever decided the gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from ..core.models import GateDecision, GateOutcome
from ..triage.delta import FindingDelta, FindingState, compute_delta
from ..triage.models import FixClass, RepoTriage
from .models import Incident, IncidentState, MaintenanceConfig, RepairAction, RepairPlan

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


#: The hint an unmerged-but-verified fix renders (R8, data-model §transitions:
#: 'verified' | identity present, not ancestor | 'verified' hint) — the text
#: `render` (T047) shows in `sdlc maintain incidents`. Recorded residual: the
#: operator resolves it by merging, rejecting the child, or disabling.
UNMERGED_HINT = "fix not on default branch"


#: The rolling execution window (R10): a start stamp is inside it iff
#: ``now - stamp <= 7 days`` — inclusive at exactly 7 days, out at 7 days
#: plus a microsecond (the convention qa pinned in T036).
_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class StartPlan:
    """One Execute pass's admission decision (023b T037, B-FR-010/011,
    R10) — PURE: inputs are never mutated, the caller applies.

    ``starts`` and ``queued`` are incident NUMBERS in walk order (the
    caller resolves them against its own candidates); ``exec_starts`` is
    the window PRUNED to the rolling 7 days, for the caller to carry back
    into the loop state (it rides continue_as_new); ``notice`` is ONE
    string per call when anything was held — the operator is notified
    once per cycle, never once per incident (None when nothing was)."""

    starts: tuple[int, ...]
    queued: tuple[int, ...]
    exec_starts: tuple[datetime, ...]
    notice: str | None


def _plan_paths(incident: Incident) -> set[str]:
    """Every path the incident's plan touches — the overlap key (R10:
    no two in-flight incidents on one path)."""
    paths: set[str] = set()
    if incident.plan is not None:
        for action in incident.plan.actions:
            paths.update(action.target_paths)
    return paths


def choose_starts(
    incidents: list[Incident],
    exec_starts: list[datetime],
    cfg: MaintenanceConfig,
    now: datetime,
) -> StartPlan:
    """The full cap policy (R10's gate order at Execute): walk the
    approved/queued candidates in incident-number order and admit a start
    only past (1) the path-overlap check — no two in-flight incidents on
    one path, the candidates started THIS pass joining the live set at
    once — then (2) the per-cycle cap, then (3) the rolling 7-day window
    cap, which counts both the carried stamps and the starts chosen
    earlier in this same pass. Everything held is QUEUED, recorded in one
    per-call notice; ``exec_starts`` older than the window is pruned from
    the returned plan. ``may_execute`` is NOT this function (T022: its
    refusals are awaiting_decision with a gate-round bump, applied by
    execute_step before classification)."""
    window = tuple(sorted(s for s in exec_starts if now - s <= _WINDOW))
    ordered = sorted(incidents, key=lambda i: i.no)
    live_paths: set[str] = set()
    for inc in ordered:
        if inc.state in (IncidentState.EXECUTING, IncidentState.VERIFYING):
            live_paths |= _plan_paths(inc)
    starts: list[int] = []
    queued: list[int] = []
    for inc in ordered:
        if inc.state not in (IncidentState.APPROVED, IncidentState.QUEUED):
            continue
        paths = _plan_paths(inc)
        if paths & live_paths:
            queued.append(inc.no)  # overlap: held without consuming a start
            continue
        if len(starts) >= cfg.max_starts_per_cycle:
            queued.append(inc.no)
            continue
        if len(window) + len(starts) >= cfg.max_starts_per_window:
            queued.append(inc.no)
            continue
        starts.append(inc.no)
        live_paths |= paths
    notice = (
        f"{len(queued)} incident(s) held queued: per-cycle cap "
        f"{cfg.max_starts_per_cycle}, window cap {cfg.max_starts_per_window} "
        "over 7 days, or a path overlap with an in-flight attempt"
        if queued
        else None
    )
    return StartPlan(tuple(starts), tuple(queued), window, notice)


def closure_outcome(
    incident: Incident,
    detect_collected: bool,
    identity_present: bool,
    child_head_is_ancestor: bool,
) -> str | None:
    """One verified incident's closure decision on a collected Detect
    (023b T033, B-FR-008, R8) — PURE: a verdict for the caller's wire
    (closure_step), never a mutation.

    Not-collected → ``None``: a lost cycle cannot strand the incident (the
    check is a state check, re-run on every collected cycle). The ancestry
    question reads the CHILD's integration head (``execution.integration_
    head``, recorded at awaiting_merge — R8's recorded-head ruling; the
    caller passes the answer, this function stays git-free). Absent +
    ancestor → ``closed``: the fix provably landed and holds. Absent +
    not-ancestor → ``resolved_externally``: the squash-merge honesty —
    ancestry is the provenance proof, so a squashed fix is retained as an
    experience, not a lesson. Present + ancestor → ``dirty``: the fix is
    on the default branch and did not hold. Present + not-ancestor →
    ``fix_not_on_default_branch``: the PR is unmerged (or squashed and
    regressed); the incident STAYS verified — it is live and blocks a
    duplicate — and ``UNMERGED_HINT`` is what render shows."""
    if not detect_collected:
        return None
    if identity_present:
        return "dirty" if child_head_is_ancestor else "fix_not_on_default_branch"
    return "closed" if child_head_is_ancestor else "resolved_externally"


#: What each dirty verdict records on the attempt (data-model §outcome):
#: loop-rejected verdicts are "rejected_by_loop"; probe-side failures keep
#: their own outcome; "empty_diff" stays available for a probe-side finding.
_DIRTY_OUTCOME: dict[str, str] = {
    "persisted": "rejected_by_loop",
    "new": "rejected_by_loop",
    "conflicted": "rejected_by_loop",
    "failed": "failed",
    "timed_out": "timed_out",
    "empty_diff": "empty_diff",
}


def apply_verdict(
    incident: Incident,
    verdict: str,
    cfg: MaintenanceConfig,
) -> Incident:
    """One verdict's pure state mapping (023b T029, B-FR-009, R11): the
    incident is never mutated — the verdict result is a NEW incident the
    caller splices into its state (report_step's only write-back).

    Dirty verdicts (``_DIRTY_OUTCOME``'s keys) fail the attempt: under the
    bound the incident reopens — ``reopens += 1``, ``gate_round += 1``
    (T031: the reopen is a new gate round, and its gate is human-only),
    plan cleared, re-planned next cycle — and at ``max_reopens`` it
    escalates with no further
    reopen. A non-retryable configuration failure escalates at once on
    attempt 1. A collected ``resolved`` verifies (the merge stays human's,
    reopens and plan untouched); ``unverifiable`` changes nothing (the
    attempt retries next cycle, bounded by the child timeout);
    ``absent_at_base`` resolves the stale incident externally — the fault
    the incident recorded does not exist at the verification base, so it
    is stale, not proven fixed (data-model §transitions)."""
    updated = incident.model_copy(deep=True)
    if verdict == "config_failed":
        updated.state = IncidentState.ESCALATED
        updated.note = "escalated: configuration failure"
        if updated.execution is not None:
            updated.execution.outcome = "config_failed"
        return updated
    if verdict == "resolved":
        updated.state = IncidentState.VERIFIED
        updated.note = "verified on the verification branch; the merge stays human"
        return updated
    if verdict == "unverifiable":
        return updated  # stays verifying; retried next cycle
    if verdict == "absent_at_base":
        updated.state = IncidentState.RESOLVED_EXTERNALLY
        updated.note = "the fault does not exist at the verification base"
        return updated
    if verdict in _DIRTY_OUTCOME:
        if updated.execution is not None:
            updated.execution.outcome = _DIRTY_OUTCOME[verdict]  # type: ignore[assignment]
        if updated.reopens < cfg.max_reopens:
            updated.state = IncidentState.REOPENED
            updated.reopens += 1
            updated.gate_round += 1  # T031: the reopen is a new gate round
            updated.plan = None  # the next plan is authored against the reopen
            updated.note = f"dirty verdict: {verdict}"
        else:
            updated.state = IncidentState.ESCALATED
            updated.note = f"escalated: dirty verdict {verdict} at the reopen bound"
        return updated
    if verdict == "regressed":
        # Closure's dirty (R8: the fix is on the default branch and did not
        # hold) — the SAME reopen mapping, but the attempt's outcome is NOT
        # stamped: the attempt completed and the child did its job; the
        # regression is new information from a later Detect, and the
        # data-model names no outcome for it (T034's cell pins the record
        # unchanged).
        if updated.reopens < cfg.max_reopens:
            updated.state = IncidentState.REOPENED
            updated.reopens += 1
            updated.gate_round += 1
            updated.plan = None
            updated.note = "dirty: the fix is on the default branch and did not hold"
        else:
            updated.state = IncidentState.ESCALATED
            updated.note = "escalated: the fix regressed at the reopen bound"
        return updated
    raise ValueError(f"unknown verdict: {verdict!r}")


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
