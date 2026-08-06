"""Typed contracts between SDLC phases.

Every phase consumes one of these models and produces the next one.
Keep them SMALL: large artifacts (specs, diffs, logs) live in the
artifact store / git; only references travel through Temporal history
(claim-check pattern, 2MB payload limit).
"""
from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel, Field, PrivateAttr, field_validator, model_validator,
)

from .measurement import CollectionState, Measurement


class ProjectMode(str, Enum):
    GREENFIELD = "greenfield"
    BROWNFIELD = "brownfield"


class HarnessKind(str, Enum):
    CLAUDE_CODE = "claude_code"   # claude -p
    OPENCODE = "opencode"         # opencode run
    CURSOR = "cursor"             # cursor-agent -p (E-35)


class GatePolicy(str, Enum):
    HARD = "hard"    # always wait for a human decision
    SOFT = "soft"    # auto-approve if quality signals pass, else escalate
    OFF = "off"      # auto-approve


class GateOutcome(str, Enum):
    APPROVE = "approve"    # proceed
    REJECT = "reject"      # terminal
    REVISE = "revise"      # loop back with guidance (Finding #6)


class TimeoutAction(str, Enum):
    """What an expired gate does (FR-303). REJECT is today's behaviour and
    the default everywhere except `merge` -- see PipelineConfig.gates."""
    REJECT = "reject"      # terminal, decided_by="timeout"
    APPROVE = "approve"
    HOLD = "hold"          # no final deadline; stays pending and visible


class GateConfig(BaseModel):
    """Per-gate policy + the confidence bar a SOFT gate must clear to
    auto-approve (FR-301), plus the E-9 timer schedule. threshold is read
    only when policy == SOFT; the *_after_hours fields fall back to a
    fraction of PipelineConfig.gate_timeout_hours when None (see
    sdlc.notify.schedule.build_schedule)."""
    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    on_timeout: TimeoutAction = TimeoutAction.REJECT
    remind_after_hours: int | None = Field(default=None, gt=0)
    escalate_after_hours: int | None = Field(default=None, gt=0)

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


class SessionEvent(BaseModel):
    """One normalised harness-transcript event (ADR-16). Harness-agnostic;
    adapters map their native streams onto this schema."""
    kind: str          # model_turn | tool_call | tool_result | file_read
                       # | file_write | command | compaction | result
                       # | tool_denied
    tool: str | None = None
    target: str | None = None      # file path or command line (scrubbed)
    exit_code: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    text: str | None = None        # payload (scrubbed)


class HarnessSession(BaseModel):
    """Canonical transcript of one harness run (ADR-16). NEVER enters
    workflow state — serialized to JSONL and claim-checked (E-38)."""
    harness: HarnessKind
    session_id: str | None = None
    model: str | None = None
    events: list[SessionEvent] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class SessionDigest(BaseModel):
    """BENCHMARK §4.3 waste aggregates + decision-skeleton. Small and
    bounded — travels inline on HarnessRunResult; always kept, even when
    the full transcript is downgraded at retro (OQ-B7)."""
    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0          # same path read more than once
    files_written: int = 0         # distinct paths written
    rewrite_churn: int = 0         # paths written more than once
    failed_commands: int = 0       # command events with exit_code not in (0, None)
    model_turns: int = 0
    compacted: bool = False
    denials: int = 0               # E-16: blocked tool calls
    escalations: int = 0           # E-17: tool calls that raised a gate
    input_tokens: int | None = None
    output_tokens: int | None = None
    decision_skeleton: list[str] = Field(default_factory=list)


class ContainmentLayer(str, Enum):
    """Where a containment rule is enforced (E-15/E-16, ADR-17)."""
    NATIVE = "native"   # declarative deny inside the harness CLI's own config
    HOOK = "hook"       # per-call inspection callback


class ToolDenial(BaseModel):
    """One blocked tool call. Small and bounded — travels inline on
    HarnessRunResult, same discipline as SessionDigest."""
    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None     # path or command line (scrubbed)
    # E-17: this denial was an ESCALATE rule the hook could not escalate
    # (batched call, or an unreadable transcript). No human was asked. It is
    # marked so the BATCHED outcome stays countable — see EscalationOutcome.
    escalation_declined: bool = False


class ContainmentReport(BaseModel):
    """What containment was ACTUALLY in force for a run. Partial coverage
    is recorded rather than refused, so a harness with fewer layers is
    visibly less contained instead of silently so (spec §5)."""
    enabled: bool = False
    layers_active: list[ContainmentLayer] = Field(default_factory=list)
    rules_enforced: list[str] = Field(default_factory=list)
    rules_unenforceable: list[str] = Field(default_factory=list)
    # E-17: rules that can actually raise a gate on THIS harness. Empty on a
    # harness without `defer`, so degradation is visible rather than silent.
    rules_escalatable: list[str] = Field(default_factory=list)


