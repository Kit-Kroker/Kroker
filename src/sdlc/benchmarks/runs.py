"""013 (data-model §1): records become runs once.

The run is the unit of every view (FR-001). `build_runs` turns a list of
records into `Run` objects — one per `run_id`, drift records aside — and
everything else (grid, heatmap layers, gate-versus-oracle, summaries,
composite decision, success-criteria scoping) reads runs, never raw
records. The status rule is the one `B/models.cell_progress` and
`grading_from_score` encode (research R-2): the 012 writer and this
reader share one body.

Imports: `B/models.py`, pydantic and the standard library only (SG-7) —
no temporalio, no report/cell/recorder. `sdlc benchmark score` runs with
no worker.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import stdev
from typing import Literal, cast

from pydantic import BaseModel, Field

from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    arm_label,
    cell_progress,
    grading_from_score,
)

# The one under-five threshold: grey heatmap cells, grey group headers,
# n/a criteria (research R-8). `sc_rollup.MIN_RUNS` aliases this.
MIN_OBSERVATIONS = 5

_EPOCH = datetime.min

Generation = Literal["pre012", "012"]
RunStatus = Literal["graded", "lost", "grading_failed", "no_oracle"]

DRIFT_CASE_ID = "_production"


class TaskOutcome(BaseModel):
    """One task's code attempts in one run (research R-5)."""

    model_config = {"frozen": True}

    task_id: str
    attempts: int
    first_passed: bool
    last_passed: bool


class Run(BaseModel):
    """One execution of one cell (FR-001). Every view reads this object."""

    model_config = {"frozen": True}

    run_id: str
    bench_run_id: str
    case_id: str
    harness: str
    arm: str
    arm_recovered: bool
    generation: Generation
    commit: str | None
    tree_dirty: bool | None
    started_at: datetime | None
    status: RunStatus
    status_derived: bool
    last_stage: str | None
    pipeline_finished: bool | None
    oracle_passed: int | None
    oracle_total: int | None
    discarded_oracle_records: int
    tasks: tuple[TaskOutcome, ...]
    qa_is_copy: bool
    tokens: int | None
    wall_clock_s: float | None
    records: tuple[BenchmarkRecord, ...] = Field(exclude=True)

    @property
    def partial_credit(self) -> float | None:
        """FR-022: tests passed over tests total of the oracle grade."""
        if self.oracle_passed is None or self.oracle_total is None:
            return None
        if self.oracle_total <= 0:
            return None
        return self.oracle_passed / self.oracle_total

    @property
    def all_pass(self) -> bool:
        return (
            self.oracle_passed is not None
            and self.oracle_total is not None
            and self.oracle_total > 0
            and self.oracle_passed == self.oracle_total
        )

    @property
    def first_attempt(self) -> tuple[int, int]:
        """FR-025: tasks whose first code attempt passed over tasks
        attempted (tasks with at least one code record)."""
        return (sum(t.first_passed for t in self.tasks), len(self.tasks))

    @property
    def after_repair(self) -> tuple[int, int]:
        """FR-025: tasks whose last code attempt passed over tasks
        attempted."""
        return (sum(t.last_passed for t in self.tasks), len(self.tasks))


class Group(BaseModel):
    """The runs of one (case, harness, arm, generation, commit) — FR-005's
    'never combine generations' and FR-008's commit groups both live in the
    key (research R-4)."""

    model_config = {"frozen": True}

    case_id: str
    harness: str
    arm: str
    generation: Generation
    commit: str | None
    runs: tuple[Run, ...]
    started: int
    graded: int
    lost: int
    grading_failed: int
    no_oracle: int
    mean: float | None
    sd: float | None
    lo: float | None
    hi: float | None
    all_pass: tuple[int, int]
    low_n: bool


class Totals(BaseModel):
    """FR-004: started == graded + lost + grading_failed + no_oracle."""

    model_config = {"frozen": True}

    started: int
    graded: int
    lost: int
    grading_failed: int
    no_oracle: int
    lost_by_stage: dict[str, int]
    discarded_oracle_records: int
    derived_statuses: int


class CompositeDecision(BaseModel):
    """Per case: whether the composite is shown and why (FR-034)."""

    model_config = {"frozen": True}

    shown: bool
    arms: int
    reason: str


