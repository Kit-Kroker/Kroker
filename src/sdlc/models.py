"""Typed contracts between SDLC phases.

Every phase consumes one of these models and produces the next one.
Keep them SMALL: large artifacts (specs, diffs, logs) live in the
artifact store / git; only references travel through Temporal history
(claim-check pattern, 2MB payload limit).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from .core.models import (
    ArtifactRef,
    ClarificationDimension,
    HarnessKind,
    RoleUsage,
)
from .measurement import Measurement


class SessionEvent(BaseModel):
    """One normalised harness-transcript event (ADR-16). Harness-agnostic;
    adapters map their native streams onto this schema."""

    kind: str  # model_turn | tool_call | tool_result | file_read
    # | file_write | command | compaction | result
    # | tool_denied
    tool: str | None = None
    target: str | None = None  # file path or command line (scrubbed)
    exit_code: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    text: str | None = None  # payload (scrubbed)


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
    file_rereads: int = 0  # same path read more than once
    files_written: int = 0  # distinct paths written
    rewrite_churn: int = 0  # paths written more than once
    failed_commands: int = 0  # command events with exit_code not in (0, None)
    model_turns: int = 0
    compacted: bool = False
    denials: int = 0  # E-16: blocked tool calls
    escalations: int = 0  # E-17: tool calls that raised a gate
    input_tokens: int | None = None
    output_tokens: int | None = None
    decision_skeleton: list[str] = Field(default_factory=list)


class ContainmentLayer(StrEnum):
    """Where a containment rule is enforced (E-15/E-16, ADR-17)."""

    NATIVE = "native"  # declarative deny inside the harness CLI's own config
    HOOK = "hook"  # per-call inspection callback


class ToolDenial(BaseModel):
    """One blocked tool call. Small and bounded — travels inline on
    HarnessRunResult, same discipline as SessionDigest."""

    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None  # path or command line (scrubbed)
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


class DeferredToolUse(BaseModel):
    """A tool call the harness suspended at, awaiting a human decision
    (E-17). Built activity-side from the CLI's `deferred_tool_use` payload;
    travels inline on HarnessRunResult — bounded, like ToolDenial."""

    tool_use_id: str  # the CLI replays THIS id on resume
    tool: str
    input_digest: str  # canonical digest of tool_input
    rule_id: str
    reason: str
    target: str | None = None  # scrubbed path/command, for the human


class ToolGrant(BaseModel):
    """One human decision about one suspended call. Single-use falls out of
    tool_use_id: the replayed call reuses it, a genuinely new call gets a
    fresh one and matches nothing."""

    tool_use_id: str
    tool: str
    input_digest: str
    rule_id: str
    approved: bool  # False = rejected / timed out / capped
    reason: str = ""  # reaches the model verbatim


class EscalationOutcome(StrEnum):
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
    decided_by: str = ""  # "" when nobody was asked
    round: int = 0  # the (gate, round) identity; 0 = no gate


class OpenQuestion(BaseModel):
    id: str
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    answer: str | None = None  # filled by human (or auto)
    # E-85: additive only -- a pre-E-85 artifact must still validate.
    dimension: ClarificationDimension | None = None
    asked_by: str | None = None  # "supervisor" | "probe:C4"
    materiality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None  # repo path/symbol grounding it


class ClarifiedRequirements(BaseModel):
    summary: str
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    out_of_scope: list[str]
    open_questions: list[OpenQuestion]
    spec_ref: ArtifactRef | None = None
    # E-85: what actually ran, and what the cap cut. `dropped` is what makes
    # the cap honest -- without it, capping and being incurious are
    # indistinguishable in the record.
    dimensions_probed: list[ClarificationDimension] = Field(default_factory=list)
    dropped: list[OpenQuestion] = Field(default_factory=list)


class ArchitectureDecision(BaseModel):
    id: str
    decision: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)


class BrownfieldDelta(BaseModel):
    """FR-102's delta: what an architecture change does to a real tree.

    Three classes rather than one flat list because they have OPPOSITE
    grounding rules -- a modified path must exist and an added path must not
    (E-84 D8) -- and a single list cannot carry that distinction.
    """

    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class ArchitectureSpec(BaseModel):
    overview: str
    decisions: list[ArchitectureDecision]
    affected_modules: list[str] = Field(default_factory=list)  # brownfield
    new_components: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    spec_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301
    delta: BrownfieldDelta | None = None  # E-84, brownfield

    @model_validator(mode="after")
    def _affected_modules_follow_the_delta(self) -> ArchitectureSpec:
        """E-84 D7: one authority for what changed.

        `affected_modules` predates the typed delta and is documented as the
        delta in docs/schemas/agents-schema.html. When a delta is present it is the
        authority and this field is derived from it; when it is absent
        (greenfield, and the seeded specs tidyup/backlog.py:103 and the
        benchmark fixtures write) the field is left exactly as given.
        """
        if self.delta is not None:
            derived = sorted(set(self.delta.modified) | set(self.delta.removed))
            if list(self.affected_modules) != derived:
                self.affected_modules = derived
        return self


class ValidationContract(BaseModel):
    """FR-803: machine-checkable 'done', frozen at planning, before code.

    QA and reviewers validate against this — never against the
    implementation or the worker's narrative.
    """

    task_id: str
    assertions: list[str]  # human-readable, test-mappable
    test_commands: list[str] = Field(default_factory=list)
    lint_commands: list[str] = Field(default_factory=list)
    stack: str = ""  # e.g. "TypeScript/Node.js, npm
    # workspaces" — copied verbatim
    # from the architecture decision;
    # a hard constraint, not a soft
    # acceptance criterion
    frozen: bool = True  # set at plan gate; immutable after


class HandoffClaim(BaseModel):
    """One assertion about the work, carrying the evidence for it.
    Evidence-first, mirroring IntegrityFlag."""

    text: str
    evidence: str  # quote/reference from the scrubbed HarnessSession


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


class HarnessRunResult(BaseModel):
    """Normalized result from any coding harness invocation."""

    harness: HarnessKind
    session_id: str | None = None
    exit_code: int
    summary: str  # harness's final text (truncated)
    cost_usd: float | None = None
    commit_sha: str | None = None  # checkpoint commit after the run
    diff_ref: ArtifactRef | None = None
    # Observability for the context-ceiling trigger (Finding #7):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_window: int | None = None
    compacted: bool = False  # harness signalled a mid-run compaction
    # E-38 (ADR-16): full scrubbed transcript as a claim-checked ref; waste
    # digest inline. The raw stdout rides a PrivateAttr so it can never
    # serialize into workflow state.
    session_ref: ArtifactRef | None = None
    session_digest: SessionDigest | None = None
    # E-15/E-16: containment outcome. Bounded and inline — the workflow and
    # the E-36 heatmap read these without loading the session artifact.
    denials: list[ToolDenial] = Field(default_factory=list)
    deferred: DeferredToolUse | None = None  # E-17: suspended tool call
    escalations: list[ToolEscalation] = Field(default_factory=list)
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


class IntegrityFlag(BaseModel):
    """One anti-cheat observation drawn from the scrubbed transcript (E-39)."""

    kind: Literal["oracle_peeking", "hardcoded_answer", "test_gaming", "excessive_backtracking"]
    detail: str
    evidence: str  # a quote/reference from the scrubbed transcript


class PlanDeviation(BaseModel):
    """One way the session departed from the task it was given (E-83).

    Evidence-first, exactly like IntegrityFlag: a deviation whose quote is
    not in the transcript is dropped, because an advisory lens that can
    invent evidence is worse than no lens.
    """

    kind: Literal["unplanned_scope", "skipped_criterion", "approach_changed"]
    detail: str
    evidence: str  # a VERBATIM span from the scrubbed transcript


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


class SubQuestion(BaseModel):
    id: str
    question: str


class ConsultedSource(BaseModel):
    """Judgment before label: assess the source, THEN attach a relevance tag."""

    url: str
    title: str = ""
    assessment: str = ""  # what this source is / is worth
    relevance: str = ""  # e.g. "high" / "peripheral"


class GroundedFinding(BaseModel):
    """quote BEFORE claim (spec §4): commit to a verbatim span actually in the
    fetched bytes, then state what it supports. The verifier (research/verify.py)
    asserts `quote` is a substring of the page fetched THIS run for `source_url`."""

    source_url: str
    quote: str  # verbatim span from bytes fetched this run
    claim: str
    sub_question_ids: list[str] = Field(default_factory=list)


class InferredFinding(BaseModel):
    """reasoning BEFORE claim. `fetched_at` is set only when the lead came from
    the corpus (a recalled lead honestly belongs here, never in grounded)."""

    reasoning: str
    claim: str
    based_on: list[str] = Field(default_factory=list)  # source urls / lead ids
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
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))


class SubQuestionFinding(BaseModel):
    """One sub-question's result: its own partial ResearchBrief plus spend.

    `failed=True` means the sub-question exhausted its retries or hit a
    non-retryable error. Its siblings survive -- a partial answer from three
    of four sub-questions is worth far more than nothing -- and the merge
    turns this into a Gap so a short brief is explained rather than just
    short."""

    sub_question: SubQuestion
    brief: ResearchBrief = Field(default_factory=ResearchBrief)
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))
    failed: bool = False
    error: str = ""


class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.

    FR-915: a non-MEASURED state means the seam could not measure, so the
    advisory check passes as a no-op rather than forcing a spurious human
    override every run. A MEASURED 0.0 is a real zero and is graded as one.
    """

    coverage: Measurement