class ContainmentConfig(BaseModel):
    """FR-703 containment knobs. `strict` promotes partial layer coverage
    from 'recorded' to 'refuse to start'."""
    policy_path: str | None = None      # None -> $SDLC_CONTAINMENT_POLICY -> discovery
    strict: bool = False


class DeferredToolUse(BaseModel):
    """A tool call the harness suspended at, awaiting a human decision
    (E-17). Built activity-side from the CLI's `deferred_tool_use` payload;
    travels inline on HarnessRunResult — bounded, like ToolDenial."""
    tool_use_id: str              # the CLI replays THIS id on resume
    tool: str
    input_digest: str             # canonical digest of tool_input
    rule_id: str
    reason: str
    target: str | None = None     # scrubbed path/command, for the human


class ToolGrant(BaseModel):
    """One human decision about one suspended call. Single-use falls out of
    tool_use_id: the replayed call reuses it, a genuinely new call gets a
    fresh one and matches nothing."""
    tool_use_id: str
    tool: str
    input_digest: str
    rule_id: str
    approved: bool                # False = rejected / timed out / capped
    reason: str = ""              # reaches the model verbatim


class EscalationOutcome(str, Enum):
    """How an escalation ended. BATCHED and CAPPED never reached a human."""
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CAPPED = "capped"
    BATCHED = "batched"


class ToolEscalation(BaseModel):
    """The workflow's record of one escalation, for events.jsonl + E-36."""
    tool: str
    rule_id: str
    target: str | None = None
    outcome: EscalationOutcome
    decided_by: str = ""          # "" when nobody was asked
    round: int = 0                # the (gate, round) identity; 0 = no gate



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


class HandoffClaim(BaseModel):
    """One assertion about the work, carrying the evidence for it.
    Evidence-first, mirroring IntegrityFlag."""
    text: str
    evidence: str            # quote/reference from the scrubbed HarnessSession


class HandoffSummary(BaseModel):
    """FR-805: structured task-to-task handoff (intra-run continuity).

    Split by provenance: `files_touched` is computed from the materialized
    diff by the workflow, so no model can misreport it. The claim lists are
    extracted from the scrubbed session -- the diff cannot state WHY an
    approach was chosen or what was knowingly left undone.
    """
    task_id: str
    files_touched: list[str] = Field(default_factory=list)
    what_changed: list[HandoffClaim] = Field(default_factory=list)
    decisions_made: list[HandoffClaim] = Field(default_factory=list)
    open_concerns: list[HandoffClaim] = Field(default_factory=list)


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
    # E-38 (ADR-16): full scrubbed transcript as a claim-checked ref; waste
    # digest inline. The raw stdout rides a PrivateAttr so it can never
    # serialize into workflow state.
    session_ref: ArtifactRef | None = None
    session_digest: SessionDigest | None = None
    # E-15/E-16: containment outcome. Bounded and inline — the workflow and
    # the E-36 heatmap read these without loading the session artifact.
    denials: list[ToolDenial] = Field(default_factory=list)
    deferred: DeferredToolUse | None = None      # E-17: suspended tool call
    containment: ContainmentReport | None = None
    _raw_stdout: str = PrivateAttr(default="")

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
    deep_review: "DeepReviewReport | None" = None   # E-39: advisory lens
    notes: str = ""


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
    path: str = ""                  # http: resolved against adapter.endpoint()
    expect_status: int = 200        # http
    command: str = ""               # command: expects exit 0
    timeout_s: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _kind_carries_its_fields(self) -> "SmokeCheck":
        if self.kind == "http" and not self.path.strip():
            raise ValueError("an http smoke check requires a path")
        if self.kind == "command" and not self.command.strip():
            raise ValueError("a command smoke check requires a command")
        return self


class SmokeState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"      # the assertion was evaluated and did not hold
    ERRORED = "errored"    # we could not evaluate it at all


class SmokeCheckResult(BaseModel):
    """Tri-state on purpose (D-3). 'The adapter could not reach the service'
    is not a pass and is not a failed assertion -- collapsing the two is
    E-40's malformed-SARIF-reads-as-clean hole in a new location. Both
    non-passing states carry a reason, exactly as Measurement does."""
    name: str
    state: SmokeState
    detail: str = ""

    @model_validator(mode="after")
    def _failure_explains_itself(self) -> "SmokeCheckResult":
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
    def _failure_accounts_for_the_rollback(self) -> "DeployReport":
        if self.rolled_back and not self.rolled_back_to:
            raise ValueError("rolled_back requires rolled_back_to")
        if (not self.deployed and not self.rolled_back
                and not self.rollback_reason.strip()):
            raise ValueError(
                "a failed deploy must say why it was not rolled back")
        return self


