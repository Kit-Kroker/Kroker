"""E-84 D3/D4/D6/D13: the brownfield branch, wired."""

from __future__ import annotations

import asyncio
import inspect
import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.activities import RepoProbeInput, evaluate_gate
from sdlc.assessment.activities import (
    AssessmentTree,
    AssessmentTreeInput,
    ScanSignalInput,
)
from sdlc.assessment.scan.models import (
    CATEGORIES,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from sdlc.context.models import RepoObservation
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    ProjectMode,
)
from sdlc.measurement import Measurement
from sdlc.models import (
    AnalysisReport,
    ArchitectureDecision,
    ArchitectureSpec,
    BrownfieldDelta,
    ClarifiedRequirements,
    ImplementationPlan,
    MergeVerdict,
    QAReport,
    ReviewReport,
)
from sdlc.observability.activities import export_run_artifacts
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.fakes.canned import (
    ANALYSIS_OK,
    CLARIFIED,
    MERGE_OK,
    PLAN,
    QA_OK,
    QUESTION_IDS,
    REVIEW_OK,
    e2e_config,
)
from tests.fakes.fake_activities import GIT_FAKES, fake_classify_repo
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy


def test_the_pipeline_reads_the_mode():
    """Before E-84, IdeaBrief.mode was written by three callers and read by
    nothing in src/sdlc/. That is the defect this task closes."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "ProjectMode.BROWNFIELD" in src or "classify(" in src


def test_context_runs_after_the_integration_branch_is_cut():
    """D4: the map must describe the tree the work is actually based on, so
    it pins integration.head_sha rather than the base branch's tip."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("setup_integration_branch") < src.index("_context(")


def test_seeded_runs_still_short_circuit_before_context():
    """D13: tidy-up children declare BROWNFIELD and have no Architect call to
    ground, so they must not pay for a map nothing reads (E-44 D1)."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("if seeded is not None") < src.index("_context(")


@activity.defn(name="assessment_resolve_tree")
async def fake_resolve_tree(inp: AssessmentTreeInput) -> AssessmentTree:
    return AssessmentTree(tree_hash="t" * 40)


def _make_measured_signal(sid: ScanSignalId) -> SignalOutput:
    m = Measurement.measured(1.0)
    row = ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=SignalSource.COMPUTED,
        collected=m,
        categories={k: m for k in CATEGORIES[sid]},
    )
    sources = []
    if sid == ScanSignalId.S1:
        sources = [
            SourceCandidate(
                signal=ScanSignalId.S1,
                local_id="S1-app",
                name="app",
                rule="s1_domain_term",
                detail="main app",
                confidence_contribution=Confidence.HIGH,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE, value="GET /health", path="app/main.py", line=10
                    ),
                    CandidateMember(
                        kind=MemberKind.FILE_PATH, value="app/main.py", path="app/main.py"
                    ),
                ],
            )
        ]
    return SignalOutput(row=row, sources=sources)


@activity.defn(name="scan_packages")
async def fake_scan_packages(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.S1)


@activity.defn(name="scan_schema")
async def fake_scan_schema(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.S2)


@activity.defn(name="scan_entrypoints")
async def fake_scan_entrypoints(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.S3)


@activity.defn(name="scan_frontend")
async def fake_scan_frontend(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.S4)


@activity.defn(name="scan_security_static")
async def fake_scan_security_static(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.SS1)


@activity.defn(name="scan_config_infra")
async def fake_scan_config_infra(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.SS3)


@activity.defn(name="scan_sensitivity")
async def fake_scan_sensitivity(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.SS4)


@activity.defn(name="scan_tests_inventory")
async def fake_scan_tests_inventory(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.QS1)


@activity.defn(name="scan_coverage")
async def fake_scan_coverage(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.QS2)


@activity.defn(name="scan_testability")
async def fake_scan_testability(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.QS3)


@activity.defn(name="scan_ci")
async def fake_scan_ci(inp: ScanSignalInput) -> SignalOutput:
    return _make_measured_signal(ScanSignalId.QS4)


SCAN_FAKES = [
    fake_scan_packages,
    fake_scan_schema,
    fake_scan_entrypoints,
    fake_scan_frontend,
    fake_scan_security_static,
    fake_scan_config_infra,
    fake_scan_sensitivity,
    fake_scan_tests_inventory,
    fake_scan_coverage,
    fake_scan_testability,
    fake_scan_ci,
]

ARCH_BROWNFIELD = ArchitectureSpec(
    overview="Brownfield endpoint modification.",
    decisions=[
        ArchitectureDecision(id="d1", decision="Update endpoint", rationale="matches stack")
    ],
    delta=BrownfieldDelta(modified=["app/main.py"]),
    confidence=0.95,
)

BROWNFIELD_SPECS = [
    ("clarify_agent", ClarifiedRequirements, CLARIFIED),
    ("architect_agent", ArchitectureSpec, ARCH_BROWNFIELD),
    ("planner_agent", ImplementationPlan, PLAN),
    ("qa_analyst_agent", QAReport, QA_OK),
    ("reviewer_agent", ReviewReport, REVIEW_OK),
    ("analyst_agent", AnalysisReport, ANALYSIS_OK),
    ("merge_verdict_agent", MergeVerdict, MERGE_OK),
]


async def _wait_for_status(handle, target: str, timeout_s: float = 15.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for status {target!r}")


async def _drive(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=gate, round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
        )


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_brownfield_intake_rejects_non_git_repo():
    """D3: intake observes the repo is not a git repo -> fails closed."""

    @activity.defn(name="classify_repo")
    async def fake_bad_classify(inp: RepoProbeInput) -> RepoObservation:
        return RepoObservation(
            is_git_repo=False, base_branch_resolves=False, reason="not a git repository"
        )

    activities = [
        evaluate_gate,
        export_run_artifacts,
        *[a for a in GIT_FAKES if a is not fake_classify_repo],
        fake_bad_classify,
    ]

    idea = IdeaBrief(
        title="Brownfield task",
        description="Modify endpoint",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/invalid/repo",
        base_branch="main",
    )
    cfg = e2e_config()

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue="bf-intake",
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=activities,
                plugins=[PydanticAIPlugin()],
            ):
                res = await env.client.execute_workflow(
                    FeatureWorkflow.run,
                    args=[idea, cfg],
                    id=f"bf-intake-{uuid.uuid4()}",
                    task_queue="bf-intake",
                )
    assert res.startswith("rejected:intake")
    assert "not a git repository" in res


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_brownfield_full_run_ships_end_to_end():
    """Behavioral proof: Stage 0 intake passes, Stage 2 context runs and
    projects CodebaseMap, render_for_prompt() executes, Architecture delta
    is checked, and pipeline reaches deployed."""
    reset_deploy()
    activities = [
        evaluate_gate,
        export_run_artifacts,
        fake_resolve_tree,
        *SCAN_FAKES,
        *GIT_FAKES,
        *DEPLOY_FAKES,
        *fake_agent_activities(BROWNFIELD_SPECS),
    ]

    idea = IdeaBrief(
        title="Brownfield task",
        description="Modify endpoint",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/fake/repo",
        base_branch="main",
    )
    cfg = e2e_config()
    cfg.deploy.enabled = True

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue="bf-e2e",
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=activities,
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[idea, cfg],
                    id=f"bf-e2e-{uuid.uuid4()}",
                    task_queue="bf-e2e",
                )
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
    assert result.startswith("deployed:"), result
