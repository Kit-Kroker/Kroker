"""The E-74 capture matrix (spec §4.1). Shared by M1 capture and M2 golden runs.

Drivers talk to the workflow by query/signal NAME ("pending_gate",
"answer_question", "submit_gate_decision"), never by a class attribute, so one
scenario drives FeatureWorkflow (captured) and GraphWorkflow (asserted).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from sdlc.assessment.activities import AssessmentTreeInput
from sdlc.board.activities import AttachEvidenceInput
from sdlc.context.delta import DELTA_CHECK
from sdlc.context.models import RepoObservation
from sdlc.core.models import (
    ArtifactRef,
    ExecutionMode,
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from sdlc.gate import CheckClass, CheckResult, build_check
from sdlc.harness.models import HarnessRunResult
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.pricing import PriceUsageInput
from sdlc.pricing import price_usage as real_price_usage
from sdlc.stages.analyze.models import AnalysisReport, CriterionTrace
from sdlc.stages.architecture.models import ValidationContract
from sdlc.stages.code.activities import CodingTaskInput
from sdlc.stages.context.activities import DeltaCheckInput, RepoProbeInput
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.stages.research.models import ResearchPlan
from sdlc.stages.research.stage import PlanInput
from sdlc.stages.research.verify import verify_brief_activity
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import (
    AGENT_SPECS,
    ARCH,
    PLAN,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES, fake_classify_repo, git_fakes_except
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy
from tests.research.test_research_e2e import _research_fake_activities
from tests.test_feature_brownfield_stages import (
    BROWNFIELD_SPECS,
    SCAN_FAKES,
    fake_resolve_tree,
)

Handle = Any


# ---- driver helpers (by name) -------------------------------------------------


async def wait_for(handle: Handle, target: str, timeout_s: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    while asyncio.get_event_loop().time() < deadline:
        last = await handle.query("status")
        if last == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r} (last={last!r})")


async def answer_clarify(handle: Handle) -> None:
    await wait_for(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal("answer_question", args=[qid, "yes"])


async def decide(handle: Handle, gate: str, round_: int, outcome: GateOutcome, **kw: Any) -> None:
    await wait_for(handle, f"awaiting:{gate}")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate=gate, round=round_, outcome=outcome, decided_by="human", **kw),
    )


A, R, V = GateOutcome.APPROVE, GateOutcome.REJECT, GateOutcome.REVISE


# ---- scenario-specific fakes ---------------------------------------------------


@activity.defn(name="price_usage")
async def fixed_price(inp: PriceUsageInput) -> float | None:
    return 1.0  # every metered proposer call costs exactly $1 (tests/test_budget_gate.py)


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    """No-op delivery (bug notify-flake). GateHost._gate notifies through the
    production `notify` activity (NOTIFY_ACT), so every golden whose workflow
    opens a gate schedules `activity:notify`; the harness must REGISTER that
    type -- an unregistered pending activity task races the next workflow
    task and hard-fails it ("Activity function notify not registered"), the
    full-file flake. The harness never delivers anything, and the success
    path iterates `out.results` OUTSIDE _notify's try/except (gates.py), so
    the fake returns the real contract shape with zero deliveries."""
    return Results()


@activity.defn(name="plan_research")
async def fake_plan_research(inp: PlanInput) -> ResearchPlan:
    """Empty decomposition (bug notify-flake). research_greenfield's golden
    memorializes the DEGRADED research path: plan_research scheduled once,
    and no research_subquestion / synthesize_brief after it -- the
    unregistered expiry used to fail the fan-out into
    _degraded_research_brief (caught at stages/research/step.py). The same
    exception is caught today, so registration may not CHANGE the run: an
    empty plan lands in that same all-findings-failed degrade branch
    deterministically and schedules nothing extra, keeping the command
    projection byte-identical."""
    return ResearchPlan()


@activity.defn(name="assessment_resolve_tree")
async def unresolvable_tree(inp: AssessmentTreeInput) -> None:
    raise ApplicationError("no tree for this commit", non_retryable=True)


_BLOCKING: dict[str, asyncio.Event] = {}


@activity.defn(name="run_coding_task")
async def blocking_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    _BLOCKING["started"].set()
    while not activity.is_cancelled():
        activity.heartbeat()
        await asyncio.sleep(0.2)
    raise asyncio.CancelledError()


_WAVES: dict[str, asyncio.Event] = {}


def _waves_before() -> None:
    reset_deploy()
    _WAVES["t1_done"] = asyncio.Event()


def _t1_gated_evidence() -> Any:
    """t1's LAST command in run_one is its `review` evidence write
    (build.run_tasks: qa, review, deep_review=None). Setting the event there
    orders every command of the wave, whichever completion lands first."""

    @activity.defn(name="attach_task_evidence")
    async def gated(inp: AttachEvidenceInput) -> ArtifactRef:
        if inp.task_id == "t1" and inp.kind == "review":
            _WAVES["t1_done"].set()
        return ArtifactRef(kind="board_evidence", uri="file:///fake/evidence", sha256="0" * 64)

    return gated


def _staggered_coding_task() -> Any:
    @activity.defn(name="run_coding_task")
    async def staggered(inp: CodingTaskInput) -> HarnessRunResult:
        if inp.task_id == "t2":
            await asyncio.wait_for(_WAVES["t1_done"].wait(), timeout=120)
        return HarnessRunResult(
            harness=inp.harness,
            session_id=f"s-{inp.task_id}",
            exit_code=0,
            summary="implemented",
            commit_sha="cafe1234",
            input_tokens=1000,
            output_tokens=200,
            context_window=200000,
        )

    return staggered


def _two_task_plan() -> ImplementationPlan:
    def task(tid: str) -> DevTask:
        return DevTask(
            id=tid,
            title=f"Implement {tid}",
            description=f"Task {tid}.",
            acceptance_criteria=[f"{tid} works"],
            contract=ValidationContract(
                task_id=tid,
                assertions=[f"{tid} works"],
                test_commands=["pytest -q"],
                lint_commands=["ruff check ."],
                stack="Python/FastAPI",
            ),
        )

    return ImplementationPlan(tasks=[task("t1"), task("t2")], confidence=0.95)


def _specs_with_plan(plan: ImplementationPlan) -> list:
    analysis = AnalysisReport(
        traceability=[
            CriterionTrace(
                task_id=t.id,
                criterion=crit,
                tests=[f"test_{t.id}_returns_200"],
            )
            for t in plan.tasks
            for crit in t.acceptance_criteria
        ],
        summary="all criteria traced",
        confidence=0.95,
    )
    return [
        (
            name,
            typ,
            plan if name == "planner_agent" else analysis if name == "analyst_agent" else value,
        )
        for name, typ, value in AGENT_SPECS
    ]


def brownfield_idea() -> IdeaBrief:
    return IdeaBrief(
        title="Brownfield task",
        description="Modify endpoint",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/fake/repo",
        base_branch="main",
    )


def _deploying(cfg: PipelineConfig) -> PipelineConfig:
    cfg.deploy.enabled = True
    return cfg


# ---- the scenario record -------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    name: str
    idea: Callable[[], IdeaBrief]
    cfg: Callable[[], PipelineConfig]
    activities: Callable[[], list]
    drive: Callable[[Handle, Any], Awaitable[None]]
    seeded: Callable[[], SeededWork | None] = lambda: None
    before: Callable[[], None] = lambda: None
    # "concurrent": driver runs beside handle.result() with time skipping off.
    # "then_skip": driver runs with skipping off, then result() with skipping on.
    # "partial": driver reaches a mid-flight point; the harness then terminates.
    # "expect_error": driver runs beside result(), and result() is expected to raise.
    mode: str = "concurrent"
    golden: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def _base_activities(specs: list = AGENT_SPECS) -> list:
    return [
        evaluate_gate,
        export_run_artifacts,
        fake_notify,
        *GIT_FAKES,
        *DEPLOY_FAKES,
        *fake_agent_activities(specs),
    ]


async def _drive_happy(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    for gate in ("architecture", "plan", "deploy"):
        await decide(handle, gate, 1, A)


async def _drive_arch_revise_final(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, V, guidance="split the service")
    await decide(handle, "architecture", 2, V, guidance="keep it single")
    await decide(handle, "architecture", 3, A)
    await decide(handle, "plan", 1, A)
    await decide(handle, "deploy", 1, A)


async def _drive_rounds_1(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, V, guidance="once more")
    await decide(handle, "architecture", 2, A)
    await decide(handle, "plan", 1, A)
    await decide(handle, "deploy", 1, A)


async def _drive_plan_revise(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, A)
    await decide(handle, "plan", 1, V, guidance="smaller tasks")
    await decide(handle, "plan", 2, A)
    await decide(handle, "deploy", 1, A)


async def _drive_timeout(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await wait_for(handle, "awaiting:architecture")


async def _drive_nothing(handle: Handle, env: Any) -> None:
    return None


async def _drive_deploy_only(handle: Handle, env: Any) -> None:
    await decide(handle, "deploy", 1, A)


async def _drive_budget_clarify_reject(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "budget", 1, R)


async def _drive_budget_arch_reject(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, R)
    await decide(handle, "budget", 1, A)


async def _drive_research(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "deploy", 1, A)


async def _drive_clarify_only(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)


async def _drive_cancel(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, A)
    await decide(handle, "plan", 1, A)
    await asyncio.wait_for(_BLOCKING["started"].wait(), timeout=60)
    await handle.cancel()


def _budget_cfg(budget: float) -> Callable[[], PipelineConfig]:
    def make() -> PipelineConfig:
        cfg = e2e_config()
        cfg.run_budget_usd = budget
        return cfg

    return make


def _budget_activities() -> list:
    fakes = [a for a in GIT_FAKES if a is not real_price_usage]
    return [
        evaluate_gate,
        export_run_artifacts,
        fake_notify,
        fixed_price,
        *fakes,
        *DEPLOY_FAKES,
        *fake_agent_activities(AGENT_SPECS),
    ]


def _research_cfg() -> PipelineConfig:
    cfg = PipelineConfig(
        research_enabled=True,
        gates={
            "research": GateConfig(policy=GatePolicy.OFF),
            "architecture": GateConfig(policy=GatePolicy.OFF),
            "plan": GateConfig(policy=GatePolicy.OFF),
            "deploy": GateConfig(policy=GatePolicy.HARD),
        },
        memoization_enabled=False,
        review_enabled=True,
    )
    cfg.deploy.enabled = True
    return cfg


def _rounds_1_cfg() -> PipelineConfig:
    cfg = _deploying(e2e_config())
    cfg.max_gate_rounds = 1
    return cfg


def _timeout_cfg() -> PipelineConfig:
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    return cfg


def _waves_cfg() -> PipelineConfig:
    cfg = _deploying(e2e_config())
    cfg.execution_mode = ExecutionMode.WAVES
    return cfg


def _cancel_before() -> None:
    _BLOCKING["started"] = asyncio.Event()


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "greenfield_happy",
        greenfield_idea,
        lambda: _deploying(e2e_config()),
        _base_activities,
        _drive_happy,
        before=reset_deploy,
    ),
    Scenario(
        "brownfield_happy",
        brownfield_idea,
        lambda: _deploying(e2e_config()),
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            fake_resolve_tree,
            *SCAN_FAKES,
            *GIT_FAKES,
            *DEPLOY_FAKES,
            *fake_agent_activities(BROWNFIELD_SPECS),
        ],
        _drive_happy,
        before=reset_deploy,
    ),
    Scenario(
        "intake_reject",
        lambda: IdeaBrief(
            title="Brownfield task",
            description="Modify endpoint",
            mode=ProjectMode.BROWNFIELD,
            repo_url="/invalid/repo",
            base_branch="main",
        ),
        e2e_config,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            *[a for a in GIT_FAKES if a is not fake_classify_repo],
            _bad_classify(),
        ],
        _drive_nothing,
    ),
    Scenario(
        "context_reject",
        brownfield_idea,
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, unresolvable_tree, *SCAN_FAKES, *GIT_FAKES],
        _drive_nothing,
    ),
    Scenario(
        "arch_revise_final",
        greenfield_idea,
        lambda: _deploying(e2e_config()),
        _base_activities,
        _drive_arch_revise_final,
        before=reset_deploy,
    ),
    Scenario(
        "arch_timeout_reject",
        greenfield_idea,
        _timeout_cfg,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            *GIT_FAKES,
            *fake_agent_activities(AGENT_SPECS),
        ],
        _drive_timeout,
        mode="then_skip",
    ),
    Scenario(
        "plan_revise_approve",
        greenfield_idea,
        lambda: _deploying(e2e_config()),
        _base_activities,
        _drive_plan_revise,
        before=reset_deploy,
    ),
    Scenario(
        "waves",
        greenfield_idea,
        _waves_cfg,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            *git_fakes_except("run_coding_task", "attach_task_evidence"),
            _staggered_coding_task(),
            _t1_gated_evidence(),
            *DEPLOY_FAKES,
            *fake_agent_activities(_specs_with_plan(_two_task_plan())),
        ],
        _drive_happy,
        before=_waves_before,
    ),
    Scenario(
        "seeded",
        greenfield_idea,
        lambda: _deploying(e2e_config()),
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            *GIT_FAKES,
            *DEPLOY_FAKES,
            *fake_agent_activities(
                [
                    s
                    for s in AGENT_SPECS
                    if s[0] not in {"clarify_agent", "architect_agent", "planner_agent"}
                ]
            ),
        ],
        _drive_deploy_only,
        seeded=lambda: SeededWork(arch=ARCH, plan=PLAN),
        before=reset_deploy,
    ),
    Scenario(
        "budget_clarify_reject",
        greenfield_idea,
        _budget_cfg(0.5),
        _budget_activities,
        _drive_budget_clarify_reject,
    ),
    Scenario(
        "budget_arch_reject",
        greenfield_idea,
        _budget_cfg(1.5),
        _budget_activities,
        _drive_budget_arch_reject,
    ),
    Scenario(
        "research_greenfield",
        greenfield_idea,
        _research_cfg,
        lambda: [
            evaluate_gate,
            verify_brief_activity,
            export_run_artifacts,
            fake_notify,
            fake_plan_research,
            *GIT_FAKES,
            *DEPLOY_FAKES,
            *_research_fake_activities(),
            *fake_agent_activities(AGENT_SPECS),
        ],
        _drive_research,
        before=reset_deploy,
    ),
    Scenario(
        "delta_failed",
        brownfield_idea,
        e2e_config,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_resolve_tree,
            *SCAN_FAKES,
            *git_fakes_except("check_brownfield_delta"),
            _failing_delta(),
            *fake_agent_activities(BROWNFIELD_SPECS),
        ],
        _drive_clarify_only,
        mode="expect_error",
    ),
    Scenario(
        "cancel_during_code",
        greenfield_idea,
        e2e_config,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            *git_fakes_except("run_coding_task"),
            blocking_coding_task,
            *fake_agent_activities(AGENT_SPECS),
        ],
        _drive_cancel,
        before=_cancel_before,
        mode="expect_error",
    ),
    Scenario(
        "max_gate_rounds_1",
        greenfield_idea,
        _rounds_1_cfg,
        _base_activities,
        _drive_rounds_1,
        before=reset_deploy,
    ),
    Scenario(
        "partial_awaiting_architecture",
        greenfield_idea,
        e2e_config,
        lambda: [
            evaluate_gate,
            export_run_artifacts,
            fake_notify,
            *GIT_FAKES,
            *fake_agent_activities(AGENT_SPECS),
        ],
        _drive_timeout,
        mode="partial",
        golden=False,
    ),
)

GOLDEN_SCENARIOS: tuple[Scenario, ...] = tuple(s for s in SCENARIOS if s.golden)


def _bad_classify() -> Any:
    @activity.defn(name="classify_repo")
    async def bad_classify(inp: RepoProbeInput) -> RepoObservation:
        return RepoObservation(
            is_git_repo=False, base_branch_resolves=False, reason="not a git repository"
        )

    return bad_classify


def _failing_delta() -> Any:
    @activity.defn(name="check_brownfield_delta")
    async def failing_delta(inp: DeltaCheckInput) -> CheckResult:
        return build_check(
            DELTA_CHECK, False, CheckClass.ABSOLUTE, "delta path nonexistent.py not in git tree"
        )

    return failing_delta
