"""Artifact models for the review stage (spec A §2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..code.models import IntegrityFlag
from ..plan.models import PlanDeviation


class ReviewFinding(BaseModel):
    assertion: str  # which contract assertion / concern
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    suggested_fix: str = ""


class ReviewReport(BaseModel):
    """Clean-context reviewer output (ADR-6/ADR-12/FR-204). Emitted from
    orchestrator-assembled inputs only — frozen contract + materialized diff +
    test output. The reviewer holds no tools, no repo, no worker session, and
    never resumes the developer's harness session."""

    approve: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301

    @property
    def blocking_findings(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity in ("critical", "high")]


class DeepReviewReport(BaseModel):
    """Advisory full-transcript lens (E-39). Reads the SCRUBBED HarnessSession
    as data — never the raw session, never via resume. Model family is
    ADR-6-independent of dev. NEVER blocks: the clean-context reviewer
    (ReviewReport) is the sole blocking lens; this report is recorded and
    retained for signal only. Fields are evidence-first."""

    findings: list[ReviewFinding] = Field(default_factory=list)
    integrity_flags: list[IntegrityFlag] = Field(default_factory=list)
    plan_deviations: list[PlanDeviation] = Field(default_factory=list)
    summary: str = ""
    approve: bool = True  # advisory opinion only
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def cheat_detected(self) -> bool:
        return bool(self.integrity_flags)
