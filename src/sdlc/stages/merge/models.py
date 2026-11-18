"""Artifact models for the merge stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement
from ...toolchain.lint_scope import (  # 026 T011: moved verbatim; re-exported
    LintFinding as LintFinding,
)
from ...toolchain.lint_scope import (
    ScopedLintReport as ScopedLintReport,
)
from ...toolchain.lint_scope import (
    _unmeasured_is_empty,
)

__all__ = [
    "LintFinding",
    "ScopedLintReport",
    "CoverageReport",
    "MergeVerdict",
    "ScopedTestReport",
]


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


class ScopedTestReport(BaseModel):
    """DS6/DS7: whole suite at head, targeted corroboration at base.
    `build_integration_green` passes iff MEASURED and `introduced` is empty."""

    state: CollectionState
    reason: str = ""
    introduced: list[str] = Field(default_factory=list)
    preexisting: list[str] = Field(default_factory=list)
    preexisting_flaky: list[str] = Field(default_factory=list)
    head_failed: int = 0
    diagnostic: str = ""

    @model_validator(mode="after")
    def _fail_closed(self) -> ScopedTestReport:
        _unmeasured_is_empty(
            self.state,
            self.reason,
            introduced=self.introduced,
            preexisting=self.preexisting,
            preexisting_flaky=self.preexisting_flaky,
            head_failed=self.head_failed,
        )
        return self
