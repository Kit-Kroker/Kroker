"""Typed contracts for pipeline-step benchmarking.

One BenchmarkRecord per stage boundary and per code-task attempt. The three
dimensions (quality / cost / speed) are kept RAW — never pre-normalized — so
the reporter can recompute under different weights without re-running.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from ..agents.loader import HARNESS_ROLES, PROPOSER_ROLES
from ..models import GatePolicy, HarnessKind, PlanDrift, SessionDigest


class Arm(BaseModel):
    """A named role→model mix: one cell of the model×role sweep. `default`
    (optional) sets the model for every overridable role; `role_models`
    overrides specific roles and wins over `default`. Roles left unset (with
    `default=None`) keep the registry default at run time."""
    name: str
    default: str | None = None
    role_models: dict[str, str] = Field(default_factory=dict)

    def resolve(self) -> dict[str, str]:
        if self.default is None:
            return dict(self.role_models)
        base = {r: self.default for r in (HARNESS_ROLES | PROPOSER_ROLES)}
        base.update(self.role_models)
        return base


class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"
    ORACLE = "oracle"
    ORACLE_TASK = "oracle_task"


class BenchmarkOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVISED = "revise"
    ESCALATED = "escalated"


class QualityScore(BaseModel):
    score: float | None = None              # 0.0..1.0; None when judge errored
    components: dict[str, float] = Field(default_factory=dict)
    # Non-DAG lenses (deep_review/adversary/handoff) are judges too. Omitting
    # one here is not a type error at the call site -- _stage_record passes
    # `judge: str` straight through -- it is a ValidationError swallowed by the
    # caller's `except Exception`. tests/test_judge_literal.py pins the set.
    judge: Literal["contract", "llm_judge", "human_override", "error",
                   "oracle", "deep_review", "adversary", "handoff",
                   "staged_rubric"]


class CostBag(BaseModel):
    usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class SpeedBag(BaseModel):
    wall_clock_s: float
    started_at: datetime
    ended_at: datetime


class WasteBag(BaseModel):
    """BENCHMARK.md §4.3 coordination-and-waste aggregates for one coding
    attempt: activity that did not advance the goal. Projected from
    SessionDigest, minus the unbounded decision_skeleton and the token
    fields CostBag already owns.

    A record carries `waste=None` when no harness session was captured --
    proposer stages have no transcript at all. None means NOT MEASURED and
    must render blank; an all-zero bag would be indistinguishable from a
    genuinely clean run.
    """
    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0      # same path read more than once
    files_written: int = 0     # distinct paths written
    rewrite_churn: int = 0     # paths written more than once
    failed_commands: int = 0   # command events with non-zero exit
    model_turns: int = 0
    denials: int = 0           # E-16: blocked tool calls
    escalations: int = 0       # E-17: tool calls that raised a gate
    compacted: bool = False

    @classmethod
    def from_digest(cls, d: SessionDigest | None) -> "WasteBag | None":
        if d is None:
            return None
        return cls(
            tool_calls=d.tool_calls, file_reads=d.file_reads,
            file_rereads=d.file_rereads, files_written=d.files_written,
            rewrite_churn=d.rewrite_churn,
            failed_commands=d.failed_commands, model_turns=d.model_turns,
            denials=d.denials, escalations=d.escalations,
            compacted=d.compacted)


class BenchmarkRecord(BaseModel):
    # identity
    run_id: str
    bench_run_id: str                       # parent BenchmarkWorkflow id; "_drift/<date>" for drift
    case_id: str                            # golden case name; "_production" for drift
    scope: BenchmarkScope
    stage: str
    task_id: str | None = None
    attempt: int | None = None
    role: str
    harness: HarnessKind | None = None
    # Set only when harness == CREW: the CLI the crew's lead ran under
    # (spec §5). Without it every crew:<lead_harness> cell collapses to one
    # record identity and the lead sweep cannot be told apart in a report.
    lead_harness: HarnessKind | None = None
    model: str
    prompt_sha: str = ""
    # raw dimensions
    quality: QualityScore
    cost: CostBag = Field(default_factory=CostBag)
    speed: SpeedBag
    waste: WasteBag | None = None           # None = no session captured
    plan_drift: "PlanDrift | None" = None    # None = not measured (E-83)
    outcome: BenchmarkOutcome
    fix_attempts: int = 0
    error: str | None = None


class CompositeWeights(BaseModel):
    quality: float = 0.6
    cost: float = 0.2
    speed: float = 0.2


class CaseSpec(BaseModel):
    """A golden case: the idea + the (harness, model) matrix to run it on."""
    case_id: str
    idea_summary: str
    description: str = ""
    mode: Literal["greenfield", "brownfield"] = "greenfield"
    repo_url: str | None = None
    # Raw strings on purpose: `crew:<lead_harness>` (spec §5) is not a
    # HarnessKind value, so parsing stays in expand_matrix where the entry
    # can be named in the error.
    harnesses: list[str]
    models: list[str]
    judge_model: str                        # cross-family (ADR-6)
    rubrics: dict[str, str] = Field(default_factory=dict)  # stage -> rubric file
    # E-83: stage -> veto file. Mirrors `rubrics`. Absent = no vetoes for
    # that stage, which is not an error -- vetoes are opt-in per case.
    vetoes: dict[str, str] = Field(default_factory=dict)
    # FR-107: run the research stage for this case. Default False so existing
    # cases inherit no behavior change -- including no new abort path, since
    # a grounding-verifier violation hard-returns the whole run
    # (feature.py:717).
    research_enabled: bool = False
    # E-67: run DAG stage 13 for this case. Default False -- a deploying case
    # needs a real target and a Docker daemon on the runner, which most cases
    # neither have nor want.
    deploy_enabled: bool = False
    # E-31: declares the held-out oracle's language. Set => this case opts
    # into oracle grading (BenchmarkWorkflow runs grade_oracle after the
    # child). Also the value the manifest-vs-marker mismatch signal compares
    # against. None => no oracle grade for this case.
    language: str | None = None
    # E-79: the case's held-out oracle needs live network (DevEval's
    # ArXiv_digest calls the ArXiv API; chakin downloads word vectors).
    # Refused at matrix expansion until the E-21 network tier exists --
    # NFR-5 assumes no egress beyond the declared research/OSV paths.
    network_required: bool = False
    # per-model extra CLI args (e.g. opencode's `--variant` reasoning-effort
    # flag) forwarded to every role's harness invocation for that model.
    extra_args_by_model: dict[str, list[str]] = Field(default_factory=dict)
    # E-37: named role→model mixes. Each arm is one cell (crossed with
    # harnesses). When empty, `models` is desugared to one arm per model
    # (harness roles only) for backward compatibility — see expand_matrix.
    arms: list[Arm] = Field(default_factory=list)
    # Every gate in the child FeatureWorkflow runs under this policy (SOFT:
    # auto-approve on a passing quality signal, else escalate; HARD: always
    # escalate; OFF: always auto-approve). SOFT is the default so a task that
    # exhausts its fix budget still gets judged instead of rubber-stamped
    # into a merge-time rejection. HARD will block a cell on
    # PipelineConfig.gate_timeout_hours (default 48h) if nothing answers the
    # escalation — pass --gate-policy off for a fire-and-forget batch run.
    gate_policy: GatePolicy = GatePolicy.SOFT


class BenchmarkCell(BaseModel):
    """One cell of the matrix: a (case, harness, arm) triple to execute.
    `lead_harness` is set only on harness=CREW cells expanded from a
    `crew:<lead_harness>` entry — the CLI the crew's lead runs under."""
    case_id: str
    harness: HarnessKind
    lead_harness: HarnessKind | None = None
    arm_name: str
    role_models: dict[str, str] = Field(default_factory=dict)

    @property
    def cell_id(self) -> str:
        lead = f":{self.lead_harness.value}" if self.lead_harness else ""
        return f"{self.case_id}#{self.harness.value}{lead}#{self.arm_name}"


class BenchmarkSummary(BaseModel):
    """Aggregate over all records for one (case, stage, harness, model),
    split further by lead_harness on harness=CREW records -- otherwise a
    crew:<lead_harness> sweep blends different leads into one composite."""
    case_id: str
    stage: str
    harness: HarnessKind | None
    lead_harness: HarnessKind | None = None
    model: str
    n: int
    mean_quality: float | None
    mean_cost_usd: float | None
    mean_wall_clock_s: float | None
    composite: float | None
    errors: list[str] = Field(default_factory=list)
