"""FeatureWorkflow — idea → deployed feature.

Deterministic orchestration only. All I/O happens in activities or inside
TemporalAgent-managed activities. Human-in-the-loop gates are durable
signal waits with a per-gate policy (hard / soft / off).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import (
        CodingTaskInput, DeployInput, DiffInput, LintInput, PROpenInput,
        QAInput, WorktreeInput, create_worktree, deploy, evaluate_gate,
        get_task_diff, open_pull_request, run_coding_task, run_lint,
        run_test_suite,
    )
    from ..agents.roles import (
        MODEL, PROMPT_SHAS, t_architect, t_clarify, t_merge_verdict,
        t_planner, t_qa,
    )
    from ..benchmarks.judge import (
        JudgeInput, _build_judge_input, judge_artifact,
    )
    from ..benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CostBag,
        QualityScore, SpeedBag,
    )
    from ..benchmarks.recorder import record_benchmark
    from ..gate import (
        CheckClass, CheckResult, GateOverride, GateReport, QualityGateInput,
        build_check,
    )
    from ..memoization.activities import (
        CacheGetInput, CachePutInput, cache_get, cache_put,
    )
    from ..memoization.cache import content_key
    from ..memory.activities import (
        RecallInput, RetainInput, WatermarkInput, capture_watermark,
        recall_snapshot, retain,
    )
    from ..models import (
        ArchitectureSpec, ClarifiedRequirements, DevTask, ExecutionMode,
        GateDecision, GateOutcome, GatePolicy, HandoffSummary, IdeaBrief,
        ImplementationPlan, MemoryKind, MergeVerdict, PipelineConfig,
        RecallSnapshot, RetainItem, RoleConfig, TaskResult, gate_key,
    )

ACT = dict(start_to_close_timeout=timedelta(minutes=10),
           retry_policy=RetryPolicy(maximum_attempts=3))
# Coding/test-suite runs stream output in bursts; a quiet LLM turn can
# outlast a short heartbeat window and get killed as a false-dead worker.
# Both knobs are env-configurable since "how long is one attempt allowed
# to run silently" is a deployment/harness choice, not a code constant.
LONG_ACT_HEARTBEAT_MINUTES = int(
    os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
LONG_ACT_TIMEOUT_HOURS = int(
    os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
LONG_ACT = dict(
    start_to_close_timeout=timedelta(hours=LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2))
RECORD_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                  retry_policy=RetryPolicy(maximum_attempts=5))
MEM_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
              retry_policy=RetryPolicy(maximum_attempts=5))


def _long_act(role_cfg: RoleConfig | None = None) -> dict:
    """LONG_ACT, with a role's own timeout/heartbeat overrides if it has any."""
    if role_cfg is None:
        return LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return LONG_ACT
    return dict(
        start_to_close_timeout=timedelta(
            hours=hours if hours is not None else LONG_ACT_TIMEOUT_HOURS),
        heartbeat_timeout=timedelta(
            minutes=minutes if minutes is not None
            else LONG_ACT_HEARTBEAT_MINUTES),
        retry_policy=RetryPolicy(maximum_attempts=2))


