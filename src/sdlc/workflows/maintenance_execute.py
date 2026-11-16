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

Caps arrive in US5: ``choose_starts`` (the full eligibility policy,
R10) classifies admissions BEFORE the walk; this module applies it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from datetime import timedelta

    from temporalio.common import RetryPolicy, WorkflowIDReusePolicy

    from .. import pools
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
        UNMERGED_HINT,
        apply_verdict,
        choose_starts,
        classify_verification,
        closure_outcome,
        may_execute,
        merge_reject_decision,
    )
    from ..maintenance.models import (
        ExecutionRecord,
        Incident,
        IncidentState,
        MaintenanceState,
        VerificationResult,
    )
    from ..maintenance.render import render_retention, retention_kind
    from ..measurement import CollectionState
    from ..memory.activities import RetainInput, retain
    from ..memory.models import RetainItem
    from ..notify.activities import notify
    from ..notify.contract import NotifyInput, NotifyReason
    from ..pending import StageGatePending, TaskEscalationPending
    from ..tidyup.backlog import repair_work_for, seeded_work_for
    from ..triage.models import FixClass, RepoTriage, SignalResult, finding_identity
    from ..vcs.integration import (
        VerifyBranchInput,
        build_verification_branch,
        is_ancestor,
        remove_verification_tree,
    )
    from .gates import NOTIFY_ACT
    from .memory_host import MEM_ACT
    from .pipeline_child import start_repair_child
    from .tidyup import _default_fix_cfg
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

#: The closure ancestry check: read-only git plumbing, no mutation (R8).
ANCESTRY_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


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
    # The FULL policy (T037, R10): classify once, walk the admitted starts,
    # carry the pruned window back — the stamps for this pass's starts are
    # appended below so the NEXT call's window sees them. The policy sees
    # ALL incidents: the path-overlap gate reads the live executing/
    # verifying attempts, which are never candidates themselves.
    admissions = choose_starts(state.incidents, state.exec_starts, loop_cfg, now)
    chosen = set(admissions.starts)
    # R10: the operator is notified ONCE PER CYCLE when anything was held —
    # never once per incident. The notice rides the loop's only outbound
    # channel; a hold is a remind, not an escalation (no fallback tier).
    if admissions.notice is not None:
        await workflow.execute_activity(
            notify,
            NotifyInput(
                run_id=workflow.info().workflow_id,
                pending=StageGatePending(
                    key=f"maintenance:caps:{state.cycle}",
                    gate="execution_caps",
                    round=state.cycle,
                    spec_summary=admissions.notice,
                ),
                reason=NotifyReason.REMIND,
                opened_at=now,
                now=now,
            ),
            **NOTIFY_ACT,
        )
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
    # R10: the window is pruned at each Execute; this pass's stamps join it.
    state.exec_starts = [*admissions.exec_starts, *([now] * len(records))]
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


async def _decide(state: MaintenanceState, inc: Incident, verdict: str) -> None:
    """One verdict's write-back (T031): apply_verdict is pure, the splice
    is the durable record, and an ESCALATION notifies the operator exactly
    once — the notify rides the transition itself, and an escalated
    incident is terminal (never probed again), so there is no second one."""
    updated = apply_verdict(inc, verdict, state.config)
    _splice(state, updated)
    if updated.state is not IncidentState.ESCALATED:
        return
    await workflow.execute_activity(
        notify,
        NotifyInput(
            run_id=workflow.info().workflow_id,
            pending=TaskEscalationPending(
                key=f"maintenance:escalation:{updated.no}",
                gate="maintenance_escalation",
                round=updated.gate_round,
                task_id=(
                    updated.execution.child_id
                    if updated.execution is not None
                    else f"inc{updated.no}"
                ),
                analysis=updated.note,
                attempts=updated.attempt,
            ),
            reason=NotifyReason.ESCALATE,
            opened_at=workflow.now(),
            now=workflow.now(),
        ),
        **NOTIFY_ACT,
    )


