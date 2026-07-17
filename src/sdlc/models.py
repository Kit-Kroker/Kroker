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

from pydantic import BaseModel, Field, field_validator


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


class GateOutcome(str, Enum):
    APPROVE = "approve"    # proceed
    REJECT = "reject"      # terminal
    REVISE = "revise"      # loop back with guidance (Finding #6)


class GateConfig(BaseModel):
    """Per-gate policy + the confidence bar a SOFT gate must clear to
    auto-approve (FR-301). threshold is read only when policy == SOFT."""
    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    @classmethod
    def _coerce(cls, v: "GateConfig | GatePolicy | str | dict") -> "GateConfig":
        if isinstance(v, GateConfig):
            return v
        if isinstance(v, dict):
            return cls(**v)
        return cls(policy=GatePolicy(v))


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
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301


class ValidationContract(BaseModel):
    """FR-803: machine-checkable 'done', frozen at planning, before code.

    QA and reviewers validate against this — never against the
    implementation or the worker's narrative.
    """
    task_id: str
    assertions: list[str]                   # human-readable, test-mappable
    test_commands: list[str] = Field(default_factory=list)
    lint_commands: list[str] = Field(default_factory=list)
    stack: str = ""                         # e.g. "TypeScript/Node.js, npm
                                             # workspaces" — copied verbatim
                                             # from the architecture decision;
                                             # a hard constraint, not a soft
                                             # acceptance criterion
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
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301


class HarnessRunResult(BaseModel):
    """Normalized result from any coding harness invocation."""
    harness: HarnessKind
    session_id: str | None = None
    exit_code: int
    summary: str                            # harness's final text (truncated)
    cost_usd: float | None = None
    commit_sha: str | None = None           # checkpoint commit after the run
    diff_ref: ArtifactRef | None = None
    # Observability for the context-ceiling trigger (Finding #7):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_window: int | None = None
    compacted: bool = False                 # harness signalled a mid-run compaction

    def near_context_ceiling(self, fraction: float = 0.75) -> bool:
        """True when the run is at/over the usable context budget. A
        harness-signalled compaction always counts; otherwise compare
        input tokens to a fraction of the window. Unknown token data is
        treated as 'not at ceiling' so callers fall back to the resume
        counter rather than mis-triggering."""
        if self.compacted:
            return True
        if self.input_tokens is None or not self.context_window:
            return False
        return self.input_tokens > fraction * self.context_window


class TaskResult(BaseModel):
    task_id: str
    status: Literal["done", "failed", "quarantined"]
    attempts: int
    branch: str
    run: HarnessRunResult | None = None
    handoff: HandoffSummary | None = None   # FR-805
    qa: QAReport | None = None              # NEW: evidence for the merge gate
    review: ReviewReport | None = None      # FR-204: clean-context review evidence
    notes: str = ""


class QAReport(BaseModel):
    tests_passed: bool
    coverage_pct: float | None = None
    failing_tests: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    stack_mismatch: bool = False            # diff uses a fundamentally
                                             # different language/runtime
                                             # than the contract's frozen
                                             # stack, not merely incomplete
    report_ref: ArtifactRef | None = None


class SecurityFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    rule: str                               # which scanner rule matched
    detail: str
    path: str = ""


class SecurityReport(BaseModel):
    """Deterministic scanner evidence for the merge gate's absolute floor
    (FR-106/NFR-5/SC-5). `critical` is the count feeding the
    `security_no_critical` absolute check; a minimal ruleset now, seam to a
    real SAST later."""
    critical: int
    findings: list[SecurityFinding] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    assertion: str                          # which contract assertion / concern
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


