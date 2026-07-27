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
from ..models import HarnessKind


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
    judge: Literal["contract", "llm_judge", "human_override", "error", "oracle"]


class CostBag(BaseModel):
    usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class SpeedBag(BaseModel):
    wall_clock_s: float
    started_at: datetime
    ended_at: datetime


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
    model: str
    prompt_sha: str = ""
    # raw dimensions
    quality: QualityScore
    cost: CostBag = Field(default_factory=CostBag)
    speed: SpeedBag
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
    harnesses: list[HarnessKind]
    models: list[str]
    judge_model: str                        # cross-family (ADR-6)
    rubrics: dict[str, str] = Field(default_factory=dict)  # stage -> rubric file
    # FR-107: run the research stage for this case. Default False so existing
    # cases inherit no behavior change -- including no new abort path, since
    # a grounding-verifier violation hard-returns the whole run
    # (feature.py:717).
    research_enabled: bool = False
    # E-31: declares the held-out oracle's language. Set => this case opts
    # into oracle grading (BenchmarkWorkflow runs grade_oracle after the
    # child). Also the value the manifest-vs-marker mismatch signal compares
    # against. None => no oracle grade for this case.
    language: str | None = None
    # per-model extra CLI args (e.g. opencode's `--variant` reasoning-effort
    # flag) forwarded to every role's harness invocation for that model.
    extra_args_by_model: dict[str, list[str]] = Field(default_factory=dict)
    # E-37: named role→model mixes. Each arm is one cell (crossed with
    # harnesses). When empty, `models` is desugared to one arm per model
    # (harness roles only) for backward compatibility — see expand_matrix.
    arms: list[Arm] = Field(default_factory=list)


class BenchmarkCell(BaseModel):
    """One cell of the matrix: a (case, harness, arm) triple to execute."""
    case_id: str
    harness: HarnessKind
    arm_name: str
    role_models: dict[str, str] = Field(default_factory=dict)

    @property
    def cell_id(self) -> str:
        return f"{self.case_id}#{self.harness.value}#{self.arm_name}"


class BenchmarkSummary(BaseModel):
    """Aggregate over all records for one (case, stage, harness, model)."""
    case_id: str
    stage: str
    harness: HarnessKind | None
    model: str
    n: int
    mean_quality: float | None
    mean_cost_usd: float | None
    mean_wall_clock_s: float | None
    composite: float | None
    errors: list[str] = Field(default_factory=list)
