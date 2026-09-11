"""Artifact models for the merge stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement


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


def _unmeasured_is_empty(state: CollectionState, reason: str, **carried: object) -> None:
    """FR-915 at the type: an unmeasured delta carries nothing that could read
    as "zero introduced", and says why it is unmeasured."""
    if state is CollectionState.MEASURED:
        return
    loaded = [name for name, value in carried.items() if value]
    if loaded:
        raise ValueError(f"{state.value} report must not carry {loaded}")
    if not reason.strip():
        raise ValueError(f"{state.value} report requires a reason")


class LintFinding(BaseModel):
    rule: str
    path: str  # repo-relative POSIX
    line: str  # normalized source line: the DS3 identity text


class ScopedLintReport(BaseModel):
    """DS5/DS7: lint at the pinned base and the integration head. `lint_clean`
    passes iff MEASURED and `introduced` is empty. Policy relaxation is
    reported, never gated (DS5's named residual)."""

    state: CollectionState
    reason: str = ""
    introduced: list[LintFinding] = Field(default_factory=list)
    preexisting: int = 0
    resolved: int = 0
    policy_paths_changed: list[str] = Field(default_factory=list)
    suppressions_added: int = 0

    @model_validator(mode="after")
    def _fail_closed(self) -> ScopedLintReport:
        _unmeasured_is_empty(
            self.state,
            self.reason,
            introduced=self.introduced,
            preexisting=self.preexisting,
            resolved=self.resolved,
            policy_paths_changed=self.policy_paths_changed,
            suppressions_added=self.suppressions_added,
        )
        return self


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