def parse_run_id(run_id: str) -> tuple[str, str, str] | None:
    """`<bench_run_id>/<case>#<harness[:lead]>#<arm>` -> its last three
    parts; None when the shape does not match. The id is formed exactly as
    `B/workflow.py` forms it: `f"{bench_run_id}/{cell.cell_id}"`, so the
    arm may itself contain `#` (split at most twice, research R-3)."""
    if "/" not in run_id:
        return None
    _bench, rest = run_id.split("/", 1)
    if not _bench:
        return None
    parts = rest.split("#", 2)
    if len(parts) < 3 or not all(parts):
        return None
    case, harness, arm = parts
    return case, harness, arm


def attempt_sort_key(r: BenchmarkRecord) -> tuple[int, datetime]:
    """The shared attempt ordering (research R-5): attempt number with
    `None` read as 0, then start time."""
    return (r.attempt or 0, r.speed.started_at)


def gate_passed(stage: str, outcome: BenchmarkOutcome) -> bool | None:
    """Research R-9 / FR-030: None for `not_evaluated`; True for pass; True
    for `revise` when the stage is `merge` (a pass with waived advisory
    checks, amendment A1); every other verdict is a rejection."""
    if outcome is BenchmarkOutcome.NOT_EVALUATED:
        return None
    if outcome is BenchmarkOutcome.PASS:
        return True
    if outcome is BenchmarkOutcome.REVISED and stage == "merge":
        return True
    return False


def _is_oracle_scope(r: BenchmarkRecord) -> bool:
    return r.scope is BenchmarkScope.ORACLE


def _oracle_components(records: list[BenchmarkRecord]) -> tuple[int | None, int | None]:
    """(passed, total) from the last oracle-scope record's quality
    components; (None, None) when there is no oracle record or the grade
    carries no components (contract §1.4)."""
    for r in reversed(records):
        if not _is_oracle_scope(r):
            continue
        comps = r.quality.components
        passed = comps.get("passed")
        total = comps.get("total")
        if passed is None or total is None:
            return None, None
        return int(passed), int(total)
    return None, None


