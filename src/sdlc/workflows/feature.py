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
        CodingTaskInput, CoverageInput, DeployInput, DiffInput,
        IntegrationHandle, IntegrationInput, LintInput, MergeInput,
        PROpenInput, QAInput, SecurityScanInput, WorktreeInput,
        create_worktree, deploy, evaluate_gate, get_task_diff,
        measure_coverage, merge_into_integration, open_pull_request,
        run_coding_task, run_lint, run_test_suite, security_scan,
        setup_integration_branch,
    )
    from ..agents.roles import (
        PROMPT_SHAS, STAGE_MODELS, t_analyst, t_architect, t_clarify,
        t_merge_verdict, t_planner, t_qa, t_research, t_reviewer,
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
        AnalysisReport, ArchitectureSpec, ClarifiedRequirements,
        CoverageReport, DevTask, ExecutionMode, GateConfig, GateDecision,
        GateOutcome, GatePolicy, HandoffSummary, IdeaBrief,
        ImplementationPlan, MemoryKind, MergeVerdict, PipelineConfig,
        RecallSnapshot, ResearchBrief, RetainItem, RoleConfig,
        SecurityReport, TaskResult, gate_key,
    )
    from ..research.deps import ResearchDeps
    from ..research.retain import verified_findings_to_retain
    from ..research.verify import (
        GroundingViolation, brief_digest, verify_brief_activity,
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


def _merge_evidence_all_green(results: list) -> bool:
    """True only when every task has positive, passing QA evidence.

    SC-5: a done task with missing QA (e.g. an escalation-approved task
    whose fix loop exhausted) is treated as FAILURE — never a vacuous
    `all([])` pass. The merge absolute check must see real green evidence."""
    return bool(results) and all(
        r.qa is not None and r.qa.tests_passed for r in results)


def untraced_criteria(authoritative: list[tuple[str, str]],
                      report: AnalysisReport) -> list[str]:
    """FR-106 enforcement (workflow-side, NOT the LLM's verdict).

    A criterion is traced iff the Analyst's report contains a CriterionTrace
    for that exact (task_id, criterion) with a non-empty `tests` list. Any
    authoritative criterion the report omits OR maps to zero tests is untraced.
    Enforced against the plan's authoritative set so an Analyst cannot hide a
    gap by forgetting to list a criterion. Returns "task_id: criterion" labels
    in authoritative order."""
    traced = {(t.task_id, t.criterion)
              for t in report.traceability if t.tests}
    return [f"{task_id}: {criterion}"
            for (task_id, criterion) in authoritative
            if (task_id, criterion) not in traced]


# Fallbacks only for contracts predating test_commands/lint_commands
# (legacy cached artifacts) — every fresh plan populates both per-stack.
DEFAULT_TEST_CMD = "pytest -q --maxfail=25"
DEFAULT_LINT_CMD = "ruff check ."


def _contract_stack_directive(contract) -> str:
    """Surface the frozen stack as a standalone, non-negotiable line —
    not just one bullet among the assertions. A coding agent on a
    greenfield (empty) worktree has no existing scaffolding to anchor
    it to the required language/runtime, so the constraint needs to be
    unmissable rather than buried in prose."""
    if not contract or not contract.stack:
        return ""
    return (f"MANDATORY STACK (do not deviate, even when revising): "
            f"{contract.stack}\n")


def _contract_shell_cmd(commands: list[str] | None, default: str) -> str:
    """Join a contract's stack-specific test/lint commands into one shell
    command (`&&`-chained so an earlier failure short-circuits the rest).
    Falls back to `default` (a Python toolchain command) only when the
    contract carries none — e.g. a legacy/cached artifact predating this
    field, never as a silent stack-mismatch."""
    if not commands:
        return default
    return " && ".join(commands)


def _should_resume_session(qa, resumes: int, max_resumes: int,
                           near_ceiling: bool) -> bool:
    """FR-802 resume budget, with a stack-mismatch override: a session
    that already committed to the wrong language/runtime is a worse
    starting point than a fresh one — the agent is anchored to files it
    would need to delete wholesale. Never resume it, regardless of
    remaining resume budget or context headroom."""
    if qa.stack_mismatch:
        return False
    return resumes < max_resumes and not near_ceiling


def _auto_decision_for(name: str, cfg: PipelineConfig,
                       confidence: float | None) -> GateDecision | None:
    """FR-301: SOFT + confidence >= threshold -> an APPROVE decision _gate()
    can short-circuit on. None confidence (missing/legacy artifact) or below
    threshold -> None, falling through to the human wait -- never a silent
    auto-approve on absent data (same defensive stance as
    HarnessRunResult.near_context_ceiling())."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    return GateDecision(
        gate=name, round=1, outcome=GateOutcome.APPROVE, decided_by="policy",
        comments=f"auto-approved: confidence={confidence:.2f} "
                f">= threshold={gate_cfg.threshold:.2f}")


@workflow.defn
class FeatureWorkflow:
    def __init__(self) -> None:
        self._gate_decisions: dict[str, GateDecision] = {}
        self._question_answers: dict[str, str] = {}
        self._status: str = "starting"
        self._memory_watermark: str | None = None
        # ADR-14: one sdlc/<run_id>/integration branch accumulates completed
        # task work. _integration_head advances after each successful merge;
        # _integration_wt is the worktree path (set once at run start, stable).
        self._integration_head: str | None = None
        self._integration_wt: str | None = None

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
                     stage: str, author_model: str) -> QualityScore:
        """Judge a proposer-stage artifact iff benchmarking is on AND a
        rubric is registered for the stage.

        Returns a graceful QualityScore(score=None, judge='llm_judge') when
        judging is skipped — when not benchmarking, or no rubric exists for
        the stage — so the record still emits without failing the stage.
        The LLM call lives in the judge_artifact activity, never in workflow
        code.

        ``stage`` is the rubric-map key carried on cfg.benchmark.rubrics
        (e.g. 'clarifier', 'architect'), NOT the record's stage field.

        Author model: passed in by the caller, which knows both this rubric key
        and the stage name STAGE_MODELS is keyed by. The judge_model (e.g.
        'openai/gpt-5.2') differs from the author → ADR-6 cross-family satisfied.
        """
        fallback = QualityScore(score=None, judge="llm_judge")
        if not self._benchmarking(cfg):
            return fallback
        judge_input: JudgeInput | None = _build_judge_input(
            artifact_json=artifact_json,
            rubrics=cfg.benchmark.rubrics,
            stage=stage,
            author_model=author_model,
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
                            input_json: str,
                            output_type: type, run_fn) -> tuple[object, bool]:
        """Skips `run_fn()` (a no-arg async callable invoking the proposer
        agent) when an identical (stage, input, prompt, model,
        upstream-recall-watermark) combination was already computed — the
        ADR-5 dev-loop cache. Returns (output, was_cache_hit).

        The stage's model is resolved here from STAGE_MODELS rather than passed
        in: it MUST be the model that role actually binds, or a role's model
        change would leave the key unmoved and serve a result computed by the
        previous model."""
        if not cfg.memoization_enabled:
            return await run_fn(), False
        key = content_key(stage, input_json, PROMPT_SHAS[stage],
                          STAGE_MODELS[stage],
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
        policy = cfg.gates.get(
            name, GateConfig(policy=cfg.default_gate_policy)).policy
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
        escalate to a final human gate (the configured policy still applies,
        but no auto_decision is passed, so SOFT also waits) (FR-301).
        `run_fn(guidance: str | None)` must re-execute the producer with the
        guidance injected."""
        guidance: str | None = None
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            auto = _auto_decision_for(
                name, cfg, getattr(artifact, "confidence", None))
            decision = await self._gate(name, cfg, auto_decision=auto,
                                        round=round)
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
        # Exhausted: one final HARD gate decides accept-anyway vs abandon.
        artifact = await run_fn(guidance)
        decision = await self._gate(name, cfg, round=cfg.max_gate_rounds + 1)
        return artifact, decision

    async def _merge_task(self, tr: TaskResult,
                          repo_path: str) -> str | None:
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
            MergeInput(repo_path=repo_path,
                       run_id=workflow.info().workflow_id,
                       task_branch=tr.branch,
                       integration_path=self._integration_wt),
            **ACT,
        )
        if merge_res.conflict:
            # Falsified `overlaps` declaration → terminal status, not a raise.
            return f"failed:integration-conflict:{tr.task_id}"
        self._integration_head = merge_res.integration_head
        return None

    async def _dev_task(self, task: DevTask, repo_path: str,
                        from_ref: str, cfg: PipelineConfig,
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
                          task_id=task.id, from_ref=from_ref),
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
        stack_directive = _contract_stack_directive(contract)
        prompt = (
            f"Task: {task.title}\n{task.description}\n"
            + stack_directive
            + "Your work will be validated against this frozen contract:\n- "
            + "\n- ".join(assertions)
            + ("\nHandoffs from preceding tasks:\n" + "\n".join(handoff_notes)
               if handoff_notes else "")
            + "\nWork only in this worktree. Run the tests before finishing."
            + "\nThis worktree is already a git repository (checked out on its"
            " own branch) even if the task looks like a fresh/greenfield"
            " project — do NOT run `git init`, and do NOT delete or modify"
            " the `.git` file/directory."
        )

        session_id: str | None = None
        resumes = 0
        run = None
        for attempt in range(1, cfg.max_fix_attempts + 2):
            _attempt_started = workflow.now()
            run = await workflow.execute_activity(
                run_coding_task,
                CodingTaskInput(harness=role_cfg.harness, prompt=prompt,
                                worktree=worktree, model=role_cfg.model,
                                session_id=session_id),
                **_long_act(role_cfg),
            )

            # Clean-context validation: contract + tests + diff. No narrative.
            # Uses the contract's own stack-specific test_commands (FR-803)
            # rather than QAInput's Python-toolchain default — a non-Python
            # stack must never be QA'd with pytest.
            test_cmd = _contract_shell_cmd(
                contract.test_commands if contract else None,
                DEFAULT_TEST_CMD)
            qa_raw = await workflow.execute_activity(
                run_test_suite, QAInput(worktree=worktree, test_cmd=test_cmd),
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

            # Second clean-context judge (FR-204): same inputs as QA — frozen
            # contract + materialized diff + test output. No narrative, no
            # session. A different model family than the developer (ADR-6).
            review = None
            if cfg.review_enabled:
                review = (await t_reviewer.run(
                    "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                    + f"\nTest results: {qa_raw.model_dump_json()}"
                    + f"\nDiff:\n{diff['patch']}")).output

            await self._record(cfg, self._stage_record(
                cfg, stage="code", role=task.role,
                started=_attempt_started, ended=workflow.now(),
                quality_score=(1.0 if (qa.tests_passed and not qa.issues)
                               else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS
                         if (qa.tests_passed and not qa.issues)
                         else BenchmarkOutcome.FAIL),
                model=role_cfg.model,
                harness=role_cfg.harness,
                cost_usd=run.cost_usd,
                fix_attempts=attempt - 1,
                task_id=task.id, attempt=attempt - 1))

            review_ok = review is None or review.approve
            if qa.tests_passed and not qa.issues and review_ok:
                handoff = HandoffSummary(
                    task_id=task.id,
                    what_changed=[task.title],
                    files_touched=diff["files"],
                    open_concerns=[],
                )
                return TaskResult(task_id=task.id, status="done",
                                  attempts=attempt, branch=handle.branch,
                                  run=run, handoff=handoff, qa=qa_raw,
                                  review=review)

            if attempt > cfg.max_fix_attempts:
                break

            review_issues = (
                [f"{f.severity}: {f.assertion} — {f.detail}"
                 for f in review.blocking_findings] if review else [])
            issues = "\n- ".join(
                list(qa.issues or qa.failing_tests) + review_issues)
            await self._retain(
                cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                text=f"task {task.id} ({task.title}) attempt {attempt} failed: "
                    f"{issues}",
                metadata={"task_id": task.id,
                         "run_id": workflow.info().workflow_id})
            if _should_resume_session(qa, resumes, cfg.max_session_resumes,
                                      run.near_context_ceiling()):
                session_id = run.session_id       # resume: context intact
                resumes += 1
                prompt = (stack_directive
                          + f"Previous attempt has issues. Fix them:\n- {issues}")
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
                    if qa.stack_mismatch else
                    "A previous session implemented part of this in the same "
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

        # Escalate: human decides whether to accept, retry, or quarantine.
        decision = await self._gate(f"task:{task.id}", cfg)
        return TaskResult(
            task_id=task.id,
            status="done" if decision.approved else "quarantined",
            attempts=cfg.max_fix_attempts + 1,
            branch=handle.branch,
            qa=qa_raw,
            review=review,
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

        # ADR-14: one sdlc/<run_id>/integration branch accumulates completed
        # task work; dependent tasks branch from its head. The activity hands
        # back both the head SHA and the worktree path — the workflow never
        # computes the path itself (that would read SDLC_WORKTREES_ROOT from
        # the env, a determinism violation).
        integration: IntegrationHandle = await workflow.execute_activity(
            setup_integration_branch,
            IntegrationInput(repo_path=repo_path,
                             run_id=workflow.info().workflow_id,
                             base_branch=idea.base_branch),
            **ACT,
        )
        self._integration_head = integration.head_sha
        self._integration_wt = integration.worktree_path

        # 0. RESEARCH (FR-107) — optional, human-gated, NOT memoized. A served
        # memo means pages were not fetched this run, so a brief cannot be
        # cached (spec finding 4). The brief contributes only its canonical
        # digest to downstream keys (finding 3), never its prose.
        brief_digest_val = ""
        if cfg.research_enabled and t_research is not None:
            self._status = "researching"
            _r_started = workflow.now()
            deps = ResearchDeps(
                run_id=workflow.info().workflow_id,
                provider=cfg.roles.get("research").provider
                    if cfg.roles.get("research") else "fake",
                max_searches=cfg.research.max_searches,
                max_fetches=cfg.research.max_fetches,
                max_cost_usd=cfg.research.max_cost_usd,
                memory_backend=cfg.memory.backend,
                memory_base_url=cfg.memory.base_url,
                memory_bank=cfg.memory.project_bank,
                memory_watermark=self._memory_watermark)
            # NOTE (accepted loss, 2026-07-17 human decision): the budget
            # counter on deps.budget accumulates correctly for direct/test
            # invocation, but under TemporalAgent each tool activity receives
            # a fresh deserialized copy, so charge() never raises mid-run.
            # Per-run budget enforcement is effectively absent under
            # temporalization; restoring it needs a disk-persisted counter
            # (deferred — not this task).
            brief: ResearchBrief = (await t_research.run(
                idea.model_dump_json(), deps=deps)).output
            # Task 7 fallback (Task 1 finding A): the original
            # @agent.output_validator was silently dropped by TemporalAgent, so
            # grounding is enforced here as a post-run ACTIVITY. Reads page
            # files (I/O) — must run via execute_activity, not inline, or
            # test_factory_purity.py fires. Raises GroundingViolation if any
            # grounded quote is not a substring of a page fetched this run;
            # the stage fails closed (no ModelRetry, no retry).
            try:
                await workflow.execute_activity(
                    verify_brief_activity,
                    args=[brief, workflow.info().workflow_id],
                    start_to_close_timeout=timedelta(minutes=1))
            except GroundingViolation:
                self._status = "rejected:research.grounding"
                return "rejected:research.grounding"
            brief_digest_val = brief_digest(brief)
            gate = await self._gate("research", cfg)
            if not gate.approved:
                return "rejected:research"
            for item in verified_findings_to_retain(
                    brief, workflow.info().workflow_id,
                    bank=cfg.memory.project_bank):
                await self._retain(cfg, item.kind, item.bank, item.text,
                                   item.metadata)
            await self._record(cfg, self._stage_record(
                cfg, stage="research", role="research",
                started=_r_started, ended=workflow.now(),
                quality_score=None, judge="contract",
                outcome=BenchmarkOutcome.PASS,
                model=STAGE_MODELS.get("research", "unknown")))

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
            cfg, "clarify", idea.model_dump_json() + brief_digest_val,
            ClarifiedRequirements, _run_clarify)
        if reqs.open_questions:
            clarify_policy = cfg.gates.get("clarify", GateConfig()).policy
            if clarify_policy == GatePolicy.OFF:
                # unattended run (e.g. a benchmark cell) — no human is
                # present to answer; fall back to the clarifier's own
                # suggested_answer rather than blocking forever.
                for q in reqs.open_questions:
                    q.answer = q.suggested_answer
            else:
                self._status = "awaiting:clarify"
                await workflow.wait_condition(
                    lambda: all(q.id in self._question_answers
                                for q in reqs.open_questions),
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                for q in reqs.open_questions:
                    q.answer = self._question_answers.get(q.id)
        _ended = workflow.now()
        _quality = await self._judge(cfg, reqs.model_dump_json(), "clarifier",
                                     author_model=STAGE_MODELS["clarify"])
        await self._record(cfg, self._stage_record(
            cfg, stage="clarify", role="clarify",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=BenchmarkOutcome.PASS,
            model=STAGE_MODELS["clarify"]))
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
                reqs.model_dump_json() + (guidance or ""),
                ArchitectureSpec, _produce)
            return arch

        arch, gate = await self._revisable_stage("architecture", cfg,
                                                 _run_architect)
        _ended = workflow.now()
        _quality = await self._judge(cfg, arch.model_dump_json(), "architect",
                                     author_model=STAGE_MODELS["architect"])
        await self._record(cfg, self._stage_record(
            cfg, stage="architecture", role="architect",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model=STAGE_MODELS["architect"]))
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
                arch.model_dump_json() + (guidance or ""),
                ImplementationPlan, _produce)
            return plan

        plan, gate = await self._revisable_stage("plan", cfg, _run_plan)
        _ended = workflow.now()
        _quality = await self._judge(cfg, plan.model_dump_json(), "planner",
                                     author_model=STAGE_MODELS["plan"])
        await self._record(cfg, self._stage_record(
            cfg, stage="plan", role="planner",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model=STAGE_MODELS["plan"]))
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

        async def run_one(t: DevTask) -> TaskResult:
            """Execute the task only. Merging is a separate concern — see
            _merge_task (Resolution B: merging inside run_one would race
            the integration worktree under wave mode's asyncio.gather)."""
            r = await self._dev_task(t, repo_path, self._integration_head,
                                     cfg, handoffs)
            done[r.task_id] = r
            if r.handoff:
                handoffs.append(r.handoff)
            remaining.pop(r.task_id)
            return r

        while remaining:
            ready = [t for t in remaining.values()
                     if all(d in done for d in t.depends_on)]
            if not ready:
                return "failed:dependency-cycle"

            if cfg.execution_mode == ExecutionMode.SERIAL:
                # SERIAL: execute + merge sequentially so the next task
                # branches from the updated integration head.
                tr = await run_one(ready[0])
                if tr.status == "done":
                    conflict = await self._merge_task(tr, repo_path)
                    if conflict:
                        return conflict
            else:
                # Wave mode: execute the batch in parallel (preserving the
                # gather), THEN merge results sequentially so integration
                # updates are ordered — two tasks racing the integration
                # worktree would corrupt the merge (Resolution B).
                batch, seen = [], set()
                for t in ready:
                    if seen.isdisjoint(t.overlaps):
                        batch.append(t)
                        seen.update(t.overlaps)
                results = await asyncio.gather(*[run_one(t) for t in batch])
                for tr in results:
                    if tr.status == "done":
                        conflict = await self._merge_task(tr, repo_path)
                        if conflict:
                            return conflict

            if any(r.status == "quarantined" for r in done.values()):
                return "failed:quarantined-tasks"

        # 4b. ANALYZE (stage 9) — clean-context Analyst proposes the
        # criterion->test mapping; the workflow enforces it (FR-106). Runs on
        # the integrated whole, before the merge gate.
        self._status = "analyzing"
        _an_started = workflow.now()
        integration_diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=self._integration_wt,
                      branch_point=idea.base_branch),
            **ACT)
        authoritative: list[tuple[str, str]] = [
            (t.id, c) for t in plan.tasks for c in t.acceptance_criteria]
        _criteria_lines = "\n".join(f"- [{tid}] {crit}"
                                    for tid, crit in authoritative)
        _qa_lines = "\n".join(
            f"- {r.task_id}: tests_passed={r.qa.tests_passed if r.qa else 'n/a'}"
            f" failing={r.qa.failing_tests if r.qa else []}"
            for r in done.values())
        analysis: AnalysisReport = (await t_analyst.run(
            "Acceptance criteria (task_id in brackets):\n" + _criteria_lines
            + "\nAggregate test output:\n" + _qa_lines
            + f"\nIntegration diff stat:\n{integration_diff['stat']}"
            + f"\nIntegration diff:\n{integration_diff['patch']}")).output
        untraced = untraced_criteria(authoritative, analysis)
        cov: CoverageReport = await workflow.execute_activity(
            measure_coverage,
            CoverageInput(worktree=self._integration_wt,
                          changed_files=integration_diff["files"]),
            **ACT)
        await self._record(cfg, self._stage_record(
            cfg, stage="analyze", role="analyst",
            started=_an_started, ended=workflow.now(),
            quality_score=(1.0 if not untraced else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.PASS if not untraced
                     else BenchmarkOutcome.FAIL),
            model=STAGE_MODELS["analyze"]))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"analyze: {len(authoritative)} criteria, "
                 f"{len(untraced)} untraced. {analysis.summary}",
            metadata={"stage": "analyze",
                      "run_id": workflow.info().workflow_id})
        if untraced:
            await self._retain(
                cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                text=f"untraced acceptance criteria at merge: {untraced}",
                metadata={"stage": "analyze",
                          "run_id": workflow.info().workflow_id})

        # 5. MERGE — DeterministicQualityGate first (SC-5), then the human
        # gate (which doubles as the advisory-override mechanism), then
        # MergeVerdict advisory only under SOFT policy.
        _started = workflow.now()

        # 5a. Collect typed evidence from the run. The merge stage runs
        # against the integration worktree (ADR-14), where every completed
        # task's merge has accumulated.
        integration_worktree = self._integration_wt
        # Same stack-awareness as the per-task QA command: use the plan's
        # own lint_commands rather than assuming a Python toolchain against
        # whatever stack the architecture actually chose.
        lint_commands = next(
            (t.contract.lint_commands for t in plan.tasks
             if t.contract and t.contract.lint_commands), None)
        lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
        lint_clean, lint_detail = await workflow.execute_activity(
            run_lint, LintInput(worktree=integration_worktree,
                                lint_cmd=lint_cmd), **ACT)
        security: SecurityReport = await workflow.execute_activity(
            security_scan,
            SecurityScanInput(worktree=integration_worktree), **ACT)
        all_tests_green = _merge_evidence_all_green(list(done.values()))

        checks = [
            build_check("build_integration_green", all_tests_green,
                        CheckClass.ABSOLUTE,
                        detail="aggregate of per-task pytest runs"),
            build_check("lint_clean", lint_clean, CheckClass.ABSOLUTE,
                        detail=lint_detail),
            build_check(
                "security_no_critical", security.critical == 0,
                CheckClass.ABSOLUTE,
                detail=f"{security.critical} critical finding(s)"),
            build_check(
                "review_severity",
                all(r.review is None or r.review.approve
                    for r in done.values()),
                CheckClass.ADVISORY,
                detail="clean-context reviewer blocking findings (FR-204)"),
            build_check(
                "traceability", not untraced, CheckClass.ADVISORY,
                detail=(f"{len(untraced)} criterion(s) without a test: "
                        f"{untraced[:10]}" if untraced
                        else "every acceptance criterion traces to >=1 test")),
            build_check(
                "coverage",
                (True if not cov.measured
                 else (cov.diff_pct or 0.0) >= cfg.coverage_threshold),
                CheckClass.ADVISORY,
                detail=(cov.detail if not cov.measured
                        else f"diff coverage {cov.diff_pct:.1f}% vs threshold "
                             f"{cfg.coverage_threshold:.1f}%")),
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
                metadata={"gate": "merge", "round": "1",
                          "run_id": workflow.info().workflow_id})
            await self._record(cfg, self._stage_record(
                cfg, stage="merge", role="reviewer",
                started=_started, ended=workflow.now(),
                quality_score=0.0,
                judge="contract",
                outcome=BenchmarkOutcome.FAIL,
                model="deterministic"))
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
            if cfg.gates.get("merge", GateConfig()).policy == GatePolicy.SOFT:
                verdict: MergeVerdict = (await t_merge_verdict.run(
                    "Advisory only — the deterministic gate already passed. "
                    f"Task results: {[r.model_dump() for r in done.values()]}"
                )).output
                auto = _auto_decision_for(
                    "merge", cfg,
                    verdict.confidence if verdict.approve else None)
                if auto is None:
                    # Soft policy + (negative verdict OR confidence below
                    # threshold) = escalate to human.
                    gate = await self._gate("merge", cfg)
                    if not gate.approved:
                        return "rejected:merge:soft-verdict"

        _ended = workflow.now()
        await self._record(cfg, self._stage_record(
            cfg, stage="merge", role="reviewer",
            started=_started, ended=_ended,
            quality_score=(1.0 if gate_report.passed else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.REVISED if overrides
                     else BenchmarkOutcome.PASS),
            model="deterministic"))
        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=(f"merge gate: passed={gate_report.passed} "
                  f"overridden={[o.check for o in overrides]}"),
            metadata={"gate": "merge", "round": "1",
                      "run_id": workflow.info().workflow_id})

        pr_url = await workflow.execute_activity(
            open_pull_request,
            PROpenInput(worktree=self._integration_wt, title=idea.title,
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
            model=STAGE_MODELS["devops"]))
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