@workflow.defn
class FeatureWorkflow:
    def __init__(self) -> None:
        self._gate_decisions: dict[str, GateDecision] = {}
        self._question_answers: dict[str, str] = {}
        self._status: str = "starting"
        self._memory_watermark: str | None = None

    # ----------------------- benchmark recording ------------------------

    @staticmethod
    def _benchmarking(cfg: PipelineConfig) -> bool:
        return bool(cfg.benchmark and cfg.benchmark.case_id)

    def _stage_record(self, cfg: PipelineConfig, stage: str, role: str,
                      started: datetime, ended: datetime,
                      quality_score: float | None, judge: str,
                      outcome: BenchmarkOutcome, model: str,
                      harness=None, cost_usd: float | None = None,
                      fix_attempts: int = 0,
                      task_id: str | None = None,
                      attempt: int | None = None) -> BenchmarkRecord:
        scope = (BenchmarkScope.TASK_ATTEMPT if task_id is not None
                 else BenchmarkScope.STAGE)
        return BenchmarkRecord(
            run_id=workflow.info().workflow_id,
            bench_run_id=cfg.benchmark.bench_run_id or "_unknown",
            case_id=cfg.benchmark.case_id or "_unknown",
            scope=scope, stage=stage, task_id=task_id, attempt=attempt,
            role=role, harness=harness, model=model, prompt_sha="",
            quality=QualityScore(score=quality_score, judge=judge),
            cost=CostBag(usd=cost_usd),
            speed=SpeedBag(wall_clock_s=(ended - started).total_seconds(),
                           started_at=started, ended_at=ended),
            outcome=outcome, fix_attempts=fix_attempts,
        )

    async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord
                      ) -> None:
        if not self._benchmarking(cfg):
            return
        await workflow.execute_activity(record_benchmark, record, **RECORD_ACT)

    async def _judge(self, cfg: PipelineConfig, artifact_json: str,
                     stage: str) -> QualityScore:
        """Judge a proposer-stage artifact iff benchmarking is on AND a
        rubric is registered for the stage.

        Returns a graceful QualityScore(score=None, judge='llm_judge') when
        judging is skipped — when not benchmarking, or no rubric exists for
        the stage — so the record still emits without failing the stage.
        The LLM call lives in the judge_artifact activity, never in workflow
        code.

        ``stage`` is the rubric-map key carried on cfg.benchmark.rubrics
        (e.g. 'clarifier', 'architect'), NOT the record's stage field.

        Author model: proposer agents bind roles.MODEL today (foundation
        limitation — they don't yet honor cfg.roles), so the same constant is
        the author identity for every proposer stage. The judge_model (e.g.
        'openai/gpt-5.2') differs from the author ('zai-coding-plan/...') →
        ADR-6 cross-family satisfied.
        """
        fallback = QualityScore(score=None, judge="llm_judge")
        if not self._benchmarking(cfg):
            return fallback
        judge_input: JudgeInput | None = _build_judge_input(
            artifact_json=artifact_json,
            rubrics=cfg.benchmark.rubrics,
            stage=stage,
            author_model=MODEL,
            judge_model=cfg.benchmark.judge_model,
        )
        if judge_input is None:
            return fallback
        return await workflow.execute_activity(
            judge_artifact, judge_input, **RECORD_ACT)

    # ------------------------------ memory -------------------------------

    async def _recall(self, cfg: PipelineConfig, bank: str, query: str,
                      filters: dict[str, str]) -> RecallSnapshot:
        if not cfg.memory.enabled:
            return RecallSnapshot(query_hash="", bank=bank,
                                  watermark="unknown", items=[])
        return await workflow.execute_activity(
            recall_snapshot,
            RecallInput(bank=bank, query=query, filters=filters,
                       watermark=self._memory_watermark,
                       backend=cfg.memory.backend, base_url=cfg.memory.base_url),
            **MEM_ACT)

    async def _retain(self, cfg: PipelineConfig, kind: MemoryKind, bank: str,
                      text: str, metadata: dict[str, str]) -> None:
        if not cfg.memory.enabled:
            return
        try:
            await workflow.execute_activity(
                retain,
                RetainInput(item=RetainItem(kind=kind, bank=bank, text=text,
                                            metadata=metadata),
                           backend=cfg.memory.backend,
                           base_url=cfg.memory.base_url),
                **MEM_ACT)
        except Exception:
            pass

    async def _cached_stage(self, cfg: PipelineConfig, stage: str,
                            input_json: str, model_id: str,
                            output_type: type, run_fn) -> tuple[object, bool]:
        """Skips `run_fn()` (a no-arg async callable invoking the proposer
        agent) when an identical (stage, input, prompt, model,
        upstream-recall-watermark) combination was already computed — the
        ADR-5 dev-loop cache. Returns (output, was_cache_hit)."""
        if not cfg.memoization_enabled:
            return await run_fn(), False
        key = content_key(stage, input_json, PROMPT_SHAS[stage], model_id,
                          self._memory_watermark or "none")
        cached = await workflow.execute_activity(
            cache_get, CacheGetInput(key=key), **MEM_ACT)
        if cached is not None:
            return output_type.model_validate_json(cached), True
        result = await run_fn()
        await workflow.execute_activity(
            cache_put,
            CachePutInput(key=key, payload_json=result.model_dump_json()),
            **MEM_ACT)
        return result, False

    # ---------------- signals / queries (the HITL surface) --------------

    @workflow.signal
    def submit_gate_decision(self, decision: GateDecision) -> None:
        # Idempotent per (gate, round): first decision for a round wins.
        key = gate_key(decision.gate, decision.round)
        if key not in self._gate_decisions:
            decision.decided_at = workflow.now()
            self._gate_decisions[key] = decision

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
                    auto_decision: GateDecision | None = None,
                    round: int = 1) -> GateDecision:
        """Durable HITL gate with policy-based auto-approval."""
        policy = cfg.gates.get(name, GatePolicy.HARD)
        key = gate_key(name, round)

        if policy == GatePolicy.OFF:
            decision = GateDecision(gate=name, round=round,
                                    outcome=GateOutcome.APPROVE,
                                    decided_by="policy")
        elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            decision = auto_decision
        else:
            self._status = f"awaiting:{name}"
            try:
                await workflow.wait_condition(
                    lambda: key in self._gate_decisions,
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                decision = self._gate_decisions[key]
            except TimeoutError:
                decision = GateDecision(gate=name, round=round,
                                        outcome=GateOutcome.REJECT,
                                        decided_by="timeout")
            finally:
                self._status = "running"

        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=f"gate {name}#{round}: {decision.outcome.value}"
                f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "round": str(round),
                      "run_id": workflow.info().workflow_id})
        return decision

    async def _revisable_stage(self, name: str, cfg: PipelineConfig,
                               run_fn) -> tuple[object, GateDecision]:
        """Run a proposer stage, gate it, and on REVISE re-run with the
        human's guidance at round+1, up to cfg.max_gate_rounds. Past that,
        escalate to a HARD human gate (FR-301). `run_fn(guidance: str | None)`
        must re-execute the producer with the guidance injected."""
        guidance: str | None = None
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            decision = await self._gate(name, cfg, round=round)
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
        # Exhausted: one final HARD gate decides accept-anyway vs abandon.
        artifact = await run_fn(guidance)
        decision = await self._gate(name, cfg, round=cfg.max_gate_rounds + 1)
        return artifact, decision

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
        handle = await workflow.execute_activity(
            create_worktree,
            WorktreeInput(repo_path=repo_path, run_id=workflow.info().workflow_id,
                          task_id=task.id, from_ref=base_branch),
            **ACT,
        )
        worktree = handle.path
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
                **_long_act(role_cfg),
            )

            # Clean-context validation: contract + tests + diff. No narrative.
            qa_raw = await workflow.execute_activity(
                run_test_suite, QAInput(worktree=worktree),
                **_long_act(cfg.roles.get("test", role_cfg)))
            diff = await workflow.execute_activity(
                get_task_diff,
                DiffInput(worktree=worktree, branch_point=handle.branch_point),
                **ACT,
            )
            qa = (await t_qa.run(
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nTest results: {qa_raw.model_dump_json()}"
                + f"\nDiff stat:\n{diff['stat']}"
                + f"\nDiff:\n{diff['patch']}")).output

            await self._record(cfg, self._stage_record(
                cfg, stage="code", role=task.role,
                started=workflow.now(), ended=workflow.now(),
                quality_score=(1.0 if (qa.tests_passed and not qa.issues)
                               else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS
                         if (qa.tests_passed and not qa.issues)
                         else BenchmarkOutcome.FAIL),
                model=role_cfg.model or "zai-coding-plan/glm-5.2",
                harness=role_cfg.harness,
                cost_usd=run.cost_usd,
                fix_attempts=attempt - 1,
                task_id=task.id, attempt=attempt - 1))

            if qa.tests_passed and not qa.issues:
                handoff = HandoffSummary(
                    task_id=task.id,
                    what_changed=[task.title],
                    files_touched=diff["files"],
                    open_concerns=[],
                )
                return TaskResult(task_id=task.id, status="done",
                                  attempts=attempt, branch=handle.branch,
                                  run=run, handoff=handoff, qa=qa_raw)

            if attempt > cfg.max_fix_attempts:
                break

            issues = "\n- ".join(qa.issues or qa.failing_tests)
            await self._retain(
                cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                text=f"task {task.id} ({task.title}) attempt {attempt} failed: "
                    f"{issues}",
                metadata={"task_id": task.id,
                         "run_id": workflow.info().workflow_id})
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
            branch=handle.branch,
            qa=None,
            notes=decision.comments or "",
        )

    # ------------------------------ run ---------------------------------

    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                await workflow.execute_activity(
                    capture_watermark,
                    WatermarkInput(bank=cfg.memory.project_bank,
                                  backend=cfg.memory.backend,
                                  base_url=cfg.memory.base_url),
                    **MEM_ACT))
        repo_path = idea.repo_url or "/var/sdlc/repo"  # prepared by a setup activity IRL

        # 1. CLARIFY — open questions answered by human via signals
        self._status = "clarifying"
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"clarify:{idea.title}",
            filters={"stage": "clarify"})

        async def _run_clarify():
            return (await t_clarify.run(
                idea.model_dump_json()
                + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                   if snapshot.items else ""))).output

        reqs, _ = await self._cached_stage(
            cfg, "clarify", idea.model_dump_json(), MODEL,
            ClarifiedRequirements, _run_clarify)
        if reqs.open_questions:
            self._status = "awaiting:clarify"
            await workflow.wait_condition(
                lambda: all(q.id in self._question_answers
                            for q in reqs.open_questions),
                timeout=timedelta(hours=cfg.gate_timeout_hours),
            )
            for q in reqs.open_questions:
                q.answer = self._question_answers.get(q.id)
        _ended = workflow.now()
        _quality = await self._judge(cfg, reqs.model_dump_json(), "clarifier")
        await self._record(cfg, self._stage_record(
            cfg, stage="clarify", role="clarify",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=BenchmarkOutcome.PASS,
            model="anthropic:glm-5.2"))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"clarify: {reqs.summary}",
            metadata={"stage": "clarify", "run_id": workflow.info().workflow_id})

        # 2. ARCHITECT (+ human approval of the spec)
        self._status = "architecting"
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"architect:{idea.title}",
            filters={"stage": "architect"})

        async def _run_architect(guidance: str | None):
            prompt = (f"mode={idea.mode.value}\n{reqs.model_dump_json()}"
                      + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                         if snapshot.items else "")
                      + (f"\nRevision guidance from reviewer:\n{guidance}"
                         if guidance else ""))

            async def _produce():
                return (await t_architect.run(prompt)).output
            arch, _ = await self._cached_stage(
                cfg, "architect",
                reqs.model_dump_json() + (guidance or ""), MODEL,
                ArchitectureSpec, _produce)
            return arch

        arch, gate = await self._revisable_stage("architecture", cfg,
                                                 _run_architect)
        _ended = workflow.now()
        _quality = await self._judge(cfg, arch.model_dump_json(), "architect")
        await self._record(cfg, self._stage_record(
            cfg, stage="architecture", role="architect",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"architect: {arch.overview}",
            metadata={"stage": "architect", "run_id": workflow.info().workflow_id})
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"plan:{idea.title}",
            filters={"stage": "plan"})

        async def _run_plan(guidance: str | None):
            prompt = (arch.model_dump_json()
                      + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                         if snapshot.items else "")
                      + (f"\nRevision guidance from reviewer:\n{guidance}"
                         if guidance else ""))

            async def _produce():
                return (await t_planner.run(prompt)).output
            plan, _ = await self._cached_stage(
                cfg, "plan",
                arch.model_dump_json() + (guidance or ""), MODEL,
                ImplementationPlan, _produce)
            return plan

        plan, gate = await self._revisable_stage("plan", cfg, _run_plan)
        _ended = workflow.now()
        _quality = await self._judge(cfg, plan.model_dump_json(), "planner")
        await self._record(cfg, self._stage_record(
            cfg, stage="plan", role="planner",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"plan: {len(plan.tasks)} tasks",
            metadata={"stage": "plan", "run_id": workflow.info().workflow_id})
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

        # 5. MERGE — DeterministicQualityGate first (SC-5), then the human
        # gate (which doubles as the advisory-override mechanism), then
        # MergeVerdict advisory only under SOFT policy.
        _started = workflow.now()

        # 5a. Collect typed evidence from the run.
        integration_worktree = repo_path  # Task 3 will make this the integration wt
        lint_clean, lint_detail = await workflow.execute_activity(
            run_lint, LintInput(worktree=integration_worktree), **ACT)
        all_tests_green = all(
            r.qa.tests_passed for r in done.values() if r.qa is not None)

        checks = [
            build_check("build_integration_green", all_tests_green,
                        CheckClass.ABSOLUTE,
                        detail="aggregate of per-task pytest runs"),
            build_check("lint_clean", lint_clean, CheckClass.ABSOLUTE,
                        detail=lint_detail),
        ]
        gate_report: GateReport = await workflow.execute_activity(
            evaluate_gate, QualityGateInput(checks=checks), **ACT)

        # 5b. Absolute failure = terminal. No override path exists.
        absolute_blocking = [
            c.name for c in gate_report.checks
            if c.name in gate_report.blocking
            and c.classification is CheckClass.ABSOLUTE]
        if absolute_blocking:
            await self._retain(
                cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
                text=f"merge blocked (absolute): {absolute_blocking}",
                metadata={"gate": "merge", "run_id": workflow.info().workflow_id})
            return f"rejected:merge:absolute-gate-failed:{','.join(absolute_blocking)}"

        # 5c. Advisory failure: the human merge gate IS the override. A
        # human APPROVE records audited GateOverrides; REJECT terminates.
        overrides: list[GateOverride] = []
        if not gate_report.passed:
            advisory_blocking = [
                c.name for c in gate_report.checks
                if c.name in gate_report.blocking
                and c.classification is CheckClass.ADVISORY]
            gate = await self._gate("merge", cfg)
            if not gate.approved:
                return "rejected:merge:advisory"
            # Human waved the advisory checks through — record each waiver.
            reviewer = gate.reviewer or "human"
            reason = gate.comments or "advisory override"
            overrides = [
                GateOverride(check=n, approved_by=reviewer, reason=reason)
                for n in advisory_blocking]
            gate_report = await workflow.execute_activity(
                evaluate_gate,
                QualityGateInput(checks=checks, overrides=overrides), **ACT)
        else:
            # 5d. Gate passed clean. MergeVerdict is advisory and ONLY
            # consulted under SOFT policy — it can approve an already-clean
            # build; it can never reach this branch otherwise.
            if cfg.gates.get("merge", GatePolicy.HARD) == GatePolicy.SOFT:
                verdict: MergeVerdict = (await t_merge_verdict.run(
                    "Advisory only — the deterministic gate already passed. "
                    f"Task results: {[r.model_dump() for r in done.values()]}"
                )).output
                if not verdict.approve:
                    # Soft policy + negative verdict = escalate to human.
                    gate = await self._gate("merge", cfg)
                    if not gate.approved:
                        return "rejected:merge:soft-verdict"
            gate = GateDecision(gate="merge", outcome=GateOutcome.APPROVE,
                                decided_by="policy")

        _ended = workflow.now()
        await self._record(cfg, self._stage_record(
            cfg, stage="merge", role="reviewer",
            started=_started, ended=_ended,
            quality_score=(1.0 if gate_report.passed else 0.0),
            judge="deterministic_gate",
            outcome=BenchmarkOutcome.PASS,
            model="deterministic"))
        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=(f"merge gate: passed={gate_report.passed} "
                  f"overridden={[o.check for o in overrides]}"),
            metadata={"gate": "merge", "run_id": workflow.info().workflow_id})

        pr_url = await workflow.execute_activity(
            open_pull_request,
            PROpenInput(worktree=repo_path, title=idea.title,
                        body=arch.overview, base_branch=idea.base_branch),
            **ACT,
        )

        # 6. DEPLOY gate → deploy
        _started = workflow.now()
        gate = await self._gate("deploy", cfg)
        _ended = workflow.now()
        await self._record(cfg, self._stage_record(
            cfg, stage="deploy", role="devops",
            started=_started, ended=_ended,
            quality_score=None, judge="llm_judge",
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
        if not gate.approved:
            return f"merged-not-deployed:{pr_url}"
        await workflow.execute_activity(
            deploy,
            DeployInput(environment="staging", version=idea.title,
                        command="make deploy ENV=staging", cwd=repo_path),
            **_long_act(cfg.roles.get("devops")),
        )
        self._status = "deployed"
        return f"deployed:{pr_url}"
