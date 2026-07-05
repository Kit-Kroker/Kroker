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
        CodingTaskInput, DeployInput, DiffInput, PROpenInput, QAInput,
        WorktreeInput, create_worktree, deploy, get_task_diff,
        open_pull_request, run_coding_task, run_test_suite,
    )
    from ..agents.roles import (
        MODEL, t_architect, t_clarify, t_merge_verdict, t_planner, t_qa,
    )
    from ..benchmarks.judge import (
        JudgeInput, _build_judge_input, judge_artifact,
    )
    from ..benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CostBag,
        QualityScore, SpeedBag,
    )
    from ..benchmarks.recorder import record_benchmark
    from ..memory.activities import (
        RecallInput, RetainInput, WatermarkInput, capture_watermark,
        recall_snapshot, retain,
    )
    from ..models import (
        DevTask, ExecutionMode, GateDecision, GateOutcome, GatePolicy,
        HandoffSummary, IdeaBrief, MemoryKind, MergeVerdict, PipelineConfig,
        RecallSnapshot, RetainItem, RoleConfig, TaskResult,
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
            return GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="policy")

        if policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            return auto_decision  # quality-gate agent said yes → no human

        self._status = f"awaiting:{name}"
        try:
            await workflow.wait_condition(
                lambda: name in self._gate_decisions,
                timeout=timedelta(hours=cfg.gate_timeout_hours),
            )
        except TimeoutError:
            return GateDecision(gate=name, outcome=GateOutcome.REJECT,
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
            branch=handle.branch,
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
        _ended = workflow.now()
        _quality = await self._judge(cfg, reqs.model_dump_json(), "clarifier")
        await self._record(cfg, self._stage_record(
            cfg, stage="clarify", role="clarify",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=BenchmarkOutcome.PASS,
            model="anthropic:glm-5.2"))

        # 2. ARCHITECT (+ human approval of the spec)
        self._status = "architecting"
        _started = workflow.now()
        arch = (await t_architect.run(
            f"mode={idea.mode.value}\n{reqs.model_dump_json()}")).output
        gate = await self._gate("architecture", cfg)
        _ended = workflow.now()
        _quality = await self._judge(cfg, arch.model_dump_json(), "architect")
        await self._record(cfg, self._stage_record(
            cfg, stage="architecture", role="architect",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        _started = workflow.now()
        plan = (await t_planner.run(arch.model_dump_json())).output
        gate = await self._gate("plan", cfg)
        _ended = workflow.now()
        _quality = await self._judge(cfg, plan.model_dump_json(), "planner")
        await self._record(cfg, self._stage_record(
            cfg, stage="plan", role="planner",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
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

        # 5. MERGE gate — advisory MergeVerdict only informs the SOFT path.
        # (Plan 2 runs the DeterministicQualityGate before this consult.)
        _started = workflow.now()
        verdict: MergeVerdict = (await t_merge_verdict.run(
            "Advisory only. Given these task results, should the merge "
            f"proceed? Task results: {[r.model_dump() for r in done.values()]}"
        )).output
        auto = GateDecision(
            gate="merge", outcome=(GateOutcome.APPROVE if verdict.approve
                                   else GateOutcome.REJECT),
            decided_by="policy", comments=verdict.rationale)
        gate = await self._gate("merge", cfg, auto_decision=auto)
        _ended = workflow.now()
        _quality = await self._judge(cfg, auto.model_dump_json(), "merge")
        await self._record(cfg, self._stage_record(
            cfg, stage="merge", role="reviewer",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model="anthropic:glm-5.2"))
        if not gate.approved:
            return "rejected:merge"

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
