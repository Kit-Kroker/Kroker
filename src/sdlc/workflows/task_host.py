"""TaskHost -- per-task execution loop and integration branch merge (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Consumes: GateHost, ReportHost, BoardHost, BenchmarkHost, MemoryHost, RoleHost via the MRO.
Owns: _session_refs. (Eliminates _escalation_round as instance state per Rule 2).
"""

from __future__ import annotations

import os
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import (
        CodingTaskInput,
        DiffInput,
        MergeInput,
        WorktreeInput,
        create_worktree,
        get_task_diff,
        merge_into_integration,
        run_coding_task,
    )
    from ..agents.roles import STAGE_MODELS, resolve_role_model, t_qa, t_reviewer
    from ..benchmarks.models import BenchmarkOutcome, WasteBag
    from ..core.models import (
        ArtifactRef,
        GateOutcome,
        GatePolicy,
        HarnessKind,
        PipelineConfig,
        RoleConfig,
        RoleUsage,
    )
    from ..crew.activities import LoadCrewInput, load_crew
    from ..models import (
        DeferredToolUse,
        DevTask,
        EscalationOutcome,
        MemoryKind,
        ToolDenial,
        ToolEscalation,
        ToolGrant,
        compute_plan_drift,
    )
    from ..observability.trace import RunEventKind
    from ..pending import GateContext
    from ..prompts import reviewer_prompt
    from ..stages.qa import step as qa_step
    from ..stages.qa.activities import QAInput, run_test_suite
    from ..stages.qa.step import _fix_loop_issues
    from .crew import FS_ACT, CrewTaskInput, CrewTaskWorkflow
    from .models import TaskResult

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)

