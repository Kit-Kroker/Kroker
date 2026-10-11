"""Root-cause labels and matrix for benchmark failures (round 015, Phase 6, US3).

US3: beside the error-class matrix, score builds a root-cause view:
lost runs and failed requirements counted under planning, execution,
verification or unattributed, per arm.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .models import (
    POST_CODE_STAGES,
    TASK_LOOP_STAGES,
    BenchmarkRecord,
    BenchmarkScope,
)
from .paths import cases_dir as _default_cases_dir
from .runs import _EPOCH, MIN_OBSERVATIONS, Run
from .tasks import TaskSuite, load_task_suite

PLANNING_STAGES: frozenset[str] = frozenset({"research", "clarify", "architecture", "plan"})

EXECUTION_STAGES: frozenset[str] = TASK_LOOP_STAGES | POST_CODE_STAGES | {"code"}

ROOT_CAUSES: tuple[str, ...] = ("planning", "execution", "verification", "unattributed")


class Label(BaseModel):
    """A human-authored root cause label for one run and task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    task_id: str
    cause: str
    note: str = ""


class RootCauseCell(BaseModel):
    """One cell in the root-cause matrix for one cause."""

    model_config = ConfigDict(frozen=True)

    cause: str
    numerator: int = 0
    denominator: int = 0
    lost_runs: int = 0
    runs_started: int = 0
    failed_requirements: int = 0
    requirements_graded: int = 0
    low_n: bool = False

    @property
    def rate(self) -> float | None:
        return self.numerator / self.denominator if self.denominator > 0 else None


class RootCauseRow(BaseModel):
    """One row of the root-cause matrix: per case, harness, arm, generation, identity."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    harness: str
    arm: str
    generation: str
    oracle_id: str | None = None
    cells: dict[str, RootCauseCell]

    @property
    def planning(self) -> RootCauseCell:
        return self.cells["planning"]

    @property
    def execution(self) -> RootCauseCell:
        return self.cells["execution"]

    @property
    def verification(self) -> RootCauseCell:
        return self.cells["verification"]

    @property
    def unattributed(self) -> RootCauseCell:
        return self.cells["unattributed"]


class RootCauseMatrix(BaseModel):
    """The root-cause matrix for one case."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    rows: list[RootCauseRow]
    labelled: int = 0
    unlabelled: int = 0
    no_requirement_results: int = 0
    notes: list[str] = Field(default_factory=list)


def load_labels(
    case_id: str,
    labels_root: Path | str | None = None,
    suite: TaskSuite | None = None,
    records: Iterable[BenchmarkRecord] | None = None,
) -> list[Label]:
    """Load and validate human labels from <labels root>/<case_id>/*.yaml.

    Returns [] when the directory is absent.
    Raises ValueError naming the entry for:
    - an unknown cause
    - a task_id not in the case's mapping
    - a run_id not among the bench run's records
    - a run_id of another case
    """
    root = Path(labels_root) if labels_root is not None else _default_cases_dir().parent / "labels"
    case_dir = root / case_id
    if not case_dir.is_dir():
        return []

    if suite is None:
        suite = load_task_suite(case_id)
    known_tasks = {t.id for t in suite.tasks} if suite is not None else set()

    recs_list = list(records) if records is not None else None

    from .report import _read_all

    out: list[Label] = []
    for yaml_file in sorted(case_dir.glob("*.yaml")):
        bench_run_id = yaml_file.stem
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        entries = raw.get("labels", [])
        if not entries:
            continue

        if recs_list is not None:
            bench_recs = [r for r in recs_list if r.bench_run_id == bench_run_id]
        else:
            bench_recs = _read_all(bench_run_id, None)

        bench_runs_by_id: dict[str, str] = {r.run_id: r.case_id for r in bench_recs}

        for entry in entries:
            run_id = entry.get("run_id", "")
            task_id = entry.get("task_id", "")
            cause = entry.get("cause", "")
            note = entry.get("note", "")

            if cause not in ROOT_CAUSES:
                raise ValueError(f"unknown cause {cause!r} in label entry {entry} from {yaml_file}")

            if suite is not None and task_id not in known_tasks:
                raise ValueError(
                    f"task_id {task_id!r} not in case {case_id} mapping in entry {entry}"
                )

            if run_id not in bench_runs_by_id:
                raise ValueError(
                    f"run_id {run_id!r} not among records of bench run {bench_run_id}: {entry}"
                )

            if bench_runs_by_id[run_id] != case_id:
                raise ValueError(
                    f"run_id {run_id!r} belongs to case {bench_runs_by_id[run_id]!r}, "
                    f"not {case_id}: {entry}"
                )

            out.append(Label(run_id=run_id, task_id=task_id, cause=cause, note=note))

    return out


