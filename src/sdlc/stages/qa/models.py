"""Artifact models for the qa stage (spec A §2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ...core.models import ArtifactRef
from ...measurement import CollectionState

SecuritySeverity = Literal["critical", "high", "medium", "low"]


class QAReport(BaseModel):
    """Clean-context QA evidence for the merge gate.

    Deliberately carries NO coverage number: coverage is measured
    deterministically into CoverageReport (FR-106), and a model-asserted
    figure beside a measured one is a second registry for one fact -- the
    failure mode the agents.yaml / cfg.roles work already paid for once.
    """

    tests_passed: bool
    failing_tests: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    stack_mismatch: bool = False  # diff uses a fundamentally
    # different language/runtime
    # than the contract's frozen
    # stack, not merely incomplete
    # The runner aborted before the end of the suite (-x / --maxfail). Tests
    # ordered after the stopping point DID NOT RUN, which is a different fact
    # from "they ran and failed" -- the same distinction CoverageReport draws
    # with `measured` (E-30/FR-915). Without it a task whose own tests sort
    # after an unrelated failure receives a verdict on evidence that was never
    # collected (P2 demonstration, 2026-08-19: a Go adapter's 23 tests never
    # executed across four attempts while QA reported tests_passed=False).
    stopped_early: bool = False
    report_ref: ArtifactRef | None = None


class SecurityFinding(BaseModel):
    severity: SecuritySeverity
    rule: str  # which scanner rule matched
    detail: str
    path: str = ""
    line: str = ""  # normalized source line: the DS3 identity text


class SecurityReport(BaseModel):
    """Deterministic scanner evidence for the merge gate's absolute floor
    (FR-106/NFR-5/SC-5).

    FR-915: `state` is REQUIRED and has no default. A producer cannot forget
    to say whether a scan happened, because `critical=0` from a broken scanner
    is byte-identical to `critical=0` from a clean repository -- and the check
    reading this is absolute.
    """

    critical: int
    findings: list[SecurityFinding] = Field(default_factory=list)
    state: CollectionState
    reason: str = ""


class ScopedSecurityReport(BaseModel):
    """DS4/DS7: the two-point security delta the merge gate reads.

    `security_scan_collected` reads `state` (both points collected);
    `security_no_critical` counts introduced criticals only. A report that is
    not MEASURED carries no counts at all, so it can never read as "zero
    introduced" (FR-915).
    """

    state: CollectionState
    reason: str = ""
    introduced: list[SecurityFinding] = Field(default_factory=list)
    preexisting: int = 0
    resolved: int = 0

    @property
    def introduced_critical(self) -> int:
        return sum(1 for f in self.introduced if f.severity == "critical")

    @model_validator(mode="after")
    def _unmeasured_carries_nothing(self) -> ScopedSecurityReport:
        if self.state is not CollectionState.MEASURED:
            if self.introduced or self.preexisting or self.resolved:
                raise ValueError(f"{self.state.value} report must not carry findings or counts")
            if not self.reason.strip():
                raise ValueError(f"{self.state.value} report requires a reason")
        return self