class IntegrityFlag(BaseModel):
    """One anti-cheat observation drawn from the scrubbed transcript (E-39)."""
    kind: Literal["oracle_peeking", "hardcoded_answer",
                  "test_gaming", "excessive_backtracking"]
    detail: str
    evidence: str            # a quote/reference from the scrubbed transcript


class DeepReviewReport(BaseModel):
    """Advisory full-transcript lens (E-39). Reads the SCRUBBED HarnessSession
    as data — never the raw session, never via resume. Model family is
    ADR-6-independent of dev. NEVER blocks: the clean-context reviewer
    (ReviewReport) is the sole blocking lens; this report is recorded and
    retained for signal only. Fields are evidence-first."""
    findings: list[ReviewFinding] = Field(default_factory=list)
    integrity_flags: list[IntegrityFlag] = Field(default_factory=list)
    summary: str = ""
    approve: bool = True          # advisory opinion only
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def cheat_detected(self) -> bool:
        return bool(self.integrity_flags)


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


class RoleUsage(BaseModel):
    """One role's accumulated model spend across the run (E-33).

    cost_usd None is load-bearing: tokens are facts from the run; dollars
    are a lookup that can fail. A pricing miss must never discard tokens,
    so the field stays None until the first successfully priced call."""
    role: str                       # "architect", "dev", "clarify", ...
    model: str                      # last model seen for the role
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None


class SubQuestion(BaseModel):
    id: str
    question: str


class ConsultedSource(BaseModel):
    """Judgment before label: assess the source, THEN attach a relevance tag."""
    url: str
    title: str = ""
    assessment: str = ""            # what this source is / is worth
    relevance: str = ""             # e.g. "high" / "peripheral"


class GroundedFinding(BaseModel):
    """quote BEFORE claim (spec §4): commit to a verbatim span actually in the
    fetched bytes, then state what it supports. The verifier (research/verify.py)
    asserts `quote` is a substring of the page fetched THIS run for `source_url`."""
    source_url: str
    quote: str                      # verbatim span from bytes fetched this run
    claim: str
    sub_question_ids: list[str] = Field(default_factory=list)


class InferredFinding(BaseModel):
    """reasoning BEFORE claim. `fetched_at` is set only when the lead came from
    the corpus (a recalled lead honestly belongs here, never in grounded)."""
    reasoning: str
    claim: str
    based_on: list[str] = Field(default_factory=list)   # source urls / lead ids
    fetched_at: str | None = None


class Contradiction(BaseModel):
    topic: str
    positions: list[str] = Field(default_factory=list)
    assessment: str = ""
    unresolved: bool = True


class Gap(BaseModel):
    sub_question_id: str
    what_is_missing: str
    why_it_matters: str = ""


