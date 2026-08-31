"""FeatureWorkflow — idea → deployed feature.

Deterministic orchestration only. All I/O happens in activities or inside
TemporalAgent-managed activities. Human-in-the-loop gates are durable
signal waits with a per-gate policy (hard / soft / off).
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..activities import (
        CodingTaskInput, CoverageInput, DeltaCheckInput, DiffInput,
        IntegrationChecks, IntegrationChecksInput,
        IntegrationHandle, IntegrationInput, LintInput, MergeInput,
        PROpenInput, QAInput, RepoProbeInput, SecurityScanInput, WorktreeInput,
        check_brownfield_delta, classify_repo, create_worktree, evaluate_gate,
        get_task_diff, measure_coverage, merge_into_integration,
        open_pull_request, run_coding_task, run_integration_checks, run_lint,
        run_test_suite, security_scan, setup_integration_branch,
    )
    from ..agents.roles import (
        PROMPT_SHAS, STAGE_MODELS, STAGE_ROLES, t_adversary, t_analyst,
        t_architect, t_clarify, t_clarify_probe, t_clarify_route,
        t_deep_review, t_handoff, t_merge_verdict,
        t_planner, t_qa, t_research, t_reviewer,
    )
    from ..benchmarks.judge import (
        JudgeInput, _build_judge_input, judge_artifact,
    )
    from ..benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope,
        QualityScore, SpeedBag, WasteBag,
    )
    from ..benchmarks.recorder import record_benchmark
    from ..board.activities import (AttachEvidenceInput,
                                    PublishArtifactInput, SetTaskStatusInput,
                                    SyncPlanTasksInput, attach_task_evidence,
                                    publish_artifact_version,
                                    set_task_authoritative, sync_plan_tasks)
    from ..board.models import ArtifactStatus, TaskStatus
    from ..clarify.merge import merge_clarification
    from ..clarify.models import ProbeResult
    from ..clarify.prompts import probe_prompt, probe_prompt_digest
    from ..clarify.routing import grounded_dimensions, live_dimensions
    from ..context.classify import classify
    from ..context.models import CodebaseMap
    from ..context.project import map_digest, project
    from ..context.render import render_for_prompt
    from ..crew.activities import LoadCrewInput, load_crew
    from ..gate import (
        CheckClass, CheckResult, GateOverride, GateReport, QualityGateInput,
        build_check,
    )
    from ..measurement import CollectionState
    from ..memoization.activities import (
        CacheGetInput, CachePutInput, cache_get, cache_put,
    )
    from ..memoization.cache import content_key
    from ..memory.activities import (
        RecallInput, ReflectInput, RetainInput, WatermarkInput,
        capture_watermark, recall_snapshot, reflect, retain,
    )
    from ..observability.activities import RunExportInput, export_run_artifacts
    from ..observability.summary import build_run_summary
    from ..observability.trace import RunEvent, RunEventKind
    from ..observability.usage import cost_bag_from_spend, merge_usage
    from ..pricing import PriceUsageInput, price_usage
    from ..prompts import (analyst_prompt, clarify_prompt,
                           merge_verdict_prompt, planner_prompt, qa_prompt,
                           reviewer_prompt)
    from ..artifacts.retention import (RetentionInput, apply_session_retention,
                                        keep_full_transcripts)
    from ..artifacts.read import LoadSessionInput, load_session
    from ..harness.session import session_text_from_jsonl
    from ..notify.contract import NotifyReason
    from ..models import (
        AnalysisReport, ArchitectureSpec, ArtifactRef, ClarificationDimension,
        ClarifiedRequirements,
        DeferredToolUse, EscalationOutcome, ToolDenial, ToolEscalation, ToolGrant,
        CoverageReport, DeepReviewReport, DeployPlan, DeployReport, DevTask,
        ExecutionMode, Gap, GateConfig,
        GateDecision,
        GateOutcome, GatePolicy, HandoffSummary, IdeaBrief,
        ImplementationPlan, MemoryKind, MergeVerdict, PipelineConfig, PlanDrift,
        ProjectMode,
        RecallSnapshot, ResearchBrief, ResearchPlan, RetainItem, RoleConfig,
        RoleUsage, RunState, RunSummary, SecurityReport, SeededWork, SmokeCheck,
        SubQuestionFinding,
        TaskResult, compute_plan_drift,
    )
    from .crew import FS_ACT, CrewTaskInput, CrewTaskWorkflow
    from .deployment import DeploymentInput, DeploymentWorkflow
    from .gates import GateHost
    from .scanning import scan_tree
    from ..handoff import (
        claim_survival_score, cross_check_claims, verified_integrity_flags,
        verified_plan_deviations,
    )
    from ..pending import GateContext, clarify_pending
    from ..research.deps import ResearchDeps
    from ..research.retain import verified_findings_to_retain
    from ..research.stage import (PlanInput, SubQuestionInput, SynthesizeInput,
                                  plan_research, research_subquestion,
                                  synthesize_brief)
    from ..research.verify import (
        brief_digest, verify_brief_activity,
    )

INTAKE_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
                  retry_policy=RetryPolicy(maximum_attempts=3))
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
# Code-review C2: deterministic substring check — retrying cannot change the
# outcome, so maximum_attempts=1 (no retries). Matches the *_ACT convention.
VERIFY_ACT = dict(
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy=RetryPolicy(maximum_attempts=1),
)
# E-33: pricing is a deterministic local table lookup — retrying cannot
# change the outcome (VERIFY_ACT rationale); the caller treats failure as
# "price unknown", so 1 attempt, short timeout.
PRICE_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                 retry_policy=RetryPolicy(maximum_attempts=1))
# E-32: export is best-effort — a single attempt, no retry hammering (a failing
# export must never change the run's return string).
EXPORT_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
                  retry_policy=RetryPolicy(maximum_attempts=1))

# E-78: the board is NOT best-effort like EXPORT_ACT. Agents read tasks from
# it, so a lost write is a correctness bug, not a missing report. The store's
# writes are idempotent (sync uses ON CONFLICT DO NOTHING), so retrying is
# safe.
BOARD_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                 retry_policy=RetryPolicy(maximum_attempts=5))

# E-30: run_integration_checks runs a real test suite + lint against the merged
# integration head. Generous start_to_close (> the activity's internal test
# 600s + fallback 600s + lint 300s worst case); 2 attempts like the per-task
# test run. It does not heartbeat, so no heartbeat_timeout.
INTEG_ACT = dict(start_to_close_timeout=timedelta(minutes=30),
        retry_policy=RetryPolicy(maximum_attempts=2))

# Fan-out research. Durations follow the shape measured by the prior art:
# planning is short and schema-constrained; a sub-question runs a full agent
# with search and page fetches and legitimately takes minutes.
RESEARCH_PLAN_ACT = dict(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=3))
# The heartbeat is the important knob. A sub-question can run for many
# minutes, so without heartbeating the server waits out the full
# start_to_close before rescheduling a lost worker; with it, ~60s.
# Invariant: stage.HEARTBEAT_INTERVAL_SECONDS < heartbeat_timeout <
# start_to_close_timeout.
RESEARCH_SQ_ACT = dict(
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
        non_retryable_error_types=["BudgetExceeded", "UsageLimitExceeded"]))
RESEARCH_SYNTH_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3))


def resolve_role_model(cfg: "PipelineConfig", stage: str) -> str:
    """The model this run uses for `stage`. A per-run override in cfg.roles
    (keyed by the registry ROLE name) wins; otherwise the registry default
    (STAGE_MODELS[stage]). Keyed by stage because STAGE_ROLES is the one place
    stage↔role divergence is reconciled."""
    role = STAGE_ROLES[stage]
    rc = cfg.roles.get(role)
    if rc is not None and rc.model is not None:
        return rc.model
    return STAGE_MODELS[stage]


def _probe_results_from(
    dimensions: "Sequence[ClarificationDimension]",
    results: "Sequence[object]",
) -> list["ProbeResult"]:
    """Pair each probed dimension with its result, discarding the dead ones.

    An exception means the probe never produced an answer, so the dimension
    is ABSENT from the output -- and therefore absent from dimensions_probed,
    which is what distinguishes "never ran" from "ran and abstained".

    The asked-for dimension overrides whatever the model reported: the burst
    knows which probe it dispatched, and a mislabelled result would attribute
    questions to a dimension that never ran.
    """
    out: list[ProbeResult] = []
    for dim, res in zip(dimensions, results):
        if isinstance(res, BaseException):
            continue
        out.append(res if res.dimension is dim
                   else res.model_copy(update={"dimension": dim}))
    return out


def _clarify_memo_extra(cfg: "PipelineConfig",
                        codebase_map: "CodebaseMap | None") -> str:
    """The E-85 terms appended to the clarify stage's memo input.

    Empty when the fan-out is off, so a flag-off run keys exactly as it did
    pre-E-85 and its existing memos keep hitting. That emptiness is the
    whole "the default pipeline is byte-identical to today" guarantee, so it
    lives in a helper a test can pin rather than inline in the stage.

    On, three terms, each covering something the base key cannot see:
      - the probe-prompt digest, or editing a probe serves a stale
        clarification silently;
      - the codebase-map digest, or a clarification grounded in a tree
        survives that tree changing;
      - the question cap, which decides which questions reach a human and
        which land on `dropped`. Spec section 10 names it as the first knob
        the benchmark tunes, so a memo made under a different cap is a
        differently shaped artifact, not the same one.
    """
    if not cfg.clarify_probes_enabled:
        return ""
    digest = map_digest(codebase_map) if codebase_map is not None else "none"
    return (f"|e85:{probe_prompt_digest()}|map:{digest}"
            f"|cap:{cfg.clarify_question_cap}")


async def _clarify_fanout(run_role, *, route_agent, probe_agent,
                          route_prompt: str, idea_json: str, grounding: str,
                          mode: "ProjectMode", cap: int):
    """The E-85 clarify orchestration: route, fan out, merge.

    Module-level and collaborator-injected so the orchestration is testable
    without Temporal: `run_role(agent, prompt)` is the caller's already-bound
    model-egress point (self._run_role with cfg / role / model / `into`
    applied) and returns an AgentRunResult.

    `route_prompt` carries NO map content. ROUTE_SCOPE tells the supervisor
    it cannot read the codebase; handing it one anyway contradicts its own
    instructions. It learns greenfield-vs-brownfield from idea.mode inside
    idea_json, and live_dimensions enforces the mode narrowing in code
    regardless of what the model asks for.
    """
    route = (await run_role(route_agent, route_prompt)).output
    dims = live_dimensions(route.live_dimensions, mode)
    reqs_json = route.model_dump_json()

    async def _probe(d):
        return (await run_role(probe_agent, probe_prompt(
            d, idea_json=idea_json, requirements_json=reqs_json,
            grounding=grounding))).output

    # return_exceptions=True IS the degrade-alone rule here: a probe that
    # times out, loses its worker or exhausts its BOUNDED retries (see
    # CLARIFY_FANOUT_ACTIVITY_CONFIG -- without a maximum_attempts Temporal
    # would retry forever and this gather would never return) raises inside
    # its own coroutine and gather captures it, leaving every sibling's
    # result intact. _probe_results_from turns each captured exception into
    # a dropped dimension.
    results = await asyncio.gather(*[_probe(d) for d in dims],
                                   return_exceptions=True)
    return merge_clarification(route, _probe_results_from(dims, results),
                               cap=cap, grounded=grounded_dimensions(mode))


def _requirements_for_downstream(reqs: "ClarifiedRequirements") -> str:
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


def _deploy_result(report: "DeployReport", decision: "GateDecision | None",
                   pr_url: str) -> str:
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


def _deploy_verdict(report: "DeployReport") -> str:
    """What the deploy_failed gate renders. The rollback reason plus, when
    available, the deploy command's own output -- without it the human
    deciding what to do next never sees what the apply actually produced
    (F4: the common smoke-fails case)."""
    if report.apply_detail.strip():
        return (f"{report.rollback_reason}\n\nDeploy output:\n"
                f"{report.apply_detail}")
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


class _BudgetRejected(Exception):
    """Raised at a budget-gate reject; caught in run() so the terminal
    outcome is the ordinary string "rejected:budget" and retro still runs."""


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
        gaps=[Gap(sub_question_id="research-stage",
                  what_is_missing="the research stage did not complete",
                  why_it_matters=str(exc))],
        summary=f"Research stopped early: {exc}")


def _findings_from_results(subs: list[SubQuestion],
                           results: list) -> list[SubQuestionFinding]:
    """Turn gather(..., return_exceptions=True) output into findings.

    Sub-questions are INDEPENDENT -- that is the premise of the fan-out. Letting
    one exception propagate would cancel the gather and discard every sibling
    finding already paid for. A partial brief from three of four sub-questions
    is worth far more than nothing, so a failure becomes a failed finding that
    the merge turns into a Gap."""
    out: list[SubQuestionFinding] = []
    for sub, result in zip(subs, results):
        if isinstance(result, BaseException):
            out.append(SubQuestionFinding(
                sub_question=sub, failed=True, error=str(result)))
        else:
            out.append(result)
    return out


def _should_refine(round_n: int, cfg: "ResearchConfig") -> bool:
    """Whether a REVISE at `round_n` gets another wave. Exhaustion is NOT a
    rejection -- the stage proceeds with the brief it has."""
    return round_n <= cfg.max_refine_rounds


def _refine_seed(brief: "ResearchBrief") -> tuple[list, list]:
    """What round two should target: everything round one could not resolve.

    Richer than a free-text note, because the SGR brief already carries the
    machine-readable version. Resolved contradictions are excluded -- they are
    answered, and re-researching them spends the run ceiling on finished work."""
    return list(brief.gaps), [c for c in brief.contradictions if c.unresolved]


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
        for label, claims in (("did", h.what_changed),
                              ("decided", h.decisions_made),
                              ("concerns", h.open_concerns)):
            if claims:
                parts.append(f"{label}: " + "; ".join(c.text for c in claims))
        if parts:
            notes.append(f"- {h.task_id}: " + " | ".join(parts))
    return notes


def _fix_loop_issues(qa, qa_raw, review, adversary=None) -> str:
    """Assemble the retry prompt's issue list from BOTH judges.

    The task gate anchors on `qa_raw.tests_passed` — the subprocess exit code
    — because an LLM opinion must never overwrite a deterministic signal. The
    retry prompt has to carry that same evidence, or the agent is asked to fix
    something it cannot see: a clean-context QA that judges the diff
    contract-compliant while pytest is red leaves the LLM-side issue list
    empty, and the fix loop then sends `Fix them:\\n- ` with nothing after the
    dash (bench-todo-api-greenfield-1785444047: 8 of 12 attempts burned
    re-confirming the stack directive while the real ModuleNotFoundError was
    never shown). Returns "" when neither judge has anything actionable —
    callers must treat that as a harness fault, not another attempt.

    `adversary` is the optional decorrelated second opinion (spec part 2).
    Its blocking findings join the primary's, because on a split the primary
    approved and contributed nothing -- without the union the retry prompt
    would carry no instruction at all."""
    deterministic: list[str] = []
    if not qa_raw.tests_passed:
        if qa_raw.issues:
            deterministic.append(
                "test command failed:\n"
                + "\n".join(qa_raw.issues)[-_TEST_OUTPUT_MAX:])
        if qa_raw.failing_tests:
            deterministic.append(
                "failing tests: " + ", ".join(qa_raw.failing_tests[:25]))
        if qa_raw.stopped_early:
            # Without this the agent reads a truncated run as the whole
            # story and starts fixing the one test it was shown. In the P2
            # demonstration that test was unrelated to every task that
            # attacked it, and the tasks' own tests -- sorting after it --
            # never ran at all.
            deterministic.append(
                "NOTE: the test run STOPPED EARLY (-x / --maxfail), so tests "
                "ordered after the failure above did not run. This is a "
                "partial result, not a verdict on your work: the failure "
                "shown may be unrelated to your task, and your own tests may "
                "not have executed. Check whether it is yours before "
                "changing it.")
    review_issues = [
        f"{f.severity}: {f.assertion} — {f.detail}"
        for r in (review, adversary) if r is not None
        for f in r.blocking_findings
    ]
    return "\n- ".join(
        list(qa.issues or qa.failing_tests) + deterministic + review_issues)


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
            return (f"task {t.id!r} depends on unknown task id(s) "
                    f"{unknown!r}")

    by_id = {t.id: t for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(ids, WHITE)

    def visit(tid: str, path: list[str]) -> str | None:
        color[tid] = GRAY
        for dep in by_id[tid].depends_on:
            if color[dep] == GRAY:
                cycle = path[path.index(dep):] + [dep]
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


def _spec_summary(artifact: object) -> str:
    """Best-effort one-field summary of a proposer artifact for gate render.
    ClarifiedRequirements has `summary`; ArchitectureSpec has `overview`;
    fall back to the type name so the field is never empty."""
    return (getattr(artifact, "summary", None)
            or getattr(artifact, "overview", None)
            or type(artifact).__name__)


def escalations_from_denials(denials: list[ToolDenial]) -> list[ToolEscalation]:
    """Denials the hook could not escalate (batched call, unreadable
    transcript). No human was asked, so there is no gate and no round — but
    they must still be countable, or the size of the solo-only hole would be
    invisible (E-17 §6)."""
    return [ToolEscalation(tool=d.tool, rule_id=d.rule_id, target=d.target,
                           outcome=EscalationOutcome.BATCHED)
            for d in denials if d.escalation_declined]


def _escalation_summary(task_id: str, title: str,
                        deferred: DeferredToolUse) -> str:
    """What the human is actually deciding, rendered into the GateContext
    field the E-6 channel contract already renders (the same way the budget
    gate puts its cost table there)."""
    return (f"Task {task_id} ({title}) is blocked on a tool call.\n"
            f"  tool:   {deferred.tool}\n"
            f"  target: {deferred.target or '(none)'}\n"
            f"  rule:   {deferred.rule_id} — {deferred.reason}\n"
            "Approve to permit exactly this one call; reject to refuse it "
            "(the task continues either way).")


@workflow.defn
class FeatureWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._question_answers: dict[str, str] = {}
        self._memory_watermark: str | None = None
        # E-42: cfg is threaded as a parameter everywhere else; the gate hooks
        # run inside GateHost and cannot receive it, so run() stashes it here.
        self._cfg: PipelineConfig | None = None
        # E-10: run_state() needs the brief and the start time, which are
        # run() parameters/locals everywhere else -- same reason _cfg is
        # stashed here rather than threaded.
        self._idea: IdeaBrief | None = None
        self._started_at: datetime | None = None
        # run_state() is unit-tested on bare instances (no workflow event
        # loop, where workflow.info() raises), so run() stashes the id --
        # the run_summary query likewise reads only stashed state.
        self._run_id: str = ""
        # ADR-14: one sdlc/<run_id>/integration branch accumulates completed
        # task work. _integration_head advances after each successful merge;
        # _integration_wt is the worktree path (set once at run start, stable).
        self._integration_head: str | None = None
        self._integration_wt: str | None = None
        # E-32: append-only domain trace; source for RunSummary + events.jsonl.
        self._trace: list[RunEvent] = []
        self._seq: int = 0
        self._run_summary: RunSummary | None = None
        # E-38: session refs collected per coding attempt; retro applies
        # the OQ-B7 retention policy over them.
        self._session_refs: list[ArtifactRef] = []
        # E-33: per-role spend accumulated across the run; budget state.
        self._role_usage: dict[str, RoleUsage] = {}
        self._budget_threshold: float = 0.0
        self._budget_crossings: int = 0
        # E-17: monotonic gate round for tool-approval escalations. ONE
        # counter for the whole run: _dev_task runs concurrently across tasks
        # in wave mode, and workflow code is single-threaded, so a shared
        # counter keeps (gate, round) unique and replay-deterministic where a
        # per-task round would collide.
        self._escalation_round: int = 0
        # E-78: surrogate artifact_version.id of the current plan, captured
        # when the plan stage publishes. Task board writes key off it.
        self._plan_version: int | None = None
        # E-84: stage 2 codebase map for brownfield runs (None for greenfield).
        self._codebase_map: CodebaseMap | None = None

    # ----------------------- benchmark recording ------------------------

    @staticmethod
    def _benchmarking(cfg: PipelineConfig) -> bool:
        return bool(cfg.benchmark and cfg.benchmark.case_id)

    def _stage_record(self, cfg: PipelineConfig, stage: str, role: str,
                      started: datetime, ended: datetime,
                      quality_score: float | None, judge: str,
                      outcome: BenchmarkOutcome, model: str,
                      harness=None, cost_usd: float | None = None,
                      spend: RoleUsage | None = None,
                      fix_attempts: int = 0,
                      task_id: str | None = None,
                      attempt: int | None = None,
                      waste: "WasteBag | None" = None,
                      plan_drift: "PlanDrift | None" = None,
                      error: str | None = None) -> BenchmarkRecord:
        scope = (BenchmarkScope.TASK_ATTEMPT if task_id is not None
                 else BenchmarkScope.STAGE)
        return BenchmarkRecord(
            run_id=workflow.info().workflow_id,
            bench_run_id=cfg.benchmark.bench_run_id or "_unknown",
            case_id=cfg.benchmark.case_id or "_unknown",
            scope=scope, stage=stage, task_id=task_id, attempt=attempt,
            role=role, harness=harness, model=model, prompt_sha="",
            quality=QualityScore(score=quality_score, judge=judge),
            cost=cost_bag_from_spend(spend, cost_usd),
            speed=SpeedBag(wall_clock_s=(ended - started).total_seconds(),
                           started_at=started, ended_at=ended),
            waste=waste,
            plan_drift=plan_drift,
            outcome=outcome, fix_attempts=fix_attempts, error=error,
        )

    # ----------------------- board (E-78) -------------------------------

    async def _board_publish(self, cfg: PipelineConfig, key: str,
                             content_json: str, *, approved: bool = True
                             ) -> int:
        """Publish one project artifact version. A rejected gate still writes
        history — the pointer just does not move."""
        run_id = workflow.info().workflow_id
        result = await workflow.execute_activity(
            publish_artifact_version,
            PublishArtifactInput(
                project=cfg.project_key, key=key, run_id=run_id,
                content_json=content_json, actor=f"workflow:{run_id}",
                status=(ArtifactStatus.CURRENT if approved
                        else ArtifactStatus.REJECTED)),
            **BOARD_ACT)
        return result.version_id

    async def _board_sync_tasks(self, cfg: PipelineConfig,
                                plan_version: int,
                                tasks: list[DevTask]) -> None:
        run_id = workflow.info().workflow_id
        await workflow.execute_activity(
            sync_plan_tasks,
            SyncPlanTasksInput(
                project=cfg.project_key, plan_version=plan_version,
                run_id=run_id, tasks=tasks, actor=f"workflow:{run_id}"),
            **BOARD_ACT)

    async def _board_task_status(self, cfg: PipelineConfig, task_id: str,
                                 status: TaskStatus, *,
                                 fix_attempts: int | None = None,
                                 error: str | None = None,
                                 branch: str | None = None) -> None:
        if self._plan_version is None:
            return                      # no plan published (early rejection)
        run_id = workflow.info().workflow_id
        await workflow.execute_activity(
            set_task_authoritative,
            SetTaskStatusInput(
                project=cfg.project_key, plan_version=self._plan_version,
                task_id=task_id, status=status, actor=f"workflow:{run_id}",
                fix_attempts=fix_attempts, error=error, branch=branch),
            **BOARD_ACT)

    async def _board_evidence(self, cfg: PipelineConfig, task_id: str,
                              kind: str, content_json: str) -> None:
        if self._plan_version is None:
            return
        await workflow.execute_activity(
            attach_task_evidence,
            AttachEvidenceInput(
                project=cfg.project_key, plan_version=self._plan_version,
                task_id=task_id, run_id=workflow.info().workflow_id,
                kind=kind, content_json=content_json),
            **BOARD_ACT)

    # ----------------------- benchmark recording ------------------------

    async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord
                      ) -> None:
        self._emit(
            RunEventKind.STAGE_ENDED, stage=record.stage,
            role=record.role, outcome=record.outcome.value,
            duration_s=str(record.speed.wall_clock_s),
            fix_attempts=str(record.fix_attempts),
            **({"cost_usd": str(record.cost.usd)}
               if record.cost.usd is not None else {}))
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
            vetoes=cfg.benchmark.vetoes,
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

    async def _on_gate_awaited(self, name: str, round: int) -> None:
        self._emit(RunEventKind.GATE_AWAITED, stage=name,
                   gate=name, round=str(round))

    async def _on_gate_decided(self, name: str, round: int,
                               policy: GatePolicy, decision: GateDecision,
                               confidence: float | None = None) -> None:
        conf = confidence
        self._emit(
            RunEventKind.GATE_DECIDED, stage=name,
            gate=name, round=str(round), policy=policy.value,
            decided_by=decision.decided_by,
            approved=("true" if decision.approved else "false"),
            **({"confidence": str(conf)} if conf is not None else {}))
        cfg = self._cfg
        if cfg is None:
            return
        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=f"gate {name}#{round}: {decision.outcome.value}"
                f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "round": str(round),
                      "run_id": workflow.info().workflow_id})

    async def _on_notified(self, gate: str, reason: NotifyReason,
                           notifier: str, delivered: bool,
                           error: str = "") -> None:
        self._emit(RunEventKind.GATE_NOTIFIED, stage=gate, gate=gate,
                   reason=reason.value, notifier=notifier,
                   delivered="true" if delivered else "false",
                   **({"error": error} if error else {}))

    async def _cached_stage(self, cfg: PipelineConfig, stage: str,
                            input_json: str,
                            output_type: type, run_fn) -> tuple[object, bool]:
        """Skips `run_fn()` (a no-arg async callable invoking the proposer
        agent) when an identical (stage, input, prompt, model,
        upstream-recall-watermark) combination was already computed — the
        ADR-5 dev-loop cache. Returns (output, was_cache_hit).

        The stage's model is resolved per-run (resolve_role_model): a per-role
        override MUST move the key, or a stale result computed by a different
        model would be served."""
        if not cfg.memoization_enabled:
            return await run_fn(), False
        key = content_key(stage, input_json, PROMPT_SHAS[stage],
                          resolve_role_model(cfg, stage),
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
    # E-42: submit_gate_decision / status / pending_gate / pending_decisions
    # moved to GateHost. answer_question stays here -- clarify is a
    # feature-pipeline concept, and the triage workflow has no questions.

    @workflow.signal
    def answer_question(self, question_id: str, answer: str) -> None:
        self._question_answers.setdefault(question_id, answer)
        self._pending.pop(question_id, None)

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
        priced = [u.cost_usd for u in self._role_usage.values()
                  if u.cost_usd is not None]
        budget = (self._cfg.run_budget_usd
                  if self._cfg and self._cfg.run_budget_usd > 0 else None)
        stage = next((e.stage for e in reversed(self._trace)
                      if e.kind is RunEventKind.STAGE_STARTED), None)
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

    def _emit(self, kind: RunEventKind, stage: str | None = None,
              **data: str) -> None:
        """Append a domain event to the run trace. Pure state mutation — safe
        in workflow code (no I/O, deterministic seq + workflow.now())."""
        self._trace.append(RunEvent(seq=self._seq, at=workflow.now(),
                                    kind=kind, stage=stage, data=data))
        self._seq += 1

    def _stage(self, status: str, trace: str | None = None) -> None:
        """Record stage start: _status keeps the run's status vocabulary
        (status() query consumers), while the STAGE_STARTED trace event uses
        the canonical stage nouns -- the same vocabulary STAGE_ENDED,
        run_summary.terminal_stage, and the dashboard's CANONICAL_STAGES
        (benchmarks/heatmap.py) already speak. Two vocabularies in one trace
        is how the fleet view and the benchmarks come to disagree."""
        self._status = status
        self._emit(RunEventKind.STAGE_STARTED, stage=trace or status)

    def _track_usage(self, *, role: str, model: str,
                     input_tokens: int = 0, output_tokens: int = 0,
                     cache_read_tokens: int = 0, cache_write_tokens: int = 0,
                     cost_usd: float | None = None,
                     into: RoleUsage | None = None) -> None:
        """Fold one model call into the run's per-role accumulator and emit
        a MODEL_USAGE event. Pure state mutation — safe in workflow code.
        `into` additionally folds the same delta into a caller-held bag
        (per-stage benchmark records)."""
        bag = self._role_usage.setdefault(
            role, RoleUsage(role=role, model=model))
        for target in (bag, into) if into is not None else (bag,):
            merge_usage(target, model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read_tokens=cache_read_tokens,
                        cache_write_tokens=cache_write_tokens,
                        cost_usd=cost_usd)
        self._emit(
            RunEventKind.MODEL_USAGE, role=role, model=model, calls="1",
            input_tokens=str(input_tokens), output_tokens=str(output_tokens),
            cache_read_tokens=str(cache_read_tokens),
            cache_write_tokens=str(cache_write_tokens),
            **({"cost_usd": str(cost_usd)} if cost_usd is not None else {}))

    async def _run_role(self, cfg: PipelineConfig, role: str, model: str,
                        agent, *args, into: RoleUsage | None = None,
                        **kwargs):
        """E-33 single model-egress point (folds E-19): run a proposer
        agent, capture its usage, price it (replay-safe: in an activity),
        accumulate per role. Returns the AgentRunResult — callers keep
        taking .output. Pricing failure of ANY kind degrades to usd=None;
        it must never fail the stage."""
        result = await agent.run(*args, **kwargs)
        u = result.usage
        usd: float | None = None
        if u.input_tokens or u.output_tokens:
            try:
                usd = await workflow.execute_activity(
                    price_usage,
                    PriceUsageInput(
                        model=model,
                        input_tokens=u.input_tokens or 0,
                        output_tokens=u.output_tokens or 0,
                        cache_read_tokens=u.cache_read_tokens or 0,
                        cache_write_tokens=u.cache_write_tokens or 0),
                    **PRICE_ACT)
            except Exception:
                usd = None
        self._track_usage(
            role=role, model=model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=u.cache_read_tokens or 0,
            cache_write_tokens=u.cache_write_tokens or 0,
            cost_usd=usd, into=into)
        return result

    async def _fan_out_research(self, cfg: PipelineConfig, idea,
                                deps: "ResearchDeps",
                                spend: RoleUsage,
                                id_offset: int = 0,
                                guidance: str = "",
                                gaps: list | None = None,
                                contradictions: list | None = None
                                ) -> list[SubQuestionFinding]:
        """One wave: plan -> N parallel sub-questions. The caller synthesizes
        a brief over the returned findings.

        Returns the raw per-sub-question findings so a refine round can
        EXTEND the finding list rather than discarding round one."""
        model = STAGE_MODELS.get("research", "unknown")

        plan: ResearchPlan = await workflow.execute_activity(
            plan_research,
            PlanInput(idea_json=idea.model_dump_json(),
                      max_sub_questions=cfg.research.max_sub_questions,
                      model=model, id_offset=id_offset, guidance=guidance,
                      gaps=gaps or [], contradictions=contradictions or []),
            **RESEARCH_PLAN_ACT)
        await self._fold_research_usage(cfg, plan.usage, spend)

        # THE fan-out. return_exceptions=True because the sub-questions are
        # independent: one failure must not cancel the gather and throw away
        # siblings already paid for.
        results = await asyncio.gather(*[
            workflow.execute_activity(
                research_subquestion,
                SubQuestionInput(
                    sub_question=sq, deps=deps, model=model,
                    max_requests=cfg.research.max_requests,
                    max_run_cost_usd=cfg.research.max_run_cost_usd),
                **RESEARCH_SQ_ACT)
            for sq in plan.sub_questions
        ], return_exceptions=True)

        findings = _findings_from_results(plan.sub_questions, results)
        for f in findings:
            await self._fold_research_usage(cfg, f.usage, spend)
        return findings

    async def _fold_research_usage(self, cfg: PipelineConfig,
                                   usage: RoleUsage,
                                   into: RoleUsage) -> None:
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
                    cache_write_tokens=usage.cache_write_tokens),
                **PRICE_ACT)
        except Exception:
            usd = None
        self._track_usage(
            role="research", model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=usd, into=into)

    async def _run_deep_review(self, cfg, run, contract, assertions, diff,
                               task) -> "DeepReviewReport | None":
        """E-39 advisory lens: read the SCRUBBED harness transcript as data and
        emit a DeepReviewReport. Recorded + retained for signal ONLY — never
        consulted in the task's success condition. Once per task, over the
        final HarnessRunResult. Best-effort: any failure returns None so an
        observability lens can never fail delivery."""
        if not (cfg.deep_review_enabled and t_deep_review is not None
                and run is not None and run.session_ref is not None):
            return None
        _started = workflow.now()
        try:
            loaded = await workflow.execute_activity(
                load_session, LoadSessionInput(ref=run.session_ref), **ACT)
            # Code review #1: render the plain-text view both prompts and the
            # verifier ground on -- raw JSONL would drop legitimate evidence.
            transcript = session_text_from_jsonl(loaded.text) + (
                f"\n[transcript truncated; digest follows]\n"
                f"{run.session_digest.model_dump_json()}"
                if loaded.truncated and run.session_digest is not None else "")
            spend = RoleUsage(role="deep_review", model=resolve_role_model(cfg, "deep_review"))
            report = (await self._run_role(
                cfg, "deep_review", resolve_role_model(cfg, "deep_review"), t_deep_review,
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nThe task as planned:\n{task.model_dump_json()}"
                + f"\nDiff:\n{diff['patch']}"
                + "\nScrubbed harness transcript (how the diff was reached):\n"
                + transcript, into=spend)).output
            # E-43: an accusation must point at a line the transcript
            # contains. Verified against `transcript`, the same bytes the
            # lens itself read. Dropping, never failing -- this lens must
            # never fail delivery.
            kept_flags, dropped_flags = verified_integrity_flags(
                report.integrity_flags, transcript)
            if dropped_flags:
                workflow.logger.warning(
                    "deep_review: dropped %d integrity flag(s) for task %s "
                    "whose evidence is not in the transcript",
                    dropped_flags, task.id)
            kept_devs, dropped_devs = verified_plan_deviations(
                report.plan_deviations, transcript)
            if dropped_devs:
                workflow.logger.warning(
                    "deep_review: dropped %d plan deviation(s) for task %s "
                    "whose evidence is not in the transcript",
                    dropped_devs, task.id)
            report = report.model_copy(update={
                "integrity_flags": kept_flags,
                "plan_deviations": kept_devs})
            await self._record(cfg, self._stage_record(
                cfg, stage="deep_review", role="deep_review",
                started=_started, ended=workflow.now(),
                quality_score=(0.0 if report.cheat_detected or not report.approve
                               else 1.0),
                judge="deep_review",
                outcome=(BenchmarkOutcome.FAIL if report.cheat_detected
                         else BenchmarkOutcome.PASS),
                model=resolve_role_model(cfg, "deep_review"), spend=spend,
                task_id=task.id))
            if report.cheat_detected:
                await self._retain(
                    cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                    text=f"deep_review flagged task {task.id}: "
                         + "; ".join(f"{f.kind}: {f.detail}"
                                     for f in report.integrity_flags),
                    metadata={"task_id": task.id,
                              "run_id": workflow.info().workflow_id})
        except Exception:
            # A lens must never fail delivery -- but a silent swallow is how
            # the judge-Literal defect survived unnoticed across every run.
            workflow.logger.warning(
                "deep_review lens failed for task %s; continuing without it",
                task.id, exc_info=True)
            return None
        return report

    async def _run_adversary(self, cfg, contract, assertions, diff, qa_raw,
                             task) -> "ReviewReport | None":
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
            report = (await self._run_role(
                cfg, "adversary", model, t_adversary,
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nTest results: {qa_raw.model_dump_json()}"
                + f"\nDiff:\n{diff['patch']}",
                into=spend)).output
            await self._record(cfg, self._stage_record(
                cfg, stage="adversary", role="adversary",
                started=_started, ended=workflow.now(),
                quality_score=(1.0 if report.approve else 0.0),
                judge="adversary",
                outcome=(BenchmarkOutcome.PASS if report.approve
                         else BenchmarkOutcome.FAIL),
                model=model, spend=spend, task_id=task.id,
                fix_attempts=0))          # cause row: volume lives on code/qa
            if not report.approve:
                await self._retain(
                    cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                    text=f"adversary split from reviewer on task {task.id}: "
                         + "; ".join(f"{f.assertion}: {f.detail}"
                                     for f in report.blocking_findings),
                    metadata={"task_id": task.id,
                              "run_id": workflow.info().workflow_id})
            return report
        except Exception:
            workflow.logger.warning(
                "adversary lens failed for task %s; treating as agreement",
                task.id, exc_info=True)
            return None

    async def _run_handoff(self, cfg, run, contract, assertions, diff,
                           task) -> "HandoffSummary":
        """FR-805: extract task-to-task claims from the scrubbed session.

        files_touched is filled HERE from the diff, never by the model, so
        the extractor structurally cannot misreport which files changed.
        Best-effort: any failure returns the mechanical handoff rather than
        failing a task that already passed.
        """
        files = diff["files"]
        fallback = HandoffSummary(task_id=task.id, files_touched=files)
        if not (t_handoff is not None and run is not None
                and run.session_ref is not None):
            return fallback
        _started = workflow.now()
        try:
            loaded = await workflow.execute_activity(
                load_session, LoadSessionInput(ref=run.session_ref), **ACT)
            model = resolve_role_model(cfg, "handoff")
            spend = RoleUsage(role="handoff", model=model)
            # Code review #1: the store holds JSONL, but the prompt elicits
            # prose evidence and the verifier must ground on the SAME bytes the
            # model saw -- so both consume the rendered plain-text view, not
            # raw JSONL (which would drop every legitimate claim).
            session_text = session_text_from_jsonl(loaded.text)
            out = (await self._run_role(
                cfg, "handoff", model, t_handoff,
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nDiff:\n{diff['patch']}"
                + "\nScrubbed harness transcript:\n" + session_text,
                into=spend)).output

            kept_total = 0
            dropped_total = 0
            fields = {}
            for name in ("what_changed", "decisions_made", "open_concerns"):
                checked = cross_check_claims(
                    getattr(out, name), files, session_text=session_text)
                fields[name] = checked.kept
                kept_total += len(checked.kept)
                dropped_total += checked.dropped_paths + checked.dropped_quotes

            handoff = HandoffSummary(task_id=task.id, files_touched=files,
                                     **fields)
            await self._record(cfg, self._stage_record(
                cfg, stage="handoff", role="handoff",
                started=_started, ended=workflow.now(),
                # .value is None when no claims were extracted, which is
                # exactly what quality_score must carry -- never a 0.0.
                quality_score=claim_survival_score(
                    kept_total, dropped_total).value,
                judge="handoff", outcome=BenchmarkOutcome.PASS,
                model=model, spend=spend, task_id=task.id,
                fix_attempts=0))
            return handoff
        except Exception:
            workflow.logger.warning(
                "handoff extraction failed for task %s; using mechanical "
                "handoff", task.id, exc_info=True)
            return fallback

    async def _record_escalation(self, cfg: PipelineConfig, task: DevTask,
                                 esc: ToolEscalation) -> None:
        """Trace event (events.jsonl / report.html) plus a benchmark record
        so E-36's case x stage heatmap sees approval friction."""
        self._emit(RunEventKind.TOOL_ESCALATION, stage="tool_approval",
                   task_id=task.id, tool=esc.tool, rule_id=esc.rule_id,
                   outcome=esc.outcome.value, decided_by=esc.decided_by,
                   round=str(esc.round),
                   **({"target": esc.target} if esc.target else {}))
        now = workflow.now()
        # `judge` is a constrained Literal on QualityScore — "policy" is not a
        # member. A gate-decided outcome is a human override; a capped or
        # batched one was decided deterministically, with nobody asked.
        judge = "human_override" if esc.decided_by == "human" else "contract"
        await self._record(cfg, self._stage_record(
            cfg, stage="tool_approval", role="human",
            started=now, ended=now,
            quality_score=None, judge=judge,
            outcome=(BenchmarkOutcome.PASS
                     if esc.outcome is EscalationOutcome.APPROVED
                     else BenchmarkOutcome.ESCALATED),
            model="human", task_id=task.id))

    async def _check_budget(self, cfg: PipelineConfig) -> None:
        """E-33/FR-701 run-budget enforcement. Called at SERIAL points only
        (stage boundaries + the task loop after merges) — never inside a
        wave-mode gather, so gate rounds cannot race. Approve grants one
        more increment; the while-loop re-gates a spend that jumped
        multiple increments at once."""
        if cfg.run_budget_usd <= 0:
            return
        total = sum(u.cost_usd or 0.0 for u in self._role_usage.values())
        while total >= self._budget_threshold:
            self._budget_crossings += 1
            rows = "\n".join(
                f"  {u.role} ({u.model}): ${u.cost_usd:.4f}"
                for u in self._role_usage.values()
                if u.cost_usd is not None)
            decision = await self._gate(
                "budget", cfg.gate_settings(), round=self._budget_crossings,
                context=GateContext(spec_summary=(
                    f"Run cost ${total:.4f} >= budget "
                    f"${self._budget_threshold:.2f}\n{rows}")),
                default_policy=GatePolicy.HARD)
            if decision.outcome is not GateOutcome.APPROVE:
                # REVISE has nothing to revise here — any non-approve
                # terminates (spec §5).
                raise _BudgetRejected()
            self._budget_threshold += cfg.run_budget_usd

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
            checks.append(SmokeCheck(name="liveness", kind="http",
                                     path="/health"))
        return DeployPlan(
            environment="staging",
            version=_sanitize_tag(workflow.info().workflow_id),
            smoke_checks=checks,
        )

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
            decision = await self._gate(
                name, cfg.gate_settings(), auto_decision=auto, round=round,
                context=GateContext(spec_summary=_spec_summary(artifact)),
                confidence=getattr(artifact, "confidence", None))
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
        # Exhausted: one final HARD gate decides accept-anyway vs abandon.
        artifact = await run_fn(guidance)
        decision = await self._gate(
            name, cfg.gate_settings(), round=cfg.max_gate_rounds + 1,
            context=GateContext(spec_summary=_spec_summary(artifact)))
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
        handoff_notes = _handoff_notes(prior_handoffs)
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

        crew_layout = crew_roles = None
        crew_sessions: dict[str, str] = {}
        if role_cfg.harness is HarnessKind.CREW:
            crew_layout, crew_roles = await workflow.execute_activity(
                load_crew, LoadCrewInput(layout=role_cfg.layout or "code",
                                         lead_harness=role_cfg.lead_harness,
                                         lead_model=role_cfg.model),
                **FS_ACT)

        session_id: str | None = None
        resumes = 0
        run = None
        attempt = 0
        # Attempts available before the escalation gate fires. A REVISE at
        # that gate grants exactly one more (see the escalation below), the
        # same "one producer re-run per round" rule _revisable_stage applies
        # to the stage gates.
        budget = cfg.max_fix_attempts + 1
        gate_round = 0
        while True:
            attempt += 1
            _attempt_started = workflow.now()
            self._emit(RunEventKind.FIX_ATTEMPT, stage="code",
                       task_id=task.id, attempt=str(attempt))
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
                    crew = await workflow.execute_child_workflow(
                        CrewTaskWorkflow.run,
                        CrewTaskInput(
                            layout=crew_layout.layout, lead=crew_layout.lead,
                            roles=crew_roles, prompt=prompt,
                            worktree=worktree, task_id=task.id,
                            attempt=attempt,
                            deliverable_path=crew_layout.deliverable.path,
                            rounds_max=crew_layout.rounds.max,
                            wall_clock_s=crew_layout.limits.wall_clock_s,
                            turn_timeout_s=crew_layout.limits.turn_timeout_s,
                            cost_usd=crew_layout.limits.cost_usd,
                            sessions=crew_sessions,
                            containment_enabled=cfg.containment_enabled,
                            containment_policy_path=cfg.containment.policy_path,
                            containment_strict=cfg.containment.strict,
                            grants=grants),
                        id=f"{workflow.info().workflow_id}-crew-"
                           f"{task.id}-{attempt}",
                        execution_timeout=timedelta(
                            seconds=crew_layout.limits.wall_clock_s + 600),
                    )
                    crew_sessions = crew.sessions
                    run = crew.run
                else:
                    # The existing call, moved into the else branch verbatim:
                    # same CodingTaskInput(...) arguments, same _long_act.
                    run = await workflow.execute_activity(
                        run_coding_task,
                        CodingTaskInput(harness=role_cfg.harness, prompt=prompt,
                                        worktree=worktree, model=role_cfg.model,
                                        session_id=session_id,
                                        task_id=task.id, attempt=attempt,
                                        containment_enabled=cfg.containment_enabled,
                                        containment_policy_path=cfg.containment.policy_path,
                                        containment_strict=cfg.containment.strict,
                                        grants=grants),
                        **_long_act(role_cfg),
                    )
                for esc in escalations_from_denials(run.denials):
                    await self._record_escalation(cfg, task, esc)
                if run.deferred is None or capped:
                    break
                # Resuming for an approval is NOT a failure resume: it costs
                # neither a fix attempt nor the FR-802 resume budget.
                session_id = run.session_id
                if asked >= cfg.max_tool_escalations:
                    capped = True
                    grants = [ToolGrant(
                        tool_use_id=run.deferred.tool_use_id,
                        tool=run.deferred.tool,
                        input_digest=run.deferred.input_digest,
                        rule_id=run.deferred.rule_id, approved=False,
                        reason="escalation cap reached")]
                    await self._record_escalation(
                        cfg, task,
                        ToolEscalation(tool=run.deferred.tool,
                                       rule_id=run.deferred.rule_id,
                                       target=run.deferred.target,
                                       outcome=EscalationOutcome.CAPPED,
                                       decided_by="policy"))
                    continue          # one more resume, only to deliver the deny
                asked += 1
                self._escalation_round += 1
                decision = await self._gate(
                    "tool_approval", cfg.gate_settings(), round=self._escalation_round,
                    context=GateContext(spec_summary=_escalation_summary(
                        task.id, task.title, run.deferred)),
                    default_policy=GatePolicy.HARD)
                grants = [ToolGrant(
                    tool_use_id=run.deferred.tool_use_id,
                    tool=run.deferred.tool,
                    input_digest=run.deferred.input_digest,
                    rule_id=run.deferred.rule_id,
                    approved=decision.approved,
                    reason=decision.comments or "")]
                await self._record_escalation(
                    cfg, task,
                    ToolEscalation(
                        tool=run.deferred.tool, rule_id=run.deferred.rule_id,
                        target=run.deferred.target,
                        outcome=(EscalationOutcome.APPROVED
                                 if decision.approved
                                 else EscalationOutcome.TIMEOUT
                                 if decision.decided_by == "timeout"
                                 else EscalationOutcome.REJECTED),
                        decided_by=decision.decided_by,
                        round=self._escalation_round))
            if run.session_ref is not None:
                self._session_refs.append(run.session_ref)

            # E-33 harness join: the harness reports REAL dollars (CLI
            # total_cost_usd) — no pricing activity needed. Accumulate
            # under the executing role.
            self._track_usage(
                role="dev", model=role_cfg.model,
                input_tokens=run.input_tokens or 0,
                output_tokens=run.output_tokens or 0,
                cost_usd=run.cost_usd)

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
            qa_spend = RoleUsage(role="qa", model=resolve_role_model(cfg, "qa"))
            qa = (await self._run_role(cfg, "qa", resolve_role_model(cfg, "qa"), t_qa,
                qa_prompt(assertions, qa_raw.model_dump_json(),
                          diff["stat"], diff["patch"]), into=qa_spend)).output

            # Second clean-context judge (FR-204): same inputs as QA — frozen
            # contract + materialized diff + test output. No narrative, no
            # session. A different model family than the developer (ADR-6).
            review = None
            if cfg.review_enabled:
                review = (await self._run_role(cfg, "reviewer", STAGE_MODELS.get("review", "unknown"), t_reviewer,
                    reviewer_prompt(assertions, qa_raw.model_dump_json(),
                                    diff["patch"]))).output

            # `qa_raw.tests_passed` is the actual subprocess exit code;
            # `qa.tests_passed` is the LLM QA agent's OWN retyped guess at
            # the same fact (its instructions ask it to judge contract
            # compliance, not to re-derive this bit) and can disagree with
            # ground truth. The pass/fail gate must anchor on qa_raw here —
            # an LLM opinion must never overwrite a deterministic signal.
            task_passed = qa_raw.tests_passed and not qa.issues

            await self._record(cfg, self._stage_record(
                cfg, stage="code", role=task.role,
                started=_attempt_started, ended=workflow.now(),
                quality_score=(1.0 if task_passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if task_passed
                         else BenchmarkOutcome.FAIL),
                model=role_cfg.model,
                harness=role_cfg.harness,
                cost_usd=run.cost_usd,
                waste=WasteBag.from_digest(run.session_digest),
                plan_drift=compute_plan_drift(task, diff.get("files", [])),
                fix_attempts=attempt - 1,
                task_id=task.id, attempt=attempt - 1))

            # The QA report gets its OWN record. The stage="code" record above
            # keeps its deterministic contract score (1.0 iff tests passed and
            # no issues) -- an LLM opinion must never overwrite a deterministic
            # signal. Cardinality is per-task-attempt, not once-per-run like
            # clarifier/architect/planner; scoring.py means over them natively.
            _qa_quality = await self._judge(
                cfg, qa.model_dump_json(), "qa",
                author_model=resolve_role_model(cfg, "qa"))
            await self._record(cfg, self._stage_record(
                cfg, stage="qa", role="qa",
                started=_attempt_started, ended=workflow.now(),
                quality_score=_qa_quality.score, judge=_qa_quality.judge,
                outcome=(BenchmarkOutcome.PASS if task_passed
                         else BenchmarkOutcome.FAIL),
                model=resolve_role_model(cfg, "qa"), spend=qa_spend,
                task_id=task.id, attempt=attempt - 1))

            review_ok = review is None or review.approve
            if review is not None:
                # The primary's verdict has never been recorded, so
                # review-driven rework showed as fix_attempts on code/qa with
                # no cause row at all. Disagreement is a RELATION between two
                # records; the adversary's is meaningless without this one.
                await self._record(cfg, self._stage_record(
                    cfg, stage="review", role="reviewer",
                    started=_attempt_started, ended=workflow.now(),
                    quality_score=(1.0 if review.approve else 0.0),
                    judge="contract",
                    outcome=(BenchmarkOutcome.PASS if review.approve
                             else BenchmarkOutcome.FAIL),
                    model=STAGE_MODELS.get("review", "unknown"),
                    task_id=task.id, attempt=attempt - 1,
                    fix_attempts=0))      # cause row; volume lives on code/qa

            adversary = None
            if task_passed and review_ok:
                # Approving path only: a rejection is already headed for the
                # fix loop, so the expensive error is a false approve. The
                # adversary is a SECOND opinion -- it presupposes a first, so
                # it never runs when review is disabled (review is None); the
                # primary reviewer is the sole designated blocking lens, which
                # is the entire justification for this lens being fail-open.
                if review is not None:
                    adversary = await self._run_adversary(
                        cfg, contract, assertions, diff, qa_raw, task)
                # A split fails the attempt ONLY when the adversary has
                # actionable (critical/high) findings. A reject with no
                # blocking findings has nothing to put in a retry prompt -- it
                # would hit the ``if not issues: break`` below and silently
                # abandon a task that passed its gate. Same rule as the primary:
                # blocking_findings is actionable, the boolean is not.
                if adversary is None or adversary.approve \
                        or not adversary.blocking_findings:
                    deep = await self._run_deep_review(
                        cfg, run, contract, assertions, diff, task)
                    handoff = await self._run_handoff(
                        cfg, run, contract, assertions, diff, task)
                    return TaskResult(task_id=task.id, status="done",
                                      attempts=attempt, branch=handle.branch,
                                      run=run, handoff=handoff, qa=qa_raw,
                                      review=review, deep_review=deep)
                # Split: fall through to the retry path below. max_fix_attempts
                # still bounds it, and exhaustion enters the existing
                # accept / retry-with-guidance / quarantine gate unchanged.

            issues = ("" if attempt >= budget
                      else _fix_loop_issues(qa, qa_raw, review, adversary))
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
                    task.id, attempt, qa_raw.tests_passed)
                budget = attempt          # nothing to retry on → escalate now

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
                decision = await self._gate(
                    f"task:{task.id}", cfg.gate_settings(), round=gate_round,
                    context=GateContext(task_id=task.id, analysis=analysis,
                                        attempts=attempt))
                if (decision.outcome is GateOutcome.REVISE
                        and gate_round <= cfg.max_gate_rounds):
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
                        + "Contract:\n- " + "\n- ".join(assertions)
                    )
                    continue
                deep = await self._run_deep_review(
                    cfg, run, contract, assertions, diff, task)
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

    # ------------------------------ run ---------------------------------

    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None,
                  seeded: SeededWork | None = None) -> str:
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
        self._budget_threshold = cfg.run_budget_usd    # E-33
        try:
            result = await self._pipeline(idea, cfg, seeded)
        except _BudgetRejected:
            result = "rejected:budget"
        await self._retro(cfg, idea, result)
        return result

    async def _retro(self, cfg: PipelineConfig, idea: IdeaBrief,
                     result: str) -> None:
        """Stage 14 (E-32). Best-effort: any failure is swallowed so the run's
        return string is never changed."""
        try:
            if cfg.memory.enabled:
                self._emit(RunEventKind.MEMORY_RETAINED, stage="retro",
                           item="run_summary")
            self._emit(RunEventKind.RUN_FINISHED, stage="retro", outcome=result)
            summary = build_run_summary(
                run_id=workflow.info().workflow_id,
                mode=idea.mode.value,
                outcome=result, trace=self._trace,
                memory_enabled=cfg.memory.enabled,
                memory_watermark=self._memory_watermark,
                budget_usd=(cfg.run_budget_usd
                            if cfg.run_budget_usd > 0 else None),
                title=idea.title,
                repo_url=idea.repo_url)
            self._run_summary = summary

            if cfg.memory.enabled:
                await self._retain(
                    cfg, MemoryKind.RUN_SUMMARY, cfg.memory.project_bank,
                    text=summary.model_dump_json(),
                    metadata={"run_id": workflow.info().workflow_id,
                              "stage": "retro"})
                try:
                    await workflow.execute_activity(
                        reflect,
                        ReflectInput(bank=cfg.memory.project_bank,
                                     backend=cfg.memory.backend,
                                     base_url=cfg.memory.base_url),
                        **MEM_ACT)
                except Exception:
                    pass

            try:
                await workflow.execute_activity(
                    export_run_artifacts,
                    RunExportInput(run_id=workflow.info().workflow_id,
                                   summary=summary, trace=self._trace),
                    **EXPORT_ACT)
            except Exception:
                pass

            # E-38: OQ-B7 retention — downgrade clean-green non-benchmark
            # runs to digest-only. Best-effort like the export above.
            try:
                had_fix = any(
                    ev.kind == RunEventKind.FIX_ATTEMPT
                    and ev.data.get("attempt") not in (None, "1")
                    for ev in self._trace)
                await workflow.execute_activity(
                    apply_session_retention,
                    RetentionInput(
                        refs=self._session_refs,
                        keep_full=keep_full_transcripts(
                            outcome=result,
                            had_fix_attempts=had_fix,
                            is_benchmark=cfg.benchmark.case_id is not None)),
                    **EXPORT_ACT)
            except Exception:
                pass
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
                tree_hash=out.tree_hash or "", commit_sha=commit_sha,
                modules_collected=out.result.collected,
                contracts_collected=out.result.collected,
                hot_spots_collected=out.result.collected,
                collected=out.result.collected)
        return project(out.scan, out.tree_hash, commit_sha)

    async def _pipeline(self, idea: IdeaBrief, cfg: PipelineConfig,
                        seeded: SeededWork | None = None) -> str:
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                await workflow.execute_activity(
                    capture_watermark,
                    WatermarkInput(bank=cfg.memory.project_bank,
                                  backend=cfg.memory.backend,
                                  base_url=cfg.memory.base_url),
                    **MEM_ACT))
        repo_path = idea.repo_url or "/var/sdlc/repo"  # prepared by a setup activity IRL

        # 0. INTAKE (E-84 D3) -- deterministic, no model call. IdeaBrief.mode
        # is declared by the operator; this verifies the declaration against
        # the tree and fails closed when brownfield has nothing to map.
        self._stage("intake")
        observed = await workflow.execute_activity(
            classify_repo,
            RepoProbeInput(repo_dir=repo_path, base_branch=idea.base_branch),
            **INTAKE_ACT)
        verdict = classify(observed, idea.mode)
        if verdict.warning:
            self._emit(RunEventKind.STAGE_ENDED, stage="intake",
                       warning=verdict.warning)
        if not verdict.ok:
            return f"rejected:intake ({verdict.reason})"

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

        # E-44 D1: a seeded run enters at stage 4. Research, clarify,
        # architecture and planning decide WHAT to build; a mechanical triage
        # finding already answers that, and clarify's open-question wait would
        # park a tidy-up run on a question the finding contains.
        if seeded is not None:
            arch, plan = seeded.arch, seeded.plan
            self._stage("coding", "code")
            return await self._build_and_merge(idea, cfg, arch, plan,
                                               repo_path)

        # 2. CONTEXT (E-84 D1/D4/D6) -- brownfield only. Pinned to the
        # integration head, which is the branch point the work is based on.
        self._codebase_map = None
        if idea.mode is ProjectMode.BROWNFIELD:
            self._stage("mapping", "context")
            self._codebase_map = await self._context(
                repo_path, self._integration_head)
            if self._codebase_map.collected.state \
                    is not CollectionState.MEASURED:
                # D6: proceeding would silently drop the delta check exactly
                # when the ground is weakest -- the shape of the
                # malformed-SARIF-reads-as-clean hole (FR-915).
                return (f"rejected:context "
                        f"({self._codebase_map.collected.reason})")

        # 0. RESEARCH (FR-107) — optional, human-gated, NOT memoized. A served
        # memo means pages were not fetched this run, so a brief cannot be
        # cached (spec finding 4). The brief contributes only its canonical
        # digest to downstream keys (finding 3), never its prose.
        brief_digest_val = ""
        if cfg.research_enabled and t_research is not None:
            self._stage("researching", "research")
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
            # Budget enforcement under fan-out: each sub-question charges its
            # OWN persisted scope ("sq-<id>") plus the shared "run" ceiling via
            # charge_scoped inside the toolset, so one sub-question cannot
            # drain the run. research_subquestion degrades a BudgetExceeded /
            # UsageLimitExceeded into a gap rather than re-raising -- the
            # counter is persisted, so a retry would hit the same exhausted
            # cap six times with backoff (bench-todo-api-greenfield-1785485669:
            # an uncaught UsageLimitExceeded once killed the whole
            # FeatureWorkflow, not just the research stage).
            research_spend = RoleUsage(role="research",
                                       model=STAGE_MODELS.get("research", "unknown"))
            try:
                findings = await self._fan_out_research(cfg, idea, deps,
                                                        research_spend)
                if all(f.failed for f in findings):
                    # No brief to synthesize -- and no point paying for the
                    # call. Degrade the STAGE, never the run (2026-07-20
                    # decision).
                    brief = _degraded_research_brief(
                        RuntimeError("every sub-question failed"))
                else:
                    brief, synth_usage = await workflow.execute_activity(
                        synthesize_brief,
                        SynthesizeInput(idea_json=idea.model_dump_json(),
                                        findings=findings,
                                        model=STAGE_MODELS.get("research", "unknown")),
                        **RESEARCH_SYNTH_ACT)
                    await self._fold_research_usage(cfg, synth_usage,
                                                    research_spend)
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
                verify_brief_activity,
                args=[brief, workflow.info().workflow_id],
                **VERIFY_ACT)
            if violations:
                # Ungrounded brief: fail this stage but do NOT stop the
                # pipeline (2026-07-20 human decision — see report for
                # rationale). Nothing from an unverified brief is trustworthy
                # enough to retain to memory or feed into downstream content
                # keys, so brief_digest_val stays "" and retain is skipped;
                # everything after research proceeds on the idea alone, same
                # as a research-disabled run.
                self._stage("research_failed", "research")
                err = "; ".join(
                    f"{v.kind}: {v.source}: {v.quote[:80]!r}"
                    for v in violations)
                await self._record(cfg, self._stage_record(
                    cfg, stage="research", role="research",
                    started=_r_started, ended=workflow.now(),
                    quality_score=None, judge="error",
                    outcome=BenchmarkOutcome.FAIL,
                    model=STAGE_MODELS.get("research", "unknown"),
                    spend=research_spend,
                    error=f"rejected:research.grounding: {err}"))
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
                            cfg, idea, deps, research_spend,
                            id_offset=len(findings),
                            guidance=gate.guidance or "",
                            gaps=gaps, contradictions=conflicts)
                        # Re-merge over ALL findings: round one is never discarded.
                        brief, synth_usage = await workflow.execute_activity(
                            synthesize_brief,
                            SynthesizeInput(
                                idea_json=idea.model_dump_json(),
                                findings=findings,
                                model=STAGE_MODELS.get("research", "unknown")),
                            **RESEARCH_SYNTH_ACT)
                        await self._fold_research_usage(cfg, synth_usage,
                                                        research_spend)
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
                        **VERIFY_ACT)
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
                            brief, workflow.info().workflow_id,
                            bank=cfg.memory.project_bank):
                        await self._retain(cfg, item.kind, item.bank,
                                           item.text, item.metadata)
                    _r_quality = await self._judge(
                        cfg, brief.model_dump_json(), "research",
                        author_model=STAGE_MODELS.get("research", "unknown"))
                    await self._record(cfg, self._stage_record(
                        cfg, stage="research", role="research",
                        started=_r_started, ended=workflow.now(),
                        quality_score=_r_quality.score, judge=_r_quality.judge,
                        outcome=BenchmarkOutcome.PASS,
                        model=STAGE_MODELS.get("research", "unknown"),
                        spend=research_spend))
                else:
                    # A refine round failed grounding: record FAIL, mirroring
                    # the initial-violations path. retain is skipped (nothing
                    # from an unverified brief is trustworthy) and the run
                    # proceeds on the idea alone, same as a research-disabled
                    # run.
                    await self._record(cfg, self._stage_record(
                        cfg, stage="research", role="research",
                        started=_r_started, ended=workflow.now(),
                        quality_score=None, judge="error",
                        outcome=BenchmarkOutcome.FAIL,
                        model=STAGE_MODELS.get("research", "unknown"),
                        spend=research_spend,
                        error="rejected:research.grounding (refine)"))

        # E-33: serial budget check after the research section (runs whether
        # research is on or off; off-by-default research adds no spend here).
        await self._check_budget(cfg)

        # 1. CLARIFY — open questions answered by human via signals
        self._stage("clarifying", "clarify")
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"clarify:{idea.title}",
            filters={"stage": "clarify"})

        clarify_spend = RoleUsage(role="clarify", model=resolve_role_model(cfg, "clarify"))

        async def _run_clarify_single():
            """Pre-E-85 path: one call, one prompt. Byte-identical to before."""
            return (await self._run_role(cfg, "clarify", resolve_role_model(cfg, "clarify"), t_clarify,
                clarify_prompt(idea.model_dump_json(), snapshot.items),
                into=clarify_spend)).output

        async def _run_clarify_fanout():
            """E-85: supervisor routes and asks C1/C2, probes fan out per
            dimension, pure merge ranks and caps.

            Every call still leaves through _run_role -- _clarify_fanout
            takes the already-bound egress as its collaborator, so E-33's
            accounting covers the route call and all N probes.

            The probes get render_for_prompt's BOUNDED rendering, never the
            raw map JSON: fan-out multiplies input cost by N, which makes
            this the largest cost lever in the stage, and the architect
            stage already reads the map the same way.
            """
            async def _egress(agent, prompt):
                return await self._run_role(
                    cfg, "clarify", resolve_role_model(cfg, "clarify"),
                    agent, prompt, into=clarify_spend)

            return await _clarify_fanout(
                _egress,
                route_agent=t_clarify_route, probe_agent=t_clarify_probe,
                route_prompt=clarify_prompt(idea.model_dump_json(),
                                            snapshot.items),
                idea_json=idea.model_dump_json(),
                grounding=(render_for_prompt(self._codebase_map)
                           if self._codebase_map is not None else ""),
                mode=idea.mode, cap=cfg.clarify_question_cap)

        # E-85: the fan-out's extra memo terms (probe prompts, tree, cap).
        # Empty with the flag off, so flag-off memos keep hitting -- the
        # rationale for each term lives on _clarify_memo_extra.
        _clarify_key_extra = _clarify_memo_extra(cfg, self._codebase_map)

        reqs, _ = await self._cached_stage(
            cfg, "clarify",
            idea.model_dump_json() + brief_digest_val + _clarify_key_extra,
            ClarifiedRequirements,
            _run_clarify_fanout if cfg.clarify_probes_enabled
            else _run_clarify_single)
        if reqs.open_questions:
            for q in reqs.open_questions:
                self._emit(RunEventKind.CLARIFICATION_ASKED, stage="clarify",
                           question_id=q.id, question=q.question,
                           # data is dict[str, str] -- "" not None, or the
                           # RunEvent fails validation on the flag-off path.
                           dimension=q.dimension.value if q.dimension else "")
            clarify_policy = cfg.gates.get("clarify", GateConfig()).policy
            if clarify_policy == GatePolicy.OFF:
                # unattended run (e.g. a benchmark cell) — no human is
                # present to answer; fall back to the clarifier's own
                # suggested_answer rather than blocking forever.
                for q in reqs.open_questions:
                    q.answer = q.suggested_answer
            else:
                self._status = "awaiting:clarify"
                for p in clarify_pending(reqs.open_questions, set(),
                                         opened_at=workflow.now()):
                    self._pending[p.key] = p
                await workflow.wait_condition(
                    lambda: all(q.id in self._question_answers
                                for q in reqs.open_questions),
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                for q in reqs.open_questions:
                    q.answer = self._question_answers.get(q.id)
                    self._pending.pop(q.id, None)
            for q in reqs.open_questions:
                answered = ("human" if q.id in self._question_answers
                            else "suggested" if q.answer is not None
                            else "unanswered")
                self._emit(RunEventKind.CLARIFICATION_ANSWERED, stage="clarify",
                           question_id=q.id, answered_by=answered)
        _ended = workflow.now()
        _quality = await self._judge(cfg, reqs.model_dump_json(), "clarifier",
                                     author_model=resolve_role_model(cfg, "clarify"))
        await self._record(cfg, self._stage_record(
            cfg, stage="clarify", role="clarify",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=BenchmarkOutcome.PASS,
            model=resolve_role_model(cfg, "clarify"), spend=clarify_spend))
        await self._board_publish(cfg, "requirements", reqs.model_dump_json())
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"clarify: {reqs.summary}",
            metadata={"stage": "clarify", "run_id": workflow.info().workflow_id})

        # E-33: serial budget check after clarify.
        await self._check_budget(cfg)

        # 2. ARCHITECT (+ human approval of the spec)
        self._stage("architecting", "architecture")
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"architect:{idea.title}",
            filters={"stage": "architect"})

        arch_spend = RoleUsage(role="architect", model=resolve_role_model(cfg, "architect"))

        # E-84 D10/D12: render the codebase map once upfront for prompt and memo key.
        map_block = ""
        map_key = ""
        if self._codebase_map is not None:
            rendered_map = render_for_prompt(self._codebase_map)
            map_key = map_digest(self._codebase_map)
            map_block = (f"\n\nCodebase map at commit "
                         f"{self._codebase_map.commit_sha[:12]}:\n{rendered_map}")

        async def _run_architect(guidance: str | None):
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
            architect_deps = ResearchDeps(
                run_id=workflow.info().workflow_id,
                provider=(cfg.roles.get("research").provider
                          if cfg.research_enabled and cfg.roles.get("research")
                          else "fake"),
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
                scope="architect")

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
                    + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                       if snapshot.items else "")
                    + (f"\nRevision guidance from reviewer:\n{guidance}"
                       if guidance else "")
                    + (f"\nDelta correction required:\n{delta_guidance}"
                       if delta_guidance else ""))

                async def _produce():
                    return (await self._run_role(
                        cfg, "architect", resolve_role_model(cfg, "architect"),
                        t_architect, prompt, deps=architect_deps,
                        into=arch_spend)).output

                cache_key = (
                    reqs_for_architect
                    + (guidance or "")
                    + (map_key if self._codebase_map is not None else "")
                    + (delta_guidance or ""))
                arch, _ = await self._cached_stage(
                    cfg, "architect", cache_key, ArchitectureSpec, _produce)

                if self._codebase_map is None:
                    return arch

                delta_check = await workflow.execute_activity(
                    check_brownfield_delta,
                    DeltaCheckInput(
                        repo_dir=repo_path,
                        commit_sha=self._codebase_map.commit_sha,
                        delta=arch.delta),
                    **INTAKE_ACT)
                if delta_check.passed:
                    return arch

                if delta_retries <= 0:
                    raise ApplicationError(
                        f"brownfield architecture delta failed grounding check "
                        f"after retries: {delta_check.detail}",
                        non_retryable=True)
                delta_retries -= 1
                delta_guidance = (
                    f"The proposed delta does not match the repository at "
                    f"{self._codebase_map.commit_sha[:12]}: "
                    f"{delta_check.detail}. Update delta.added, delta.modified, "
                    f"and delta.removed so every path resolves.")

        arch, gate = await self._revisable_stage("architecture", cfg,
                                                 _run_architect)
        _ended = workflow.now()
        _quality = await self._judge(cfg, arch.model_dump_json(), "architect",
                                     author_model=resolve_role_model(cfg, "architect"))
        await self._record(cfg, self._stage_record(
            cfg, stage="architecture", role="architect",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model=resolve_role_model(cfg, "architect"), spend=arch_spend))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"architect: {arch.overview}",
            metadata={"stage": "architect", "run_id": workflow.info().workflow_id})
        await self._check_budget(cfg)   # E-33: serial boundary after architect
        await self._board_publish(cfg, "architecture", arch.model_dump_json(),
                                  approved=gate.approved)
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        _started = workflow.now()
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"plan:{idea.title}",
            filters={"stage": "plan"})

        plan_spend = RoleUsage(role="planner", model=resolve_role_model(cfg, "plan"))

        async def _run_plan(guidance: str | None):
            prompt = planner_prompt(arch.model_dump_json(), snapshot.items,
                                    guidance)

            async def _produce():
                return (await self._run_role(cfg, "planner", resolve_role_model(cfg, "plan"), t_planner, prompt, into=plan_spend)).output
            plan, _ = await self._cached_stage(
                cfg, "plan",
                arch.model_dump_json() + (guidance or ""),
                ImplementationPlan, _produce)
            return plan

        plan, gate = await self._revisable_stage("plan", cfg, _run_plan)
        _ended = workflow.now()
        _quality = await self._judge(cfg, plan.model_dump_json(), "planner",
                                     author_model=resolve_role_model(cfg, "plan"))
        await self._record(cfg, self._stage_record(
            cfg, stage="plan", role="planner",
            started=_started, ended=_ended,
            quality_score=_quality.score, judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved
                     else BenchmarkOutcome.REVISED),
            model=resolve_role_model(cfg, "plan"), spend=plan_spend))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"plan: {len(plan.tasks)} tasks",
            metadata={"stage": "plan", "run_id": workflow.info().workflow_id})
        await self._check_budget(cfg)   # E-33: serial boundary after planner
        self._plan_version = await self._board_publish(
            cfg, "plan", plan.model_dump_json(), approved=gate.approved)
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

    async def _build_and_merge(self, idea: IdeaBrief, cfg: PipelineConfig,
                               arch: ArchitectureSpec,
                               plan: ImplementationPlan,
                               repo_path: str) -> str:
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
                r = await self._dev_task(t, repo_path, self._integration_head,
                                         cfg, handoffs)
            except Exception as exc:
                # _dev_task's own fix loop is exhausted before it raises, so a
                # propagating exception means the run is aborting. Record a
                # terminal status so the board (which agents read for live
                # state) does not leave this task looking forever in_progress
                # — indistinguishable from a task still running.
                await self._board_task_status(
                    cfg, t.id, TaskStatus.FAILED,
                    error=f"unhandled: {type(exc).__name__}: {exc}")
                raise
            _BOARD_STATUS = {"done": TaskStatus.DONE,
                             "failed": TaskStatus.FAILED,
                             "quarantined": TaskStatus.QUARANTINED}
            await self._board_task_status(
                cfg, t.id, _BOARD_STATUS[r.status],
                fix_attempts=r.attempts, branch=r.branch,
                error=(r.notes or None
                       if r.status != "done" else None))
            for kind, report in (("qa", r.qa), ("review", r.review),
                                 ("deep_review", r.deep_review)):
                if report is not None:
                    await self._board_evidence(cfg, t.id, kind,
                                               report.model_dump_json())
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

            await self._check_budget(cfg)   # E-33: serial boundary per task wave

        # 4b. ANALYZE (stage 9) — clean-context Analyst proposes the
        # criterion->test mapping; the workflow enforces it (FR-106). Runs on
        # the integrated whole, before the merge gate.
        self._stage("analyzing", "analyze")
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
        analyst_spend = RoleUsage(role="analyst", model=resolve_role_model(cfg, "analyze"))
        analysis: AnalysisReport = (await self._run_role(cfg, "analyst", resolve_role_model(cfg, "analyze"), t_analyst,
            analyst_prompt(_criteria_lines, _qa_lines,
                           integration_diff["stat"],
                           integration_diff["patch"]), into=analyst_spend)).output
        untraced = untraced_criteria(authoritative, analysis)
        await self._record(cfg, self._stage_record(
            cfg, stage="analyze", role="analyst",
            started=_an_started, ended=workflow.now(),
            quality_score=(1.0 if not untraced else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.PASS if not untraced
                     else BenchmarkOutcome.FAIL),
            model=resolve_role_model(cfg, "analyze"), spend=analyst_spend))
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

        await self._check_budget(cfg)   # E-33: serial boundary after analyst

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
            IntegrationChecksInput(worktree=integration_worktree,
                                   changed_files=integration_diff["files"]),
            **INTEG_ACT)
        if ichecks.toolchain is not None:
            all_tests_green = ichecks.qa.tests_passed
            lint_clean, lint_detail = ichecks.lint_clean, ichecks.lint_detail
        else:
            lint_commands = next(
                (t.contract.lint_commands for t in plan.tasks
                 if t.contract and t.contract.lint_commands), None)
            lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
            lint_clean, lint_detail = await workflow.execute_activity(
                run_lint, LintInput(worktree=integration_worktree,
                                    lint_cmd=lint_cmd), **ACT)
            all_tests_green = _merge_evidence_all_green(list(done.values()))

        # Coverage is read AFTER the integration test run that emits
        # coverage.xml (E-30 closes the FR-106 gap: the artifact now lands where
        # the seam reads). measured=False stays a no-op advisory pass.
        cov: CoverageReport = await workflow.execute_activity(
            measure_coverage,
            CoverageInput(worktree=integration_worktree,
                          changed_files=integration_diff["files"]),
            **ACT)

        security: SecurityReport = await workflow.execute_activity(
            security_scan,
            SecurityScanInput(worktree=integration_worktree), **ACT)

        checks = [
            build_check("build_integration_green", all_tests_green,
                        CheckClass.ABSOLUTE,
                        detail="aggregate of per-task pytest runs"),
            build_check("lint_clean", lint_clean, CheckClass.ABSOLUTE,
                        detail=lint_detail),
            # FR-915: "the scan found nothing" and "no scan happened" are
            # different facts and get different check names. Conflating them
            # into one compound condition is the exact defect this split
            # exists to prevent, reproduced inside the gate that prevents it.
            build_check(
                "security_scan_collected",
                security.state is CollectionState.MEASURED,
                CheckClass.ABSOLUTE,
                detail=(security.reason or "security scan ran")),
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
                (True if cov.coverage.state is not CollectionState.MEASURED
                 else cov.coverage.value >= cfg.coverage_threshold),
                CheckClass.ADVISORY,
                detail=(cov.coverage.reason
                        if cov.coverage.state is not CollectionState.MEASURED
                        else f"diff coverage {cov.coverage.value:.1f}% vs "
                             f"threshold {cfg.coverage_threshold:.1f}%")),
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
            gate = await self._gate(
                "merge", cfg.gate_settings(),
                context=GateContext(checks=gate_report.checks))
            if not gate.approved:
                return "rejected:merge:advisory"
            # Human waved the advisory checks through — record each waiver.
            reviewer = gate.reviewer or "human"
            reason = gate.comments or "advisory override"
            overrides = [
                GateOverride(check=n, approved_by=reviewer, reason=reason)
                for n in advisory_blocking]
            self._emit(
                RunEventKind.GATE_DECIDED, stage="merge", gate="merge",
                round="1", policy="soft", decided_by=(gate.reviewer or "human"),
                approved="true",
                overrides=",".join(o.check for o in overrides))
            gate_report = await workflow.execute_activity(
                evaluate_gate,
                QualityGateInput(checks=checks, overrides=overrides), **ACT)
        else:
            # 5d. Gate passed clean. MergeVerdict is advisory and ONLY
            # consulted under SOFT policy — it can approve an already-clean
            # build; it can never reach this branch otherwise.
            if cfg.gates.get("merge", GateConfig()).policy == GatePolicy.SOFT:
                verdict: MergeVerdict = (await self._run_role(cfg, "merge_verdict", STAGE_MODELS.get("merge_verdict", "unknown"), t_merge_verdict,
                    merge_verdict_prompt([r.model_dump()
                                          for r in done.values()])
                )).output
                auto = _auto_decision_for(
                    "merge", cfg,
                    verdict.confidence if verdict.approve else None)
                if auto is None:
                    # Soft policy + (negative verdict OR confidence below
                    # threshold) = escalate to human.
                    gate = await self._gate(
                        "merge", cfg.gate_settings(),
                        context=GateContext(checks=gate_report.checks))
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
                PROpenInput(worktree=self._integration_wt, title=idea.title,
                            body=arch.overview, base_branch=idea.base_branch),
                **ACT,
            )

        # 6. DEPLOY gate → DeploymentWorkflow child (E-67/FR-1104)
        _started = workflow.now()
        gate = await self._gate("deploy", cfg.gate_settings())
        _ended = workflow.now()
        if not gate.approved or not cfg.deploy.enabled:
            # The deploy stage did not run: record the gate decision only.
            await self._record(cfg, self._stage_record(
                cfg, stage="deploy", role="devops",
                started=_started, ended=_ended,
                quality_score=None, judge="llm_judge",
                outcome=(BenchmarkOutcome.PASS if gate.approved
                         else BenchmarkOutcome.REVISED),
                model=resolve_role_model(cfg, "devops")))
            return f"merged-not-deployed:{pr_url}"

        plan = self._deploy_plan(cfg)
        attempt = 1
        while True:
            report = await workflow.execute_child_workflow(
                DeploymentWorkflow.run,
                DeploymentInput(plan=plan, cfg=cfg.deploy,
                                repo_path=repo_path, attempt=attempt),
                # Derived, never generated: replay must produce the same id,
                # and a retry round stays identifiable in the Temporal UI.
                id=f"{workflow.info().workflow_id}-deploy-{attempt}",
                task_queue=workflow.info().task_queue,
            )
            if report.deployed:
                # One record, reflecting the actual result -- never a
                # premature PASS from the gate. (SC-5 / E-40: a reading must
                # not read as clean when it was not.)
                await self._record(cfg, self._stage_record(
                    cfg, stage="deploy", role="devops",
                    started=_started, ended=workflow.now(),
                    quality_score=None, judge="contract",
                    outcome=BenchmarkOutcome.PASS,
                    model=resolve_role_model(cfg, "devops")))
                self._stage("deployed", "deploy")
                return _deploy_result(report, None, pr_url)

            # The gate opens even when the rollback itself failed -- that is
            # the case a human most needs to see.
            decision = await self._gate(
                "deploy_failed", cfg.gate_settings(), round=attempt,
                context=GateContext(
                    # ABSOLUTE: the human is not waving a check through --
                    # the rollback already happened. They are deciding what
                    # to do next.
                    checks=[CheckResult(name=c.name, passed=c.passed,
                                        classification=CheckClass.ABSOLUTE,
                                        detail=c.detail)
                            for c in report.checks],
                    verdict=_deploy_verdict(report)),
                default_policy=GatePolicy.HARD)
            if (decision.outcome is GateOutcome.REVISE
                    and attempt < cfg.max_gate_rounds):
                attempt += 1
                continue
            # Rolled back or deploy-broken: record FAIL, never the gate's PASS.
            await self._record(cfg, self._stage_record(
                cfg, stage="deploy", role="devops",
                started=_started, ended=workflow.now(),
                quality_score=None, judge="contract",
                outcome=BenchmarkOutcome.FAIL,
                model=resolve_role_model(cfg, "devops")))
            self._stage("deploy_failed", "deploy")
            return _deploy_result(report, decision, pr_url)