def _task_outcomes(records: list[BenchmarkRecord]) -> tuple[TaskOutcome, ...]:
    """Per task with at least one code record, attempts sorted by
    `attempt_sort_key`; first/last attempt pass flags (research R-5)."""
    by_task: dict[str, list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        if r.stage == "code" and r.task_id is not None:
            by_task[r.task_id].append(r)
    outcomes = []
    for task_id in sorted(by_task):
        attempts = sorted(by_task[task_id], key=attempt_sort_key)
        outcomes.append(
            TaskOutcome(
                task_id=task_id,
                attempts=len(attempts),
                first_passed=attempts[0].outcome is BenchmarkOutcome.PASS,
                last_passed=attempts[-1].outcome is BenchmarkOutcome.PASS,
            )
        )
    return tuple(outcomes)


def _qa_is_copy(records: list[BenchmarkRecord], generation: Generation) -> bool:
    """True exactly for a pre-012 run whose every qa record's outcome equals
    the code record's outcome for the same (task_id, attempt) (research
    R-5). A run with no qa record is not a copy of anything."""
    if generation != "pre012":
        return False
    code_by_key: dict[tuple[str | None, int | None], BenchmarkOutcome] = {}
    for r in records:
        if r.stage == "code" and r.task_id is not None:
            code_by_key[(r.task_id, r.attempt)] = r.outcome
    qa = [r for r in records if r.stage == "qa"]
    if not qa:
        return False
    return all(
        r.task_id is not None and code_by_key.get((r.task_id, r.attempt)) is r.outcome for r in qa
    )


def _tokens(records: list[BenchmarkRecord]) -> int | None:
    """Input + output over the run's records; None when none carry any
    (no reader guesses a zero, plan rule 3)."""
    total = 0
    measured = False
    for r in records:
        has = r.cost.input_tokens is not None or r.cost.output_tokens is not None
        measured = measured or has
        total += (r.cost.input_tokens or 0) + (r.cost.output_tokens or 0)
    return total if measured else None


def _wall_clock(records: list[BenchmarkRecord]) -> float | None:
    """The cell record's when present, else the sum over stage and attempt
    records (data-model §1.1)."""
    for r in records:
        if r.scope is BenchmarkScope.CELL:
            return r.speed.wall_clock_s
    stages = [
        r.speed.wall_clock_s
        for r in records
        if r.scope in (BenchmarkScope.STAGE, BenchmarkScope.TASK_ATTEMPT)
    ]
    return sum(stages) if stages else None


def _harness_of(records: list[BenchmarkRecord], run_id: str) -> str:
    """`harness[:lead]`, from the records or the run id; `proposer` when
    neither carries one (the pre-012 derivation of `cell_key`)."""
    for r in records:
        if r.harness is not None:
            if r.lead_harness is not None:
                return f"{r.harness.value}:{r.lead_harness.value}"
            return r.harness.value
    parsed = parse_run_id(run_id)
    if parsed is not None:
        return parsed[1]
    return "proposer"


def _arm_of(records: list[BenchmarkRecord], run_id: str) -> tuple[str, bool]:
    """Research R-3 order: `arm` on any record (012, not recovered); else
    the run id's arm part; else the oracle record's model; else `arm_label`
    of the first record. Everything but the first is recovered."""
    for r in records:
        if r.arm is not None:
            return r.arm, False
    parsed = parse_run_id(run_id)
    if parsed is not None:
        return parsed[2], True
    for r in reversed(records):
        if _is_oracle_scope(r):
            return r.model, True
    if records:
        return arm_label(records[0]), True
    return "", True


def _build_run(run_id: str, records: list[BenchmarkRecord]) -> Run:
    first = records[0]
    commits = [r.kroker_commit for r in records if r.kroker_commit is not None]
    # Contract §1.6: a run never has records of both kinds; if one does it
    # is `012`. build_runs has no note channel (it returns runs only), so
    # the classification is total and the mixed case stays visible as a 012
    # run whose pre-012 records carry no commit.
    generation: Generation = "012" if commits else "pre012"
    commit = commits[0] if commits else None
    dirty = next((r.tree_dirty for r in records if r.tree_dirty is not None), None)
    started_at = min((r.speed.started_at for r in records), default=None)

    cell_records = [r for r in records if r.scope is BenchmarkScope.CELL]
    oracle_records = [r for r in records if _is_oracle_scope(r)]
    if cell_records and cell_records[0].cell is not None:
        cell_status = cell_records[0].cell
        code_finished = cell_status.code_finished
        last_stage = cell_status.last_stage
        pipeline_finished: bool | None = cell_status.pipeline_finished
        grading: str = cell_status.grading
        status_derived = False
    else:
        last_stage, code_finished = cell_progress(records)
        pipeline_finished = None
        score = oracle_records[-1].quality.score if oracle_records else None
        grading = grading_from_score(bool(oracle_records), code_finished, score)
        status_derived = True
    # R-2's table: code not finished -> lost whatever the grading label
    # (`not_graded` only ever appears with code not finished).
    if not code_finished or grading == "not_graded":
        status: RunStatus = "lost"
    else:
        status = cast(RunStatus, grading)

    if status == "graded":
        oracle_passed, oracle_total = _oracle_components(records)
    else:
        oracle_passed, oracle_total = None, None
    discarded = len(oracle_records) if status == "lost" else 0

    arm, arm_recovered = _arm_of(records, run_id)
    parsed = parse_run_id(run_id)
    return Run(
        run_id=run_id,
        bench_run_id=first.bench_run_id,
        case_id=parsed[0] if parsed is not None else first.case_id,
        harness=_harness_of(records, run_id),
        arm=arm,
        arm_recovered=arm_recovered,
        generation=generation,
        commit=commit,
        tree_dirty=dirty,
        started_at=started_at,
        status=status,
        status_derived=status_derived,
        last_stage=last_stage,
        pipeline_finished=pipeline_finished,
        oracle_passed=oracle_passed,
        oracle_total=oracle_total,
        discarded_oracle_records=discarded,
        tasks=_task_outcomes(records),
        qa_is_copy=_qa_is_copy(records, generation),
        tokens=_tokens(records),
        wall_clock_s=_wall_clock(records),
        records=tuple(records),
    )


def build_runs(records: list[BenchmarkRecord]) -> list[Run]:
    """One `Run` per distinct `run_id`; drift records produce no run
    (contract §1.1). Sorted by case, arm, generation, start."""
    by_run: dict[str, list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        if r.case_id == DRIFT_CASE_ID:
            continue
        by_run[r.run_id].append(r)
    runs = [_build_run(run_id, recs) for run_id, recs in by_run.items()]
    runs.sort(
        key=lambda run: (
            run.case_id,
            run.arm,
            run.generation,
            run.started_at or _EPOCH,
        )
    )
    return runs


def group_runs(runs: list[Run]) -> list[Group]:
    """Groups keyed (case, harness, arm, generation, commit) — contract
    §1.8. A group's figures are over its graded runs; `sd` is the sample
    deviation, None under two; `low_n` under five."""
    keyed: dict[tuple[str, str, str, Generation, str | None], list[Run]] = defaultdict(list)
    for run in runs:
        keyed[(run.case_id, run.harness, run.arm, run.generation, run.commit)].append(run)

    groups: list[Group] = []
    for key, members in keyed.items():
        members.sort(key=lambda run: run.started_at or _EPOCH)
        case_id, harness, arm, generation, commit = key
        graded = [r for r in members if r.status == "graded"]
        credits = [r.partial_credit for r in graded if r.partial_credit is not None]
        counts = {s: 0 for s in ("graded", "lost", "grading_failed", "no_oracle")}
        for r in members:
            counts[r.status] = counts.get(r.status, 0) + 1
        mean = sum(credits) / len(credits) if credits else None
        sd = stdev(credits) if len(credits) >= 2 else None
        groups.append(
            Group(
                case_id=case_id,
                harness=harness,
                arm=arm,
                generation=generation,
                commit=commit,
                runs=tuple(members),
                started=len(members),
                graded=counts["graded"],
                lost=counts["lost"],
                grading_failed=counts["grading_failed"],
                no_oracle=counts["no_oracle"],
                mean=mean,
                sd=sd,
                lo=min(credits) if credits else None,
                hi=max(credits) if credits else None,
                all_pass=(sum(1 for r in graded if r.all_pass), len(graded)),
                low_n=len(graded) < MIN_OBSERVATIONS,
            )
        )
    groups.sort(
        key=lambda g: (g.case_id, g.harness, g.arm, g.generation, g.runs[0].started_at or _EPOCH)
    )
    return groups


def totals(runs: list[Run]) -> Totals:
    """Contract §1.7: the counts that must sum to started, lost by last
    stage (key `none` for no stage record), discarded oracle records and
    derived statuses."""
    lost_by_stage: dict[str, int] = defaultdict(int)
    for run in runs:
        if run.status == "lost":
            lost_by_stage[run.last_stage or "none"] += 1
    return Totals(
        started=len(runs),
        graded=sum(1 for r in runs if r.status == "graded"),
        lost=sum(1 for r in runs if r.status == "lost"),
        grading_failed=sum(1 for r in runs if r.status == "grading_failed"),
        no_oracle=sum(1 for r in runs if r.status == "no_oracle"),
        lost_by_stage=dict(lost_by_stage),
        discarded_oracle_records=sum(r.discarded_oracle_records for r in runs),
        derived_statuses=sum(1 for r in runs if r.status_derived),
    )


def composite_shown(runs: list[Run]) -> dict[str, CompositeDecision]:
    """Contract §7.1: shown exactly when the case has two or more
    (harness, arm) pairs within one generation that each have a graded run
    (research R-10). The decision is made here, never inferred from empty
    rows."""
    graded_arms: dict[str, dict[Generation, set[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for run in runs:
        if run.status == "graded":
            graded_arms[run.case_id][run.generation].add((run.harness, run.arm))
    decisions: dict[str, CompositeDecision] = {}
    cases = sorted({r.case_id for r in runs})
    for case in cases:
        arms = max((len(pairs) for pairs in graded_arms.get(case, {}).values()), default=0)
        shown = arms >= 2
        reason = (
            "two or more arms with a graded run in one generation"
            if shown
            else f"{arms} arm(s) with a graded run; it needs two"
        )
        decisions[case] = CompositeDecision(shown=shown, arms=arms, reason=reason)
    return decisions
