"""FeatureWorkflow — idea → deployed feature.

Deterministic orchestration only. All I/O happens in activities or inside
TemporalAgent-managed activities. Human-in-the-loop gates are durable
signal waits with a per-gate policy (hard / soft / off).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import (
        STAGE_MODELS,
        resolve_role_model,
        t_adversary,
        t_analyst,
        t_architect,
        t_clarify,
        t_clarify_probe,
        t_clarify_route,
        t_deep_review,
        t_handoff,
        t_merge_verdict,
        t_planner,
        t_research,
    )
    from ..artifacts.read import LoadSessionInput, load_session
    from ..benchmarks.models import BenchmarkOutcome
    from ..board.models import TaskStatus
    from ..context.models import CodebaseMap
    from ..context.project import map_digest, project
    from ..context.render import render_for_prompt
    from ..core.context import StageContext, StageServices
    from ..core.models import (
        ExecutionMode,
        GateConfig,
        GateDecision,
        GateOutcome,
        GatePolicy,
        IdeaBrief,
        PipelineConfig,
        ProjectMode,
        ResearchConfig,
        RoleUsage,
        RunState,
        RunSummary,
    )
    from ..gate import (
        CheckClass,
        CheckResult,
        GateOverride,
        GateReport,
        QualityGateInput,
        build_check,
    )
    from ..handoff import (
        claim_survival_score,
        cross_check_claims,
        verified_integrity_flags,
        verified_plan_deviations,
    )
    from ..harness.session import session_text_from_jsonl
    from ..measurement import CollectionState
    from ..memory.activities import WatermarkInput, capture_watermark
    from ..memory.models import MemoryKind
    from ..notify.contract import NotifyReason
    from ..observability.summary import build_run_summary
    from ..observability.trace import RunEventKind
    from ..pending import GateContext
    from ..pricing import PriceUsageInput, price_usage
    from ..prompts import analyst_prompt, merge_verdict_prompt, planner_prompt
    from ..research.deps import ResearchDeps
    from ..research.retain import verified_findings_to_retain
    from ..research.stage import (
        PlanInput,
        SubQuestionInput,
        SynthesizeInput,
        plan_research,
        research_subquestion,
        synthesize_brief,
    )
    from ..research.verify import brief_digest, verify_brief_activity
    from ..stages import clarify, intake, retro
    from ..stages.analyze.models import AnalysisReport
    from ..stages.architecture.models import ArchitectureSpec
    from ..stages.clarify.models import ClarifiedRequirements
    from ..stages.code.models import HandoffSummary
    from ..stages.context.activities import (
        DeltaCheckInput,
        check_brownfield_delta,
    )
    from ..stages.deploy.models import DeployPlan, DeployReport, SmokeCheck
    from ..stages.merge.activities import (
        CoverageInput,
        IntegrationChecks,
        IntegrationChecksInput,
        PROpenInput,
        evaluate_gate,
        measure_coverage,
        open_pull_request,
        run_integration_checks,
    )
    from ..stages.merge.models import CoverageReport, MergeVerdict
    from ..stages.plan.models import DevTask, ImplementationPlan
    from ..stages.qa.activities import LintInput, SecurityScanInput, run_lint, security_scan
    from ..stages.qa.models import SecurityReport
    from ..stages.research.models import (
        Gap,
        ResearchBrief,
        ResearchPlan,
        SubQuestion,
        SubQuestionFinding,
    )
    from ..stages.review.models import DeepReviewReport, ReviewReport
    from ..vcs import (
        DiffInput,
        IntegrationHandle,
        IntegrationInput,
        get_task_diff,
        setup_integration_branch,
    )
    from .benchmark_host import BenchmarkHost
    from .board_host import BoardHost
    from .deployment import DeploymentInput, DeploymentWorkflow
    from .gates import GateHost
    from .memory_host import MEM_ACT, MemoryHost
    from .models import SeededWork, TaskResult
    from .question_host import QuestionHost
    from .report_host import ReportHost
    from .role_host import (
        PRICE_ACT,
        RoleHost,
        _auto_decision_for,
        _BudgetRejected,
    )
    from .scanning import scan_tree
    from .task_host import TaskHost, _contract_shell_cmd

INTAKE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)
ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)
# Deterministic substring check -- retrying cannot change outcome (Code-review C2).
VERIFY_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy=RetryPolicy(maximum_attempts=1),
)


# E-30: run_integration_checks runs a real test suite + lint against the
# merged integration head. Generous start_to_close (> the activity's
# internal test 600s + fallback 600s + lint 300s worst case); 2 attempts like
# the per-task test run. It does not heartbeat, so no heartbeat_timeout.
INTEG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=30), retry_policy=RetryPolicy(maximum_attempts=2)
)

# Fan-out research. Durations follow the shape measured by the prior art:
# planning is short and schema-constrained; a sub-question runs a full agent
# with search and page fetches and legitimately takes minutes.
RESEARCH_PLAN_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5), retry_policy=RetryPolicy(maximum_attempts=3)
)
# The heartbeat is the important knob. A sub-question can run for many
# minutes, so without heartbeating the server waits out the full
# start_to_close before rescheduling a lost worker; with it, ~60s.
# Invariant: stage.HEARTBEAT_INTERVAL_SECONDS < heartbeat_timeout <
# start_to_close_timeout.
RESEARCH_SQ_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=20),
    heartbeat_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=60),
        maximum_attempts=6,
        # The budget counter is PERSISTED to disk, so a retry meets the same
        # exhausted cap: six guaranteed failures with backoff. The activity
        # already degrades these internally; this is the belt-and-braces for
        # any path that lets one escape.
        non_retryable_error_types=["BudgetExceeded", "UsageLimitExceeded"],
    ),
)
RESEARCH_SYNTH_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


def _requirements_for_downstream(reqs: ClarifiedRequirements) -> str:
    """The clarify artifact as every DOWNSTREAM role sees it.

    E-85's scope guard is "no change to downstream roles" (spec §2), and two
    of `ClarifiedRequirements`' E-85 fields are measurement rather than
    requirement:

      - `dropped` is the record of what the cap CUT, carrying each lost
        question's `why_it_matters`, `suggested_answer` and `evidence`.
        Feeding it to the architect would hand the architect the UNCAPPED
        set and undo the very protection §9's cap exists to provide -- and
        it is unbounded, since merge keeps every candidate past the cap.
      - `dimensions_probed` is stage telemetry: which probes ran. It says
        nothing about the requirement.

    Both stay on the persisted and emitted artifact -- they are the
    benchmark's measurement record (§5, §10) and must survive. They simply
    never reach a downstream prompt or a downstream memo key.

    Excluding them also restores byte-identity for the flag-off path: before
    E-85 neither field existed, so neither appeared in the architect's
    prompt or its cache key.
    """
    return reqs.model_dump_json(exclude={"dropped", "dimensions_probed"})


def _deploy_result(report: DeployReport, decision: GateDecision | None, pr_url: str) -> str:
    """Map a DeployReport plus the deploy_failed gate decision onto the run's
    terminal string. Pure, so the mapping is testable without Temporal.

    `decision` is None only when the report says deployed.

    A report whose rollback did NOT happen can never return `rolled-back:` --
    the environment is live and in an unknown state, and flattening that into
    an ordinary failure hides the one outcome needing a human immediately.
    """
    if report.deployed:
        return f"deployed:{pr_url}"
    if not report.rolled_back:
        return f"deploy-broken:{pr_url}"
    if decision is not None and decision.outcome is GateOutcome.REJECT:
        return f"deploy-rejected:{pr_url}"
    return f"rolled-back:{pr_url}"


def _deploy_verdict(report: DeployReport) -> str:
    """What the deploy_failed gate renders. The rollback reason plus, when
    available, the deploy command's own output -- without it the human
    deciding what to do next never sees what the apply actually produced
    (F4: the common smoke-fails case)."""
    if report.apply_detail.strip():
        return f"{report.rollback_reason}\n\nDeploy output:\n{report.apply_detail}"
    return report.rollback_reason


def _sanitize_tag(raw: str) -> str:
    """Turn an arbitrary workflow id into a valid image tag.

    The version becomes IMAGE_TAG for the compose adapter, and a benchmark
    child id is `f"{bench_run_id}/{cell.cell_id}"` -- the '/' (and any other
    char outside [A-Za-z0-9_.-]) is not legal in a docker tag. Replace invalid
    chars with '-', and never let the result start with '.' or '-'.
    """
    import re

    tag = re.sub(r"[^A-Za-z0-9_.-]", "-", raw)[:128]
    tag = re.sub(r"^[.-]+", "", tag) or "run"
    return tag


def _merge_evidence_all_green(results: list) -> bool:
    """True only when every task has positive, passing QA evidence.

    SC-5: a done task with missing QA (e.g. an escalation-approved task
    whose fix loop exhausted) is treated as FAILURE — never a vacuous
    `all([])` pass. The merge absolute check must see real green evidence."""
    return bool(results) and all(r.qa is not None and r.qa.tests_passed for r in results)


def untraced_criteria(authoritative: list[tuple[str, str]], report: AnalysisReport) -> list[str]:
    """FR-106 enforcement (workflow-side, NOT the LLM's verdict).

    A criterion is traced iff the Analyst's report contains a CriterionTrace
    for that exact (task_id, criterion) with a non-empty `tests` list. Any
    authoritative criterion the report omits OR maps to zero tests is untraced.
    Enforced against the plan's authoritative set so an Analyst cannot hide a
    gap by forgetting to list a criterion. Returns "task_id: criterion" labels
    in authoritative order."""
    traced = {(t.task_id, t.criterion) for t in report.traceability if t.tests}
    return [
        f"{task_id}: {criterion}"
        for (task_id, criterion) in authoritative
        if (task_id, criterion) not in traced
    ]


# Fallbacks only for contracts predating test_commands/lint_commands
# (legacy cached artifacts) — every fresh plan populates both per-stack.
DEFAULT_LINT_CMD = "ruff check ."


def _degraded_research_brief(exc: Exception) -> ResearchBrief:
    """Substitute for the research stage's output when t_research.run() is
    cut off by BudgetExceeded (the persisted search/fetch/cost cap) or
    UsageLimitExceeded (pydantic-ai's request_limit) — mirrors
    research_subquery's mid-run fallback (research/toolset.py) so the
    primary stage degrades the same way: no findings, the shortfall
    recorded as a gap, never a crash that takes the whole run down with it
    (bench-todo-api-greenfield-1785485669: an uncaught UsageLimitExceeded
    here killed the entire FeatureWorkflow, losing every other stage's
    records along with it). Empty grounded_findings means
    verify_brief_activity always returns zero violations, so this flows
    through the normal post-research code unchanged."""
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id="research-stage",
                what_is_missing="the research stage did not complete",
                why_it_matters=str(exc),
            )
        ],
        summary=f"Research stopped early: {exc}",
    )


def _findings_from_results(subs: list[SubQuestion], results: list) -> list[SubQuestionFinding]:
    """Turn gather(..., return_exceptions=True) output into findings.

    Sub-questions are INDEPENDENT -- that is the premise of the fan-out. Letting
    one exception propagate would cancel the gather and discard every sibling
    finding already paid for. A partial brief from three of four sub-questions
    is worth far more than nothing, so a failure becomes a failed finding that
    the merge turns into a Gap."""
    out: list[SubQuestionFinding] = []
    for sub, result in zip(subs, results, strict=False):
        if isinstance(result, BaseException):
            out.append(SubQuestionFinding(sub_question=sub, failed=True, error=str(result)))
        else:
            out.append(result)
    return out


def _should_refine(round_n: int, cfg: ResearchConfig) -> bool:
    """Whether a REVISE at `round_n` gets another wave. Exhaustion is NOT a
    rejection -- the stage proceeds with the brief it has."""
    return round_n <= cfg.max_refine_rounds


def _refine_seed(brief: ResearchBrief) -> tuple[list, list]:
    """What round two should target: everything round one could not resolve.

    Richer than a free-text note, because the SGR brief already carries the
    machine-readable version. Resolved contradictions are excluded -- they are
    answered, and re-researching them spends the run ceiling on finished work."""
    return list(brief.gaps), [c for c in brief.contradictions if c.unresolved]


def _validate_task_graph(tasks: list[DevTask]) -> str | None:
    """None when every task's depends_on resolves to another task in the
    same plan and the graph has no cycle; otherwise a human-readable reason.

    Catches both failure shapes the scheduler's ready-loop (run_one's caller,
    below) would otherwise only discover after burning a run: a dangling
    reference (a revision round dropped a task while a survivor still cites
    its id -- exactly bench-todo-api-greenfield-1785868165's single-task
    T7-depends-on-T3..T6 plan) and a true A->B->A cycle. Surfacing this right
    after the plan gate turns both into an immediate, legible
    `failed:plan-validation:...` instead of the scheduler's opaque
    `failed:dependency-cycle` once tasks are already mid-execution."""
    ids = {t.id for t in tasks}
    for t in tasks:
        unknown = [d for d in t.depends_on if d not in ids]
        if unknown:
            return f"task {t.id!r} depends on unknown task id(s) {unknown!r}"

    by_id = {t.id: t for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(ids, WHITE)

    def visit(tid: str, path: list[str]) -> str | None:
        color[tid] = GRAY
        for dep in by_id[tid].depends_on:
            if color[dep] == GRAY:
                cycle = path[path.index(dep) :] + [dep]
                return " -> ".join(cycle)
            if color[dep] == WHITE:
                found = visit(dep, path + [dep])
                if found:
                    return found
        color[tid] = BLACK
        return None

    for t in tasks:
        if color[t.id] == WHITE:
            cycle = visit(t.id, [t.id])
            if cycle:
                return f"dependency cycle: {cycle}"
    return None


@workflow.defn
class FeatureWorkflow(
    GateHost,
    ReportHost,
    BoardHost,
    BenchmarkHost,
    MemoryHost,
    RoleHost,
    QuestionHost,
    TaskHost,
):
    def __init__(self) -> None:
        super().__init__()
        # Stashed state for hooks/queries (E-42, E-10, ADR-14, E-84). _run_id: run_state()
        # is unit-tested on bare instances (no event loop); "" sentinels: no reader before setup.
        self._cfg: PipelineConfig | None = None
        self._idea: IdeaBrief | None = None
        self._started_at: datetime | None = None
        self._run_id: str = ""
        self._integration_head: str = ""
        self._integration_wt: str = ""
        self._run_summary: RunSummary | None = None
        self._codebase_map: CodebaseMap | None = None
        self._ctx: StageContext = StageServices(
            emit=self._emit,
            stage=self._stage,
            run_role=self._run_role,
            cached_stage=self._cached_stage,
            revisable_stage=self._revisable_stage,
            record=self._record,
            judge=self._judge,
            recall=self._recall,
            retain=self._retain,
            gate=self._gate,
            ask_and_wait=self.ask_and_wait,
        )

    async def _on_gate_awaited(self, name: str, round: int) -> None:
        self._emit(RunEventKind.GATE_AWAITED, stage=name, gate=name, round=str(round))

    async def _on_gate_decided(
        self,
        name: str,
        round: int,
        policy: GatePolicy,
        decision: GateDecision,
        confidence: float | None = None,
    ) -> None:
        conf = confidence
        self._emit(
            RunEventKind.GATE_DECIDED,
            stage=name,
            gate=name,
            round=str(round),
            policy=policy.value,
            decided_by=decision.decided_by,
            approved=("true" if decision.approved else "false"),
            **({"confidence": str(conf)} if conf is not None else {}),
        )
        cfg = self._cfg
        if cfg is None:
            return
        await self._retain(
            cfg,
            MemoryKind.GATE_FEEDBACK,
            cfg.memory.project_bank,
            text=f"gate {name}#{round}: {decision.outcome.value}"
            f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "round": str(round), "run_id": workflow.info().workflow_id},
        )

    async def _on_notified(
        self, gate: str, reason: NotifyReason, notifier: str, delivered: bool, error: str = ""
    ) -> None:
        self._emit(
            RunEventKind.GATE_NOTIFIED,
            stage=gate,
            gate=gate,
            reason=reason.value,
            notifier=notifier,
            delivered="true" if delivered else "false",
            **({"error": error} if error else {}),
        )

    # ---------------- queries (the HITL surface) ------------------------

    @workflow.query
    def run_summary(self) -> RunSummary | None:
        """The retro-stage RunSummary; None until the run terminates (E-32)."""
        return self._run_summary

    @workflow.query
    def run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10).

        None until run() stashes the brief. Every field is read from state
        the run already holds -- this query adds no bookkeeping.
        """
        if self._idea is None or self._started_at is None:
            return None
        priced = [u.cost_usd for u in self._role_usage.values() if u.cost_usd is not None]
        budget = self._cfg.run_budget_usd if self._cfg and self._cfg.run_budget_usd > 0 else None
        stage = next(
            (e.stage for e in reversed(self._trace) if e.kind is RunEventKind.STAGE_STARTED), None
        )
        return RunState(
            run_id=self._run_id,
            title=self._idea.title,
            repo_url=self._idea.repo_url,
            mode=self._idea.mode.value,
            status=self._status,
            current_stage=stage,
            started_at=self._started_at,
            decisions=list(self._gate_decisions.values()),
            roles=list(self._role_usage.values()),
            # None, not 0.0: a pricing miss must never read as a free run.
            cost_usd_total=sum(priced) if priced else None,
            budget_usd=budget,
            budget_crossings=self._budget_crossings,
        )

    # ---------------------------- helpers -------------------------------

    async def _fan_out_research(
        self,
        cfg: PipelineConfig,
        idea,
        deps: ResearchDeps,
        spend: RoleUsage,
        id_offset: int = 0,
        guidance: str = "",
        gaps: list | None = None,
        contradictions: list | None = None,
    ) -> list[SubQuestionFinding]:
        """One wave: plan -> N parallel sub-questions. The caller synthesizes
        a brief over the returned findings.

        Returns the raw per-sub-question findings so a refine round can
        EXTEND the finding list rather than discarding round one."""
        model = STAGE_MODELS.get("research", "unknown")

        plan: ResearchPlan = await workflow.execute_activity(
            plan_research,
            PlanInput(
                idea_json=idea.model_dump_json(),
                max_sub_questions=cfg.research.max_sub_questions,
                model=model,
                id_offset=id_offset,
                guidance=guidance,
                gaps=gaps or [],
                contradictions=contradictions or [],
            ),
            **RESEARCH_PLAN_ACT,
        )
        await self._fold_research_usage(cfg, plan.usage, spend)

        # THE fan-out. return_exceptions=True because the sub-questions are
        # independent: one failure must not cancel the gather and throw away
        # siblings already paid for.
        results = await asyncio.gather(
            *[
                workflow.execute_activity(
                    research_subquestion,
                    SubQuestionInput(
                        sub_question=sq,
                        deps=deps,
                        model=model,
                        max_requests=cfg.research.max_requests,
                        max_run_cost_usd=cfg.research.max_run_cost_usd,
                    ),
                    **RESEARCH_SQ_ACT,
                )
                for sq in plan.sub_questions
            ],
            return_exceptions=True,
        )

        findings = _findings_from_results(plan.sub_questions, results)
        for f in findings:
            await self._fold_research_usage(cfg, f.usage, spend)
        return findings

    async def _fold_research_usage(
        self, cfg: PipelineConfig, usage: RoleUsage, into: RoleUsage
    ) -> None:
        """E-33 amendment: fan-out moved the model call activity-side, so
        _run_role cannot wrap it. The activity hands usage back and the
        workflow prices it here -- one accounting path preserved, only the
        call site moved."""
        if not (usage.input_tokens or usage.output_tokens):
            return
        usd: float | None = None
        try:
            usd = await workflow.execute_activity(
                price_usage,
                PriceUsageInput(
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
                **PRICE_ACT,
            )
        except Exception:
            usd = None
        self._track_usage(
            role="research",
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=usd,
            into=into,
        )

    async def _run_deep_review(
        self, cfg, run, contract, assertions, diff, task
    ) -> DeepReviewReport | None:
        """E-39 advisory lens: read the SCRUBBED harness transcript as data and
        emit a DeepReviewReport. Recorded + retained for signal ONLY — never
        consulted in the task's success condition. Once per task, over the
        final HarnessRunResult. Best-effort: any failure returns None so an
        observability lens can never fail delivery."""
        if not (
            cfg.deep_review_enabled
            and t_deep_review is not None
            and run is not None
            and run.session_ref is not None
        ):
            return None
        _started = workflow.now()
        try:
            loaded = await workflow.execute_activity(
                load_session, LoadSessionInput(ref=run.session_ref), **ACT
            )
            # Code review #1: render the plain-text view both prompts and the
            # verifier ground on -- raw JSONL would drop legitimate evidence.
            transcript = session_text_from_jsonl(loaded.text) + (
                f"\n[transcript truncated; digest follows]\n{run.session_digest.model_dump_json()}"
                if loaded.truncated and run.session_digest is not None
                else ""
            )
            spend = RoleUsage(role="deep_review", model=resolve_role_model(cfg, "deep_review"))
            report = (
                await self._run_role(
                    cfg,
                    "deep_review",
                    resolve_role_model(cfg, "deep_review"),
                    t_deep_review,
                    "Frozen contract assertions:\n- "
                    + "\n- ".join(assertions)
                    + f"\nThe task as planned:\n{task.model_dump_json()}"
                    + f"\nDiff:\n{diff['patch']}"
                    + "\nScrubbed harness transcript (how the diff was reached):\n"
                    + transcript,
                    into=spend,
                )
            ).output
            # E-43: an accusation must point at a line the transcript
            # contains. Verified against `transcript`, the same bytes the
            # lens itself read. Dropping, never failing -- this lens must
            # never fail delivery.
            kept_flags, dropped_flags = verified_integrity_flags(report.integrity_flags, transcript)
            if dropped_flags:
                workflow.logger.warning(
                    "deep_review: dropped %d integrity flag(s) for task %s "
                    "whose evidence is not in the transcript",
                    dropped_flags,
                    task.id,
                )
            kept_devs, dropped_devs = verified_plan_deviations(report.plan_deviations, transcript)
            if dropped_devs:
                workflow.logger.warning(
                    "deep_review: dropped %d plan deviation(s) for task %s "
                    "whose evidence is not in the transcript",
                    dropped_devs,
                    task.id,
                )
            report = report.model_copy(
                update={"integrity_flags": kept_flags, "plan_deviations": kept_devs}
            )
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="deep_review",
                    role="deep_review",
                    started=_started,
                    ended=workflow.now(),
                    quality_score=(0.0 if report.cheat_detected or not report.approve else 1.0),
                    judge="deep_review",
                    outcome=(
                        BenchmarkOutcome.FAIL if report.cheat_detected else BenchmarkOutcome.PASS
                    ),
                    model=resolve_role_model(cfg, "deep_review"),
                    spend=spend,
                    task_id=task.id,
                ),
            )
            if report.cheat_detected:
                await self._retain(
                    cfg,
                    MemoryKind.GOTCHA,
                    cfg.memory.project_bank,
                    text=f"deep_review flagged task {task.id}: "
                    + "; ".join(f"{f.kind}: {f.detail}" for f in report.integrity_flags),
                    metadata={"task_id": task.id, "run_id": workflow.info().workflow_id},
                )
        except Exception:
            # A lens must never fail delivery -- but a silent swallow is how
            # the judge-Literal defect survived unnoticed across every run.
            workflow.logger.warning(
                "deep_review lens failed for task %s; continuing without it", task.id, exc_info=True
            )
            return None
        return report

    async def _run_adversary(
        self, cfg, contract, assertions, diff, qa_raw, task
    ) -> ReviewReport | None:
        """Spec 3.2: the decorrelated second opinion, on the APPROVING path
        only -- a rejection is already headed for the fix loop.

        Clean-context, exactly like the primary: contract + diff + test
        output, never the session (that is deep_review's job). Identical
        inputs are what make disagreement interpretable as model variance
        rather than information asymmetry.

        FAIL-OPEN: any failure returns None, which the caller treats as
        agreement. The primary reviewer is the sole designated blocking
        lens; a lens added for safety must not become a new way to fail.
        (Deliberately asymmetric to the E-38 scrub, which is fail-closed:
        a leaked credential is unrecoverable, a missed opinion is not.)
        """
        if not (cfg.adversarial_review_enabled and t_adversary is not None):
            return None
        _started = workflow.now()
        model = resolve_role_model(cfg, "adversary")
        try:
            spend = RoleUsage(role="adversary", model=model)
            report = (
                await self._run_role(
                    cfg,
                    "adversary",
                    model,
                    t_adversary,
                    "Frozen contract assertions:\n- "
                    + "\n- ".join(assertions)
                    + f"\nTest results: {qa_raw.model_dump_json()}"
                    + f"\nDiff:\n{diff['patch']}",
                    into=spend,
                )
            ).output
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="adversary",
                    role="adversary",
                    started=_started,
                    ended=workflow.now(),
                    quality_score=(1.0 if report.approve else 0.0),
                    judge="adversary",
                    outcome=(BenchmarkOutcome.PASS if report.approve else BenchmarkOutcome.FAIL),
                    model=model,
                    spend=spend,
                    task_id=task.id,
                    fix_attempts=0,
                ),
            )  # cause row: volume lives on code/qa
            if not report.approve:
                await self._retain(
                    cfg,
                    MemoryKind.GOTCHA,
                    cfg.memory.project_bank,
                    text=f"adversary split from reviewer on task {task.id}: "
                    + "; ".join(f"{f.assertion}: {f.detail}" for f in report.blocking_findings),
                    metadata={"task_id": task.id, "run_id": workflow.info().workflow_id},
                )
            return report
        except Exception:
            workflow.logger.warning(
                "adversary lens failed for task %s; treating as agreement", task.id, exc_info=True
            )
            return None

    async def _run_handoff(self, cfg, run, contract, assertions, diff, task) -> HandoffSummary:
        """FR-805: extract task-to-task claims from the scrubbed session.

        files_touched is filled HERE from the diff, never by the model, so
        the extractor structurally cannot misreport which files changed.
        Best-effort: any failure returns the mechanical handoff rather than
        failing a task that already passed.
        """
        files = diff["files"]
        fallback = HandoffSummary(task_id=task.id, files_touched=files)
        if not (t_handoff is not None and run is not None and run.session_ref is not None):
            return fallback
        _started = workflow.now()
        try:
            loaded = await workflow.execute_activity(
                load_session, LoadSessionInput(ref=run.session_ref), **ACT
            )
            model = resolve_role_model(cfg, "handoff")
            spend = RoleUsage(role="handoff", model=model)
            # Code review #1: the store holds JSONL, but the prompt elicits
            # prose evidence and the verifier must ground on the SAME bytes the
            # model saw -- so both consume the rendered plain-text view, not
            # raw JSONL (which would drop every legitimate claim).
            session_text = session_text_from_jsonl(loaded.text)
            out = (
                await self._run_role(
                    cfg,
                    "handoff",
                    model,
                    t_handoff,
                    "Frozen contract assertions:\n- "
                    + "\n- ".join(assertions)
                    + f"\nDiff:\n{diff['patch']}"
                    + "\nScrubbed harness transcript:\n"
                    + session_text,
                    into=spend,
                )
            ).output

            kept_total = 0
            dropped_total = 0
            fields = {}
            for name in ("what_changed", "decisions_made", "open_concerns"):
                checked = cross_check_claims(getattr(out, name), files, session_text=session_text)
                fields[name] = checked.kept
                kept_total += len(checked.kept)
                dropped_total += checked.dropped_paths + checked.dropped_quotes

            handoff = HandoffSummary(task_id=task.id, files_touched=files, **fields)
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="handoff",
                    role="handoff",
                    started=_started,
                    ended=workflow.now(),
                    # .value is None when no claims were extracted, which is
                    # exactly what quality_score must carry -- never a 0.0.
                    quality_score=claim_survival_score(kept_total, dropped_total).value,
                    judge="handoff",
                    outcome=BenchmarkOutcome.PASS,
                    model=model,
                    spend=spend,
                    task_id=task.id,
                    fix_attempts=0,
                ),
            )
            return handoff
        except Exception:
            workflow.logger.warning(
                "handoff extraction failed for task %s; using mechanical handoff",
                task.id,
                exc_info=True,
            )
            return fallback

    def _deploy_plan(self, cfg: PipelineConfig) -> DeployPlan:
        """The frozen DeployPlan for this run.

        TRANSITIONAL: devops_planner authoring this at the planning stage and
        the plan gate freezing it (spec D-2) is the next increment. Until
        then the run deploys with at most one liveness check -- weak but
        honest, and `frozen=True` keeps the contract's shape intact so the
        planner can start filling it without a second code path.

        The http liveness check is emitted ONLY when a base_url is configured:
        a script-adapter deploy has no endpoint, and an http check against an
        empty endpoint errors and would roll back every deploy (D-7 broken).
        With no base_url the plan therefore carries ZERO checks, so a script
        deploy succeeds on a zero exit code alone -- the one case that falls
        short of DeployReport's "deployed is earned by passing smoke checks"
        contract. A command smoke check (the natural fix for the D-7 path)
        lands with devops_planner. The version is sanitized into a valid
        image tag -- a benchmark child id carries a '/', which is not legal
        as a docker tag.
        """
        checks = []
        if cfg.deploy.base_url:
            checks.append(SmokeCheck(name="liveness", kind="http", path="/health"))
        return DeployPlan(
            environment="staging",
            version=_sanitize_tag(workflow.info().workflow_id),
            smoke_checks=checks,
        )

    # ------------------------------ run ---------------------------------

    @workflow.run
    async def run(
        self, idea: IdeaBrief, cfg: PipelineConfig | None = None, seeded: SeededWork | None = None
    ) -> str:
        if isinstance(idea, dict):
            idea = IdeaBrief.model_validate(idea)
        if isinstance(cfg, dict):
            cfg = PipelineConfig.model_validate(cfg)
        elif cfg is None:
            cfg = PipelineConfig()
        if isinstance(seeded, dict):
            seeded = SeededWork.model_validate(seeded)
        self._idea = idea
        self._started_at = workflow.now()
        self._run_id = workflow.info().workflow_id
        self._cfg = cfg
        self._budget_threshold = cfg.run_budget_usd  # E-33
        try:
            result = await self._pipeline(idea, cfg, seeded)
        except _BudgetRejected:
            result = "rejected:budget"
        await self._retro(cfg, idea, result)
        return result

    async def _retro(self, cfg: PipelineConfig, idea: IdeaBrief, result: str) -> None:
        """Stage 14 (E-32). Best-effort: any failure is swallowed so the run's
        return string is never changed."""
        try:
            summary = build_run_summary(
                run_id=workflow.info().workflow_id,
                mode=idea.mode.value,
                outcome=result,
                trace=self._trace,
                memory_enabled=cfg.memory.enabled,
                memory_watermark=self._memory_watermark,
                budget_usd=(cfg.run_budget_usd if cfg.run_budget_usd > 0 else None),
                title=idea.title,
                repo_url=idea.repo_url,
            )
            self._run_summary = summary
            await retro.step(
                self._ctx,
                cfg=cfg,
                summary=summary,
                session_refs=self._session_refs,
                trace=self._trace,
            )
        except Exception:
            # Retro must never change the run outcome (best-effort stage).
            pass

    async def _context(self, repo_path: str, commit_sha: str) -> CodebaseMap:
        """Stage 2 (E-84). The same thirteen signals the audit tier runs, over
        the same memo, with no triage (D1/D5).

        Nothing here executes the repository's code: every signal reads blob
        bytes at the pinned commit (NFR-9).
        """
        out = await scan_tree(repo_path, commit_sha, None)
        if out.scan is None:
            return CodebaseMap(
                tree_hash=out.tree_hash or "",
                commit_sha=commit_sha,
                modules_collected=out.result.collected,
                contracts_collected=out.result.collected,
                hot_spots_collected=out.result.collected,
                collected=out.result.collected,
            )
        return project(out.scan, out.tree_hash, commit_sha)

    async def _pipeline(
        self, idea: IdeaBrief, cfg: PipelineConfig, seeded: SeededWork | None = None
    ) -> str:
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                await workflow.execute_activity(
                    capture_watermark,
                    WatermarkInput(
                        bank=cfg.memory.project_bank,
                        backend=cfg.memory.backend,
                        base_url=cfg.memory.base_url,
                    ),
                    **MEM_ACT,
                )
            )
        repo_path = idea.repo_url or "/var/sdlc/repo"  # prepared by a setup activity IRL

        # 0. INTAKE (E-84 D3) -- deterministic, no model call. IdeaBrief.mode
        # is declared by the operator; this verifies the declaration against
        # the tree and fails closed when brownfield has nothing to map.
        intake_err = await intake.step(self._ctx, cfg=cfg, idea=idea, repo_path=repo_path)
        if intake_err is not None:
            return intake_err

        # ADR-14: one sdlc/<run_id>/integration branch accumulates completed
        # task work; dependent tasks branch from its head. The activity hands
        # back both the head SHA and the worktree path — the workflow never
        # computes the path itself (that would read SDLC_WORKTREES_ROOT from
        # the env, a determinism violation).
        integration: IntegrationHandle = await workflow.execute_activity(
            setup_integration_branch,
            IntegrationInput(
                repo_path=repo_path,
                run_id=workflow.info().workflow_id,
                base_branch=idea.base_branch,
            ),
            **ACT,
        )
        self._integration_head = integration.head_sha
        self._integration_wt = integration.worktree_path

        # E-44 D1: a seeded run enters at stage 4. Research, clarify,
        # architecture and planning decide WHAT to build; a mechanical triage
        # finding already answers that, and clarify's open-question wait would
        # park a tidy-up run on a question the finding contains.
        if seeded is not None:
            arch, plan = seeded.arch, seeded.plan
            self._stage("coding", "code")
            return await self._build_and_merge(idea, cfg, arch, plan, repo_path)

        # 2. CONTEXT (E-84 D1/D4/D6) -- brownfield only. Pinned to the
        # integration head, which is the branch point the work is based on.
        self._codebase_map = None
        if idea.mode is ProjectMode.BROWNFIELD:
            self._stage("mapping", "context")
            self._codebase_map = await self._context(repo_path, self._integration_head)
            if self._codebase_map.collected.state is not CollectionState.MEASURED:
                # D6: proceeding would silently drop the delta check exactly
                # when the ground is weakest -- the shape of the
                # malformed-SARIF-reads-as-clean hole (FR-915).
                return f"rejected:context ({self._codebase_map.collected.reason})"

        # 0. RESEARCH (FR-107) — optional, human-gated, NOT memoized. A served
        # memo means pages were not fetched this run, so a brief cannot be
        # cached (spec finding 4). The brief contributes only its canonical
        # digest to downstream keys (finding 3), never its prose.
        brief_digest_val = ""
        if cfg.research_enabled and t_research is not None:
            self._stage("researching", "research")
            _r_started = workflow.now()
            research_role = cfg.roles.get("research")
            deps = ResearchDeps(
                run_id=workflow.info().workflow_id,
                provider=(research_role.provider or "fake") if research_role else "fake",
                max_searches=cfg.research.max_searches,
                max_fetches=cfg.research.max_fetches,
                max_cost_usd=cfg.research.max_cost_usd,
                memory_backend=cfg.memory.backend,
                memory_base_url=cfg.memory.base_url,
                memory_bank=cfg.memory.project_bank,
                memory_watermark=self._memory_watermark,
            )
            # Budget enforcement under fan-out: each sub-question charges its
            # OWN persisted scope ("sq-<id>") plus the shared "run" ceiling via
            # charge_scoped inside the toolset, so one sub-question cannot
            # drain the run. research_subquestion degrades a BudgetExceeded /
            # UsageLimitExceeded into a gap rather than re-raising -- the
            # counter is persisted, so a retry would hit the same exhausted
            # cap six times with backoff (bench-todo-api-greenfield-1785485669:
            # an uncaught UsageLimitExceeded once killed the whole
            # FeatureWorkflow, not just the research stage).
            research_spend = RoleUsage(
                role="research", model=STAGE_MODELS.get("research", "unknown")
            )
            try:
                findings = await self._fan_out_research(cfg, idea, deps, research_spend)
                if all(f.failed for f in findings):
                    # No brief to synthesize -- and no point paying for the
                    # call. Degrade the STAGE, never the run (2026-07-20
                    # decision).
                    brief = _degraded_research_brief(RuntimeError("every sub-question failed"))
                else:
                    brief, synth_usage = await workflow.execute_activity(
                        synthesize_brief,
                        SynthesizeInput(
                            idea_json=idea.model_dump_json(),
                            findings=findings,
                            model=STAGE_MODELS.get("research", "unknown"),
                        ),
                        **RESEARCH_SYNTH_ACT,
                    )
                    await self._fold_research_usage(cfg, synth_usage, research_spend)
            except Exception as exc:
                # Fan-out / synthesis model-call failure degrades the STAGE,
                # never the run (spec §8 tier 1;
                # bench-todo-api-greenfield-1785485669: an uncaught
                # UsageLimitExceeded once killed the whole FeatureWorkflow,
                # not just the research stage). Grounding violations are NOT
                # exceptions -- they fail the stage closed below -- so this
                # broad guard only catches model-call failures (a
                # plan/synthesize ActivityError after its retries exhaust).
                brief = _degraded_research_brief(exc)
                findings = []
            # Task 7 fallback (Task 1 finding A): the original
            # @agent.output_validator was silently dropped by TemporalAgent, so
            # grounding is enforced here as a post-run ACTIVITY. Reads page
            # files (I/O) — must run via execute_activity, not inline, or
            # test_factory_purity.py fires. The activity RETURNS the violations
            # list (does not raise) so we can inspect it directly — temporalio
            # wraps activity-raised exceptions in ActivityError, which would
            # prevent catching a typed exception here. Non-empty = fail closed.
            violations = await workflow.execute_activity(
                verify_brief_activity, args=[brief, workflow.info().workflow_id], **VERIFY_ACT
            )
            if violations:
                # Ungrounded brief: fail this stage but do NOT stop the
                # pipeline (2026-07-20 human decision — see report for
                # rationale). Nothing from an unverified brief is trustworthy
                # enough to retain to memory or feed into downstream content
                # keys, so brief_digest_val stays "" and retain is skipped;
                # everything after research proceeds on the idea alone, same
                # as a research-disabled run.
                self._stage("research_failed", "research")
                err = "; ".join(f"{v.kind}: {v.source}: {v.quote[:80]!r}" for v in violations)
                await self._record(
                    cfg,
                    self._stage_record(
                        cfg,
                        stage="research",
                        role="research",
                        started=_r_started,
                        ended=workflow.now(),
                        quality_score=None,
                        judge="error",
                        outcome=BenchmarkOutcome.FAIL,
                        model=STAGE_MODELS.get("research", "unknown"),
                        spend=research_spend,
                        error=f"rejected:research.grounding: {err}",
                    ),
                )
            else:
                brief_digest_val = brief_digest(brief)
                round_n = 1
                while True:
                    gate = await self._gate("research", cfg.gate_settings(), round=round_n)
                    if gate.outcome == GateOutcome.APPROVE:
                        break
                    if gate.outcome == GateOutcome.REJECT:
                        return "rejected:research"
                    # REVISE
                    if not _should_refine(round_n, cfg.research):
                        # Exhausted: proceed with what we have. Research
                        # degrades a run; it never stops one.
                        break
                    gaps, conflicts = _refine_seed(brief)
                    try:
                        findings += await self._fan_out_research(
                            cfg,
                            idea,
                            deps,
                            research_spend,
                            id_offset=len(findings),
                            guidance=gate.guidance or "",
                            gaps=gaps,
                            contradictions=conflicts,
                        )
                        # Re-merge over ALL findings: round one is never discarded.
                        brief, synth_usage = await workflow.execute_activity(
                            synthesize_brief,
                            SynthesizeInput(
                                idea_json=idea.model_dump_json(),
                                findings=findings,
                                model=STAGE_MODELS.get("research", "unknown"),
                            ),
                            **RESEARCH_SYNTH_ACT,
                        )
                        await self._fold_research_usage(cfg, synth_usage, research_spend)
                    except Exception:
                        # Refine-round model failure: keep the prior VERIFIED
                        # brief and stop refining rather than discard round one
                        # or crash the run. Research degrades; it never stops
                        # the pipeline (spec §8).
                        break
                    # Round-2 findings must be verified too.
                    violations = await workflow.execute_activity(
                        verify_brief_activity,
                        args=[brief, workflow.info().workflow_id],
                        **VERIFY_ACT,
                    )
                    if violations:
                        self._stage("research_failed", "research")
                        brief_digest_val = ""
                        break
                    brief_digest_val = brief_digest(brief)
                    round_n += 1
                if brief_digest_val:
                    # Grounded brief (possibly after a refine round): retain,
                    # judge, and record PASS.
                    for item in verified_findings_to_retain(
                        brief, workflow.info().workflow_id, bank=cfg.memory.project_bank
                    ):
                        await self._retain(cfg, item.kind, item.bank, item.text, item.metadata)
                    _r_quality = await self._judge(
                        cfg,
                        brief.model_dump_json(),
                        "research",
                        author_model=STAGE_MODELS.get("research", "unknown"),
                    )
                    await self._record(
                        cfg,
                        self._stage_record(
                            cfg,
                            stage="research",
                            role="research",
                            started=_r_started,
                            ended=workflow.now(),
                            quality_score=_r_quality.score,
                            judge=_r_quality.judge,
                            outcome=BenchmarkOutcome.PASS,
                            model=STAGE_MODELS.get("research", "unknown"),
                            spend=research_spend,
                        ),
                    )
                else:
                    # A refine round failed grounding: record FAIL, mirroring
                    # the initial-violations path. retain is skipped (nothing
                    # from an unverified brief is trustworthy) and the run
                    # proceeds on the idea alone, same as a research-disabled
                    # run.
                    await self._record(
                        cfg,
                        self._stage_record(
                            cfg,
                            stage="research",
                            role="research",
                            started=_r_started,
                            ended=workflow.now(),
                            quality_score=None,
                            judge="error",
                            outcome=BenchmarkOutcome.FAIL,
                            model=STAGE_MODELS.get("research", "unknown"),
                            spend=research_spend,
                            error="rejected:research.grounding (refine)",
                        ),
                    )

        # E-33: serial budget check after the research section (runs whether
        # research is on or off; off-by-default research adds no spend here).
        await self._check_budget(cfg)

        # 1. CLARIFY — open questions answered by human via signals
        reqs = await clarify.step(
            self._ctx,
            cfg=cfg,
            idea=idea,
            codebase_map=self._codebase_map,
            brief_digest=brief_digest_val,
            clarify_agent=t_clarify,
            route_agent=t_clarify_route,
            probe_agent=t_clarify_probe,
            clarify_model=resolve_role_model(cfg, "clarify"),
        )
        await self._board_publish(cfg, "requirements", reqs.model_dump_json())
        await self._retain(
            cfg,
            MemoryKind.STAGE_SUMMARY,
            cfg.memory.project_bank,
            text=f"clarify: {reqs.summary}",
            metadata={"stage": "clarify", "run_id": workflow.info().workflow_id},
        )

        # E-33: serial budget check after clarify.
        await self._check_budget(cfg)

        # 2. ARCHITECT (+ human approval of the spec)
        self._stage("architecting", "architecture")
        _started = workflow.now()
        snapshot = await self._recall(
            cfg,
            cfg.memory.project_bank,
            query=f"architect:{idea.title}",
            filters={"stage": "architect"},
        )

        arch_spend = RoleUsage(role="architect", model=resolve_role_model(cfg, "architect"))

        # E-84 D10/D12: render the codebase map once upfront for prompt and memo key.
        map_block = ""
        map_key = ""
        if self._codebase_map is not None:
            rendered_map = render_for_prompt(self._codebase_map)
            map_key = map_digest(self._codebase_map)
            map_block = (
                f"\n\nCodebase map at commit {self._codebase_map.commit_sha[:12]}:\n{rendered_map}"
            )

        async def _run_architect(guidance: str | None) -> ArchitectureSpec:
            # ResearchDeps is ALWAYS constructed so the architect agent's
            # deps_type=ResearchDeps is satisfied uniformly. When research is
            # disabled, provider="fake".
            # NOTE: under the default config (research_enabled=False,
            # provider="fake", no $SDLC_RESEARCH_FAKE_CORPUS), the architect's
            # research(q) tool is advertised but will raise if the LLM calls
            # it — the fake corpus is a CI fixture, not production-accessible.
            # Set research_enabled=True and a real provider (or point
            # SDLC_RESEARCH_FAKE_CORPUS at a corpus) to use it.
            # The error surfaces to the model, which stops calling the tool;
            # the architect still produces its ArchitectureSpec.
            # NOTE (accepted loss, 2026-07-17 human decision): the budget
            # counter on deps.budget accumulates correctly for direct/test
            # invocation, but under TemporalAgent each tool activity receives
            # a fresh deserialized copy — shared-budget enforcement is
            # advisory-only when the architect runs temporalized.
            research_role = cfg.roles.get("research") if cfg.research_enabled else None
            architect_deps = ResearchDeps(
                run_id=workflow.info().workflow_id,
                provider=(research_role.provider or "fake") if research_role else "fake",
                max_searches=cfg.research.max_searches,
                max_fetches=cfg.research.max_fetches,
                max_cost_usd=cfg.research.max_cost_usd,
                memory_backend=cfg.memory.backend,
                memory_base_url=cfg.memory.base_url,
                memory_bank=cfg.memory.project_bank,
                memory_watermark=self._memory_watermark,
                # max_searches/max_fetches are PER-CONSUMER (each research
                # sub-question gets its own budget-sq-<id>.json). The architect
                # is a peer consumer in a later stage sharing the same run_id
                # (hence budget-run.json), so it must charge a dedicated scope:
                # the default 'run' would let the research fan-out's accumulated
                # searches exhaust the architect's count allowance before it
                # starts. budget-architect.json still feeds the shared run COST
                # ceiling via charge_scoped's run-counter step.
                scope="architect",
            )

            delta_retries = cfg.max_delta_retries
            delta_guidance: str | None = None
            # E-85: the architect reads the requirements, not the stage's
            # measurement record. Rendered once so the prompt and the memo
            # key below cannot drift apart.
            reqs_for_architect = _requirements_for_downstream(reqs)
            while True:
                prompt = (
                    f"mode={idea.mode.value}\n{reqs_for_architect}"
                    + (map_block if self._codebase_map is not None else "")
                    + (
                        "\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                        if snapshot.items
                        else ""
                    )
                    + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
                    + (f"\nDelta correction required:\n{delta_guidance}" if delta_guidance else "")
                )

                async def _produce(prompt: str = prompt):
                    return (
                        await self._run_role(
                            cfg,
                            "architect",
                            resolve_role_model(cfg, "architect"),
                            t_architect,
                            prompt,
                            deps=architect_deps,
                            into=arch_spend,
                        )
                    ).output

                cache_key = (
                    reqs_for_architect
                    + (guidance or "")
                    + (map_key if self._codebase_map is not None else "")
                    + (delta_guidance or "")
                )
                arch, _ = await self._cached_stage(
                    cfg, "architect", cache_key, ArchitectureSpec, _produce
                )

                if self._codebase_map is None:
                    return arch

                delta_check = await workflow.execute_activity(
                    check_brownfield_delta,
                    DeltaCheckInput(
                        repo_dir=repo_path,
                        commit_sha=self._codebase_map.commit_sha,
                        delta=arch.delta,
                    ),
                    **INTAKE_ACT,
                )
                if delta_check.passed:
                    return arch

                if delta_retries <= 0:
                    raise ApplicationError(
                        f"brownfield architecture delta failed grounding check "
                        f"after retries: {delta_check.detail}",
                        non_retryable=True,
                    )
                delta_retries -= 1
                delta_guidance = (
                    f"The proposed delta does not match the repository at "
                    f"{self._codebase_map.commit_sha[:12]}: "
                    f"{delta_check.detail}. Update delta.added, delta.modified, "
                    f"and delta.removed so every path resolves."
                )

        arch, gate = await self._revisable_stage("architecture", cfg, _run_architect)
        _ended = workflow.now()
        _quality = await self._judge(
            cfg,
            arch.model_dump_json(),
            "architect",
            author_model=resolve_role_model(cfg, "architect"),
        )
        await self._record(
            cfg,
            self._stage_record(
                cfg,
                stage="architecture",
                role="architect",
                started=_started,
                ended=_ended,
                quality_score=_quality.score,
                judge=_quality.judge,
                outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
                model=resolve_role_model(cfg, "architect"),
                spend=arch_spend,
            ),
        )
        await self._retain(
            cfg,
            MemoryKind.STAGE_SUMMARY,
            cfg.memory.project_bank,
            text=f"architect: {arch.overview}",
            metadata={"stage": "architect", "run_id": workflow.info().workflow_id},
        )
        await self._check_budget(cfg)  # E-33: serial boundary after architect
        await self._board_publish(
            cfg, "architecture", arch.model_dump_json(), approved=gate.approved
        )
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"plan:{idea.title}", filters={"stage": "plan"}
        )

        plan_spend = RoleUsage(role="planner", model=resolve_role_model(cfg, "plan"))

        async def _run_plan(guidance: str | None) -> ImplementationPlan:
            prompt = planner_prompt(arch.model_dump_json(), snapshot.items, guidance)

            async def _produce():
                return (
                    await self._run_role(
                        cfg,
                        "planner",
                        resolve_role_model(cfg, "plan"),
                        t_planner,
                        prompt,
                        into=plan_spend,
                    )
                ).output

            plan, _ = await self._cached_stage(
                cfg, "plan", arch.model_dump_json() + (guidance or ""), ImplementationPlan, _produce
            )
            return plan

        plan, gate = await self._revisable_stage("plan", cfg, _run_plan)
        _ended = workflow.now()
        _quality = await self._judge(
            cfg, plan.model_dump_json(), "planner", author_model=resolve_role_model(cfg, "plan")
        )
        await self._record(
            cfg,
            self._stage_record(
                cfg,
                stage="plan",
                role="planner",
                started=_started,
                ended=_ended,
                quality_score=_quality.score,
                judge=_quality.judge,
                outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
                model=resolve_role_model(cfg, "plan"),
                spend=plan_spend,
            ),
        )
        await self._retain(
            cfg,
            MemoryKind.STAGE_SUMMARY,
            cfg.memory.project_bank,
            text=f"plan: {len(plan.tasks)} tasks",
            metadata={"stage": "plan", "run_id": workflow.info().workflow_id},
        )
        await self._check_budget(cfg)  # E-33: serial boundary after planner
        self._plan_version = await self._board_publish(
            cfg, "plan", plan.model_dump_json(), approved=gate.approved
        )
        if not gate.approved:
            return "rejected:plan"
        graph_error = _validate_task_graph(plan.tasks)
        if graph_error:
            return f"failed:plan-validation:{graph_error}"
        # Sync tasks only after the graph is valid — an invalid plan would
        # otherwise leave PENDING rows that never move and permanently skew
        # /stats for the project.
        await self._board_sync_tasks(cfg, self._plan_version, plan.tasks)

        return await self._build_and_merge(idea, cfg, arch, plan, repo_path)

    async def _build_and_merge(
        self,
        idea: IdeaBrief,
        cfg: PipelineConfig,
        arch: ArchitectureSpec,
        plan: ImplementationPlan,
        repo_path: str,
    ) -> str:
        """Stages 4-6: tasks, merge gate, PR, deploy. Shared by the ordinary
        pipeline and by E-44's seeded entry point -- one implementation of
        'how a governed change reaches a PR' (D1)."""
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
            await self._board_task_status(cfg, t.id, TaskStatus.IN_PROGRESS)
            try:
                r = await self._dev_task(t, repo_path, self._integration_head, cfg, handoffs)
            except Exception as exc:
                # _dev_task's own fix loop is exhausted before it raises, so a
                # propagating exception means the run is aborting. Record a
                # terminal status so the board (which agents read for live
                # state) does not leave this task looking forever in_progress
                # — indistinguishable from a task still running.
                await self._board_task_status(
                    cfg, t.id, TaskStatus.FAILED, error=f"unhandled: {type(exc).__name__}: {exc}"
                )
                raise
            _BOARD_STATUS = {
                "done": TaskStatus.DONE,
                "failed": TaskStatus.FAILED,
                "quarantined": TaskStatus.QUARANTINED,
            }
            await self._board_task_status(
                cfg,
                t.id,
                _BOARD_STATUS[r.status],
                fix_attempts=r.attempts,
                branch=r.branch,
                error=(r.notes or None if r.status != "done" else None),
            )
            for kind, report in (
                ("qa", r.qa),
                ("review", r.review),
                ("deep_review", r.deep_review),
            ):
                if report is not None:
                    await self._board_evidence(cfg, t.id, kind, report.model_dump_json())
            done[r.task_id] = r
            if r.handoff:
                handoffs.append(r.handoff)
            remaining.pop(r.task_id)
            return r

        while remaining:
            ready = [t for t in remaining.values() if all(d in done for d in t.depends_on)]
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
                batch: list[DevTask] = []
                seen: set[str] = set()
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

            await self._check_budget(cfg)  # E-33: serial boundary per task wave

        # 4b. ANALYZE (stage 9) — clean-context Analyst proposes the
        # criterion->test mapping; the workflow enforces it (FR-106). Runs on
        # the integrated whole, before the merge gate.
        self._stage("analyzing", "analyze")
        _an_started = workflow.now()
        integration_diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=self._integration_wt, branch_point=idea.base_branch),
            **ACT,
        )
        authoritative: list[tuple[str, str]] = [
            (t.id, c) for t in plan.tasks for c in t.acceptance_criteria
        ]
        _criteria_lines = "\n".join(f"- [{tid}] {crit}" for tid, crit in authoritative)
        _qa_lines = "\n".join(
            f"- {r.task_id}: tests_passed={r.qa.tests_passed if r.qa else 'n/a'}"
            f" failing={r.qa.failing_tests if r.qa else []}"
            for r in done.values()
        )
        analyst_spend = RoleUsage(role="analyst", model=resolve_role_model(cfg, "analyze"))
        analysis: AnalysisReport = (
            await self._run_role(
                cfg,
                "analyst",
                resolve_role_model(cfg, "analyze"),
                t_analyst,
                analyst_prompt(
                    _criteria_lines, _qa_lines, integration_diff["stat"], integration_diff["patch"]
                ),
                into=analyst_spend,
            )
        ).output
        untraced = untraced_criteria(authoritative, analysis)
        await self._record(
            cfg,
            self._stage_record(
                cfg,
                stage="analyze",
                role="analyst",
                started=_an_started,
                ended=workflow.now(),
                quality_score=(1.0 if not untraced else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if not untraced else BenchmarkOutcome.FAIL),
                model=resolve_role_model(cfg, "analyze"),
                spend=analyst_spend,
            ),
        )
        await self._retain(
            cfg,
            MemoryKind.STAGE_SUMMARY,
            cfg.memory.project_bank,
            text=f"analyze: {len(authoritative)} criteria, "
            f"{len(untraced)} untraced. {analysis.summary}",
            metadata={"stage": "analyze", "run_id": workflow.info().workflow_id},
        )
        if untraced:
            await self._retain(
                cfg,
                MemoryKind.GOTCHA,
                cfg.memory.project_bank,
                text=f"untraced acceptance criteria at merge: {untraced}",
                metadata={"stage": "analyze", "run_id": workflow.info().workflow_id},
            )

        await self._check_budget(cfg)  # E-33: serial boundary after analyst

        # 5. MERGE — DeterministicQualityGate first (SC-5), then the human
        # gate (which doubles as the advisory-override mechanism), then
        # MergeVerdict advisory only under SOFT policy.
        _started = workflow.now()

        # 5a. Collect typed evidence from the run. The merge stage runs
        # against the integration worktree (ADR-14), where every completed
        # task's merge has accumulated.
        integration_worktree = self._integration_wt
        # E-30/FR-108/ADR-14: run the toolchain adapter (coverage-instrumented
        # tests + lint) against the merged integration head — a REAL
        # integration-green signal, and the coverage.xml measure_coverage reads.
        # No adapter for the built language => degrade to the pre-E-30 path
        # (per-task aggregate green + the plan's own lint command).
        ichecks: IntegrationChecks = await workflow.execute_activity(
            run_integration_checks,
            IntegrationChecksInput(
                worktree=integration_worktree, changed_files=integration_diff["files"]
            ),
            **INTEG_ACT,
        )
        if ichecks.toolchain is not None:
            all_tests_green = ichecks.qa.tests_passed
            lint_clean, lint_detail = ichecks.lint_clean, ichecks.lint_detail
        else:
            lint_commands = next(
                (
                    t.contract.lint_commands
                    for t in plan.tasks
                    if t.contract and t.contract.lint_commands
                ),
                None,
            )
            lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
            lint_clean, lint_detail = await workflow.execute_activity(
                run_lint, LintInput(worktree=integration_worktree, lint_cmd=lint_cmd), **ACT
            )
            all_tests_green = _merge_evidence_all_green(list(done.values()))

        # Coverage is read AFTER the integration test run that emits
        # coverage.xml (E-30 closes the FR-106 gap: the artifact now lands where
        # the seam reads). measured=False stays a no-op advisory pass.
        cov: CoverageReport = await workflow.execute_activity(
            measure_coverage,
            CoverageInput(worktree=integration_worktree, changed_files=integration_diff["files"]),
            **ACT,
        )

        security: SecurityReport = await workflow.execute_activity(
            security_scan, SecurityScanInput(worktree=integration_worktree), **ACT
        )

        # MEASURED carries a value by the Measurement validator (FR-915);
        # hoisted so the check below narrows on it instead of re-testing state.
        diff_coverage = (
            cov.coverage.value if cov.coverage.state is CollectionState.MEASURED else None
        )

        checks = [
            build_check(
                "build_integration_green",
                all_tests_green,
                CheckClass.ABSOLUTE,
                detail="aggregate of per-task pytest runs",
            ),
            build_check("lint_clean", lint_clean, CheckClass.ABSOLUTE, detail=lint_detail),
            # FR-915: "the scan found nothing" and "no scan happened" are
            # different facts and get different check names. Conflating them
            # into one compound condition is the exact defect this split
            # exists to prevent, reproduced inside the gate that prevents it.
            build_check(
                "security_scan_collected",
                security.state is CollectionState.MEASURED,
                CheckClass.ABSOLUTE,
                detail=(security.reason or "security scan ran"),
            ),
            build_check(
                "security_no_critical",
                security.critical == 0,
                CheckClass.ABSOLUTE,
                detail=f"{security.critical} critical finding(s)",
            ),
            build_check(
                "review_severity",
                all(r.review is None or r.review.approve for r in done.values()),
                CheckClass.ADVISORY,
                detail="clean-context reviewer blocking findings (FR-204)",
            ),
            build_check(
                "traceability",
                not untraced,
                CheckClass.ADVISORY,
                detail=(
                    f"{len(untraced)} criterion(s) without a test: {untraced[:10]}"
                    if untraced
                    else "every acceptance criterion traces to >=1 test"
                ),
            ),
            build_check(
                "coverage",
                (True if diff_coverage is None else diff_coverage >= cfg.coverage_threshold),
                CheckClass.ADVISORY,
                detail=(
                    cov.coverage.reason
                    if diff_coverage is None
                    else f"diff coverage {diff_coverage:.1f}% vs "
                    f"threshold {cfg.coverage_threshold:.1f}%"
                ),
            ),
        ]
        gate_report: GateReport = await workflow.execute_activity(
            evaluate_gate, QualityGateInput(checks=checks), **ACT
        )

        # 5b. Absolute failure = terminal. No override path exists.
        absolute_blocking = [
            c.name
            for c in gate_report.checks
            if c.name in gate_report.blocking and c.classification is CheckClass.ABSOLUTE
        ]
        if absolute_blocking:
            await self._retain(
                cfg,
                MemoryKind.GATE_FEEDBACK,
                cfg.memory.project_bank,
                text=f"merge blocked (absolute): {absolute_blocking}",
                metadata={"gate": "merge", "round": "1", "run_id": workflow.info().workflow_id},
            )
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="merge",
                    role="reviewer",
                    started=_started,
                    ended=workflow.now(),
                    quality_score=0.0,
                    judge="contract",
                    outcome=BenchmarkOutcome.FAIL,
                    model="deterministic",
                ),
            )
            return f"rejected:merge:absolute-gate-failed:{','.join(absolute_blocking)}"

        # 5c. Advisory failure: the human merge gate IS the override. A
        # human APPROVE records audited GateOverrides; REJECT terminates.
        overrides: list[GateOverride] = []
        if not gate_report.passed:
            advisory_blocking = [
                c.name
                for c in gate_report.checks
                if c.name in gate_report.blocking and c.classification is CheckClass.ADVISORY
            ]
            gate = await self._gate(
                "merge", cfg.gate_settings(), context=GateContext(checks=gate_report.checks)
            )
            if not gate.approved:
                return "rejected:merge:advisory"
            # Human waved the advisory checks through — record each waiver.
            reviewer = gate.reviewer or "human"
            reason = gate.comments or "advisory override"
            overrides = [
                GateOverride(check=n, approved_by=reviewer, reason=reason)
                for n in advisory_blocking
            ]
            self._emit(
                RunEventKind.GATE_DECIDED,
                stage="merge",
                gate="merge",
                round="1",
                policy="soft",
                decided_by=(gate.reviewer or "human"),
                approved="true",
                overrides=",".join(o.check for o in overrides),
            )
            gate_report = await workflow.execute_activity(
                evaluate_gate, QualityGateInput(checks=checks, overrides=overrides), **ACT
            )
        else:
            # 5d. Gate passed clean. MergeVerdict is advisory and ONLY
            # consulted under SOFT policy — it can approve an already-clean
            # build; it can never reach this branch otherwise.
            if cfg.gates.get("merge", GateConfig()).policy == GatePolicy.SOFT:
                verdict: MergeVerdict = (
                    await self._run_role(
                        cfg,
                        "merge_verdict",
                        STAGE_MODELS.get("merge_verdict", "unknown"),
                        t_merge_verdict,
                        merge_verdict_prompt([r.model_dump() for r in done.values()]),
                    )
                ).output
                auto = _auto_decision_for(
                    "merge", cfg, verdict.confidence if verdict.approve else None
                )
                if auto is None:
                    # Soft policy + (negative verdict OR confidence below
                    # threshold) = escalate to human.
                    gate = await self._gate(
                        "merge", cfg.gate_settings(), context=GateContext(checks=gate_report.checks)
                    )
                    if not gate.approved:
                        return "rejected:merge:soft-verdict"

        _ended = workflow.now()
        await self._record(
            cfg,
            self._stage_record(
                cfg,
                stage="merge",
                role="reviewer",
                started=_started,
                ended=_ended,
                quality_score=(1.0 if gate_report.passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.REVISED if overrides else BenchmarkOutcome.PASS),
                model="deterministic",
            ),
        )
        await self._retain(
            cfg,
            MemoryKind.GATE_FEEDBACK,
            cfg.memory.project_bank,
            text=(
                f"merge gate: passed={gate_report.passed} overridden={[o.check for o in overrides]}"
            ),
            metadata={"gate": "merge", "round": "1", "run_id": workflow.info().workflow_id},
        )

        if cfg.benchmark.case_id is not None:
            # Benchmark repos are local scratch checkouts with no `origin`
            # remote and no GitHub host to open a PR against -- pushing
            # would always fail past this point, turning an otherwise
            # clean run into a spurious FeatureWorkflow failure after every
            # real signal (build/lint/security/merge) already passed.
            pr_url = "skipped:benchmark-run-has-no-remote"
        else:
            pr_url = await workflow.execute_activity(
                open_pull_request,
                PROpenInput(
                    worktree=self._integration_wt,
                    title=idea.title,
                    body=arch.overview,
                    base_branch=idea.base_branch,
                ),
                **ACT,
            )

        # 6. DEPLOY gate → DeploymentWorkflow child (E-67/FR-1104)
        _started = workflow.now()
        gate = await self._gate("deploy", cfg.gate_settings())
        _ended = workflow.now()
        if not gate.approved or not cfg.deploy.enabled:
            # The deploy stage did not run: record the gate decision only.
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="deploy",
                    role="devops",
                    started=_started,
                    ended=_ended,
                    quality_score=None,
                    judge="llm_judge",
                    outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
                    model=resolve_role_model(cfg, "devops"),
                ),
            )
            return f"merged-not-deployed:{pr_url}"

        deploy_plan = self._deploy_plan(cfg)
        attempt = 1
        while True:
            report = await workflow.execute_child_workflow(
                DeploymentWorkflow.run,
                DeploymentInput(
                    plan=deploy_plan, cfg=cfg.deploy, repo_path=repo_path, attempt=attempt
                ),
                # Derived, never generated: replay must produce the same id,
                # and a retry round stays identifiable in the Temporal UI.
                id=f"{workflow.info().workflow_id}-deploy-{attempt}",
                task_queue=workflow.info().task_queue,
            )
            if report.deployed:
                # One record, reflecting the actual result -- never a
                # premature PASS from the gate. (SC-5 / E-40: a reading must
                # not read as clean when it was not.)
                await self._record(
                    cfg,
                    self._stage_record(
                        cfg,
                        stage="deploy",
                        role="devops",
                        started=_started,
                        ended=workflow.now(),
                        quality_score=None,
                        judge="contract",
                        outcome=BenchmarkOutcome.PASS,
                        model=resolve_role_model(cfg, "devops"),
                    ),
                )
                self._stage("deployed", "deploy")
                return _deploy_result(report, None, pr_url)

            # The gate opens even when the rollback itself failed -- that is
            # the case a human most needs to see.
            decision = await self._gate(
                "deploy_failed",
                cfg.gate_settings(),
                round=attempt,
                context=GateContext(
                    # ABSOLUTE: the human is not waving a check through --
                    # the rollback already happened. They are deciding what
                    # to do next.
                    checks=[
                        CheckResult(
                            name=c.name,
                            passed=c.passed,
                            classification=CheckClass.ABSOLUTE,
                            detail=c.detail,
                        )
                        for c in report.checks
                    ],
                    verdict=_deploy_verdict(report),
                ),
                default_policy=GatePolicy.HARD,
            )
            if decision.outcome is GateOutcome.REVISE and attempt < cfg.max_gate_rounds:
                attempt += 1
                continue
            # Rolled back or deploy-broken: record FAIL, never the gate's PASS.
            await self._record(
                cfg,
                self._stage_record(
                    cfg,
                    stage="deploy",
                    role="devops",
                    started=_started,
                    ended=workflow.now(),
                    quality_score=None,
                    judge="contract",
                    outcome=BenchmarkOutcome.FAIL,
                    model=resolve_role_model(cfg, "devops"),
                ),
            )
            self._stage("deploy_failed", "deploy")
            return _deploy_result(report, decision, pr_url)
