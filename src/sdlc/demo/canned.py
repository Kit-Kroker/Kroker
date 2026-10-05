"""The dry run's script: one idea and the artifact each proposer "produces".

Every value is consistent with what the next stage needs: one open question
(so the clarify answer path runs), a single task with a frozen contract, and
clean QA / review / analysis so the run reaches deploy.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..core.models import (
    GateConfig,
    GatePolicy,
    IdeaBrief,
    MemoryConfig,
    PipelineConfig,
    ProjectMode,
)
from ..stages.analyze.models import AnalysisReport, CriterionTrace
from ..stages.architecture.models import (
    ArchitectureDecision,
    ArchitectureSpec,
    ValidationContract,
)
from ..stages.clarify.models import ClarifiedRequirements, OpenQuestion
from ..stages.merge.models import MergeVerdict
from ..stages.plan.models import DevTask, ImplementationPlan
from ..stages.qa.models import QAReport
from ..stages.review.models import ReviewReport

_CRITERION = "GET /health returns 200 with a JSON body"

CLARIFIED = ClarifiedRequirements(
    summary="Add a health endpoint to the service.",
    functional_requirements=[_CRITERION],
    non_functional_requirements=["p95 under 50 ms"],
    out_of_scope=["authentication", "dependency health checks"],
    open_questions=[
        OpenQuestion(
            id="q1",
            question="Should /health be reachable without authentication?",
            why_it_matters="decides whether the route sits behind the auth middleware",
            suggested_answer="yes",
        )
    ],
)

ARCH = ArchitectureSpec(
    overview="One new route on the existing FastAPI app; no new service.",
    decisions=[
        ArchitectureDecision(
            id="d1",
            decision="Serve /health from the existing app",
            rationale="a liveness probe must share the process it reports on",
        )
    ],
    new_components=["app/health.py"],
    confidence=0.95,
)

PLAN = ImplementationPlan(
    tasks=[
        DevTask(
            id="t1",
            title="Implement /health",
            description="Add a GET /health route returning 200 and a JSON status body.",
            acceptance_criteria=[_CRITERION],
            contract=ValidationContract(
                task_id="t1",
                assertions=[_CRITERION],
                test_commands=["pytest -q"],
                lint_commands=["ruff check ."],
                stack="Python/FastAPI",
            ),
        )
    ],
    confidence=0.95,
)

ANALYSIS = AnalysisReport(
    traceability=[
        CriterionTrace(task_id="t1", criterion=_CRITERION, tests=["test_health_returns_200"])
    ],
    summary="all criteria traced",
    confidence=0.95,
)

# (production agent name, output type, canned output). The names are the
# registry's: a fake dispatches because its activity names match.
AGENT_SPECS: list[tuple[str, type, BaseModel]] = [
    ("clarify_agent", ClarifiedRequirements, CLARIFIED),
    ("architect_agent", ArchitectureSpec, ARCH),
    ("planner_agent", ImplementationPlan, PLAN),
    ("qa_analyst_agent", QAReport, QAReport(tests_passed=True)),
    ("reviewer_agent", ReviewReport, ReviewReport(approve=True, confidence=0.95)),
    ("analyst_agent", AnalysisReport, ANALYSIS),
    (
        "merge_verdict_agent",
        MergeVerdict,
        MergeVerdict(approve=True, confidence=0.95, rationale="clean"),
    ),
]


def demo_idea() -> IdeaBrief:
    return IdeaBrief(
        title="Add a health endpoint",
        description="Expose GET /health so the load balancer can probe the service.",
        mode=ProjectMode.GREENFIELD,
        # Never opened: every activity that would touch it is scripted.
        repo_url="/demo/hello-service",
        base_branch="main",
    )


def demo_config() -> PipelineConfig:
    """Every gate HARD, so the run stops where a real one would and the
    driver has to answer; memory and memoization off, so no support
    activity is scheduled; deploy on, so the run goes the whole way."""
    hard = GateConfig(policy=GatePolicy.HARD)
    cfg = PipelineConfig(
        gates={"clarify": hard, "architecture": hard, "plan": hard, "merge": hard, "deploy": hard},
        memory=MemoryConfig(enabled=False),
        memoization_enabled=False,
        review_enabled=True,
    )
    cfg.deploy.enabled = True
    return cfg