async def closure_step(state: MaintenanceState, triage: RepoTriage) -> None:
    """One verified incident's closure check on a collected Detect (023b
    T035, B-FR-008, R8). The decision is ``closure_outcome`` (pure); the
    ancestry question is a read-only activity over the CHILD's recorded
    integration head — the squash-merge honesty lives there. This is a
    state check: it re-runs on every collected cycle, so a lost cycle
    cannot strand the incident, and the outcomes route through the same
    machinery as every other verdict — dirty reopens via ``apply_verdict``
    (under the bound; escalate at it), ``closed``/``resolved_externally``
    are terminal writes, ``fix_not_on_default_branch`` keeps the incident
    verified with ``UNMERGED_HINT`` as the note (render shows it; the
    operator resolves by merging, rejecting the child, or disabling)."""
    for inc in sorted(
        (i for i in state.incidents if i.state is IncidentState.VERIFIED), key=lambda i: i.no
    ):
        record = inc.execution
        if record is None or not record.integration_head:
            continue  # never parked: nothing to prove provenance with
        sig = _signal_by(triage, inc.key.split(":", 1)[0])
        collected = sig is not None and sig.collected.state is CollectionState.MEASURED
        if not collected:
            continue  # a lost cycle: closure_outcome is None; stay verified
        present = inc.key in {finding_identity(f) for f in (sig.findings if sig else [])}
        ancestor = await workflow.execute_activity(
            is_ancestor,
            args=[state.config.repo_dir, record.integration_head, triage.commit_sha],
            **pools.on_harness(ANCESTRY_ACT, state.config.harness_queue),
        )
        outcome = closure_outcome(inc, collected, present, ancestor)
        if outcome == "dirty":
            await _decide(state, inc, "regressed")
        elif outcome == "closed":
            updated = inc.model_copy(deep=True)
            updated.state = IncidentState.CLOSED
            updated.note = "closed: the fix is on the default branch and holds"
            _splice(state, updated)
        elif outcome == "resolved_externally":
            updated = inc.model_copy(deep=True)
            updated.state = IncidentState.RESOLVED_EXTERNALLY
            updated.note = (
                "resolved externally: the identity is gone and the child head"
                " is not an ancestor (squash or rebase merge) — retained as an"
                " experience, not a lesson"
            )
            _splice(state, updated)
        elif outcome == "fix_not_on_default_branch":
            updated = inc.model_copy(deep=True)
            updated.note = UNMERGED_HINT
            _splice(state, updated)


def _signal_by(triage: RepoTriage, signal: str) -> SignalResult | None:
    return next((s for s in triage.signals if s.signal == signal), None)


async def retain_step(state: MaintenanceState) -> None:
    """One scrubbed memory record per terminal incident (023b T043,
    B-FR-012, R13). A state check, like closure: every terminal incident
    with ``retained`` False is retained once — the flag is set in the
    same step as the activity, only on success, so a failed retention
    retries next cycle (deduplicated by the backend's text hash) and a
    failed backend can never fail the cycle. Memory settings come from
    ``_default_fix_cfg().memory`` (R13: the same settings the repair
    children run with; no new configuration surface); the retain
    activity runs under ``MEM_ACT`` inside the memory host's swallow
    pattern. Text and kind come from the pure renderer (T041)."""
    memory = _default_fix_cfg().memory
    if not memory.enabled:
        return
    for inc in sorted(state.incidents, key=lambda i: i.no):
        kind = retention_kind(inc)
        if kind is None or inc.retained:
            continue
        try:
            await workflow.execute_activity(
                retain,
                RetainInput(
                    item=RetainItem(
                        kind=kind,
                        bank=memory.project_bank,
                        text=render_retention(inc),
                        metadata={"incident_no": str(inc.no), "key": inc.key},
                    ),
                    backend=memory.backend,
                    base_url=memory.base_url,
                ),
                **MEM_ACT,
            )
        except Exception:  # noqa: BLE001 — the swallow (R13): an outage
            continue  # never fails the cycle; the flag stays False
        inc.retained = True


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
                await _decide(state, inc, "config_failed")
            else:
                await _decide(state, inc, "failed")
            continue
        elif probe.phase in ("cancelled", "timed_out", "terminated", "not_found"):
            await _decide(state, inc, "timed_out")
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
                **pools.on_harness(VCS_ACT, cfg.harness_queue),
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
        await _decide(state, inc, verdict)

        if verdict != "unverifiable":
            # the attempt is decided: remove the verify worktree and ref.
            await workflow.execute_activity(
                remove_verification_tree,
                args=[cfg.repo_dir, record.child_id],
                **pools.on_harness(CLEANUP_ACT, cfg.harness_queue),
            )
