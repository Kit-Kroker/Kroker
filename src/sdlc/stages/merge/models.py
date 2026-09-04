"""Artifact models for the merge stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...measurement import Measurement


class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.

    FR-915: a non-MEASURED state means the seam could not measure, so the
    advisory check passes as a no-op rather than forcing a spurious human
    override every run. A MEASURED 0.0 is a real zero and is graded as one.
    """

    coverage: Measurement


class MergeVerdict(BaseModel):
    """Advisory LLM proposer output (Finding #5). Consulted only under a
    SOFT merge policy, and only AFTER the DeterministicQualityGate passes.
    It can approve an already-clean build; it can never bypass the gate."""

    approve: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    concerns: list[str] = Field(default_factory=list)
