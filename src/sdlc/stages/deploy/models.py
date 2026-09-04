"""Artifact models for the deploy stage (spec A §2)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ...core.models import ArtifactRef


class FeatureFlag(BaseModel):
    """NG7: recorded and exported to the adapter, never managed. The factory
    does not build feature flagging -- it names the flag the customer's own
    system owns."""

    name: str
    cohort: str = "all"


class SmokeCheck(BaseModel):
    """A deterministic, machine-checkable assertion authored BEFORE the code
    exists (D-2), so it tests the requirement rather than the implementation.
    It may not reference an implementation detail the planner could not know
    at plan time -- ports and base URLs come from adapter config."""

    name: str
    kind: Literal["http", "command"]
    path: str = ""  # http: resolved against adapter.endpoint()
    expect_status: int = 200  # http
    command: str = ""  # command: expects exit 0
    timeout_s: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _kind_carries_its_fields(self) -> SmokeCheck:
        if self.kind == "http" and not self.path.strip():
            raise ValueError("an http smoke check requires a path")
        if self.kind == "command" and not self.command.strip():
            raise ValueError("a command smoke check requires a command")
        return self


class SmokeState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"  # the assertion was evaluated and did not hold
    ERRORED = "errored"  # we could not evaluate it at all


class SmokeCheckResult(BaseModel):
    """Tri-state on purpose (D-3). 'The adapter could not reach the service'
    is not a pass and is not a failed assertion -- collapsing the two is
    E-40's malformed-SARIF-reads-as-clean hole in a new location. Both
    non-passing states carry a reason, exactly as Measurement does."""

    name: str
    state: SmokeState
    detail: str = ""

    @model_validator(mode="after")
    def _failure_explains_itself(self) -> SmokeCheckResult:
        if self.state is not SmokeState.PASSED and not self.detail.strip():
            raise ValueError(f"{self.state.value} requires a detail")
        return self

    @property
    def passed(self) -> bool:
        return self.state is SmokeState.PASSED


class RollbackPolicy(BaseModel):
    auto: bool = True
    to: Literal["previous"] = "previous"


class DeployPlan(BaseModel):
    """FR-1104. Authored by devops_planner at the planning stage, frozen and
    hashed at the plan gate with ValidationContract.frozen semantics.

    Carries intent, never mechanics, and deliberately has NO adapter field:
    FR-1105 resolves the adapter from PipelineConfig.deploy.
    """

    environment: str
    version: str
    flag: FeatureFlag | None = None
    smoke_checks: list[SmokeCheck] = Field(default_factory=list)
    rollback: RollbackPolicy = Field(default_factory=RollbackPolicy)
    frozen: bool = True


class DeployReport(BaseModel):
    """FR-1104 outcome artifact. `deployed` is earned by passing smoke checks,
    never by a zero exit code."""

    deployed: bool
    environment: str
    version: str
    adapter: str
    endpoint: str = ""
    apply_detail: str = ""
    checks: list[SmokeCheckResult] = Field(default_factory=list)
    rolled_back: bool = False
    rollback_reason: str = ""
    rolled_back_to: str | None = None
    report_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def _failure_accounts_for_the_rollback(self) -> DeployReport:
        if self.rolled_back and not self.rolled_back_to:
            raise ValueError("rolled_back requires rolled_back_to")
        if not self.deployed and not self.rolled_back and not self.rollback_reason.strip():
            raise ValueError("a failed deploy must say why it was not rolled back")
        return self


class DeploymentResult(BaseModel):
    environment: str
    version: str
    status: Literal["deployed", "failed", "rolled_back"]
    url: str | None = None
