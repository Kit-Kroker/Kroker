"""Typed contracts for pipeline-step benchmarking.

One BenchmarkRecord per stage boundary and per code-task attempt. The three
dimensions (quality / cost / speed) are kept RAW — never pre-normalized — so
the reporter can recompute under different weights without re-running.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from ..models import HarnessKind

# cell_id feeds Temporal workflow ids and, via those, git branch names
# (see benchmarks/workflow.py + activities.py's worktree helpers) — strip
# characters git rejects in refs (`:`, space, `~^?*[\`) rather than only
# the ones that happen to appear in today's model ids.
_GIT_UNSAFE = re.compile(r"[:\s~^?*\[\\]")


class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"


class BenchmarkOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVISED = "revise"
    ESCALATED = "escalated"


class QualityScore(BaseModel):
    score: float | None = None              # 0.0..1.0; None when judge errored
    components: dict[str, float] = Field(default_factory=dict)
    judge: Literal["contract", "llm_judge", "human_override", "error"]


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
    # per-model extra CLI args (e.g. opencode's `--variant` reasoning-effort
    # flag) forwarded to every role's harness invocation for that model.
    extra_args_by_model: dict[str, list[str]] = Field(default_factory=dict)


class BenchmarkCell(BaseModel):
    """One cell of the matrix: a (case, harness, model) triple to execute."""
    case_id: str
    harness: HarnessKind
    model: str

    @property
    def cell_id(self) -> str:
        safe_model = _GIT_UNSAFE.sub("-", self.model)
        return f"{self.case_id}#{self.harness.value}#{safe_model}"


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
