"""Deterministic inputs + proposer outputs for the greenfield e2e run.

Every value is self-consistent with the next stage's needs: one open
question (exercises answer_question), a single dev task with a frozen
contract, and clean QA/review so the run reaches deploy.
"""

from __future__ import annotations

from sdlc.models import (
    AnalysisReport,
    ArchitectureDecision,
    ArchitectureSpec,
    ClarifiedRequirements,
    CriterionTrace,
    DevTask,
    GateConfig,
    GatePolicy,
    IdeaBrief,
    ImplementationPlan,
    MemoryConfig,
    MergeVerdict,
    OpenQuestion,
    PipelineConfig,
    ProjectMode,
    QAReport,
    ReviewReport,
    ValidationContract,
)

QUESTION_IDS = ["q1"]

CLARIFIED = ClarifiedRequirements(
    summary="Add a greeting endpoint.",
    functional_requirements=["GET /hello returns 200"],
    non_functional_requirements=["p95 < 100ms"],
    out_of_scope=["auth"],
    open_questions=[
        OpenQuestion(
            id="q1",
            question="Anonymous access ok?",
            why_it_matters="scopes auth work",
            suggested_answer="yes",
        )
    ],
)

ARCH = ArchitectureSpec(
    overview="Single FastAPI service with one route.",
    decisions=[
        ArchitectureDecision(id="d1", decision="Use FastAPI", rationale="matches team stack")
    ],
    new_components=["app/main.py"],
    confidence=0.95,
)

PLAN = ImplementationPlan(
    tasks=[
        DevTask(
            id="t1",
            title="Implement /hello",
            description="Add GET /hello route returning 200.",
            acceptance_criteria=["GET /hello returns 200"],
            contract=ValidationContract(
                task_id="t1",
                assertions=["GET /hello returns 200"],
                test_commands=["pytest -q"],
                lint_commands=["ruff check ."],
                stack="Python/FastAPI",
            ),
        )
    ],
    confidence=0.95,
)

QA_OK = QAReport(tests_passed=True)
REVIEW_OK = ReviewReport(approve=True, confidence=0.95)
MERGE_OK = MergeVerdict(approve=True, confidence=0.95, rationale="clean")

ANALYSIS_OK = AnalysisReport(
    traceability=[
        CriterionTrace(
            task_id="t1", criterion="GET /hello returns 200", tests=["test_hello_returns_200"]
        )
    ],
    summary="all criteria traced",
    confidence=0.95,
)

AGENT_SPECS = [
    ("clarify_agent", ClarifiedRequirements, CLARIFIED),
    ("architect_agent", ArchitectureSpec, ARCH),
    ("planner_agent", ImplementationPlan, PLAN),
    ("qa_analyst_agent", QAReport, QA_OK),
    ("reviewer_agent", ReviewReport, REVIEW_OK),
    ("analyst_agent", AnalysisReport, ANALYSIS_OK),
    ("merge_verdict_agent", MergeVerdict, MERGE_OK),
]


def greenfield_idea() -> IdeaBrief:
    return IdeaBrief(
        title="Hello service",
        description="Add /hello",
        mode=ProjectMode.GREENFIELD,
        repo_url="/fake/repo",
        base_branch="main",
    )


def e2e_config() -> PipelineConfig:
    """Hermetic P1 config: memory + memoization off (no support activities
    scheduled), every gate HARD (driver approves each explicitly)."""
    hard = GateConfig(policy=GatePolicy.HARD)
    return PipelineConfig(
        gates={"clarify": hard, "architecture": hard, "plan": hard, "merge": hard, "deploy": hard},
        memory=MemoryConfig(enabled=False),
        memoization_enabled=False,
        review_enabled=True,
    )