LONG_ACT_HEARTBEAT_MINUTES = int(os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
LONG_ACT_TIMEOUT_HOURS = int(os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
LONG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

DEFAULT_TEST_CMD = "pytest -q --maxfail=25"


def _long_act(role_cfg: RoleConfig | None = None) -> workflow.ActivityConfig:
    """LONG_ACT, with a role's own timeout/heartbeat overrides if it has any."""
    if role_cfg is None:
        return LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return LONG_ACT
    return workflow.ActivityConfig(
        start_to_close_timeout=timedelta(
            hours=hours if hours is not None else LONG_ACT_TIMEOUT_HOURS
        ),
        heartbeat_timeout=timedelta(
            minutes=minutes if minutes is not None else LONG_ACT_HEARTBEAT_MINUTES
        ),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )


def _contract_stack_directive(contract) -> str:
    """Surface the frozen stack as a standalone, non-negotiable line —
    not just one bullet among the assertions. A coding agent on a
    greenfield (empty) worktree has no existing scaffolding to anchor
    it to the required language/runtime, so the constraint needs to be
    unmissable rather than buried in prose."""
    if not contract or not contract.stack:
        return ""
    return f"MANDATORY STACK (do not deviate, even when revising): {contract.stack}\n"


def _contract_shell_cmd(commands: list[str] | None, default: str) -> str:
    """Join a contract's stack-specific test/lint commands into one shell
    command (`&&`-chained so an earlier failure short-circuits the rest).
    Falls back to `default` (a Python toolchain command) only when the
    contract carries none — e.g. a legacy/cached artifact predating this
    field, never as a silent stack-mismatch."""
    if not commands:
        return default
    return " && ".join(commands)


_TEST_OUTPUT_MAX = 1500

_HANDOFF_TAIL = 5


def _handoff_notes(prior_handoffs: list) -> list[str]:
    """FR-801/805: scoped context for the NEXT task.

    Claim TEXT only -- evidence quotes are for the cross-check and the
    benchmark record, and pasting transcript excerpts into a fresh prompt
    is how authoring context leaks sideways. A handoff with no claims
    contributes no line at all: 'task-3: no concerns' is noise that taught
    the reader nothing for every run this channel has existed.
    """
    notes: list[str] = []
    for h in prior_handoffs[-_HANDOFF_TAIL:]:
        parts: list[str] = []
        for label, claims in (
            ("did", h.what_changed),
            ("decided", h.decisions_made),
            ("concerns", h.open_concerns),
        ):
            if claims:
                parts.append(f"{label}: " + "; ".join(c.text for c in claims))
        if parts:
            notes.append(f"- {h.task_id}: " + " | ".join(parts))
    return notes


def _should_resume_session(qa, resumes: int, max_resumes: int, near_ceiling: bool) -> bool:
    """FR-802 resume budget, with a stack-mismatch override: a session
    that already committed to the wrong language/runtime is a worse
    starting point than a fresh one — the agent is anchored to files it
    would need to delete wholesale. Never resume it, regardless of
    remaining resume budget or context headroom."""
    if qa.stack_mismatch:
        return False
    return resumes < max_resumes and not near_ceiling


def escalations_from_denials(denials: list[ToolDenial]) -> list[ToolEscalation]:
    """Denials the hook could not escalate (batched call, unreadable
    transcript). No human was asked, so there is no gate and no round — but
    they must still be countable, or the size of the solo-only hole would be
    invisible (E-17 §6)."""
    return [
        ToolEscalation(
            tool=d.tool, rule_id=d.rule_id, target=d.target, outcome=EscalationOutcome.BATCHED
        )
        for d in denials
        if d.escalation_declined
    ]


def _escalation_summary(task_id: str, title: str, deferred: DeferredToolUse) -> str:
    """What the human is actually deciding, rendered into the GateContext
    field the E-6 channel contract already renders (the same way the budget
    gate puts its cost table there)."""
    return (
        f"Task {task_id} ({title}) is blocked on a tool call.\n"
        f"  tool:   {deferred.tool}\n"
        f"  target: {deferred.target or '(none)'}\n"
        f"  rule:   {deferred.rule_id} — {deferred.reason}\n"
        "Approve to permit exactly this one call; reject to refuse it "
        "(the task continues either way)."
    )


class TaskHost:
    """Mixin. Owns the dev task execution loop (_dev_task) and branch merge (_merge_task).

    Consumes: GateHost, ReportHost, BoardHost, BenchmarkHost, MemoryHost, RoleHost.
    Owns: _session_refs. (Eliminates _escalation_round as instance state per Rule 2).
    """

    def __init__(self) -> None:
        super().__init__()
        self._session_refs: list[ArtifactRef] = []

    async def _merge_task(self, tr: TaskResult, repo_path: str) -> str | None:
        """Merge a completed task branch into the integration branch and
        advance self._integration_head.

        Returns a terminal status string on conflict (falsified overlaps
        declaration), else None. A conflict means the task's declared
        `overlaps` were incomplete → falsified contract → the run terminates
        with an observable status rather than raising (a raise would make
        Temporal retry a deterministic conflict). Called from both SERIAL and
        wave paths; never inside run_one (Resolution B)."""
        merge_res = await workflow.execute_activity(
            merge_into_integration,
            MergeInput(
                repo_path=repo_path,
                run_id=workflow.info().workflow_id,
                task_branch=tr.branch,
                integration_path=getattr(self, "_integration_wt", ""),
            ),
            **ACT,
        )
        if merge_res.conflict:
            # Falsified `overlaps` declaration → terminal status, not a raise.
            return f"failed:integration-conflict:{tr.task_id}"
        self._integration_head = merge_res.integration_head
        return None

    async def _record_escalation(
        self, cfg: PipelineConfig, task: DevTask, esc: ToolEscalation
    ) -> None:
        """Trace event (events.jsonl / report.html) plus a benchmark record
        so E-36's case x stage heatmap sees approval friction."""
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.TOOL_ESCALATION,
            stage="tool_approval",
            task_id=task.id,
            tool=esc.tool,
            rule_id=esc.rule_id,
            outcome=esc.outcome.value,
            decided_by=esc.decided_by,
            round=str(esc.round),
            **({"target": esc.target} if esc.target else {}),
        )
        now = workflow.now()
        # `judge` is a constrained Literal on QualityScore — "policy" is not a
        # member. A gate-decided outcome is a human override; a capped or
        # batched one was decided deterministically, with nobody asked.
        judge = "human_override" if esc.decided_by == "human" else "contract"
        await self._record(  # type: ignore[attr-defined]
            cfg,
            self._stage_record(  # type: ignore[attr-defined]
                cfg,
                stage="tool_approval",
                role="human",
                started=now,
                ended=now,
                quality_score=None,
                judge=judge,
                outcome=(
                    BenchmarkOutcome.PASS
                    if esc.outcome is EscalationOutcome.APPROVED
                    else BenchmarkOutcome.ESCALATED
                ),
                model="human",
                task_id=task.id,
            ),
        )

    async def _dev_task(
        self,
        task: DevTask,
        repo_path: str,
        from_ref: str,
        cfg: PipelineConfig,
        prior_handoffs: list,
    ) -> TaskResult:
        """dev → clean-context QA vs. frozen contract, bounded fix loop.

        FR-802: sessions resume across attempts up to max_session_resumes;
        past that, a FRESH session is seeded with a structured handoff —
        compacted context is treated as failure, never continued.
        FR-804: the QA validator sees contract + diff + test output only.
        """
        role_cfg = cfg.roles.get(task.role, cfg.roles["dev"])
        # Registry validation (validate_run_roles, ADR-6) fails closed unless
        # the dev/reviewer models are set, and the fallback here is always
        # cfg.roles["dev"] — so the role driving a task carries a model, and
        # the usage/record types below are typed on that.
        assert role_cfg.model is not None
        handle = await workflow.execute_activity(
            create_worktree,
            WorktreeInput(
                repo_path=repo_path,
                run_id=workflow.info().workflow_id,
                task_id=task.id,
                from_ref=from_ref,
            ),
            **ACT,
        )
        worktree = handle.path
        contract = task.contract
        assertions = contract.assertions if contract else task.acceptance_criteria
        # FR-801/805: scoped context — contract + recent handoff concerns,
        # never other tasks' transcripts.
        handoff_notes = _handoff_notes(prior_handoffs)
        stack_directive = _contract_stack_directive(contract)
        prompt = (
            f"Task: {task.title}\n{task.description}\n"
            + stack_directive
            + "Your work will be validated against this frozen contract:\n- "
            + "\n- ".join(assertions)
            + (
                "\nHandoffs from preceding tasks:\n" + "\n".join(handoff_notes)
                if handoff_notes
                else ""
            )
            + "\nWork only in this worktree. Run the tests before finishing."
            + "\nThis worktree is already a git repository (checked out on its"
            " own branch) even if the task looks like a fresh/greenfield"
            " project — do NOT run `git init`, and do NOT delete or modify"
            " the `.git` file/directory."
        )

        crew_layout = crew_roles = None
        crew_protocol = ""
        crew_sessions: dict[str, str] = {}
        if role_cfg.harness is HarnessKind.CREW:
            crew = await workflow.execute_activity(
                load_crew,
                LoadCrewInput(
                    layout=role_cfg.layout or "code",
                    lead_harness=role_cfg.lead_harness,
                    lead_model=role_cfg.model,
                ),
                **FS_ACT,
            )
            crew_layout, crew_roles, crew_protocol = (crew.layout, crew.roles, crew.protocol)

        session_id: str | None = None
        resumes = 0
        run = None
        attempt = 0
        escalation_round = 0
        # Attempts available before the escalation gate fires. A REVISE at
        # that gate grants exactly one more (see the escalation below), the
        # same "one producer re-run per round" rule _revisable_stage applies
        # to the stage gates.
        budget = cfg.max_fix_attempts + 1
        gate_round = 0
        while True:
            attempt += 1
            _attempt_started = workflow.now()
            self._emit(  # type: ignore[attr-defined]
                RunEventKind.FIX_ATTEMPT, stage="code", task_id=task.id, attempt=str(attempt)
            )
            # E-17: the harness may SUSPEND at a tool call an escalate rule
            # matched (claude's `defer`). The child process has already
            # exited, so the durable wait belongs here, in the workflow —
            # then we resume the same session with the human's decision.
            grants: list[ToolGrant] = []
            asked = 0
            capped = False
            while True:
                if role_cfg.harness is HarnessKind.CREW:
                    # E-88: the crew is a child workflow, not an activity.
                    # It returns the same HarnessRunResult, so everything
                    # around this call -- the E-17 deferred loop, the
                    # escalations, the cost accumulation -- is unchanged.
                    assert crew_layout is not None
                    assert crew_roles is not None
                    # mypy cannot match the MethodAsyncSingleParam overload
                    # once the id/execution_timeout keywords are present,
                    # although the shapes are identical.
                    crew = await workflow.execute_child_workflow(  # type: ignore[call-overload]
                        CrewTaskWorkflow.run,
                        CrewTaskInput(
                            layout=crew_layout.layout,
                            lead=crew_layout.lead,
                            roles=crew_roles,
                            prompt=prompt,
                            worktree=worktree,
                            task_id=task.id,
                            attempt=attempt,
                            deliverable_path=crew_layout.deliverable.path,
                            rounds_max=crew_layout.rounds.max,
                            wall_clock_s=crew_layout.limits.wall_clock_s,
                            turn_timeout_s=crew_layout.limits.turn_timeout_s,
                            cost_usd=crew_layout.limits.cost_usd,
                            sessions=crew_sessions,
                            protocol=crew_protocol,
                            containment_enabled=cfg.containment_enabled,
                            containment_policy_path=cfg.containment.policy_path,
                            containment_strict=cfg.containment.strict,
                            gate_settings=cfg.gate_settings(),
                            max_tool_escalations=cfg.max_tool_escalations,
                        ),
                        id=f"{workflow.info().workflow_id}-crew-{task.id}-{attempt}",
                        execution_timeout=timedelta(seconds=crew_layout.limits.wall_clock_s + 600),
                    )
                    crew_sessions = crew.sessions
                    run = crew.run
                    self._session_refs.extend(crew.session_refs)
                else:
                    # The existing call, moved into the else branch verbatim:
                    # same CodingTaskInput(...) arguments, same _long_act.
                    # A doing-role always carries a concrete harness here: a
                    # CREW role took the branch above, and a harnessless
                    # (proposer/research) role can never reach _dev_task.
                    assert role_cfg.harness is not None
                    run = await workflow.execute_activity(
                        run_coding_task,
                        CodingTaskInput(
                            harness=role_cfg.harness,
                            prompt=prompt,
                            worktree=worktree,
                            model=role_cfg.model,
                            session_id=session_id,
                            task_id=task.id,
                            attempt=attempt,
                            containment_enabled=cfg.containment_enabled,
                            containment_policy_path=cfg.containment.policy_path,
                            containment_strict=cfg.containment.strict,
                            grants=grants,
                        ),
                        **_long_act(role_cfg),
                    )
                assert run is not None
                for esc in run.escalations:
                    await self._record_escalation(cfg, task, esc)
                for esc in escalations_from_denials(run.denials):
                    await self._record_escalation(cfg, task, esc)
                if run.deferred is None or capped:
                    break
                # Resuming for an approval is NOT a failure resume: it costs
                # neither a fix attempt nor the FR-802 resume budget.
                session_id = run.session_id
                if asked >= cfg.max_tool_escalations:
                    capped = True
                    grants = [
                        ToolGrant(
                            tool_use_id=run.deferred.tool_use_id,
                            tool=run.deferred.tool,
                            input_digest=run.deferred.input_digest,
                            rule_id=run.deferred.rule_id,
                            approved=False,
                            reason="escalation cap reached",
                        )
                    ]
                    await self._record_escalation(
                        cfg,
                        task,
                        ToolEscalation(
                            tool=run.deferred.tool,
                            rule_id=run.deferred.rule_id,
                            target=run.deferred.target,
                            outcome=EscalationOutcome.CAPPED,
                            decided_by="policy",
                        ),
                    )
                    continue  # one more resume, only to deliver the deny
                asked += 1
                escalation_round += 1
                decision = await self._gate(  # type: ignore[attr-defined]
                    "tool_approval",
                    cfg.gate_settings(),
                    round=escalation_round,
                    context=GateContext(
                        spec_summary=_escalation_summary(task.id, task.title, run.deferred)
                    ),
                    default_policy=GatePolicy.HARD,
                )
                grants = [
                    ToolGrant(
                        tool_use_id=run.deferred.tool_use_id,
                        tool=run.deferred.tool,
                        input_digest=run.deferred.input_digest,
                        rule_id=run.deferred.rule_id,
                        approved=decision.approved,
                        reason=decision.comments or "",
                    )
                ]
                await self._record_escalation(
                    cfg,
                    task,
                    ToolEscalation(
                        tool=run.deferred.tool,
                        rule_id=run.deferred.rule_id,
                        target=run.deferred.target,
                        outcome=(
                            EscalationOutcome.APPROVED
                            if decision.approved
                            else EscalationOutcome.TIMEOUT
                            if decision.decided_by == "timeout"
                            else EscalationOutcome.REJECTED
                        ),
                        decided_by=decision.decided_by,
                        round=escalation_round,
                    ),
                )
            # The crew seam extends the FULL ref list in its branch; the
            # last ref also rides run.session_ref for the clean-context
            # consumers — don't double-count it here.
            if run.session_ref is not None and run.session_ref not in self._session_refs:
                self._session_refs.append(run.session_ref)

            # E-33 harness join: the harness reports REAL dollars (CLI
            # total_cost_usd) — no pricing activity needed. Accumulate
            # under the executing role.
            #
            # `into` is not optional here: self._role_usage is per RUN and per
            # role, while a stage='code' BenchmarkRecord is per TASK ATTEMPT,
            # so the record cannot read the accumulator. Without a bag of its
            # own the record went out with cost.usd set and
            # cost.input_tokens/output_tokens null — for every harness, not
            # only crew (cost_bag_from_spend degrades to CostBag(usd=...)
            # when spend is None). E-88's acceptance asks for non-null token
            # counts, and the tokens were in `run` the whole time.
            code_spend = RoleUsage(role="dev", model=role_cfg.model)
            self._track_usage(  # type: ignore[attr-defined]
                role="dev",
                model=role_cfg.model,
                input_tokens=run.input_tokens or 0,
                output_tokens=run.output_tokens or 0,
                cost_usd=run.cost_usd,
                into=code_spend,
            )

            # Clean-context validation: contract + tests + diff. No narrative.
            # Uses the contract's own stack-specific test_commands (FR-803)
            # rather than QAInput's Python-toolchain default — a non-Python
            # stack must never be QA'd with pytest.
            test_cmd = _contract_shell_cmd(
                contract.test_commands if contract else None, DEFAULT_TEST_CMD
            )
            qa_raw = await workflow.execute_activity(
                run_test_suite,
                QAInput(worktree=worktree, test_cmd=test_cmd),
                **_long_act(cfg.roles.get("test", role_cfg)),
            )
            diff = await workflow.execute_activity(
                get_task_diff,
                DiffInput(worktree=worktree, branch_point=handle.branch_point),
                **ACT,
            )
            qa_spend = RoleUsage(role="qa", model=resolve_role_model(cfg, "qa"))
            qa = await qa_step(
                self._ctx,  # type: ignore[attr-defined]
                cfg=cfg,
                task=task,
                contract=contract,
                diff=diff,
                worktree=worktree,
                qa_agent=t_qa,
                qa_raw=qa_raw,
                qa_spend=qa_spend,
            )

            # Second clean-context judge (FR-204): same inputs as QA — frozen
            # contract + materialized diff + test output. No narrative, no
            # session. A different model family than the developer (ADR-6).
            review = None
            if cfg.review_enabled:
                review = (
                    await self._run_role(  # type: ignore[attr-defined]
                        cfg,
                        "reviewer",
                        STAGE_MODELS.get("review", "unknown"),
                        t_reviewer,
                        reviewer_prompt(assertions, qa_raw.model_dump_json(), diff["patch"]),
                    )
                ).output

            # `qa_raw.tests_passed` is the actual subprocess exit code;
            # `qa.tests_passed` is the LLM QA agent's OWN retyped guess at
            # the same fact (its instructions ask it to judge contract
            # compliance, not to re-derive this bit) and can disagree with
            # ground truth. The pass/fail gate must anchor on qa_raw here —
            # an LLM opinion must never overwrite a deterministic signal.
            task_passed = qa_raw.tests_passed and not qa.issues

            await self._record(  # type: ignore[attr-defined]
                cfg,
                self._stage_record(  # type: ignore[attr-defined]
                    cfg,
                    stage="code",
                    role=task.role,
                    started=_attempt_started,
                    ended=workflow.now(),
                    quality_score=(1.0 if task_passed else 0.0),
                    judge="contract",
                    outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                    model=role_cfg.model,
                    harness=role_cfg.harness,
                    lead_harness=role_cfg.lead_harness,
                    cost_usd=run.cost_usd,
                    spend=code_spend,
                    waste=WasteBag.from_digest(run.session_digest),
                    plan_drift=compute_plan_drift(task, diff.get("files", [])),
                    fix_attempts=attempt - 1,
                    task_id=task.id,
                    attempt=attempt - 1,
                ),
            )

            # The QA report gets its OWN record. The stage="code" record above
            # keeps its deterministic contract score (1.0 iff tests passed and
            # no issues) -- an LLM opinion must never overwrite a deterministic
            # signal. Cardinality is per-task-attempt, not once-per-run like
            # clarifier/architect/planner; scoring.py means over them natively.
            _qa_quality = await self._judge(  # type: ignore[attr-defined]
                cfg, qa.model_dump_json(), "qa", author_model=resolve_role_model(cfg, "qa")
            )
            await self._record(  # type: ignore[attr-defined]
                cfg,
                self._stage_record(  # type: ignore[attr-defined]
                    cfg,
                    stage="qa",
                    role="qa",
                    started=_attempt_started,
                    ended=workflow.now(),
                    quality_score=_qa_quality.score,
                    judge=_qa_quality.judge,
                    outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                    model=resolve_role_model(cfg, "qa"),
                    spend=qa_spend,
                    task_id=task.id,
                    attempt=attempt - 1,
                ),
            )

            review_ok = review is None or review.approve
            if review is not None:
                # The primary's verdict has never been recorded, so
                # review-driven rework showed as fix_attempts on code/qa with
                # no cause row at all. Disagreement is a RELATION between two
                # records; the adversary's is meaningless without this one.
                await self._record(  # type: ignore[attr-defined]
                    cfg,
                    self._stage_record(  # type: ignore[attr-defined]
                        cfg,
                        stage="review",
                        role="reviewer",
                        started=_attempt_started,
                        ended=workflow.now(),
                        quality_score=(1.0 if review.approve else 0.0),
                        judge="contract",
                        outcome=(
                            BenchmarkOutcome.PASS if review.approve else BenchmarkOutcome.FAIL
                        ),
                        model=STAGE_MODELS.get("review", "unknown"),
                        task_id=task.id,
                        attempt=attempt - 1,
                        fix_attempts=0,
                    ),
                )  # cause row; volume lives on code/qa

            adversary = None
            if task_passed and review_ok:
                # Approving path only: a rejection is already headed for the
                # fix loop, so the expensive error is a false approve. The
                # adversary is a SECOND opinion -- it presupposes a first, so
                # it never runs when review is disabled (review is None); the
                # primary reviewer is the sole designated blocking lens, which
                # is the entire justification for this lens being fail-open.
                if review is not None:
                    adversary = await self._run_adversary(  # type: ignore[attr-defined]
                        cfg, contract, assertions, diff, qa_raw, task
                    )
                # A split fails the attempt ONLY when the adversary has
                # actionable (critical/high) findings. A reject with no
                # blocking findings has nothing to put in a retry prompt -- it
                # would hit the ``if not issues: break`` below and silently
                # abandon a task that passed its gate. Same rule as the primary:
                # blocking_findings is actionable, the boolean is not.
                if adversary is None or adversary.approve or not adversary.blocking_findings:
                    deep = await self._run_deep_review(  # type: ignore[attr-defined]
                        cfg, run, contract, assertions, diff, task
                    )
                    handoff = await self._run_handoff(  # type: ignore[attr-defined]
                        cfg, run, contract, assertions, diff, task
                    )
                    return TaskResult(
                        task_id=task.id,
                        status="done",
                        attempts=attempt,
                        branch=handle.branch,
                        run=run,
                        handoff=handoff,
                        qa=qa_raw,
                        review=review,
                        deep_review=deep,
                    )
                # Split: fall through to the retry path below. max_fix_attempts
                # still bounds it, and exhaustion enters the existing
                # accept / retry-with-guidance / quarantine gate unchanged.

            issues = "" if attempt >= budget else _fix_loop_issues(qa, qa_raw, review, adversary)
            if attempt < budget and not issues:
                # The task failed its gate, yet neither judge produced a
                # single actionable statement — there is nothing to put in a
                # retry prompt, so re-attempting only re-rolls the dice at
                # full cost. That combination means the gate fired on
                # something the loop cannot express (historically: harness
                # provisioning), so stop and surface it rather than burning
                # the remaining budget on a blank instruction.
                workflow.logger.warning(
                    "task %s attempt %s failed with no actionable feedback "
                    "(qa_raw.tests_passed=%s) - abandoning fix loop",
                    task.id,
                    attempt,
                    qa_raw.tests_passed,
                )
                budget = attempt  # nothing to retry on → escalate now

            if attempt >= budget:
                # Escalate: the human accepts, asks for a revision, or
                # quarantines. REVISE must be read off `outcome`, never off
                # `decision.approved` — that property is False for BOTH
                # reject and revise (its own docstring says callers who must
                # distinguish read `outcome`), and collapsing the two here
                # made APPROVE the only outcome a run could survive.
                #
                # The analysis carries the SAME evidence the fix loop got — a
                # human asked to adjudicate a task whose only real failure was
                # a red test command must be shown that command's output, not
                # an empty list.
                gate_round += 1
                analysis = _fix_loop_issues(qa, qa_raw, review) if qa else ""
                decision = await self._gate(  # type: ignore[attr-defined]
                    f"task:{task.id}",
                    cfg.gate_settings(),
                    round=gate_round,
                    context=GateContext(task_id=task.id, analysis=analysis, attempts=attempt),
                )
                if decision.outcome is GateOutcome.REVISE and gate_round <= cfg.max_gate_rounds:
                    # Bounded exactly like _revisable_stage: one more attempt
                    # per granted round, then the gate is asked again. Past
                    # max_gate_rounds the final gate decides accept-anyway vs
                    # quarantine, so revise can never loop forever.
                    guidance = decision.guidance or decision.comments or ""
                    budget = attempt + 1
                    # Fresh session: the operator is redirecting the work, and
                    # the prior session is anchored to the approach they just
                    # rejected.
                    session_id = None
                    prompt = (
                        stack_directive
                        + f"Task: {task.title}\n{task.description}\n"
                        + "An operator reviewed the previous attempts and "
                        "asked for these changes:\n"
                        + f"{guidance}\n"
                        + "Contract:\n- "
                        + "\n- ".join(assertions)
                    )
                    continue
                deep = await self._run_deep_review(  # type: ignore[attr-defined]
                    cfg, run, contract, assertions, diff, task
                )
                return TaskResult(
                    task_id=task.id,
                    status="done" if decision.approved else "quarantined",
                    # `attempt`, not the ceiling: the loop can exit early when
                    # it has no actionable feedback to retry on, and the
                    # benchmark's fix_attempts column has to reflect what was
                    # actually spent.
                    attempts=attempt,
                    branch=handle.branch,
                    qa=qa_raw,
                    review=review,
                    deep_review=deep,
                    notes=decision.comments or "",
                )

            await self._retain(  # type: ignore[attr-defined]
                cfg,
                MemoryKind.GOTCHA,
                cfg.memory.project_bank,
                text=f"task {task.id} ({task.title}) attempt {attempt} failed: {issues}",
                metadata={"task_id": task.id, "run_id": workflow.info().workflow_id},
            )
            if _should_resume_session(
                qa, resumes, cfg.max_session_resumes, run.near_context_ceiling()
            ):
                session_id = run.session_id  # resume: context intact
                resumes += 1
                prompt = stack_directive + f"Previous attempt has issues. Fix them:\n- {issues}"
            else:
                # Either past the resume bound, at/over the context ceiling
                # (compaction = failure), or the diff used the wrong
                # language/runtime entirely → fresh session seeded with a
                # structured handoff (FR-802, ADR-13). A stack mismatch is
                # never resumed even within budget: the prior session is
                # anchored to files it would need to delete wholesale.
                session_id = None
                discard_note = (
                    "The previous attempt used the WRONG language/runtime "
                    "entirely. Delete that wrong-stack scaffolding rather "
                    "than patching it, and reimplement from scratch in the "
                    "mandated stack below.\n"
                    if qa.stack_mismatch
                    else "A previous session implemented part of this in the same "
                    f"worktree (files: {', '.join(diff['files'][:20])}). "
                    "Review the current state, then fix these unmet contract "
                    "assertions.\n"
                )
                prompt = (
                    stack_directive
                    + f"Task: {task.title}\n{task.description}\n"
                    + discard_note
                    + f"Unmet contract assertions:\n- {issues}\n"
                    "Contract:\n- " + "\n- ".join(assertions)
                )
