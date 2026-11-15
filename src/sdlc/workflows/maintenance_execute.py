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
    from ..core.models import GateDecision, IdeaBrief, PipelineConfig, ProjectMode
    from ..maintenance.execution import OPS_REFUSAL_OUTCOME, may_execute
    from ..maintenance.models import (
        ExecutionRecord,
        Incident,
        IncidentState,
        MaintenanceConfig,
        MaintenanceState,
    )
    from ..notify.activities import notify
    from ..notify.contract import NotifyInput, NotifyReason
    from ..tidyup.backlog import repair_work_for, seeded_work_for
    from ..triage.models import FixClass
    from .gates import NOTIFY_ACT, gate_pending
    from .pipeline_child import start_repair_child


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


async def _notify_refusal(state: MaintenanceState, incident: Incident, now: datetime) -> None:
    """One operator notification per refusal (R6): the round-2 gate it
    opens is the pending decision the operator owes."""
    pending = gate_pending(f"repair:{incident.no}", incident.gate_round, None, opened_at=now)
    await workflow.execute_activity(
        notify,
        NotifyInput(
            run_id=workflow.info().workflow_id,
            pending=pending,
            reason=NotifyReason.OPENED,
            opened_at=now,
            now=now,
        ),
        **NOTIFY_ACT,
    )


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
            await _notify_refusal(state, inc, now)
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
        inc.note = OPS_REFUSAL_OUTCOME if any(a.kind == "ops" for a in plan.actions) else ""
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
