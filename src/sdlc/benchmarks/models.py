"""Typed contracts for pipeline-step benchmarking.

One BenchmarkRecord per stage boundary and per code-task attempt. The three
dimensions (quality / cost / speed) are kept RAW — never pre-normalized — so
the reporter can recompute under different weights without re-running.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..agents.loader import HARNESS_ROLES, PROPOSER_ROLES
from ..core.models import (
    GatePolicy,
    HarnessKind,
)
from ..harness.models import SessionDigest
from ..stages.plan.models import PlanDrift

# Who scored a stage attempt. The set is pinned by tests/test_judge_literal.py;
# _stage_record threads a plain str and relies on runtime validation, so
# callers that cannot prove the literal use a cast against this alias.
JudgeKind = Literal[
    "contract",
    "llm_judge",
    "human_override",
    "error",
    "oracle",
    "deep_review",
    "adversary",
    "handoff",
    "staged_rubric",
]


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


class BenchmarkScope(StrEnum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"
    ORACLE = "oracle"
    ORACLE_TASK = "oracle_task"
    # 012: the one cell record per cell (stage "cell", role "cell").
    CELL = "cell"


class BenchmarkOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVISED = "revise"
    ESCALATED = "escalated"
    # 012: a gate not evaluated in benchmark mode, or an oracle grade that
    # could not run. Counted by no aggregate (plan rule 3: no reader guesses).
    NOT_EVALUATED = "not_evaluated"


class QualityScore(BaseModel):
    score: float | None = None  # 0.0..1.0; None when judge errored
    components: dict[str, float] = Field(default_factory=dict)
    # Non-DAG lenses (deep_review/adversary/handoff) are judges too. Omitting
    # one here is not a type error at the call site -- _stage_record passes
    # `judge: str` straight through -- it is a ValidationError swallowed by the
    # caller's `except Exception`. tests/test_judge_literal.py pins the set.
    judge: JudgeKind


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
    file_rereads: int = 0  # same path read more than once
    files_written: int = 0  # distinct paths written
    rewrite_churn: int = 0  # paths written more than once
    failed_commands: int = 0  # command events with non-zero exit
    model_turns: int = 0
    denials: int = 0  # E-16: blocked tool calls
    escalations: int = 0  # E-17: tool calls that raised a gate
    compacted: bool = False

    @classmethod
    def from_digest(cls, d: SessionDigest | None) -> WasteBag | None:
        if d is None:
            return None
        return cls(
            tool_calls=d.tool_calls,
            file_reads=d.file_reads,
            file_rereads=d.file_rereads,
            files_written=d.files_written,
            rewrite_churn=d.rewrite_churn,
            failed_commands=d.failed_commands,
            model_turns=d.model_turns,
            denials=d.denials,
            escalations=d.escalations,
            compacted=d.compacted,
        )


class GraphAttribution(BaseModel):
    """E-77: which graph a record's run pinned, and where inside it the
    record was emitted. `BenchmarkRecord.graph = None` means pre-E-77 or a
    FeatureWorkflow run (FR-024: readers treat absent as not recorded)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_sha: str
    # None outside any activation (preamble, retro, oracle records).
    activation_id: str | None = None
    node_id: str | None = None
    round: int | None = None  # the router round of the activation (FR-014)
    node_stage: str | None = None  # resolve_stage at issue time; "unknown" allowed
    fail_reentry: Literal[0, 1] | None = None  # R-5 indicator; None = axis absent

    @model_validator(mode="after")
    def _activation_fields_need_an_activation(self) -> GraphAttribution:
        if self.activation_id is None and any(
            getattr(self, f) is not None for f in ("node_id", "round", "node_stage", "fail_reentry")
        ):
            raise ValueError("activation fields require an activation_id")
        return self


