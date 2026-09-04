"""Orchestrator envelopes (spec A §2.2 Rule 7).

Aggregates stage artifacts across stages for the orchestrator's own state and
return values. Does not live in core/ (Rule 5/7) and does not live in any single
stage slice.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from ..models import (
    ArchitectureSpec,
    DeepReviewReport,
    HandoffSummary,
    HarnessRunResult,
    ImplementationPlan,
    ReviewReport,
)
from ..stages.qa.models import QAReport


class SeededWork(BaseModel):
    """E-44 D1: an ImplementationPlan authored deterministically rather than by
    the planner.

    A FeatureWorkflow handed one of these skips stages 0-3 (research, clarify,
    architecture, planning) and enters at the code stage. Everything from
    _dev_task down is unchanged and still binding -- clean-context review
    (ADR-6/FR-204), the bounded fix loop (FR-105), the deterministic quality
    gate (FR-106), the merge gate. Those are the stages that make a run
    GOVERNED (NG5); stages 0-3 decide WHAT to build, and for a mechanical
    triage finding the finding itself already answers that.

    `arch` is seeded rather than made optional because after planning it is
    read at exactly one place -- the PR body -- so seeding it keeps stage 4
    onward free of `| None` handling.
    """

    arch: ArchitectureSpec
    plan: ImplementationPlan

    @model_validator(mode="after")
    def _plan_is_not_empty(self) -> SeededWork:
        if not self.plan.tasks:
            raise ValueError(
                "SeededWork with no tasks would open an empty PR -- the "
                "vacuous-task bypass SC-5 already closed once"
            )
        return self


class TaskResult(BaseModel):
    task_id: str
    status: Literal["done", "failed", "quarantined"]
    attempts: int
    branch: str
    run: HarnessRunResult | None = None
    handoff: HandoffSummary | None = None  # FR-805
    qa: QAReport | None = None  # NEW: evidence for the merge gate
    review: ReviewReport | None = None  # FR-204: clean-context review evidence
    deep_review: DeepReviewReport | None = None  # E-39: advisory lens
    notes: str = ""
