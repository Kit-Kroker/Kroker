"""MaintenanceWorkflow — the DAPER loop's long-lived host (023a T018; 023b
adds the execute/report/retain half).

Wire contract (contracts/workflow-wire.md — the names are recorded in
histories and live Schedules; never rename):

* id ``maint-<project>``, input ``MaintenanceState``, returns ``disabled:<p>``;
* signals ``nudge`` / ``disable`` (+ GateHost's ``submit_gate_decision``);
* queries ``incidents`` / ``maintenance_state`` (+ GateHost's
  ``pending_decisions``);
* child ``TriageWorkflow`` id ``maint-<project>-c<cycle>-triage``;
* gates ``repair:<incident_no>`` (SOFT, code-built) and
  ``detect_escalation:<signal>:<incident_no>`` (HARD).

Shape (R1–R3): the loop holds no timer of its own — it waits on the nudge
flag, so the schedule kicker, the CLI and tests all drive it through one
signal. Nudges during a cycle set the flag again and coalesce into exactly
one follow-up (R2). Gates run as their own coroutines tracked in
``_gate_tasks`` and never block the next cycle (R3); each records its
outcome on its incident. Nothing in this file writes to any repository
(FR-016): the 023b execute half lives in ``maintenance_execute.py`` behind
``cfg.execute`` and the ``maint-023b-execute`` patch.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import OUTPUT_RETRIES, STAGE_MODELS, t_maintainer
    from ..core.models import GateDecision, GateOutcome, GateSettings
    from ..maintenance.confidence import confidence_floor
    from ..maintenance.gate import (
        bears_human_required,
        escalation_gate_settings,
        repair_gate_settings,
    )
    from ..maintenance.incidents import step
    from ..maintenance.models import (
        Incident,
        IncidentState,
        MaintenanceKickInput,
        MaintenanceState,
        MaintenanceSummary,
        RepairPlan,
        RepairProposal,
    )
    from ..maintenance.prompt import render_repair_prompt
    from ..maintenance.render import gate_context_text
    from ..pending import GateContext
    from .gates import GateHost, GateWithdrawnError
    from .maintenance_execute import (
        closure_step,
        execute_step,
        report_step,
        retain_step,
        timeout_step,
    )
    from .tidyup import _default_fix_cfg
    from .triage import TriageInput, TriageWorkflow
    from .triage_child import triage_gates


@workflow.defn
class MaintenanceWorkflow(GateHost):
    """One project's loop. GateHost-only host (no ReportHost, no _cfg), like
    crew, triage, assessment and tidyup."""

    def __init__(self) -> None:
        super().__init__()
        self._state: MaintenanceState | None = None
        self._nudged = False
        self._disabling = False
        self._running = False
        self._gate_tasks: list[asyncio.Task[None]] = []

    # ------------------------------ signals ------------------------------ #

    @workflow.signal
    def nudge(self) -> None:
        self._nudged = True

    @workflow.signal
    def disable(self) -> None:
        self._disabling = True

    # ------------------------------ queries ------------------------------ #

    @workflow.query
    def incidents(self) -> list[Incident]:
        return list(self._state.incidents) if self._state else []

    @workflow.query
    def maintenance_state(self) -> MaintenanceSummary:
        if self._state is None:
            return MaintenanceSummary(
                project="?",
                cycle=0,
                baseline_recorded=False,
                running_cycle=False,
                open_gates=0,
                not_collected_streak={},
                ack_unattended_build_probe=False,
            )
        cfg = self._state.config
        window_start = workflow.now() - timedelta(days=7)
        return MaintenanceSummary(
            project=cfg.project,
            cycle=self._state.cycle,
            baseline_recorded=self._state.baseline is not None,
            running_cycle=self._running,
            open_gates=len(self._pending),
            not_collected_streak=dict(self._state.not_collected_streak),
            ack_unattended_build_probe=cfg.ack_unattended_build_probe,
            execute=cfg.execute,
            starts_in_window=sum(t >= window_start for t in self._state.exec_starts),
            in_flight=sum(
                i.state in (IncidentState.EXECUTING, IncidentState.VERIFYING)
                for i in self._state.incidents
            ),
        )

    # ------------------------------- run --------------------------------- #

    @workflow.run
    async def run(self, state: MaintenanceState) -> str:
        self._state = state
        project = state.config.project
        cycles_this_history = 0
        while not self._disabling:
            await workflow.wait_condition(lambda: self._nudged or self._disabling)
            if self._disabling:
                break
            self._nudged = False  # R2: nudges during the cycle become one follow-up
            self._running = True
            try:
                await self._cycle()
                cycles_this_history += 1
            finally:
                self._running = False
            # FR-013/R4: the history bound — continue in a fresh history
            # ONLY at the idle boundary: no cycle running (we are between
            # cycles), no pending gate, no undelivered signal, no nudge
            # already queued.
            if self._nudged or self._disabling:
                continue
            if not workflow.all_handlers_finished():
                continue
            if any(not t.done() for t in self._gate_tasks):
                continue  # a pending gate defers the roll-over
            cap = cycles_this_history >= state.config.max_cycles_per_history
            if cap or workflow.info().is_continue_as_new_suggested():
                # The carried state IS the durable record: config, baseline,
                # prev, incidents, counters and the nudge flag ride along.
                await workflow.continue_as_new(self._state)

        # Disable (R15): withdraw open gates without synthesising any
        # decision — GateDecision.decided_by has no "disable" value, and a
        # disable is none of human/policy/timeout. The gates unwind
        # themselves: _wait_for_decision raises GateWithdrawnError once
        # _disabling is set (never a task cancel — a cancel landing on a
        # gate mid-_notify would cancel an activity command the server has
        # not acknowledged, an unsatisfiable ACTIVITY_UNKNOWN activation).
        if self._gate_tasks:
            await workflow.wait_condition(lambda: all(t.done() for t in self._gate_tasks))
        for inc in self._state.incidents:
            # 023b (T045, data-model §transitions): the disable reaches the
            # IN-FLIGHT attempts too — an executing/verifying incident is
            # withdrawn like an awaiting one. The CHILD is never cancelled
            # (a disable never cancels): it outlives this loop under
            # ABANDON, its merge gate still pending for the operator.
            if inc.state in (
                IncidentState.AWAITING_DECISION,
                IncidentState.EXECUTING,
                IncidentState.VERIFYING,
            ):
                inc.state = IncidentState.WITHDRAWN
                inc.note = "maintenance disabled"
        return f"disabled:{project}"

    # ------------------------------ the cycle ----------------------------- #

    def _incident(self, no: int) -> Incident | None:
        assert self._state is not None
        return next((i for i in self._state.incidents if i.no == no), None)

    async def _cycle(self) -> None:
        assert self._state is not None
        cfg = self._state.config
        triage = await workflow.execute_child_workflow(
            TriageWorkflow.run,
            TriageInput(
                repo_dir=cfg.repo_dir,
                commit=cfg.default_branch,
                build_probe=cfg.build_probe,
                advisory_source=cfg.advisory_source,
                gates=triage_gates(GateSettings(), gating=False),
                harness_queue=cfg.harness_queue,
            ),
            id=f"maint-{cfg.project}-c{self._state.cycle}-triage",
        )
        self._state, _events = step(self._state, triage)

        # 023b Closure (B-FR-008, R8): a verified incident's provenance
        # check on THIS cycle's Detect — after Detect, before plan/gate.
        # Behind both the config and the patch marker (R15): a pre-023b
        # history never runs the ancestry activity.
        if cfg.execute and workflow.patched("maint-023b-execute"):
            await closure_step(self._state, triage)

        for inc in self._state.incidents:
            if inc.state is IncidentState.OPEN and inc.kind == "finding" and inc.plan is None:
                await self._plan(inc)
            elif inc.state is IncidentState.REOPENED and inc.plan is None:
                # 023b T031: a dirty attempt re-plans next cycle through the
                # same proposer path — apply_verdict already bumped
                # gate_round and cleared the plan, so the gate this opens is
                # human-only at the new round (data-model §transitions:
                # reopened | next cycle | re-plan → awaiting_decision).
                await self._plan(inc)
            elif inc.state is IncidentState.OPEN and inc.kind == "detect_escalation":
                self._open_escalation_gate(inc)
            elif inc.state is IncidentState.AWAITING_DECISION and inc.plan is not None:
                # T025: reproduction evidence can arrive AFTER the gate
                # opened — the floor is a fact about the world, so a
                # recurrence recomputes it (US2 AC4's "reproduced on two
                # consecutive cycles" path).
                self._reprice(inc)

        # 023b Execute (R1/R6): the act phase, after plan/gate. Behind both
        # the config and the patch marker (R15) — a pre-023b history replays
        # with execute=False and never reaches this path. A refusal comes
        # back with its gate_round already bumped; the round's gate opens
        # here, human-only, and must not block the cycle's completion (R3).
        if cfg.execute and workflow.patched("maint-023b-execute"):
            _records, refusals = await execute_step(self._state, _default_fix_cfg(), workflow.now())
            for inc in refusals:
                self._start_gate(self._repair_gate(inc.no))
            # 023b Report (R4/R5) + the timeout bound, same patch guard:
            # cancel children past child_timeout_hours, then probe and
            # verify the ones still standing.
            await timeout_step(self._state, workflow.now())
            await report_step(self._state, workflow.now())
            # 023b Retention (B-FR-012, R13), last in the cycle so every
            # terminal entry THIS cycle made — verdicts, closure, gates —
            # is retained in the same cycle. A state check: terminal
            # incidents with retained False are retained once.
            await retain_step(self._state)

    def _reprice(self, inc: Incident) -> None:
        """Recompute floor/effective from current facts; if the recomputed
        effective now clears the threshold, policy resolves the pending
        gate (R8: only reproduced mechanical findings clear the default)."""
        assert self._state is not None
        cfg = self._state.config
        if inc.finding is None or inc.decision is not None:
            return
        floor = confidence_floor(
            inc.finding,
            reproduced=inc.seen_count >= 2,
            reopens=inc.reopens,
            n_actions=len(inc.plan.actions) if inc.plan else 0,
        )
        if inc.plan is None or floor == inc.plan.floor:
            return
        inc.plan = inc.plan.model_copy(
            update={"floor": floor, "effective": min(inc.plan.self_confidence, floor)}
        )
        if inc.plan.effective > cfg.threshold:
            self.submit_gate_decision(
                GateDecision(
                    gate=f"repair:{inc.no}",
                    outcome=GateOutcome.APPROVE,
                    decided_by="policy",
                )
            )

    # ---------------------------- analyze + plan -------------------------- #

    async def _plan(self, inc: Incident) -> None:
        """One proposer call in the AssessmentWorkflow._judge degrade shape
        (FR-009): any failure becomes a note, never a crashed cycle."""
        assert self._state is not None
        cfg = self._state.config
        if t_maintainer is None:
            inc.plan_attempts += 1
            inc.note = "analysis_failed: no maintainer role is registered"
            if inc.plan_attempts >= cfg.max_plan_attempts:
                inc.state = IncidentState.ESCALATED
            return

        # FR-202 (VR-3a): the direct proposer call bypasses the RoleHost
        # seam, so the role's validated-output retry budget is forwarded
        # inline — only when set (a default 1 run carries no retries kwarg).
        run_kwargs: dict = {}
        n = OUTPUT_RETRIES.get("maintainer", 1)
        if n != 1:
            run_kwargs["retries"] = {"output": n}
        try:
            run = await t_maintainer.run(
                render_repair_prompt(inc, triage_context=self._triage_context()), **run_kwargs
            )
            proposal: RepairProposal = run.output
        except Exception as e:  # noqa: BLE001 -- the degrade path is the point
            inc.plan_attempts += 1
            inc.note = f"analysis_failed: {type(e).__name__}: {e}"[:300]
            if inc.plan_attempts >= cfg.max_plan_attempts:
                inc.state = IncidentState.ESCALATED
            return

        assert inc.finding is not None
        floor = confidence_floor(
            inc.finding,
            reproduced=inc.seen_count >= 2,
            reopens=inc.reopens,
            n_actions=len(proposal.actions),
        )
        inc.plan = RepairPlan(
            analysis=proposal.analysis,
            actions=proposal.actions,
            self_confidence=proposal.self_confidence,
            floor=floor,
            effective=min(proposal.self_confidence, floor),
            author_model=STAGE_MODELS.get("maintenance", "unknown"),
        )
        inc.note = ""
        inc.state = IncidentState.AWAITING_DECISION
        self._start_gate(self._repair_gate(inc.no))

    def _triage_context(self) -> str:
        assert self._state is not None
        prev = self._state.prev
        if prev is None:
            return "no prior triage recorded"
        counts = ", ".join(
            f"{s.signal}: {len(s.findings)} finding(s), {s.collected.state.value}"
            for s in prev.signals
        )
        return f"repo {prev.repo_dir} @ {prev.commit_sha[:12]} — {counts}"

    # ------------------------------- gates -------------------------------- #

    def _start_gate(self, coro) -> None:
        task = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._gate_tasks.append(task)
        self._gate_tasks = [t for t in self._gate_tasks if not t.done()]

    def _open_escalation_gate(self, inc: Incident) -> None:
        assert self._state is not None
        signal = inc.key.split(":", 1)[0]
        inc.state = IncidentState.AWAITING_DECISION
        self._start_gate(self._escalation_gate(inc.no, signal))

    def _gates_withdrawn(self) -> bool:
        # R15: the disable signal withdraws every open gate (see run()).
        return self._disabling

    async def _repair_gate(self, no: int) -> None:
        """The SOFT repair gate. The auto-approve candidate is offered only
        when effective >= threshold; _gate decides whether policy clears it.
        The outcome mapping per data-model §IncidentState."""
        assert self._state is not None
        cfg = self._state.config
        inc = self._incident(no)
        if inc is None or inc.plan is None:
            return
        name = f"repair:{no}"
        # R6/R8's binding consequence ("only mechanical findings reproduced
        # on two consecutive cycles clear policy" at the default 0.8) makes
        # the boundary strict: an unreproduced mechanical plan at exactly the
        # threshold stays human-gated. effective == threshold does NOT clear.
        # 023b: the gate opens at the incident's CURRENT round, and every
        # round past the first is human-only — a refusal must never be
        # re-approved by policy (no auto-decision, no re-approve loop).
        # 2026-11-19 FR-502 (maint-risk-class): an ops-bearing plan is
        # human-only from birth too — policy can never approve it, whatever
        # the confidence. bears_human_required runs BEFORE workflow.patched
        # so a pure-code_fix run never takes the marker and old histories
        # replay the conjunct as False, commands unchanged (payload-guard
        # precedent).
        human_only = inc.gate_round > 1 or (
            bears_human_required(inc.plan) and workflow.patched("maint-risk-class")
        )
        auto = (
            GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="policy")
            if not human_only and inc.plan.effective > cfg.threshold
            else None
        )
        try:
            decision = await self._gate(
                name,
                repair_gate_settings(cfg, name, human_only=human_only),
                auto_decision=auto,
                round=inc.gate_round,
                confidence=inc.plan.effective,
                author_model=inc.plan.author_model,
                context=GateContext(spec_summary=gate_context_text(inc)),
            )
        except GateWithdrawnError:
            return  # disable: the incident is recorded withdrawn by run()
        self._record_repair_outcome(no, decision)

    async def _escalation_gate(self, no: int, signal: str) -> None:
        """The HARD detect-escalation gate: any decision or timeout
        escalates (data-model)."""
        assert self._state is not None
        cfg = self._state.config
        inc = self._incident(no)
        if inc is None:
            return
        name = f"detect_escalation:{signal}:{no}"
        try:
            decision = await self._gate(
                name,
                escalation_gate_settings(cfg, name),
                context=GateContext(spec_summary=gate_context_text(inc)),
            )
        except GateWithdrawnError:
            return  # disable: the incident is recorded withdrawn by run()
        inc.decision = decision
        inc.state = IncidentState.ESCALATED
        inc.note = f"escalated by {decision.decided_by}"

    def _record_repair_outcome(self, no: int, decision: GateDecision) -> None:
        assert self._state is not None
        cfg = self._state.config
        inc = self._incident(no)
        if inc is None:
            return
        inc.decision = decision
        if decision.outcome is GateOutcome.APPROVE:
            # 023a: approval NEVER executes (terminal approved_not_executed).
            # 023b with execute on: approval hands the incident to Execute
            # (a live state — execute_step starts the child next walk).
            inc.state = (
                IncidentState.APPROVED if cfg.execute else IncidentState.APPROVED_NOT_EXECUTED
            )
            inc.note = ""
        elif decision.outcome is GateOutcome.REVISE:
            # workflow-wire.md: no REVISE path in 023a — treated as reject,
            # the guidance kept in note.
            inc.state = IncidentState.REJECTED
            inc.note = f"revise treated as reject: {decision.guidance or ''}"[:300]
        else:
            inc.state = (
                IncidentState.TIMED_OUT
                if decision.decided_by == "timeout"
                else IncidentState.REJECTED
            )
            inc.note = decision.comments or ""


@workflow.defn
class MaintenanceKickWorkflow:
    """The schedule kicker (R1, workflow-wire.md): started by a Temporal
    Schedule at cadence, it signals the project's loop and finishes. Schedules
    can only start workflows, which is why this tiny workflow exists — and why
    signalling from workflow code (no client-in-activity) is the shape. An
    absent loop is not an error: the kicker finishes not-enabled and never
    retries (R1)."""

    @workflow.run
    async def run(self, inp: MaintenanceKickInput) -> str:
        handle = workflow.get_external_workflow_handle_for(
            MaintenanceWorkflow.run, f"maint-{inp.project}"
        )
        try:
            await handle.signal(MaintenanceWorkflow.nudge)
        except Exception as e:  # noqa: BLE001 -- not-found is a verdict, not a fault
            if "not found" in str(e).lower() or "already completed" in str(e).lower():
                return f"not-enabled:{inp.project}"
            raise
        return f"nudged:{inp.project}"
