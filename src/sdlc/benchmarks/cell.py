"""012 (data-model §2.4, contract §3): one cell's status, read from its records.

`summarize_cell` is the activity the benchmark parent runs after a child
ends (R-4): the line between graded and not graded is "the code stage
finished", detected by a post-code stage record — never by the existence
of an integration branch (the branch is created before any code task
runs). `grading_status` is the pure table over (has oracle, code
finished, oracle result); `cell_record` is the pure builder for the one
cell-scope record per cell.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal, cast

from temporalio import activity

from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    GraphAttribution,
    QualityScore,
    SpeedBag,
    cell_progress,
    grading_from_score,
)
from .recorder import RecordStore

if TYPE_CHECKING:
    from .models import BenchmarkCell
    from .oracle import OracleGrade
    from .provenance import Provenance

# contract §3.4: the child's result text is truncated, not dropped.
_CHILD_RESULT_MAX = 500


@dataclass(frozen=True)
class CellProgress:
    """What the parent needs to decide the cell's grading path."""

    last_stage: str | None
    code_finished: bool


@activity.defn
async def summarize_cell(bench_run_id: str, cell_id: str) -> CellProgress:
    """Read the cell's record file (the recorder's records root honours
    SDLC_BENCHMARKS_ROOT) and report how far the cell got.

    ``last_stage`` is the latest stage by CELL_STAGE_ORDER among the
    cell's records — NOT the most recently written (contract §3.2) — and
    ``code_finished`` is true exactly when a post-code stage (analyze,
    merge, deploy) wrote a record (§3.1). The cell record itself carries
    stage "cell", which is not in CELL_STAGE_ORDER and so never counts:
    re-summarizing after the cell record lands is idempotent. Corrupt /
    partial lines are skipped by the store's reader, never raised.
    The rule itself lives in `models.cell_progress` (013, research R-2):
    one body serves the 012 writer and the 013 reader."""
    records = RecordStore(bench_run_id=bench_run_id, cell_id=cell_id).read_all()
    last_stage, code_finished = cell_progress(records)
    return CellProgress(last_stage=last_stage, code_finished=code_finished)


GradingStatus = Literal["graded", "not_graded", "grading_failed", "no_oracle"]


def grading_status(
    has_oracle: bool, code_finished: bool, grade: OracleGrade | None
) -> GradingStatus:
    """The contract §3 table, total over its three input columns:

    no oracle                    -> no_oracle (whatever code_finished)
    oracle, code not finished    -> not_graded (the oracle never runs)
    oracle, code finished, grade present with a score -> graded
    oracle, code finished, grade None or scoreless    -> grading_failed

    The table itself lives in `models.grading_from_score` (013, research
    R-2): one body serves the 012 writer and the 013 reader."""
    score = grade.score if grade is not None else None
    return cast(GradingStatus, grading_from_score(has_oracle, code_finished, score))


def cell_record(
    cell: BenchmarkCell,
    status: CellStatus,
    bench_run_id: str,
    run_id: str,
    started: datetime,
    ended: datetime,
    provenance: Provenance | None,
    graph_sha: str | None = None,
) -> BenchmarkRecord:
    """contract §3.4: the one cell record — scope cell, stage cell, role
    cell, no quality score (judge contract: the status IS the judgment),
    pass only when the cell completed, the child's result text (truncated
    to 500 characters) as the error when it did not, the run's provenance
    and the cell's identity, model deterministic (no model produced it).
    Graph attribution, when a sha is given, is the E-77 shape for records
    outside any activation: graph_sha only."""
    child_result = status.child_result
    if child_result is not None and len(child_result) > _CHILD_RESULT_MAX:
        child_result = child_result[:_CHILD_RESULT_MAX]
    graph = GraphAttribution(graph_sha=graph_sha) if graph_sha else None
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=bench_run_id,
        case_id=cell.case_id,
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=cell.harness,
        lead_harness=cell.lead_harness,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(
            wall_clock_s=(ended - started).total_seconds(), started_at=started, ended_at=ended
        ),
        outcome=(BenchmarkOutcome.PASS if status.completed else BenchmarkOutcome.FAIL),
        error=(None if status.completed else child_result),
        kroker_commit=(provenance.kroker_commit if provenance is not None else None),
        tree_dirty=(provenance.tree_dirty if provenance is not None else None),
        arm=cell.arm_name,
        cell_id=cell.cell_id,
        cell=status,
        graph=graph,
    )
