"""FeatureWorkflow — idea → deployed feature.

Deterministic orchestration only. All I/O happens in activities or inside
TemporalAgent-managed activities. Human-in-the-loop gates are durable
signal waits with a per-gate policy (hard / soft / off).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import (
        CodingTaskInput, DeployInput, DiffInput, PROpenInput, QAInput,
        WorktreeInput, create_worktree, deploy, get_task_diff,
        open_pull_request, run_coding_task, run_test_suite,
    )
    from .agents.roles import (
        t_architect, t_clarify, t_gate, t_planner, t_qa,
    )
    from .models import (
        DevTask, ExecutionMode, GateDecision, GatePolicy, HandoffSummary,
        IdeaBrief, PipelineConfig, TaskResult,
    )

ACT = dict(start_to_close_timeout=timedelta(minutes=10),
           retry_policy=RetryPolicy(maximum_attempts=3))
LONG_ACT = dict(start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2))


@workflow.defn
class FeatureWorkflow:
    def __init__(self) -> None:
        self._gate_decisions: dict[str, GateDecision] = {}
        self._question_answers: dict[str, str] = {}
        self._status: str = "starting"

    # ---------------- signals / queries (the HITL surface) --------------

    @workflow.signal
    def submit_gate_decision(self, decision: GateDecision) -> None:
        # Idempotent: first decision per gate wins.
        if decision.gate not in self._gate_decisions:
            decision.decided_at = workflow.now()
            self._gate_decisions[decision.gate] = decision

    @workflow.signal
    def answer_question(self, question_id: str, answer: str) -> None:
        self._question_answers.setdefault(question_id, answer)

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def pending_gate(self) -> str | None:
        return self._status if self._status.startswith("awaiting:") else None

    # ---------------------------- helpers -------------------------------

    async def _gate(self, name: str, cfg: PipelineConfig,
                    auto_decision: GateDecision | None = None) -> GateDecision:
        """Durable HITL gate with policy-based auto-approval."""
        policy = cfg.gates.get(name, GatePolicy.HARD)

        if policy == GatePolicy.OFF:
            return GateDecision(gate=name, approved=True, decided_by="policy")

        if policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            return auto_decision  # quality-gate agent said yes → no human

        self._status = f"awaiting:{name}"
        try:
            await workflow.wait_condition(
                lambda: name in self._gate_decisions,
                timeout=timedelta(hours=cfg.gate_timeout_hours),
            )
        except TimeoutError:
            return GateDecision(gate=name, approved=False,
                                decided_by="timeout")
        finally:
            self._status = "running"
        return self._gate_decisions[name]

    async def _dev_task(self, task: DevTask, repo_path: str,
                        base_branch: str, cfg: PipelineConfig,
                        prior_handoffs: list) -> TaskResult:
        """dev → clean-context QA vs. frozen contract, bounded fix loop.

        FR-802: sessions resume across attempts up to max_session_resumes;
        past that, a FRESH session is seeded with a structured handoff —
        compacted context is treated as failure, never continued.
        FR-804: the QA validator sees contract + diff + test output only.
        """
        role_cfg = cfg.roles.get(task.role, cfg.roles["dev"])
        worktree = await workflow.execute_activity(
            create_worktree,
            WorktreeInput(repo_path=repo_path, task_id=task.id,
                          base_branch=base_branch),
            **ACT,
        )
        contract = task.contract
        assertions = (contract.assertions if contract
                      else task.acceptance_criteria)
        # FR-801/805: scoped context — contract + recent handoff concerns,
        # never other tasks' transcripts.
        handoff_notes = [
            f"- {h.task_id}: {'; '.join(h.open_concerns) or 'no concerns'}"
            for h in prior_handoffs[-5:]
        ]
        prompt = (
            f"Task: {task.title}\n{task.description}\n"
            "Your work will be validated against this frozen contract:\n- "
            + "\n- ".join(assertions)
            + ("\nHandoffs from preceding tasks:\n" + "\n".join(handoff_notes)
               if handoff_notes else "")
            + "\nWork only in this worktree. Run the tests before finishing."
        )

        session_id: str | None = None
        resumes = 0
        run = None
        for attempt in range(1, cfg.max_fix_attempts + 2):
            run = await workflow.execute_activity(
                run_coding_task,
                CodingTaskInput(harness=role_cfg.harness, prompt=prompt,
                                worktree=worktree, model=role_cfg.model,
                                session_id=session_id),
                **LONG_ACT,
            )

            # Clean-context validation: contract + tests + diff. No narrative.
            qa_raw = await workflow.execute_activity(
                run_test_suite, QAInput(worktree=worktree), **LONG_ACT)
            diff = await workflow.execute_activity(
                get_task_diff,
                DiffInput(worktree=worktree, base_branch=base_branch),
                **ACT,
            )
            qa = (await t_qa.run(
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nTest results: {qa_raw.model_dump_json()}"
                + f"\nDiff stat:\n{diff['stat']}"
                + f"\nDiff:\n{diff['patch']}")).output

            if qa.tests_passed and not qa.issues:
                handoff = HandoffSummary(
                    task_id=task.id,
                    what_changed=[task.title],
                    files_touched=diff["files"],
                    open_concerns=[],
                )
                return TaskResult(task_id=task.id, status="done",
                                  attempts=attempt, branch=f"sdlc/{task.id}",
                                  run=run, handoff=handoff)

            if attempt > cfg.max_fix_attempts:
                break

            issues = "\n- ".join(qa.issues or qa.failing_tests)
            if resumes < cfg.max_session_resumes:
                session_id = run.session_id       # resume: context intact
                resumes += 1
                prompt = f"Previous attempt has issues. Fix them:\n- {issues}"
            else:
                session_id = None                 # FR-802: fresh session,
                prompt = (                         # seeded with a handoff
                    f"Task: {task.title}\n{task.description}\n"
                    "A previous session implemented part of this in the same "
                    f"worktree (files: {', '.join(diff['files'][:20])}). "
                    "Review the current state, then fix these unmet contract "
                    f"assertions:\n- {issues}\n"
                    "Contract:\n- " + "\n- ".join(assertions)
                )

        # Escalate: human decides whether to accept, retry, or quarantine.
        decision = await self._gate(f"task:{task.id}", cfg)
        return TaskResult(
            task_id=task.id,
            status="done" if decision.approved else "quarantined",
            attempts=cfg.max_fix_attempts + 1,
            branch=f"sdlc/{task.id}",
            notes=decision.comments or "",
        )

    # ------------------------------ run ---------------------------------

    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        repo_path = "/var/sdlc/repo"  # prepared by a setup activity IRL

        # 1. CLARIFY — open questions answered by human via signals
        self._status = "clarifying"
        reqs = (await t_clarify.run(idea.model_dump_json())).output
        if reqs.open_questions:
            self._status = "awaiting:clarify"
            await workflow.wait_condition(
                lambda: all(q.id in self._question_answers
                            for q in reqs.open_questions),
                timeout=timedelta(hours=cfg.gate_timeout_hours),
            )
            for q in reqs.open_questions:
                q.answer = self._question_answers.get(q.id)

        # 2. ARCHITECT (+ human approval of the spec)
        self._status = "architecting"
        arch = (await t_architect.run(
            f"mode={idea.mode.value}\n{reqs.model_dump_json()}")).output
        gate = await self._gate("architecture", cfg)
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        plan = (await t_planner.run(arch.model_dump_json())).output
        gate = await self._gate("plan", cfg)
        if not gate.approved:
            return "rejected:plan"

        # 4. DEV / TEST / DEVOPS tasks — ADR-13: serial by default;
        # wave mode parallelizes, but tasks sharing declared overlaps
        # serialize regardless. Handoffs flow task -> task (FR-805).
        done: dict[str, TaskResult] = {}
        handoffs: list = []
        remaining = {t.id: t for t in plan.tasks}
        import asyncio

        async def run_one(t: DevTask) -> None:
            r = await self._dev_task(t, repo_path, idea.base_branch,
                                     cfg, handoffs)
            done[r.task_id] = r
            if r.handoff:
                handoffs.append(r.handoff)
            remaining.pop(r.task_id)

        while remaining:
            ready = [t for t in remaining.values()
                     if all(d in done for d in t.depends_on)]
            if not ready:
                return "failed:dependency-cycle"

            if cfg.execution_mode == ExecutionMode.SERIAL:
                await run_one(ready[0])
            else:
                # Wave mode: batch ready tasks so no two in a batch share
                # an overlap module; batches run sequentially.
                batch, seen = [], set()
                for t in ready:
                    if seen.isdisjoint(t.overlaps):
                        batch.append(t)
                        seen.update(t.overlaps)
                await asyncio.gather(*[run_one(t) for t in batch])

            if any(r.status == "quarantined" for r in done.values()):
                return "failed:quarantined-tasks"

        # 5. MERGE gate — soft path consults the quality-gate agent first
        auto = (await t_gate.run(
            "Summarize gate decision for merging all task branches. "
            f"Task results: {[r.model_dump() for r in done.values()]}")).output
        gate = await self._gate("merge", cfg, auto_decision=auto)
        if not gate.approved:
            return "rejected:merge"

        pr_url = await workflow.execute_activity(
            open_pull_request,
            PROpenInput(worktree=repo_path, title=idea.title,
                        body=arch.overview, base_branch=idea.base_branch),
            **ACT,
        )

        # 6. DEPLOY gate → deploy
        gate = await self._gate("deploy", cfg)
        if not gate.approved:
            return f"merged-not-deployed:{pr_url}"
        await workflow.execute_activity(
            deploy,
            DeployInput(environment="staging", version=idea.title,
                        command="make deploy ENV=staging", cwd=repo_path),
            **LONG_ACT,
        )
        self._status = "deployed"
        return f"deployed:{pr_url}"
