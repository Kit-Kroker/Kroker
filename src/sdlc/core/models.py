"""The shared core models and envelopes (spec A §2.2).

Rule 5 invariant: imports nothing from stages/ and nothing from any horizontal
package. Anything a core/ type references is itself in core/.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class ProjectMode(StrEnum):
    GREENFIELD = "greenfield"
    BROWNFIELD = "brownfield"


class HarnessKind(StrEnum):
    CLAUDE_CODE = "claude_code"  # claude -p
    OPENCODE = "opencode"  # opencode run
    CURSOR = "cursor"  # cursor-agent -p (E-35)
    # E-88: a COMPOSITION mode, not a CLI. A crew role's own harness is one
    # of the three above; `crew` says the stage runs as CrewTaskWorkflow.
    # Deliberately absent from HARNESSES: there is no subprocess to build.
    CREW = "crew"


class GatePolicy(StrEnum):
    HARD = "hard"  # always wait for a human decision
    SOFT = "soft"  # auto-approve if quality signals pass, else escalate
    OFF = "off"  # auto-approve


class GateOutcome(StrEnum):
    APPROVE = "approve"  # proceed
    REJECT = "reject"  # terminal
    REVISE = "revise"  # loop back with guidance (Finding #6)


class TimeoutAction(StrEnum):
    """What an expired gate does (FR-303). REJECT is today's behaviour and
    the default everywhere except `merge` -- see PipelineConfig.gates."""

    REJECT = "reject"  # terminal, decided_by="timeout"
    APPROVE = "approve"
    HOLD = "hold"  # no final deadline; stays pending and visible


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
    def _coerce(cls, v: GateConfig | GatePolicy | str | dict) -> GateConfig:
        if isinstance(v, GateConfig):
            return v
        if isinstance(v, dict):
            return cls(**v)
        return cls(policy=GatePolicy(v))


class GateSettings(BaseModel):
    """The three fields a durable HITL gate reads (E-42 D3).

    Extracted so GateHost does not depend on PipelineConfig: a triage run has
    roles, memory, research and deploy config it will never use, and taking the
    whole object would drag all of it into triage's input contract.
    """

    gates: dict[str, GateConfig] = Field(default_factory=dict)
    default_gate_policy: GatePolicy = GatePolicy.HARD
    gate_timeout_hours: int = 48


class ArtifactRef(BaseModel):
    """Claim-check reference to a large artifact (spec, diff, report)."""

    kind: str  # e.g. "spec", "plan", "qa_report", "diff"
    uri: str  # s3://..., file://..., git ref, etc.
    sha256: str | None = None


class ContainmentConfig(BaseModel):
    """FR-703 containment knobs. `strict` promotes partial layer coverage
    from 'recorded' to 'refuse to start'."""

    policy_path: str | None = None  # None -> $SDLC_CONTAINMENT_POLICY -> discovery
    strict: bool = False


class IdeaBrief(BaseModel):
    """Pipeline input: the raw idea / feature request."""

    title: str
    description: str
    mode: ProjectMode
    repo_url: str | None = None  # required for brownfield
    base_branch: str = "main"
    constraints: list[str] = Field(default_factory=list)


class ClarificationDimension(StrEnum):
    """SWE-RPG's practitioner-derived clarification taxonomy (E-85 §1.2).

    Stands in for MAC's five MultiWOZ domains: "implement a software feature"
    is one domain in MAC's terms, so our experts specialise by the KIND of
    ambiguity they resolve rather than by business domain.
    """

    FUNCTIONAL_INTENT = "C1"  # the core behaviour change needed
    BUSINESS_SEMANTICS = "C2"  # domain rules and constraints
    TECHNICAL_CONTEXT = "C3"  # architectural and dependency considerations
    INTERFACE_SPEC = "C4"  # API contracts and signatures
    CODE_STRUCTURE = "C5"  # repository patterns and conventions
    DATA_SEMANTICS = "C6"  # data invariants and constraints


class RoleUsage(BaseModel):
    """One role's accumulated model spend across the run (E-33).

    cost_usd None is load-bearing: tokens are facts from the run; dollars
    are a lookup that can fail. A pricing miss must never discard tokens,
    so the field stays None until the first successfully priced call."""

    role: str  # "architect", "dev", "clarify", ...
    model: str  # last model seen for the role
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None


class GateDecision(BaseModel):
    gate: str  # "architecture", "merge", ...
    round: int = 1  # revision round (Finding #6)
    outcome: GateOutcome
    decided_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    comments: str | None = None
    guidance: str | None = None  # fed back into the agent on 'revise'
    # C2: authorize the NEXT attempt to edit the contract's frozen tests.
    # Read only by the code-stage task gate, and only on `revise` -- inert
    # everywhere else, exactly like `guidance` on a non-revise outcome.
    # Never inferred from `guidance` text: a session that writes gate-facing
    # prose about a "wrong test" must not be able to unfreeze itself.
    thaw_tests: bool = False
    decided_at: datetime | None = None

    @property
    def approved(self) -> bool:
        """Convenience for callers that only branch on go/no-go. `reject`
        and `revise` are both non-approvals; callers that must distinguish
        read `outcome` directly."""
        return self.outcome is GateOutcome.APPROVE


class RoleConfig(BaseModel):
    """Which harness/model a 'doing' role uses. Enables cross-harness review."""

    kind: Literal["proposer", "harness", "research"] = "harness"
    harness: HarnessKind | None = None  # None for proposer/research roles
    model: str | None = None  # e.g. "zai-coding-plan/glm-5.2"
    # E-88: only for harness == CREW. `layout` names crew/layouts/<name>.yaml;
    # `lead_harness` is the run-level override for the LEAD's CLI, so a
    # benchmark cell can read `crew:<lead_harness>` and the harness dimension
    # survives. Non-lead roles are never overridable from a run.
    layout: str | None = None
    lead_harness: HarnessKind | None = None
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
    context_budget_tokens: int = 30_000  # FR-801: enforced at prompt assembly
    extra_args: list[str] = Field(default_factory=list)
    # Long-running activity timeouts for this role's harness invocations
    # (coding/test/deploy runs). None falls back to the workflow-wide
    # SDLC_LONG_ACTIVITY_* defaults — set per-role when one agent's harness
    # is known to go quiet longer (or shorter) between heartbeats than others.
    activity_timeout_hours: int | None = None
    activity_heartbeat_minutes: int | None = None


class ExecutionMode(StrEnum):
    SERIAL = "serial"  # default: consistent design decisions (ADR-13)
    WAVES = "waves"  # dependency-ordered parallel; overlaps still serialize


class BenchmarkConfig(BaseModel):
    """Carried on PipelineConfig. case_id=None => not a benchmark run."""

    case_id: str | None = None
    bench_run_id: str | None = None
    rubrics: dict[str, str] = Field(default_factory=dict)  # stage -> rubric text
    vetoes: dict[str, str] = Field(default_factory=dict)  # stage -> veto YAML text (E-83)
    judge_model: str | None = None  # model the judge uses


def gate_key(gate: str, round: int) -> str:
    """Round-scoped gate identity — 'first decision wins' applies per round."""
    return f"{gate}#{round}"


def _memory_backend_default() -> Literal["fake", "hindsight"]:
    value = os.environ.get("SDLC_MEMORY_BACKEND", "fake")
    if value == "hindsight":
        return "hindsight"
    return "fake"


class MemoryConfig(BaseModel):
    """FR-400. `watermark=None` means "capture fresh at run start"; setting
    it pins a run to a prior freeze point (ADR-5 explicit "refresh
    memory")."""

    enabled: bool = Field(
        default_factory=lambda: os.environ.get("SDLC_MEMORY_ENABLED", "false").lower() == "true"
    )
    backend: Literal["fake", "hindsight"] = Field(default_factory=_memory_backend_default)
    base_url: str = Field(
        default_factory=lambda: os.environ.get("SDLC_MEMORY_BASE_URL", "http://localhost:8888")
    )
    org_bank: str = "org"
    project_bank: str = "project:default"
    watermark: str | None = None


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

    max_searches: int = 5  # per sub-question
    max_fetches: int = 10  # per sub-question
    max_cost_usd: float = 1.0  # per sub-question

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
    # Board identity (E-78). Deliberately NOT MemoryConfig.project_bank:
    # that addresses Hindsight, this addresses the board SQLite. Two stores,
    # two identifiers — sharing one by accident couples unrelated lifetimes.
    project_key: str = "default"
    max_session_resumes: int = 3  # FR-802: past this, fresh session
    # seeded with a handoff — compaction
    # is failure, never continued
    gates: dict[str, GateConfig] = Field(
        default_factory=lambda: {
            "clarify": GateConfig(policy=GatePolicy.HARD),
            "architecture": GateConfig(policy=GatePolicy.HARD),
            "plan": GateConfig(policy=GatePolicy.SOFT),
            # E-9: a merge gate that expires would discard a run which passed
            # every absolute check. Holding keeps it pending and visible in the
            # E-8 inbox instead. Every other gate keeps today's reject.
            "merge": GateConfig(policy=GatePolicy.HARD, on_timeout=TimeoutAction.HOLD),
            "deploy": GateConfig(policy=GatePolicy.HARD),
        }
    )
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
    roles: dict[str, RoleConfig] = Field(
        default_factory=lambda: {
            "dev": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
            "test": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
            "devops": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
        }
    )
    max_fix_attempts: int = 2  # then escalate to human
    max_tool_escalations: int = 3  # E-17: gates raised per task
    # attempt; past this, deny
    max_delta_retries: int = 1  # E-84 D11: brownfield re-prompt limit
    max_gate_rounds: int = 2  # FR-301: bounded revision loop;
    # exhaustion escalates to a hard
    # human gate
    gate_timeout_hours: int = 48
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    memoization_enabled: bool = False
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    research_enabled: bool = False  # FR-107: off by default; the
    # default pipeline is unchanged
    # until a project opts in
    containment_enabled: bool = False  # FR-703: off by default; the
    # policy is a fence, not a
    # sandbox — see ADR-17
    containment: ContainmentConfig = Field(default_factory=ContainmentConfig)
    review_enabled: bool = True  # FR-204: run the clean-context
    # reviewer per task; disable to trade
    # the anti-collusion check for cost
    deep_review_enabled: bool = False  # FR-111/E-39: opt-in transcript
    # lens; advisory, off by default
    adversarial_review_enabled: bool = False  # spec part 2: decorrelated
    # second opinion on the APPROVING
    # path only. Off by default -- it
    # changes hot-path outcomes and
    # costs a call per approving
    # attempt. Swept as a benchmark arm.
    clarify_probes_enabled: bool = False  # E-85: off by default; the
    # default pipeline stays the
    # single-call clarifier.
    clarify_question_cap: int = Field(default=5, ge=1)  # E-85 D9: hard cap
    # on the batch a human sees. MAC
    # held latency with "one
    # clarification per turn"; our
    # unit is a human blocking on
    # gate_timeout_hours.
    coverage_threshold: float = Field(default=0.0, ge=0.0, le=100.0)
    # FR-106: diff-scoped coverage (0..100) the advisory `coverage` check must
    # clear. Default 0.0 = effectively off until a project opts in AND its test
    # command emits a coverage artifact (see measure_coverage).
    run_budget_usd: float = Field(default=0.0, ge=0.0)
    # E-33/FR-701: run-level USD budget. 0.0 = off (the coverage_threshold
    # opt-in pattern). When crossed, the workflow raises a hard "budget"
    # gate; approve grants one more increment of this amount.

    def gate_settings(self) -> GateSettings:
        """Project the three gate fields. `gates` is copied, not aliased --
        a workflow handed these must not be able to mutate the config."""
        return GateSettings(
            gates=dict(self.gates),
            default_gate_policy=self.default_gate_policy,
            gate_timeout_hours=self.gate_timeout_hours,
        )


class StageOutcome(BaseModel):
    """One stage's line in a RunSummary, projected from its BenchmarkRecord."""

    stage: str
    role: str
    outcome: str  # BenchmarkOutcome value
    duration_s: float
    cost_usd: float | None = None
    fix_attempts: int = 0


class ClarificationOutcome(BaseModel):
    """SC-4 signal: was a surfaced question answered by a human (operator time),
    auto-filled from the clarifier's suggested_answer, or left unanswered."""

    question_id: str
    question: str
    answered_by: Literal["human", "suggested", "unanswered"]
    dimension: ClarificationDimension | None = None  # E-85


class GateOutcomeSummary(BaseModel):
    """SC-6 + ARCHITECTURE §10 calibration signal: policy, who decided, the
    confidence available at decision time, and any advisory checks waved."""

    gate: str
    round: int
    policy: str  # GatePolicy value
    decided_by: str  # "human" | "policy" | "timeout"
    approved: bool
    confidence: float | None = None
    overrides: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Retro-stage (14) aggregate of one run (E-32). Retained to memory,
    exported to report.html, and exposed via the run_summary() query."""

    run_id: str
    mode: str
    title: str = ""  # E-10: closed runs render from here
    repo_url: str | None = None
    outcome: str  # the run() return string
    terminal_stage: str
    started_at: datetime
    ended_at: datetime
    duration_s: float
    stages: list[StageOutcome] = Field(default_factory=list)
    clarifications: list[ClarificationOutcome] = Field(default_factory=list)
    gates: list[GateOutcomeSummary] = Field(default_factory=list)
    roles: list[RoleUsage] = Field(default_factory=list)  # E-33 rollup
    cost_usd_total: float | None = None
    budget_usd: float | None = None  # configured run budget; None = off
    budget_crossings: int = 0  # budget-gate rounds raised (E-33)
    memory_enabled: bool = False
    memory_watermark: str | None = None
    memory_retains: int = 0


class RunState(BaseModel):
    """Live counterpart to RunSummary: what a run looks like mid-flight,
    exposed via the run_state() query (E-10).

    Field names mirror RunSummary where they overlap, deliberately -- the
    fleet view and the retro report describe the same run, and two
    vocabularies for one concept is how they come to disagree.

    cost_usd_total stays None rather than 0.0 when pricing failed: see
    RoleUsage.cost_usd. A pricing miss must never read as a free run.
    """

    run_id: str
    title: str
    repo_url: str | None = None
    mode: str
    status: str  # GateHost._status verbatim
    current_stage: str | None = None  # last STAGE_STARTED in _trace
    started_at: datetime
    decisions: list[GateDecision] = Field(default_factory=list)
    roles: list[RoleUsage] = Field(default_factory=list)
    cost_usd_total: float | None = None
    budget_usd: float | None = None
    budget_crossings: int = 0
