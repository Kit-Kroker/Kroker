"""Brownfield fakes shared by the replay scenarios (020 T026).

This file was FeatureWorkflow's brownfield stage-test module. Its three
`_pipeline` source pins are deleted (stage ordering is the graph
topology's job now), and its two full-run temporal rows are deleted:
their coverage is the `brownfield_happy` and `intake_reject` goldens
(tests/replay/test_graph_golden.py) re-captured from GraphWorkflow
(020 T018). What remains is the fake inventory `tests/replay/
scenarios.py` imports: SCAN_FAKES, BROWNFIELD_SPECS, fake_resolve_tree.
"""

from __future__ import annotations

from temporalio import activity

from sdlc.assessment.activities import AssessmentTree, AssessmentTreeInput, ScanSignalInput
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
from sdlc.measurement import Measurement
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.clarify.models import ClarifiedRequirements
from sdlc.stages.context.models import BrownfieldDelta
from sdlc.stages.merge.models import MergeVerdict
from sdlc.stages.plan.models import ImplementationPlan
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport
from tests.fakes.canned import ANALYSIS_OK, CLARIFIED, MERGE_OK, PLAN, QA_OK, REVIEW_OK


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
