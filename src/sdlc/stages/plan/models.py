"""Artifact models for the plan stage (spec A §2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...core.models import ArtifactRef
from ..architecture.models import ValidationContract


class DevTask(BaseModel):
    id: str
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str]
    files_hint: list[str] = Field(default_factory=list)
    overlaps: list[str] = Field(default_factory=list)  # modules shared with
    # other tasks (FR-104):
    # overlapping tasks
    # serialize in wave mode
    contract: ValidationContract | None = None  # frozen at planning
    role: Literal["dev", "test", "devops"] = "dev"


class PlanDrift(BaseModel):
    """Deterministic plan-vs-execution drift for one task (E-83).

    None on a record means NOT MEASURED. An all-zero PlanDrift would be
    indistinguishable from a task that executed exactly to plan -- the same
    rule WasteBag states for its own bag.

    A SIGNAL, never a gate: `files_hint` is named a hint, and a planner that
    guessed wrong is a normal outcome. What it measures is planner
    calibration across many runs, not any single run's correctness.
    """

    files_hinted: int
    files_touched: int
    hinted_untouched: list[str] = Field(default_factory=list)
    touched_unhinted: list[str] = Field(default_factory=list)


def _norm_path(p: str) -> str:
    """Windows-authored hints and POSIX diff paths name the same file."""
    return p.replace("\\", "/").strip().lstrip("./")


def compute_plan_drift(task: DevTask, files_touched: list[str]) -> PlanDrift | None:
    """Pure. None when either side is absent -- a prediction that was never
    made cannot be adhered to, and a diff that does not exist cannot be
    compared."""
    if not task.files_hint or not files_touched:
        return None
    hinted = {_norm_path(p) for p in task.files_hint}
    touched = {_norm_path(p) for p in files_touched}
    return PlanDrift(
        files_hinted=len(hinted),
        files_touched=len(touched),
        hinted_untouched=sorted(hinted - touched),
        touched_unhinted=sorted(touched - hinted),
    )


class ImplementationPlan(BaseModel):
    tasks: list[DevTask]
    plan_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301


class PlanDeviation(BaseModel):
    """One way the session departed from the task it was given (E-83).

    Evidence-first, exactly like IntegrityFlag: a deviation whose quote is
    not in the transcript is dropped, because an advisory lens that can
    invent evidence is worse than no lens.
    """

    kind: Literal["unplanned_scope", "skipped_criterion", "approach_changed"]
    detail: str
    evidence: str  # a VERBATIM span from the scrubbed transcript
