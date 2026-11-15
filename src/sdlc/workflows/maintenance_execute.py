"""The Execute step (023b T022, R1/R6/B-FR-002/014): the only place a
repair child is started.

Async step functions over explicit arguments — no class, no attribute,
no handler. ``execute_step`` runs at the end of a cycle, after the
plan/gate phase, behind ``cfg.execute`` and the
``maint-023b-execute`` patch. It walks ``approved``/``queued``
incidents in number order, puts each through ``may_execute`` (R6),
and for every admitted start writes the ``ExecutionRecord``,
increments ``attempt`` and stamps ``exec_starts`` in the SAME step as
the start command, before its acknowledgement (B-FR-014). Ops actions
are never executed (B-FR-017): a mixed plan starts with its
``code_fix`` subset and records the ops refusal verbatim; an ops-only
plan is refused outright.

A refusal sends the incident back to ``awaiting_decision`` with
``gate_round += 1``; the caller opens that round's gate in the same
step, and the gate's own OPENED notification is the operator's ONE
notification (R6/data-model: "a fresh gate round opens, and the
operator is notified once") — a separate refusal notice here would
double it, and the gate-carried notice carries the deadline and stays
silent if the gate is withdrawn by a disable.

The one event-loop yield at the top (``asyncio.sleep(0)``, a bare
coroutine yield — no Temporal command, replay-safe) lets gate tasks
whose decision was recorded synchronously by ``submit_gate_decision``
finish writing their outcome before the walk reads incident states.
Without it the walk would race the one-yield-late recording and miss
approvals that already happened.

Caps arrive in US5: ``choose_starts`` here is the interim — the first
``max_starts_per_cycle`` candidates. T037 replaces it with the full
window/eligibility policy in ``S/maintenance/execution.py``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from datetime import timedelta

    from temporalio.common import RetryPolicy, WorkflowIDReusePolicy

    from ..core.models import (
        GateDecision,
        GateSettings,
        IdeaBrief,
        PipelineConfig,
        ProjectMode,
    )
    from ..maintenance.activities import probe_repair_child
    from ..maintenance.execution import (
        OPS_REFUSAL_OUTCOME,
        apply_verdict,
        classify_verification,
        may_execute,
        merge_reject_decision,
    )
    from ..maintenance.models import (
        ExecutionRecord,
        Incident,
        IncidentState,
        MaintenanceConfig,
        MaintenanceState,
        VerificationResult,
    )
    from ..tidyup.backlog import repair_work_for, seeded_work_for
    from ..triage.models import FixClass
    from ..vcs.integration import (
        VerifyBranchInput,
        build_verification_branch,
        remove_verification_tree,
    )
    from .pipeline_child import start_repair_child
    from .triage import TriageInput, TriageWorkflow
    from .triage_child import triage_gates

#: The probe: one describe + two queries against Temporal itself.
PROBE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

#: The verification build + cleanup: git plumbing in disposable worktrees,
#: idempotent on retry (the build resets to base_sha before replaying merges).
VCS_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

#: The per-attempt verify tree removal: idempotent, never raises out.
CLEANUP_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(maximum_attempts=1),
)

#: Verdicts that mean the fix did not hold (R5): the loop rejects the child's
#: merge gate for exactly these, and never for anything else.
DIRTY_VERDICTS = frozenset({"persisted", "new", "conflicted"})


def choose_starts(
    candidates: list[Incident],
    exec_starts: list[datetime],
    cfg: MaintenanceConfig,
    now: datetime,
) -> list[Incident]:
    """INTERIM (T022): the first ``max_starts_per_cycle`` candidates, in
    number order. T037 replaces this with the full eligibility policy
    (window cap, path overlap); this module's caller is its only user
    until then."""
    return candidates[: cfg.max_starts_per_cycle]


def _signal_version(state: MaintenanceState, incident: Incident) -> int:
    """The version recorded for the finding's signal — the acceptance
    criterion must name the exact signal version that produced it."""
    if state.baseline is not None:
        return state.baseline.signal_versions.get(incident.key.split(":", 1)[0], 1)
    return 1


def _work_for(state: MaintenanceState, incident: Incident):
    """``seeded_work_for`` for a mechanical single-action plan (the 023a
    one-PR shape with its ``Change nothing else`` promise);
    ``repair_work_for`` otherwise (R12: a multi-action plan may touch
    several paths, and a judgement plan is human-authored scope)."""
    plan = incident.plan
    assert plan is not None and incident.finding is not None
    version = _signal_version(state, incident)
    single_mechanical = (
        len(plan.actions) == 1
        and plan.actions[0].kind == "code_fix"
        and incident.finding.fix_class is FixClass.MECHANICAL
    )
    if single_mechanical:
        return seeded_work_for(incident.key, incident.finding, version)
    return repair_work_for(incident.key, incident.finding, version, plan.actions)


def _child_id(state: MaintenanceState, incident: Incident, attempt: int) -> str:
    """The wire formula (R1): ``maint-<project>-<run8>-inc<no>-a<attempt>``,
    ``run8`` = the loop's first execution run id prefix — stable across
    ``continue_as_new``, so a re-attach after a roll-over finds the child."""
    run8 = workflow.info().first_execution_run_id[:8]
    return f"maint-{state.config.project}-{run8}-inc{incident.no}-a{attempt}"


async def execute_step(
    state: MaintenanceState,
    cfg: PipelineConfig,
    now: datetime,
) -> tuple[list[ExecutionRecord], list[Incident]]:
    """Walk ``approved``/``queued`` incidents in number order; start one
    seeded repair child per admitted candidate, refuse the rest.

    ``cfg`` is the CHILD's pipeline config (``_default_fix_cfg``), not the
    loop's ``MaintenanceConfig`` — the loop config rides ``state``.

    Returns ``(records, refusals)`` — the records written this step and
    the incidents refused back to ``awaiting_decision``. The caller opens
    each refusal's next ``repair:<n>`` round (the gate host owns gate
    tasks); ``execute_step`` itself owns the notification.
    """
    await asyncio.sleep(0)  # the one-yield barrier: settle resolved gate tasks
    loop_cfg = state.config
    candidates = sorted(
        (i for i in state.incidents if i.state in (IncidentState.APPROVED, IncidentState.QUEUED)),
        key=lambda i: i.no,
    )
    chosen = {i.no for i in choose_starts(candidates, state.exec_starts, loop_cfg, now)}
    records: list[ExecutionRecord] = []
    refusals: list[Incident] = []
    for inc in candidates:
        plan = inc.plan
        decision: GateDecision | None = inc.decision
        if plan is None or decision is None:
            # Impossible by construction (a gate records its decision in the
            # same step it approves); the walk leaves such an incident for
            # the next cycle rather than guessing.
            continue
        refusal = may_execute(inc, plan, decision, loop_cfg)
        if refusal is not None:
            inc.state = IncidentState.AWAITING_DECISION
            inc.gate_round += 1
            inc.note = refusal.outcome
            refusals.append(inc)
            continue
        if inc.no not in chosen:
            inc.state = IncidentState.QUEUED  # admitted, held by the interim cap
            continue
        work = _work_for(state, inc)
        attempt = inc.attempt + 1
        record = ExecutionRecord(
            attempt=attempt,
            child_id=_child_id(state, inc, attempt),
            base_sha=inc.commit_sha,
            started_at=now,
        )
        # B-FR-014: the record, the counters and the stamp land in the
        # same step as the start command, before its acknowledgement.
        inc.attempt = attempt
        inc.execution = record
        inc.executions.append(record)
        inc.state = IncidentState.EXECUTING
        has_ops = any(a.kind == "ops" for a in plan.actions)
        # B-FR-017: the ops proposal is recorded verbatim on the ATTEMPT's
        # record, not just the note — Report (T027) clears the plan and
        # rewrites the note on a dirty verdict, and the executions list is
        # the durable attempt history the operator reads.
        record.detail = OPS_REFUSAL_OUTCOME if has_ops else ""
        inc.note = record.detail
        state.exec_starts.append(now)
        records.append(record)
        await start_repair_child(
            child_id=record.child_id,
            idea=IdeaBrief(
                title=work.plan.tasks[0].title,
                description=work.arch.overview,
                mode=ProjectMode.BROWNFIELD,
                repo_url=state.config.repo_dir,
                base_branch=record.base_sha,
            ),
            cfg=cfg,
            seeded=work,
            task_queue=workflow.info().task_queue,
        )
    return records, refusals


# --------------------------------------------------------------------------
# Report (023b T027, R4/R5) and the timeout bound.
# --------------------------------------------------------------------------


def _live_attempt_incidents(state: MaintenanceState) -> list[Incident]:
    return sorted(
        (
            i
            for i in state.incidents
            if i.state in (IncidentState.EXECUTING, IncidentState.VERIFYING)
        ),
        key=lambda i: i.no,
    )


def _splice(state: MaintenanceState, updated: Incident) -> None:
    """``apply_verdict`` is pure: the verdict result replaces the incident
    in the loop's durable list (continue_as_new carries the list)."""
    state.incidents = [updated if i.no == updated.no else i for i in state.incidents]


