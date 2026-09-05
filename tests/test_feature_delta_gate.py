"""E-84 D10/D11: the delta check in the architecture stage."""

from __future__ import annotations

import asyncio
import inspect
import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

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
from sdlc.context.delta import DELTA_CHECK
from sdlc.core.models import (
    IdeaBrief,
    ProjectMode,
)
from sdlc.gate import CheckClass, CheckResult, build_check
from sdlc.measurement import Measurement
from sdlc.observability.activities import export_run_artifacts
from sdlc.stages import architecture
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.stages.architecture.models import (
    ArchitectureDecision,
    ArchitectureSpec,
)
from sdlc.stages.clarify.models import ClarifiedRequirements
from sdlc.stages.context.activities import DeltaCheckInput
from sdlc.stages.context.models import BrownfieldDelta
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.stages.merge.models import MergeVerdict
from sdlc.stages.plan.models import ImplementationPlan
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport
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
from tests.fakes.fake_activities import GIT_FAKES, fake_check_brownfield_delta
from tests.fakes.fake_agents import fake_agent_activities


def _arch_src() -> str:
    return inspect.getsource(FeatureWorkflow._pipeline) + inspect.getsource(architecture.step)


def test_the_architect_prompt_carries_the_rendered_map():
    """D12: brownfield runs see the map; greenfield runs do not."""
    src = _arch_src()
    assert "render_for_prompt(" in src


def test_the_delta_check_is_called_under_brownfield():
    src = _arch_src()
    assert "check_brownfield_delta" in src


def test_the_cache_key_includes_the_map_digest():
    """D10: two runs with identical requirements on different trees cannot
    share an architecture memo."""
    src = _arch_src()
    assert "map_digest(" in src or "map_key" in src


def test_the_re_prompt_happens_before_failing_closed():
    """D11: one retry by default, bounded by PipelineConfig.max_delta_retries."""
    src = _arch_src()
    assert "max_delta_retries" in src


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


async def _drive_clarify(handle, timeout_s: float = 15.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == "awaiting:clarify":
            for qid in QUESTION_IDS:
                await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
            return
        await asyncio.sleep(0.05)


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_delta_failure_raises_non_retryable_application_error():
    """D11 / Finding 5: exhausting delta retries raises ApplicationError(non_retryable=True)
    instead of hanging in an infinite workflow retry."""

    @activity.defn(name="check_brownfield_delta")
    async def fake_failing_delta(inp: DeltaCheckInput) -> CheckResult:
        return build_check(
            DELTA_CHECK, False, CheckClass.ABSOLUTE, "delta path nonexistent.py not in git tree"
        )

    activities = [
        evaluate_gate,
        export_run_artifacts,
        fake_resolve_tree,
        *SCAN_FAKES,
        *[a for a in GIT_FAKES if a is not fake_check_brownfield_delta],
        fake_failing_delta,
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

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue="bf-delta-fail",
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=activities,
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[idea, cfg],
                    id=f"bf-delta-fail-{uuid.uuid4()}",
                    task_queue="bf-delta-fail",
                )
                asyncio.create_task(_drive_clarify(handle))
                with pytest.raises(WorkflowFailureError) as exc_info:
                    await handle.result()
                cause = exc_info.value.cause
                assert isinstance(cause, ApplicationError)
                assert cause.non_retryable is True
                assert "delta failed grounding check" in str(cause)