class ResearchBrief(BaseModel):
    """FR-107 grounded research brief. Field order is reasoning order (SGR):
    decompose -> gather -> what the bytes say -> what I concluded -> where
    sources disagree -> what I could not answer -> summary -> ref -> confidence.
    tests/test_research_models.py pins the order; a reorder is a regression."""
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    sources_consulted: list[ConsultedSource] = Field(default_factory=list)
    grounded_findings: list[GroundedFinding] = Field(default_factory=list)
    inferred_findings: list[InferredFinding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    summary: str = ""
    brief_ref: ArtifactRef | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ResearchPlan(BaseModel):
    """The planner's output, WITH its model spend.

    Carrying `usage` is why this type exists rather than a bare
    list[SubQuestion]: fan-out moves the model call activity-side, out of
    _run_role's reach, so an activity that calls a model must hand its usage
    back or the spend is silently lost (E-33 amendment, fan-out design §7)."""
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    usage: RoleUsage = Field(
        default_factory=lambda: RoleUsage(role="research", model="unknown"))


class SubQuestionFinding(BaseModel):
    """One sub-question's result: its own partial ResearchBrief plus spend.

    `failed=True` means the sub-question exhausted its retries or hit a
    non-retryable error. Its siblings survive -- a partial answer from three
    of four sub-questions is worth far more than nothing -- and the merge
    turns this into a Gap so a short brief is explained rather than just
    short."""
    sub_question: SubQuestion
    brief: ResearchBrief = Field(default_factory=ResearchBrief)
    usage: RoleUsage = Field(
        default_factory=lambda: RoleUsage(role="research", model="unknown"))
    failed: bool = False
    error: str = ""


class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.

    FR-915: a non-MEASURED state means the seam could not measure, so the
    advisory check passes as a no-op rather than forcing a spurious human
    override every run. A MEASURED 0.0 is a real zero and is graded as one.
    """
    coverage: Measurement


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
    kind: Literal["proposer", "harness", "research"] = "harness"
    harness: HarnessKind | None = None      # None for proposer/research roles
    model: str | None = None                # e.g. "zai-coding-plan/glm-5.2"
    # Which search provider a kind=research role uses. None for every other
    # kind. 'tavily' and 'exa' each require their API key reachable at boot
    # (validated in agents/loader.py); 'fake' is the CI/default opt-out.
    provider: Literal["tavily", "exa", "fake"] | None = None
    # Absolute paths to agents/research/tools/*.py, populated by the registry
    # loader for a kind=research role ONLY. Paths, not imported modules: the
    # loader validates them structurally (name/signature) but nothing imports
    # a tool as a side effect of importing roles (registry spec finding 3).
    tool_files: list[str] = Field(default_factory=list)
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
    RESEARCH_FINDING = "research_finding"    # verified grounded findings only
    RUN_SUMMARY = "run_summary"              # retro-stage per-run summary (E-32)


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


def _memory_backend_default() -> Literal["fake", "hindsight"]:
    value = os.environ.get("SDLC_MEMORY_BACKEND", "fake")
    return value if value in ("fake", "hindsight") else "fake"


class MemoryConfig(BaseModel):
    """FR-400. `watermark=None` means "capture fresh at run start"; setting
    it pins a run to a prior freeze point (ADR-5 explicit "refresh
    memory")."""
    enabled: bool = Field(
        default_factory=lambda: os.environ.get(
            "SDLC_MEMORY_ENABLED", "false").lower() == "true")
    backend: Literal["fake", "hindsight"] = Field(
        default_factory=_memory_backend_default)
    base_url: str = Field(
        default_factory=lambda: os.environ.get(
            "SDLC_MEMORY_BASE_URL", "http://localhost:8888"))
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
    base_url: str = "http://localhost:8888"

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


class ResearchConfig(BaseModel):
    """Research bounds (spec §3). Enforced INSIDE the tool functions, not the
    prompt. Exceeding one raises an ordinary error and the shortfall lands in
    the brief's `gaps`.

    SCOPE CHANGE (2026-08-04 fan-out design): max_searches/max_fetches/
    max_cost_usd/max_requests are PER SUB-QUESTION, not per run. Dividing a
    5-search pool across 4 sub-questions gives 1 search each -- shallower than
    the single-agent stage it replaces, which defeats the point. The run-level
    bound is max_run_cost_usd, enforced on the shared "run" budget scope.
    """
    max_sub_questions: int = 4
    """Fan-out width. A HARD SLICE applied to the planner's output, never a
    request the model is trusted to honour: measured behaviour is that a
    planner always returns the top of whatever range it is given, even for a
    yes/no lookup. Also the practical concurrency bound, since each
    sub-question runs an agent with its own CodeMode sandbox."""

    max_searches: int = 5               # per sub-question
    max_fetches: int = 10               # per sub-question
    max_cost_usd: float = 1.0           # per sub-question

    max_run_cost_usd: float = 4.0
    """Hard whole-run ceiling across every sub-question and every refine
    round, on the shared "run" budget scope. Deliberately equal to
    max_sub_questions * max_cost_usd: a refine round draws down what round
    one left unspent rather than being granted a fresh allowance."""

    max_refine_rounds: int = 1
    """Rounds of gate-driven refinement after the first brief. A refine
    triggers a whole second fan-out, so this is a spend ceiling as much as a
    complexity ceiling. Exhausting it proceeds with the current brief -- it
    is never a rejection."""

    max_requests: int = 40
    """Cap passed as pydantic-ai's UsageLimits(request_limit=...) around ONE
    sub-question's agent run. Independent of the tool-call bounds above:
    those cap web_search/get_page/deep_search calls; this caps total model
    requests (every turn, retry, and structured-output validation pass),
    staying under pydantic-ai's own default of 50 so an exhaustion is ours to
    catch and degrade, not an uncaught crash."""


class DeployConfig(BaseModel):
    """FR-1105: the hosting target is an adapter resolved from configuration,
    not a choice an agent makes. Off by default (D-9)."""
    enabled: bool = False
    adapter: Literal["compose", "script"] = "compose"
    # compose: base URL http smoke checks resolve against. The port is a
    # deployment fact the planner cannot know at plan time, so it lives here
    # rather than in the frozen DeployPlan.
    base_url: str | None = None
    # script: overrides for the deploy/rollback/version make targets.
    commands: dict[str, str] = Field(default_factory=dict)
    readiness_timeout_s: int = Field(default=60, ge=1)


class PipelineConfig(BaseModel):
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    max_session_resumes: int = 3            # FR-802: past this, fresh session
                                            # seeded with a handoff — compaction
                                            # is failure, never continued
    gates: dict[str, GateConfig] = Field(default_factory=lambda: {
        "clarify": GateConfig(policy=GatePolicy.HARD),
        "architecture": GateConfig(policy=GatePolicy.HARD),
        "plan": GateConfig(policy=GatePolicy.SOFT),
        # E-9: a merge gate that expires would discard a run which passed
        # every absolute check. Holding keeps it pending and visible in the
        # E-8 inbox instead. Every other gate keeps today's reject.
        "merge": GateConfig(policy=GatePolicy.HARD,
                            on_timeout=TimeoutAction.HOLD),
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
    max_tool_escalations: int = 3            # E-17: gates raised per task
                                             # attempt; past this, deny
    max_gate_rounds: int = 2                # FR-301: bounded revision loop;
                                            # exhaustion escalates to a hard
                                            # human gate
    gate_timeout_hours: int = 48
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    memoization_enabled: bool = False
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    research_enabled: bool = False          # FR-107: off by default; the
                                            # default pipeline is unchanged
                                            # until a project opts in
    containment_enabled: bool = False       # FR-703: off by default; the
                                            # policy is a fence, not a
                                            # sandbox — see ADR-17
    containment: ContainmentConfig = Field(default_factory=ContainmentConfig)
    review_enabled: bool = True             # FR-204: run the clean-context
                                            # reviewer per task; disable to trade
                                            # the anti-collusion check for cost
    deep_review_enabled: bool = False       # FR-111/E-39: opt-in transcript
                                            # lens; advisory, off by default
    adversarial_review_enabled: bool = False   # spec part 2: decorrelated
                                            # second opinion on the APPROVING
                                            # path only. Off by default -- it
                                            # changes hot-path outcomes and
                                            # costs a call per approving
                                            # attempt. Swept as a benchmark arm.
    coverage_threshold: float = Field(default=0.0, ge=0.0, le=100.0)
    # FR-106: diff-scoped coverage (0..100) the advisory `coverage` check must
    # clear. Default 0.0 = effectively off until a project opts in AND its test
    # command emits a coverage artifact (see measure_coverage).
    run_budget_usd: float = Field(default=0.0, ge=0.0)
    # E-33/FR-701: run-level USD budget. 0.0 = off (the coverage_threshold
    # opt-in pattern). When crossed, the workflow raises a hard "budget"
    # gate; approve grants one more increment of this amount.


class StageOutcome(BaseModel):
    """One stage's line in a RunSummary, projected from its BenchmarkRecord."""
    stage: str
    role: str
    outcome: str            # BenchmarkOutcome value
    duration_s: float
    cost_usd: float | None = None
    fix_attempts: int = 0


class ClarificationOutcome(BaseModel):
    """SC-4 signal: was a surfaced question answered by a human (operator time),
    auto-filled from the clarifier's suggested_answer, or left unanswered."""
    question_id: str
    question: str
    answered_by: Literal["human", "suggested", "unanswered"]


class GateOutcomeSummary(BaseModel):
    """SC-6 + ARCHITECTURE §10 calibration signal: policy, who decided, the
    confidence available at decision time, and any advisory checks waved."""
    gate: str
    round: int
    policy: str             # GatePolicy value
    decided_by: str         # "human" | "policy" | "timeout"
    approved: bool
    confidence: float | None = None
    overrides: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Retro-stage (14) aggregate of one run (E-32). Retained to memory,
    exported to report.html, and exposed via the run_summary() query."""
    run_id: str
    mode: str
    outcome: str            # the run() return string
    terminal_stage: str
    started_at: datetime
    ended_at: datetime
    duration_s: float
    stages: list[StageOutcome] = Field(default_factory=list)
    clarifications: list[ClarificationOutcome] = Field(default_factory=list)
    gates: list[GateOutcomeSummary] = Field(default_factory=list)
    roles: list[RoleUsage] = Field(default_factory=list)   # E-33 rollup
    cost_usd_total: float | None = None
    budget_usd: float | None = None     # configured run budget; None = off
    budget_crossings: int = 0           # budget-gate rounds raised (E-33)
    memory_enabled: bool = False
    memory_watermark: str | None = None
    memory_retains: int = 0