async def timeout_step(state: MaintenanceState, now: datetime) -> None:
    """Cancel and fail every child that has not reached its merge gate
    within ``child_timeout_hours`` (R7's bound): the cancel is the only
    place the loop stops a child (data-model: a disable never cancels).
    The mapping to dirty happens in report_step, which sees the cancelled
    child on its next probe."""
    cfg = state.config
    deadline = timedelta(hours=cfg.child_timeout_hours)
    for inc in _live_attempt_incidents(state):
        record = inc.execution
        if record is None or now - record.started_at < deadline:
            continue
        await workflow.get_external_workflow_handle(record.child_id).cancel()
        record.outcome = "timed_out"  # type: ignore[assignment]
        inc.note = "child exceeded child_timeout_hours"


async def report_step(state: MaintenanceState, now: datetime) -> None:
    """Probe every executing/verifying incident and act on what it shows
    (R4/R5). ``awaiting_merge`` means the child parked: record the
    integration branch and head, build the verification tree, re-detect at
    it, classify, reject the child's merge on a dirty verdict — the ONLY
    decision the loop ever sends — and clean the attempt's tree. A child
    that failed, was cancelled, or changed nothing is a failed attempt; a
    non-retryable failure escalates at once (data-model). A not-collected
    re-detect leaves the incident ``verifying`` for the next cycle."""
    cfg = state.config
    for inc in _live_attempt_incidents(state):
        record = inc.execution
        if record is None:
            continue  # impossible by construction; the walk stays total
        probe = await workflow.execute_activity(probe_repair_child, record.child_id, **PROBE_ACT)
        if probe.phase == "running":
            continue  # still working; the timeout bound is timeout_step's
        if probe.phase == "completed":
            # merged-not-deployed: the PR is opened, not merged — the fault
            # persists on the default branch and that is NOT dirty
            # (data-model §present). The verify pass below still measures.
            record.outcome = "awaiting_merge"
        elif probe.phase == "failed":
            if probe.non_retryable:
                _splice(state, apply_verdict(inc, "config_failed", cfg))
            else:
                _splice(state, apply_verdict(inc, "failed", cfg))
            continue
        elif probe.phase in ("cancelled", "timed_out", "terminated", "not_found"):
            _splice(state, apply_verdict(inc, "timed_out", cfg))
            continue

        # awaiting_merge (or completed-with-PR): the verify pass.
        if inc.state is IncidentState.EXECUTING:
            record.integration_branch = probe.integration_branch
            record.integration_head = probe.integration_head
            record.outcome = "awaiting_merge"
            inc.state = IncidentState.VERIFYING

        conflicted = False
        verify_head = record.base_sha
        try:
            result = await workflow.execute_activity(
                build_verification_branch,
                VerifyBranchInput(
                    repo_path=cfg.repo_dir,
                    base_sha=record.base_sha,
                    tidyup_id=record.child_id,
                    branches=[record.integration_branch or ""],
                ),
                **VCS_ACT,
            )
            conflicted = bool(result.conflicted)
            verify_head = result.head_sha
        except Exception as e:  # noqa: BLE001 — a non-conflict build failure
            # is a RESULT (R4): conflicted, dirty.
            conflicted = True
            inc.note = f"verification build failed: {e}"[:300]

        verify_triage = await workflow.execute_child_workflow(
            TriageWorkflow.run,
            TriageInput(
                repo_dir=cfg.repo_dir,
                commit=verify_head,
                build_probe=cfg.build_probe,
                advisory_source=cfg.advisory_source,
                gates=triage_gates(GateSettings(), gating=False),
            ),
            id=f"{record.child_id}-verify",
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        )
        base_triage = state.prev
        if base_triage is None or base_triage.commit_sha != record.base_sha:
            base_triage = await workflow.execute_child_workflow(
                TriageWorkflow.run,
                TriageInput(
                    repo_dir=cfg.repo_dir,
                    commit=record.base_sha,
                    build_probe=cfg.build_probe,
                    advisory_source=cfg.advisory_source,
                    gates=triage_gates(GateSettings(), gating=False),
                ),
                id=f"{record.child_id}-base",
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
        verdict = classify_verification(base_triage, verify_triage, inc.key, conflicted)
        inc.verification = VerificationResult(
            child_id=record.child_id,
            base_sha=record.base_sha,
            verify_head=verify_head,
            collected=verdict != "unverifiable",
            verdict=verdict,  # type: ignore[arg-type]
        )

        if verdict in DIRTY_VERDICTS and probe.pending_merge_round is not None:
            await workflow.get_external_workflow_handle(record.child_id).signal(
                "submit_gate_decision",
                merge_reject_decision(probe.pending_merge_round, verdict),
            )
        _splice(state, apply_verdict(inc, verdict, cfg))

        if verdict != "unverifiable":
            # the attempt is decided: remove the verify worktree and ref.
            await workflow.execute_activity(
                remove_verification_tree,
                args=[cfg.repo_dir, record.child_id],
                **CLEANUP_ACT,
            )
