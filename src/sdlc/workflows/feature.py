"""FeatureWorkflow â€” idea â†’ deployed feature.

Deterministic orchestration only. All I/O happens in activities or inside
TemporalAgent-managed activities. Human-in-the-loop gates are durable
signal waits with a per-gate policy (hard / soft / off).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import (
        STAGE_MODELS,
        resolve_role_model,
        t_analyst,
        t_architect,
        t_clarify,
        t_clarify_probe,
        t_clarify_route,
        t_handoff,
        t_merge_verdict,
        t_planner,
        t_research,
    )
    from ..artifacts.read import LoadSessionInput, load_session
    from ..benchmarks.models import BenchmarkOutcome
    from ..context.models import CodebaseMap
    from ..core.context import StageContext, StageServices
    from ..core.models import (
        IdeaBrief,
        PipelineConfig,
        ProjectMode,
        RoleUsage,
        RunState,
        RunSummary,
    )
    from ..handoff import (
        claim_survival_score,
        cross_check_claims,
    )
    from ..harness.session import session_text_from_jsonl
    from ..memory.activities import WatermarkInput, capture_watermark
    from ..memory.models import MemoryKind
    from ..stages import (
        analyze,
        architecture,
        clarify,
        context,
        deploy,
        intake,
        merge,
        research,
    )
    from ..stages import (
        plan as plan_stage,
    )
    from ..stages.analyze.models import untraced_criteria
    from ..stages.architecture.models import ArchitectureSpec
    from ..stages.clarify.models import ClarifiedRequirements
    from ..stages.code.models import HandoffSummary
    from ..stages.deploy.models import DeployPlan
    from ..stages.plan.models import ImplementationPlan
    from ..stages.plan.validation import validate_task_graph as _validate_task_graph
    from ..vcs import (
        DiffInput,
        IntegrationHandle,
        IntegrationInput,
        get_task_diff,
        setup_integration_branch,
    )
    from .benchmark_host import BenchmarkHost
    from .board_host import BoardHost
    from .build import run_tasks
    from .gates import GateHost
    from .memory_host import MEM_ACT, MemoryHost
    from .models import SeededWork
    from .question_host import QuestionHost
    from .report_host import ReportHost
    from .role_host import (
        RoleHost,
        _BudgetRejected,
    )
    from .run_host import RunHost
    from .task_host import TaskHost

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


def _requirements_for_downstream(reqs: ClarifiedRequirements) -> str:
    """The clarify artifact as every DOWNSTREAM role sees it.

    E-85's scope guard is "no change to downstream roles" (spec Â§2), and two
    of `ClarifiedRequirements`' E-85 fields are measurement rather than
    requirement:

      - `dropped` is the record of what the cap CUT, carrying each lost
        question's `why_it_matters`, `suggested_answer` and `evidence`.
        Feeding it to the architect would hand the architect the UNCAPPED
        set and undo the very protection Â§9's cap exists to provide -- and
        it is unbounded, since merge keeps every candidate past the cap.
      - `dimensions_probed` is stage telemetry: which probes ran. It says
        nothing about the requirement.

    Both stay on the persisted and emitted artifact -- they are the
    benchmark's measurement record (Â§5, Â§10) and must survive. They simply
    never reach a downstream prompt or a downstream memo key.

    Excluding them also restores byte-identity for the flag-off path: before
    E-85 neither field existed, so neither appeared in the architect's
    prompt or its cache key.
    """
    return reqs.model_dump_json(exclude={"dropped", "dimensions_probed"})


def _merge_evidence_all_green(results: list) -> bool:
    """True only when every task has positive, passing QA evidence.

    SC-5: a done task with missing QA (e.g. an escalation-approved task
    whose fix loop exhausted) is treated as FAILURE â€” never a vacuous
    `all([])` pass. The merge absolute check must see real green evidence."""
    return bool(results) and all(r.qa is not None and r.qa.tests_passed for r in results)


# Fallbacks only for contracts predating test_commands/lint_commands
# (legacy cached artifacts) â€” every fresh plan populates both per-stack.
DEFAULT_LINT_CMD = "ruff check ."


@workflow.defn
class FeatureWorkflow(
    RunHost,
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
        self._integration_head: str = ""
        self._base_sha: str = ""  # DS2: setup head, pinned; _integration_head advances per merge
        self._integration_wt: str = ""
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

    # ---------------- queries (the HITL surface) ------------------------

    @workflow.query
    def run_summary(self) -> RunSummary | None:
        """The retro-stage RunSummary; None until the run terminates (E-32)."""
        return self._run_summary

    @workflow.query
    def run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10)."""
        return self._snapshot_run_state()

    # ---------------------------- helpers -------------------------------

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
        """The frozen DeployPlan for this run."""
        return deploy._deploy_plan(cfg, workflow.info().workflow_id)

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

    async def _context(
        self,
        repo_path: str,
        commit_sha: str,
        idea: IdeaBrief | None = None,
        cfg: PipelineConfig | None = None,
    ) -> CodebaseMap | str | None:
        """Stage 2 context mapping for brownfield projects (E-84). Delegates to context.step."""
        if idea is None:
            return await context.build_map(repo_path, commit_sha)
        return await context.step(
            self._ctx,
            cfg=cfg or self._cfg or PipelineConfig(),
            idea=idea,
            repo_path=repo_path,
            commit_sha=commit_sha,
        )

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
        # back both the head SHA and the worktree path â€” the workflow never
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
        self._base_sha = integration.head_sha
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
            context_res = await self._context(repo_path, self._integration_head, idea=idea, cfg=cfg)
            if isinstance(context_res, str):
                return context_res
            self._codebase_map = context_res

        # 0. RESEARCH (FR-107) â€” optional, human-gated, NOT memoized. A served
        # memo means pages were not fetched this run, so a brief cannot be
        # cached (spec finding 4). The brief contributes only its canonical
        # digest to downstream keys (finding 3), never its prose.
        brief_digest_val = ""
        if cfg.research_enabled and t_research is not None:
            res = await research.step(
                self._ctx,
                cfg=cfg,
                idea=idea,
                memory_watermark=self._memory_watermark,
                research_agent=t_research,
                research_model=resolve_role_model(cfg, "research"),
            )
            if res.rejection:
                return res.rejection
            brief_digest_val = res.digest

        # E-33: serial budget check after the research section (runs whether
        # research is on or off; off-by-default research adds no spend here).
        await self._check_budget(cfg)

        # 1. CLARIFY â€” open questions answered by human via signals
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
        arch, gate = await architecture.step(
            self._ctx,
            cfg=cfg,
            requirements=reqs,
            codebase_map=self._codebase_map,
            memory_watermark=self._memory_watermark,
            idea=idea,
            repo_path=repo_path,
            architect_agent=t_architect,
            architect_model=resolve_role_model(cfg, "architect"),
        )
        await self._check_budget(cfg)  # E-33: serial boundary after architect
        await self._board_publish(
            cfg, "architecture", arch.model_dump_json(), approved=gate.approved
        )
        if not gate.approved:
            return "rejected:architecture"

        # 3. PLAN (soft gate by default)
        plan, gate = await plan_stage.step(
            self._ctx,
            cfg=cfg,
            architecture=arch,
            requirements=reqs,
            idea=idea,
            planner_agent=t_planner,
            planner_model=resolve_role_model(cfg, "plan"),
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
        # Sync tasks only after the graph is valid â€” an invalid plan would
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
        # 4. DEV / TEST / DEVOPS tasks â€” ADR-13: serial by default;
        # wave mode parallelizes, but tasks sharing declared overlaps
        # serialize regardless. Handoffs flow task -> task (FR-805).
        done, failure = await run_tasks(self, cfg=cfg, plan=plan, repo_path=repo_path)
        if failure is not None:
            return failure

        # 4b. ANALYZE (stage 9) â€” clean-context Analyst proposes the
        # criterion->test mapping; the workflow enforces it (FR-106). Runs on
        # the integrated whole, before the merge gate.
        # The integration diff is run context shared by analyze AND the merge
        # gate below (changed_files); the orchestrator fetches it once, before
        # the step call. Consequence, accepted: analyze's STAGE_STARTED event
        # now lands after the diff fetch instead of before it.
        integration_diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=self._integration_wt, branch_point=self._base_sha),
            **ACT,
        )
        authoritative: list[tuple[str, str]] = [
            (t.id, c) for t in plan.tasks for c in t.acceptance_criteria
        ]
        analysis = await analyze.step(
            self._ctx,
            cfg=cfg,
            plan=plan,
            task_results=done,
            diff=integration_diff,
            integration_wt=self._integration_wt,
            base_branch=idea.base_branch,
            analyst_agent=t_analyst,
            analyst_model=resolve_role_model(cfg, "analyze"),
        )
        untraced = untraced_criteria(authoritative, analysis)

        await self._check_budget(cfg)  # E-33: serial boundary after analyst

        # 5. MERGE — DeterministicQualityGate first (SC-5), then the human
        # gate (which doubles as the advisory-override mechanism), then
        # MergeVerdict advisory only under SOFT policy.
        pr_url = await merge.step(
            self._ctx,
            cfg=cfg,
            task_results=list(done.values()),
            integration_wt=self._integration_wt,
            idea=idea,
            arch=arch,
            plan=plan,
            base_sha=self._base_sha,
            integration_diff=integration_diff,
            untraced=untraced,
            merge_agent=t_merge_verdict,
            merge_model=STAGE_MODELS.get("merge_verdict", "unknown"),
        )
        if pr_url.startswith("rejected:"):
            return pr_url

        # 6. DEPLOY gate → DeploymentWorkflow child (E-67/FR-1104)
        return await deploy.step(
            self._ctx,
            cfg=cfg,
            deploy_plan=self._deploy_plan(cfg),
            repo_path=repo_path,
            pr_url=pr_url,
        )