class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.
    `measured=False` means no coverage artifact was emitted by the run's test
    commands — the seam could not measure, so the check passes rather than
    forcing a spurious human override every run."""
    measured: bool
    diff_pct: float | None = None       # 0..100 over changed files
    detail: str = ""


class GateDecision(BaseModel):
    gate: str                               # "architecture", "merge", ...
    round: int = 1                          # revision round (Finding #6)
    outcome: GateOutcome
    decided_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    comments: str | None = None
    guidance: str | None = None             # fed back into the agent on 'revise'
    decided_at: datetime | None = None

    @property
    def approved(self) -> bool:
        """Convenience for callers that only branch on go/no-go. `reject`
        and `revise` are both non-approvals; callers that must distinguish
        read `outcome` directly."""
        return self.outcome is GateOutcome.APPROVE


class DeploymentResult(BaseModel):
    environment: str
    version: str
    status: Literal["deployed", "failed", "rolled_back"]
    url: str | None = None


class RoleConfig(BaseModel):
    """Which harness/model a 'doing' role uses. Enables cross-harness review."""
    kind: Literal["proposer", "harness"] = "harness"
    harness: HarnessKind | None = None      # None for proposer roles
    model: str | None = None                # e.g. "zai-coding-plan/glm-5.2"
    # Loaded from agents/<role>/instructions.md by the registry loader (E-2).
    # None for harness roles: they run a CLI and carry no prompt of ours.
    # PROMPT_SHAS hashes these bytes, so editing one invalidates exactly that
    # stage's memo — which content_key already did via prompt_sha before the
    # text moved house. Moving it buys no new cache capability.
    instructions: str | None = None
    context_budget_tokens: int = 30_000     # FR-801: enforced at prompt assembly
    extra_args: list[str] = Field(default_factory=list)
    # Long-running activity timeouts for this role's harness invocations
    # (coding/test/deploy runs). None falls back to the workflow-wide
    # SDLC_LONG_ACTIVITY_* defaults — set per-role when one agent's harness
    # is known to go quiet longer (or shorter) between heartbeats than others.
    activity_timeout_hours: int | None = None
    activity_heartbeat_minutes: int | None = None


class ExecutionMode(str, Enum):
    SERIAL = "serial"    # default: consistent design decisions (ADR-13)
    WAVES = "waves"      # dependency-ordered parallel; overlaps still serialize


class BenchmarkConfig(BaseModel):
    """Carried on PipelineConfig. case_id=None => not a benchmark run."""
    case_id: str | None = None
    bench_run_id: str | None = None
    rubrics: dict[str, str] = Field(default_factory=dict)   # stage -> rubric text
    judge_model: str | None = None                          # model the judge uses


def gate_key(gate: str, round: int) -> str:
    """Round-scoped gate identity — 'first decision wins' applies per round."""
    return f"{gate}#{round}"


class MergeVerdict(BaseModel):
    """Advisory LLM proposer output (Finding #5). Consulted only under a
    SOFT merge policy, and only AFTER the DeterministicQualityGate passes.
    It can approve an already-clean build; it can never bypass the gate."""
    approve: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    concerns: list[str] = Field(default_factory=list)


class MemoryKind(str, Enum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"


class RecallSnapshot(BaseModel):
    """Persisted, hashed recall result — FR-402: a declared stage input,
    never a live side-channel. `degraded=True` means the backend was
    unreachable; the pipeline proceeds with an empty snapshot rather than
    blocking on memory."""
    query_hash: str
    bank: str
    watermark: str
    items: list[str] = Field(default_factory=list)
    degraded: bool = False


class RetainItem(BaseModel):
    kind: MemoryKind
    bank: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """FR-400. `watermark=None` means "capture fresh at run start"; setting
    it pins a run to a prior freeze point (ADR-5 explicit "refresh
    memory")."""
    enabled: bool = False
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8088"
    org_bank: str = "org"
    project_bank: str = "project:default"
    watermark: str | None = None


KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}


class ScheduleAction(BaseModel):
    """The start-workflow action of a schedule asset. Temporal Schedules can
    only start workflows, never activities — hence ReflectWorkflow."""
    workflow: str
    banks: list[str] = Field(min_length=1)
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8088"

    @field_validator("workflow")
    @classmethod
    def _known_workflow(cls, v: str) -> str:
        if v not in KNOWN_SCHEDULE_WORKFLOWS:
            raise ValueError(
                f"unknown workflow {v!r}; known: "
                f"{sorted(KNOWN_SCHEDULE_WORKFLOWS)}")
        return v


class ScheduleSpecAsset(BaseModel):
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def _cron_shape(cls, v: str) -> str:
        if len(v.split()) != 5:
            raise ValueError(
                f"cron must have 5 whitespace-separated fields, got "
                f"{len(v.split())}: {v!r}")
        return v


class ScheduleAsset(BaseModel):
    """One schedules/<id>.yaml. `id` comes from the filename, not the body —
    the filename is the API."""
    id: str
    spec: ScheduleSpecAsset
    action: ScheduleAction


class PipelineConfig(BaseModel):
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    max_session_resumes: int = 3            # FR-802: past this, fresh session
                                            # seeded with a handoff — compaction
                                            # is failure, never continued
    gates: dict[str, GateConfig] = Field(default_factory=lambda: {
        "clarify": GateConfig(policy=GatePolicy.HARD),
        "architecture": GateConfig(policy=GatePolicy.HARD),
        "plan": GateConfig(policy=GatePolicy.SOFT),
        "merge": GateConfig(policy=GatePolicy.HARD),
        "deploy": GateConfig(policy=GatePolicy.HARD),
    })
    # Policy for gates not named in `gates` above — e.g. the per-task
    # escalation gate `task:<id>` fired when a dev task exhausts its fix
    # budget. Kept separate from `gates` since task ids aren't known upfront.
    default_gate_policy: GatePolicy = GatePolicy.HARD

    @field_validator("gates", mode="before")
    @classmethod
    def _coerce_gates(cls, v):
        if not isinstance(v, dict):
            return v
        return {k: GateConfig._coerce(gv) for k, gv in v.items()}
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
    # Harness-execution roles ONLY (keys match DevTask.role). This is a
    # hardcoded MIRROR of the agents/ registry's harness roles, not a second registry:
    # PipelineConfig is constructed inside the workflow (feature.py:602), so
    # this default cannot read the file. agents/loader.py asserts the two agree
    # at boot. Change one, change both, or the worker won't start.
    roles: dict[str, RoleConfig] = Field(default_factory=lambda: {
        "dev": RoleConfig(harness=HarnessKind.OPENCODE,
                          model="zai-coding-plan/glm-5.2"),
        "test": RoleConfig(harness=HarnessKind.OPENCODE,
                           model="zai-coding-plan/glm-5.2"),
        "devops": RoleConfig(harness=HarnessKind.OPENCODE,
                             model="zai-coding-plan/glm-5.2"),
    })
    max_fix_attempts: int = 2                # then escalate to human
    max_gate_rounds: int = 2                # FR-301: bounded revision loop;
                                            # exhaustion escalates to a hard
                                            # human gate
    gate_timeout_hours: int = 48
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    memoization_enabled: bool = False
    review_enabled: bool = True             # FR-204: run the clean-context
                                            # reviewer per task; disable to trade
                                            # the anti-collusion check for cost
    coverage_threshold: float = Field(default=0.0, ge=0.0, le=100.0)
    # FR-106: diff-scoped coverage (0..100) the advisory `coverage` check must
    # clear. Default 0.0 = effectively off until a project opts in AND its test
    # command emits a coverage artifact (see measure_coverage).