class CellStatus(BaseModel):
    """012 (data-model §1.2): one cell's outcome status, carried only on the
    cell record (`BenchmarkRecord.cell`, scope `CELL`). `completed` is
    stored, not derived at read: it is `pipeline_finished and code_finished`
    at write time. `last_stage` is the latest stage by `CELL_STAGE_ORDER`
    that wrote a record; None when the cell wrote none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline_finished: bool
    code_finished: bool
    completed: bool
    last_stage: str | None = None
    grading: Literal["graded", "not_graded", "grading_failed", "no_oracle"]
    # The child's return text or its failure text, truncated to 500 chars.
    child_result: str | None = None


class BenchmarkRecord(BaseModel):
    # identity
    run_id: str
    bench_run_id: str  # parent BenchmarkWorkflow id; "_drift/<date>" for drift
    case_id: str  # golden case name; "_production" for drift
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
    waste: WasteBag | None = None  # None = no session captured
    plan_drift: PlanDrift | None = None  # None = not measured (E-83)
    outcome: BenchmarkOutcome
    fix_attempts: int = 0
    error: str | None = None
    # E-77: the graph the record's run pinned; None = FeatureWorkflow or a
    # pre-E-77 record (contracts/records-and-store.md).
    graph: GraphAttribution | None = None
    # 012 (data-model §1.1): provenance and cell identity. None = the record
    # predates 012 / the field is not recorded — never a real value guessed
    # by a reader. A 012 writer always writes a commit id or the literal
    # "unknown" (contract §2.1).
    kroker_commit: str | None = None
    tree_dirty: bool | None = None
    # The cell label (ruling R1: the arm name) and the cell id; identical on
    # every record of one cell so they land in one file and one report row.
    arm: str | None = None
    cell_id: str | None = None
    # Set only on the cell record (scope CELL).
    cell: CellStatus | None = None


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
    judge_model: str  # cross-family (ADR-6)
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


# 012 (data-model §2.3): the record stage names in pipeline order. Every
# writer stage is in it (a test fails when a writer uses a name that is
# not); intake and retro emit trace events only and write no record.
CELL_STAGE_ORDER: tuple[str, ...] = (
    "research",
    "clarify",
    "architecture",
    "plan",
    "code",
    "tool_approval",
    "qa",
    "review",
    "adversary",
    "deep_review",
    "handoff",
    "analyze",
    "merge",
    "deploy",
)

# 012: a post-code stage record is the "code stage finished" signal (R-4).
POST_CODE_STAGES: frozenset[str] = frozenset({"analyze", "merge", "deploy"})

# 013 (data-model §2): the per-task loop stages. The reader side uses them
# to position a run lost inside the loop (its attrition position is `code`).
TASK_LOOP_STAGES: frozenset[str] = frozenset(
    {"code", "tool_approval", "qa", "review", "adversary", "deep_review", "handoff"}
)

# 013 (data-model §2): the judge kinds that produce a rubric SCORE on one
# comparable scale. The lenses and the deterministic instruments are
# excluded: they are different instruments, not two versions of one scale.
# `score._SCORING_JUDGES` is an alias of this set.
RUBRIC_JUDGES: frozenset[str] = frozenset({"llm_judge", "staged_rubric"})


def cell_progress(records: Iterable[BenchmarkRecord]) -> tuple[str | None, bool]:
    """013 (data-model §2): the body of `summarize_cell` (cell.py), moved so
    the 012 writer and the 013 reader share one rule (research R-2).
    ``last_stage`` is the latest stage by CELL_STAGE_ORDER among the records
    — NOT the most recently written — and ``code_finished`` is true exactly
    when a post-code stage (analyze, merge, deploy) wrote a record. Stages
    outside CELL_STAGE_ORDER ("cell", "oracle", unknown names) never count."""
    order = {stage: i for i, stage in enumerate(CELL_STAGE_ORDER)}
    known = [r.stage for r in records if r.stage in order]
    last_stage = max(known, key=lambda s: order[s], default=None)
    code_finished = any(r.stage in POST_CODE_STAGES for r in records)
    return last_stage, code_finished


def grading_from_score(has_oracle: bool, code_finished: bool, score: float | None) -> str:
    """013 (data-model §2): the body of `grading_status` (cell.py), moved.
    The 012 contract §3 table, total over its three input columns:

    no oracle                    -> no_oracle (whatever code_finished)
    oracle, code not finished    -> not_graded (the oracle never runs)
    oracle, code finished, score present -> graded
    oracle, code finished, score None    -> grading_failed
    """
    if not has_oracle:
        return "no_oracle"
    if not code_finished:
        return "not_graded"
    if score is not None:
        return "graded"
    return "grading_failed"


def cell_key(r: BenchmarkRecord) -> str | None:
    """012 (data-model §2.3): one label per cell. The record's `cell_id`
    when set (a 012 record), else the pre-012 derivation — exactly
    `recorder._cell_id_for`: `case#harness[:lead]#model` with `proposer`
    when the record has no harness, and None for drift records
    (`case_id == "_production"`), which share one file per bench run."""
    if r.cell_id is not None:
        return r.cell_id
    if r.case_id == "_production":
        return None
    h = r.harness.value if r.harness else "proposer"
    if r.lead_harness is not None:
        h = f"{h}:{r.lead_harness.value}"
    return f"{r.case_id}#{h}#{r.model}"


def arm_label(r: BenchmarkRecord) -> str:
    """012 (data-model §2.3): the cell's label for readers — the arm name
    (ruling R1) when the record carries one, else the record's model
    (the pre-012 label)."""
    return r.arm if r.arm is not None else r.model


def is_pre012(r: BenchmarkRecord) -> bool:
    """012 (data-model §2.3): True exactly when the record predates the
    round (`kroker_commit is None`) and is not a drift record: drift
    records are written outside benchmark runs by a writer this round
    does not change, never carry a commit, and are not counted as
    pre-012 (contract §7.2)."""
    return r.kroker_commit is None and r.case_id != "_production"


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
    # 012 (data-model §1.4): the cell the row belongs to (012 rows only);
    # `pre012` marks a row that aggregates pre-012 records only — a row
    # never mixes kinds (contract §7.3).
    cell_id: str | None = None
    arm: str | None = None
    pre012: bool = False
