"""Typed contracts between SDLC phases.

Every phase consumes one of these models and produces the next one.
Keep them SMALL: large artifacts (specs, diffs, logs) live in the
artifact store / git; only references travel through Temporal history
(claim-check pattern, 2MB payload limit).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProjectMode(str, Enum):
    GREENFIELD = "greenfield"
    BROWNFIELD = "brownfield"


class HarnessKind(str, Enum):
    CLAUDE_CODE = "claude_code"   # claude -p
    OPENCODE = "opencode"         # opencode run


class GatePolicy(str, Enum):
    HARD = "hard"    # always wait for a human decision
    SOFT = "soft"    # auto-approve if quality signals pass, else escalate
    OFF = "off"      # auto-approve


class ArtifactRef(BaseModel):
    """Claim-check reference to a large artifact (spec, diff, report)."""
    kind: str                      # e.g. "spec", "plan", "qa_report", "diff"
    uri: str                       # s3://..., file://..., git ref, etc.
    sha256: str | None = None


class IdeaBrief(BaseModel):
    """Pipeline input: the raw idea / feature request."""
    title: str
    description: str
    mode: ProjectMode
    repo_url: str | None = None            # required for brownfield
    base_branch: str = "main"
    constraints: list[str] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    id: str
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    answer: str | None = None              # filled by human (or auto)


class ClarifiedRequirements(BaseModel):
    summary: str
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    out_of_scope: list[str]
    open_questions: list[OpenQuestion]
    spec_ref: ArtifactRef | None = None


class ArchitectureDecision(BaseModel):
    id: str
    decision: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)


class ArchitectureSpec(BaseModel):
    overview: str
    decisions: list[ArchitectureDecision]
    affected_modules: list[str] = Field(default_factory=list)  # brownfield
    new_components: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    spec_ref: ArtifactRef | None = None


class ValidationContract(BaseModel):
    """FR-803: machine-checkable 'done', frozen at planning, before code.

    QA and reviewers validate against this — never against the
    implementation or the worker's narrative.
    """
    task_id: str
    assertions: list[str]                   # human-readable, test-mappable
    test_commands: list[str] = Field(default_factory=list)
    frozen: bool = True                     # set at plan gate; immutable after


class HandoffSummary(BaseModel):
    """FR-805: structured task-to-task handoff (intra-run continuity)."""
    task_id: str
    what_changed: list[str]
    decisions_made: list[str] = Field(default_factory=list)
    open_concerns: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)


class DevTask(BaseModel):
    id: str
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str]
    files_hint: list[str] = Field(default_factory=list)
    overlaps: list[str] = Field(default_factory=list)   # modules shared with
                                                        # other tasks (FR-104):
                                                        # overlapping tasks
                                                        # serialize in wave mode
    contract: ValidationContract | None = None          # frozen at planning
    role: Literal["dev", "test", "devops"] = "dev"


class ImplementationPlan(BaseModel):
    tasks: list[DevTask]
    plan_ref: ArtifactRef | None = None


class HarnessRunResult(BaseModel):
    """Normalized result from any coding harness invocation."""
    harness: HarnessKind
    session_id: str | None = None
    exit_code: int
    summary: str                            # harness's final text (truncated)
    cost_usd: float | None = None
    commit_sha: str | None = None           # checkpoint commit after the run
    diff_ref: ArtifactRef | None = None


class TaskResult(BaseModel):
    task_id: str
    status: Literal["done", "failed", "quarantined"]
    attempts: int
    branch: str
    run: HarnessRunResult | None = None
    handoff: HandoffSummary | None = None   # FR-805
    notes: str = ""


class QAReport(BaseModel):
    tests_passed: bool
    coverage_pct: float | None = None
    failing_tests: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    report_ref: ArtifactRef | None = None


class GateDecision(BaseModel):
    gate: str                               # "spec", "plan", "merge", "deploy"
    approved: bool
    decided_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    comments: str | None = None
    decided_at: datetime | None = None


class DeploymentResult(BaseModel):
    environment: str
    version: str
    status: Literal["deployed", "failed", "rolled_back"]
    url: str | None = None


class RoleConfig(BaseModel):
    """Which harness/model a 'doing' role uses. Enables cross-harness review."""
    harness: HarnessKind
    model: str | None = None                # e.g. "anthropic/claude-sonnet-4-6"
    context_budget_tokens: int = 30_000     # FR-801: enforced at prompt assembly
    extra_args: list[str] = Field(default_factory=list)


class ExecutionMode(str, Enum):
    SERIAL = "serial"    # default: consistent design decisions (ADR-13)
    WAVES = "waves"      # dependency-ordered parallel; overlaps still serialize


class PipelineConfig(BaseModel):
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    max_session_resumes: int = 3            # FR-802: past this, fresh session
                                            # seeded with a handoff — compaction
                                            # is failure, never continued
    gates: dict[str, GatePolicy] = Field(default_factory=lambda: {
        "clarify": GatePolicy.HARD,
        "architecture": GatePolicy.HARD,
        "plan": GatePolicy.SOFT,
        "merge": GatePolicy.HARD,
        "deploy": GatePolicy.HARD,
    })
    roles: dict[str, RoleConfig] = Field(default_factory=lambda: {
        "dev": RoleConfig(harness=HarnessKind.CLAUDE_CODE),
        "test": RoleConfig(harness=HarnessKind.CLAUDE_CODE),
        "reviewer": RoleConfig(harness=HarnessKind.OPENCODE,
                               model="openai/gpt-5.2"),  # cross-harness review
        "devops": RoleConfig(harness=HarnessKind.CLAUDE_CODE),
    })
    max_fix_attempts: int = 2                # then escalate to human
    gate_timeout_hours: int = 48