def build_root_cause(
    case_id: str,
    runs: list[Run],
    records: Iterable[BenchmarkRecord],
    suite: TaskSuite | None = None,
    labels: list[Label] | None = None,
) -> RootCauseMatrix:
    """Build the root-cause matrix for one case from runs, records and labels."""
    case_runs = [r for r in runs if r.case_id == case_id]
    recs_list = list(records)

    labels_map: dict[tuple[str, str], Label] = {}
    if labels:
        for item in labels:
            labels_map[(item.run_id, item.task_id)] = item

    by_row: dict[tuple[str, str, str, str, str | None], list[Run]] = defaultdict(list)
    for run in case_runs:
        by_row[(run.case_id, run.harness, run.arm, run.generation, run.oracle_id)].append(run)

    sorted_keys = sorted(
        by_row.keys(),
        key=lambda k: (
            k[0],
            k[2],  # arm
            k[3],  # generation
            k[4] or "",  # oracle_id
            min(r.started_at or _EPOCH for r in by_row[k]),
        ),
    )

    total_labelled = 0
    total_unlabelled = 0
    total_no_req_results = 0
    matrix_notes: list[str] = []

    rows: list[RootCauseRow] = []

    recs_by_run: dict[str, list[BenchmarkRecord]] = defaultdict(list)
    for r in recs_list:
        recs_by_run[r.run_id].append(r)

    for key in sorted_keys:
        c_id, harness, arm, generation, oracle_id = key
        row_runs = by_row[key]
        runs_started = len(row_runs)

        lost_by_cause = {c: 0 for c in ROOT_CAUSES}
        failed_by_cause = {c: 0 for c in ROOT_CAUSES}
        requirements_graded = 0

        for run in row_runs:
            if run.status == "lost":
                if run.last_stage in PLANNING_STAGES:
                    lost_by_cause["planning"] += 1
                elif run.last_stage in EXECUTION_STAGES:
                    lost_by_cause["execution"] += 1
                elif run.last_stage is None or run.last_stage == "":
                    lost_by_cause["planning"] += 1
                    matrix_notes.append(
                        f"run {run.run_id}: no stage recorded; counted under planning"
                    )
                else:
                    lost_by_cause["planning"] += 1
                    matrix_notes.append(
                        f"run {run.run_id}: unknown last stage "
                        f"{run.last_stage}; counted under planning"
                    )

            elif run.status == "graded":
                run_recs = run.records if run.records else tuple(recs_by_run.get(run.run_id, []))
                ot_recs = [r for r in run_recs if r.scope == BenchmarkScope.ORACLE_TASK]
                if not ot_recs:
                    total_no_req_results += 1
                else:
                    for rec in ot_recs:
                        requirements_graded += 1
                        score = rec.quality.score if rec.quality else None
                        if score is not None and score >= 1.0:
                            continue
                        task_id = rec.task_id or ""
                        lbl = labels_map.get((run.run_id, task_id))
                        if lbl is not None:
                            failed_by_cause[lbl.cause] += 1
                            total_labelled += 1
                        else:
                            failed_by_cause["unattributed"] += 1
                            total_unlabelled += 1

        cells: dict[str, RootCauseCell] = {}
        for cause in ROOT_CAUSES:
            lr = lost_by_cause[cause]
            fr = failed_by_cause[cause]
            if cause in ("planning", "execution"):
                num = lr
                den = runs_started
            else:
                num = fr
                den = requirements_graded

            low_n = den < MIN_OBSERVATIONS

            cells[cause] = RootCauseCell(
                cause=cause,
                numerator=num,
                denominator=den,
                lost_runs=lr,
                runs_started=runs_started,
                failed_requirements=fr,
                requirements_graded=requirements_graded,
                low_n=low_n,
            )

        rows.append(
            RootCauseRow(
                case_id=c_id,
                harness=harness,
                arm=arm,
                generation=generation,
                oracle_id=oracle_id,
                cells=cells,
            )
        )

    return RootCauseMatrix(
        case_id=case_id,
        rows=rows,
        labelled=total_labelled,
        unlabelled=total_unlabelled,
        no_requirement_results=total_no_req_results,
        notes=matrix_notes,
    )
