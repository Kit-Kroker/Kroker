"""Artifact models for the analyze stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..review.models import ReviewFinding


class CriterionTrace(BaseModel):
    """One acceptance criterion and the test(s) the Analyst says verify it."""

    task_id: str
    criterion: str
    tests: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Clean-context Analyst output (stage 9 / FR-106). Emitted from
    orchestrator-assembled inputs only — the authoritative acceptance-criteria
    list + materialized integration diff + aggregate test output. The Analyst
    holds no tools, no repo, no worker session.

    The Analyst PROPOSES the criterion->test mapping; the workflow ENFORCES
    completeness against the plan's criteria. This model never carries a
    pass/fail verdict. `findings` ride along for memory/observability and are
    NOT wired as a blocking gate check.
    """

    traceability: list[CriterionTrace] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


def untraced_criteria(authoritative: list[tuple[str, str]], report: AnalysisReport) -> list[str]:
    """FR-106 enforcement (workflow-side, NOT the LLM's verdict).

    A criterion is traced iff the Analyst's report contains a CriterionTrace
    for that exact (task_id, criterion) with a non-empty `tests` list. Any
    authoritative criterion the report omits OR maps to zero tests is untraced.
    Enforced against the plan's authoritative set so an Analyst cannot hide a
    gap by forgetting to list a criterion. Returns "task_id: criterion" labels
    in authoritative order.
    """
    traced = {(t.task_id, t.criterion) for t in report.traceability if t.tests}
    return [
        f"{task_id}: {criterion}"
        for (task_id, criterion) in authoritative
        if (task_id, criterion) not in traced
    ]