class DeploymentResult(BaseModel):
    environment: str
    version: str
    status: Literal["deployed", "failed", "rolled_back"]
    url: str | None = None


class MergeVerdict(BaseModel):
    """Advisory LLM proposer output (Finding #5). Consulted only under a
    SOFT merge policy, and only AFTER the DeterministicQualityGate passes.
    It can approve an already-clean build; it can never bypass the gate."""

    approve: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    concerns: list[str] = Field(default_factory=list)


class MemoryKind(StrEnum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"
    RESEARCH_FINDING = "research_finding"  # verified grounded findings only
    RUN_SUMMARY = "run_summary"  # retro-stage per-run summary (E-32)


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
            raise ValueError(f"unknown workflow {v!r}; known: {sorted(KNOWN_SCHEDULE_WORKFLOWS)}")
        return v


class ScheduleSpecAsset(BaseModel):
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def _cron_shape(cls, v: str) -> str:
        if len(v.split()) != 5:
            raise ValueError(
                f"cron must have 5 whitespace-separated fields, got {len(v.split())}: {v!r}"
            )
        return v


class ScheduleAsset(BaseModel):
    """One schedules/<id>.yaml. `id` comes from the filename, not the body —
    the filename is the API."""

    id: str
    spec: ScheduleSpecAsset
    action: ScheduleAction
