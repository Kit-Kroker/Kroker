"""The layered benchmark heatmap (013, contract 3; E-36 heir).

Four layers on identical stage columns over `Run` objects from
`B/runs.py`: attrition (where runs were lost), first-attempt failure,
wasted tokens, and per-run oracle marks. Pure aggregation: no I/O, no
temporalio. Scales and the HTML renderer live in `B/heatmap_render.py`;
`render_heatmap_json` here serialises the layered model (the output file
name `heatmap.json` is kept; its schema changed in 013, research R-6).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .models import (
    CELL_STAGE_ORDER,
    TASK_LOOP_STAGES,
    BenchmarkRecord,
    BenchmarkScope,
    is_pre012,
)
from .runs import MIN_OBSERVATIONS, Run, attempt_sort_key, gate_passed

# Record-vocabulary stage order (SDLC-spec 15-stage DAG); the synthetic
# ``oracle`` column trails. Only columns with an observed cell are rendered.
# 013: this list is the GRAPH's stage vocabulary, no longer the heatmap's
# columns — the layered heatmap below orders its columns by
# ``models.CELL_STAGE_ORDER`` (data-model section 3).
CANONICAL_STAGES: list[str] = [
    "intake",
    "constitution",
    "context",
    "requirements",
    "research",
    "clarify",
    "architecture",
    "planning",
    "code",
    "review",
    "adversary",
    "handoff",
    "deep_review",
    "analyze",
    "qa",
    "quality_gate",
    "deploy",
    "retro",
]


# --- 013 (T007): the layered heatmap (data-model §3, contract §3) ---------------
#
# Four grids on identical stage columns: where runs were lost (attrition),
# how often a first attempt failed, how many tokens went to thrown-away
# work, and what the oracle said per run (marks, not cells). Columns come
# from `CELL_STAGE_ORDER` plus the trailing unknown stages and `oracle`;
# scales, cell states and the HTML renderer live in `B/heatmap_render.py`.

LAYERS: tuple[str, ...] = ("attrition", "first_attempt", "wasted_tokens", "oracle")
ORACLE_COLUMN: str = "oracle"

# The scopes a stage cell counts: cell (status), oracle and oracle-task
# (grade) records are in no cell (contract §3.4).
_CELL_SCOPES = (BenchmarkScope.STAGE, BenchmarkScope.TASK_ATTEMPT)

_EPOCH = datetime.min


class LayerCell(BaseModel):
    """One counting layer's cell at (row, stage) — contract §3.2 to §3.4."""

    model_config = {"frozen": True}

    layer: str
    row: str
    stage: str
    num: float
    den: float
    observations: int
    value: float | None
    state: Literal["value", "low_n", "blank", "copy"]
    not_measured: int = 0


class OracleMark(BaseModel):
    """The oracle layer: one mark per graded run (contract §3.5)."""

    model_config = {"frozen": True}

    row: str
    run_id: str
    passed: int
    total: int


class HeatmapRow(BaseModel):
    """One (case, harness, arm, generation) row and its header figures."""

    model_config = {"frozen": True}

    key: str
    case_id: str
    harness: str
    arm: str
    generation: str
    language: str
    started: int
    lost_before_code: int
    lost_tokens: int | None
    no_stage_recorded: int


class LayeredHeatmap(BaseModel):
    """The layers over one shared column set (contract §3.1)."""

    model_config = {"frozen": True}

    rows: tuple[HeatmapRow, ...] = ()
    stages: tuple[str, ...] = ()
    cells: tuple[LayerCell, ...] = ()
    oracle_marks: tuple[OracleMark, ...] = ()
    pre012_records: int = 0


def _attrition_position(run: Run) -> str | None:
    """Contract §3.2: a lost run's last stage inside the task loop folds to
    `code`; a run with no stage record has no position at all."""
    if run.last_stage is None:
        return None
    if run.status != "lost":
        return run.last_stage
    return "code" if run.last_stage in TASK_LOOP_STAGES else run.last_stage


def _code_facts(run: Run) -> dict[str, tuple[int, bool]]:
    """Per task: (highest code-attempt number, the last code attempt
    passed) — the inputs of the superseded and never-passed waste rules
    (contract §3.4)."""
    by_task: dict[str, list[BenchmarkRecord]] = defaultdict(list)
    for r in run.records:
        if r.stage == "code" and r.task_id is not None:
            by_task[r.task_id].append(r)
    facts: dict[str, tuple[int, bool]] = {}
    for task_id, attempts in by_task.items():
        attempts.sort(key=attempt_sort_key)
        facts[task_id] = (
            max(r.attempt or 0 for r in attempts),
            gate_passed("code", attempts[-1].outcome) is True,
        )
    return facts


def _wasted(run: Run, facts: dict[str, tuple[int, bool]], r: BenchmarkRecord) -> bool:
    """Contract §3.4: the run is lost; or the record's attempt is
    superseded by a later code attempt of its task; or the task's last
    code attempt did not pass. A task record with no attempt number lives
    on the first and third rule only."""
    if run.status == "lost":
        return True
    task = r.task_id
    if task is None or task not in facts:
        return False
    max_attempt, last_passed = facts[task]
    if r.attempt is not None and (r.attempt or 0) < max_attempt:
        return True
    return not last_passed


def _cell_state(observations: int, den: float) -> Literal["value", "low_n", "blank"]:
    """Contract §4.2's state rule; the `copy` state is the qa cell's alone
    and is decided by the caller."""
    if den <= 0:
        return "blank"
    return "low_n" if observations < MIN_OBSERVATIONS else "value"


def build_layers(runs: list[Run], language_by_case: dict[str, str] | None = None) -> LayeredHeatmap:
    """Contract §3: one row per (case, harness, arm, generation); the four
    layers share one column set — a column appears when any layer of any
    row has a non-blank cell in it, and `oracle` trails."""
    language_by_case = language_by_case or {}
    order = {stage: i for i, stage in enumerate(CELL_STAGE_ORDER)}
    code_idx = order["code"]

    by_row: dict[tuple[str, str, str, str], list[Run]] = defaultdict(list)
    for run in runs:
        by_row[(run.case_id, run.harness, run.arm, run.generation)].append(run)
    keys = sorted(
        by_row,
        key=lambda k: (
            k[0],
            k[2],
            k[3],
            min(r.started_at or _EPOCH for r in by_row[k]),
        ),
    )

    rows: list[HeatmapRow] = []
    marks: list[OracleMark] = []
    present: set[str] = set()
    # Per-row aggregates kept for the dense-cell pass below.
    attr_rows: list[dict[str, tuple[int, int]]] = []  # stage -> (lost at, reached)
    wrote_rows: list[set[str]] = []
    first_rows: list[dict[str, tuple[float, float]]] = []
    waste_rows: list[dict[str, tuple[float, float, int, int]]] = []
    copy_rows: list[bool] = []

    for key in keys:
        case_id, harness, arm, generation = key
        members = sorted(by_row[key], key=lambda r: r.started_at or _EPOCH)
        positions = [_attrition_position(m) for m in members]
        idx = [order[p] if p in order else None for p in positions]
        lost_at: dict[str, int] = defaultdict(int)
        for m, p in zip(members, positions, strict=True):
            if m.status == "lost" and p is not None:
                lost_at[p] += 1
        attr_rows.append(
            {
                stage: (lost_at.get(stage, 0), sum(1 for i in idx if i is not None and i >= s_idx))
                for stage, s_idx in order.items()
            }
        )
        written = {r.stage for m in members for r in m.records if r.scope in _CELL_SCOPES}
        wrote_rows.append(written)
        present |= {s for s in written if s in order and attr_rows[-1][s][1] > 0}
        if lost_at.get("code"):
            present.add("code")

        lost = [m for m in members if m.status == "lost"]
        token_list = [m.tokens for m in lost if m.tokens is not None]
        rows.append(
            HeatmapRow(
                key=f"{case_id} / {harness} / {arm} / {generation}",
                case_id=case_id,
                harness=harness,
                arm=arm,
                generation=generation,
                language=language_by_case.get(case_id, ""),
                started=len(members),
                lost_before_code=sum(
                    1
                    for m, p in zip(members, positions, strict=True)
                    if m.status == "lost" and (p is None or order.get(p, code_idx) < code_idx)
                ),
                lost_tokens=sum(token_list) if token_list else None,
                no_stage_recorded=sum(1 for m in members if m.last_stage is None),
            )
        )

        # First-attempt failure: units are (run, task) at a task stage, the
        # run itself elsewhere; `not_evaluated` firsts are in neither count
        # (contract §3.3). A copy run in a mixed row leaves the qa cell.
        copy_qa = bool(members) and all(m.qa_is_copy for m in members)
        copy_rows.append(copy_qa)
        first_data: dict[str, tuple[float, float]] = {}
        for m in members:
            by_stage: dict[str, list[BenchmarkRecord]] = defaultdict(list)
            for r in m.records:
                if r.scope in _CELL_SCOPES:
                    by_stage[r.stage].append(r)
            for stage, recs in by_stage.items():
                if stage == "qa" and m.qa_is_copy and not copy_qa:
                    continue
                units: dict[tuple[str, str | None], list[BenchmarkRecord]] = defaultdict(list)
                for r in recs:
                    units[(m.run_id, r.task_id)].append(r)
                num = den = 0.0
                for unit in units.values():
                    unit.sort(key=attempt_sort_key)
                    verdict = gate_passed(stage, unit[0].outcome)
                    if verdict is None:
                        continue
                    den += 1.0
                    num += 0.0 if verdict else 1.0
                prev = first_data.get(stage, (0.0, 0.0))
                first_data[stage] = (prev[0] + num, prev[1] + den)
        first_rows.append(first_data)
        present |= {s for s, (_n, d) in first_data.items() if d > 0}
        if copy_qa:
            present.add("qa")

        # Wasted tokens (contract §3.4): records at the stage with token
        # data are the observations; those without are `not_measured`.
        waste_data: dict[str, tuple[float, float, int, int]] = {}
        for m in members:
            facts = _code_facts(m)
            for r in m.records:
                if r.scope not in _CELL_SCOPES:
                    continue
                num, den, obs, not_measured = waste_data.get(r.stage, (0.0, 0.0, 0, 0))
                if r.cost.input_tokens is None and r.cost.output_tokens is None:
                    not_measured += 1
                else:
                    tokens = (r.cost.input_tokens or 0) + (r.cost.output_tokens or 0)
                    den += tokens
                    obs += 1
                    if _wasted(m, facts, r):
                        num += tokens
                waste_data[r.stage] = (num, den, obs, not_measured)
        waste_rows.append(waste_data)
        present |= {s for s, (_n, d, _o, _nm) in waste_data.items() if d > 0}

        for m in members:
            if m.status == "graded" and m.oracle_passed is not None and m.oracle_total is not None:
                marks.append(
                    OracleMark(
                        row=rows[-1].key,
                        run_id=m.run_id,
                        passed=m.oracle_passed,
                        total=m.oracle_total,
                    )
                )

    if marks:
        present.add(ORACLE_COLUMN)
    ordered = [s for s in CELL_STAGE_ORDER if s in present]
    unknown = sorted(present - set(CELL_STAGE_ORDER) - {ORACLE_COLUMN})
    stages = tuple(ordered + unknown + ([ORACLE_COLUMN] if marks else []))

    cells: list[LayerCell] = []
    for row_i, row in enumerate(rows):
        attr_data = attr_rows[row_i]
        written = wrote_rows[row_i]
        first_data = first_rows[row_i]
        waste_data = waste_rows[row_i]
        for stage in stages:
            # Attrition: dense cells over the known stages carry their
            # numbers; a stage no run of the row wrote is blank (the code
            # exception: a lost run folded to `code` fills it, §3.2).
            if stage in order:
                lost_n, reached = attr_data[stage]
                non_blank = stage in written or (stage == "code" and lost_n > 0)
                state = _cell_state(reached, float(reached)) if non_blank else "blank"
                cells.append(
                    LayerCell(
                        layer="attrition",
                        row=row.key,
                        stage=stage,
                        num=float(lost_n),
                        den=float(reached),
                        observations=reached,
                        value=lost_n / reached if state != "blank" and reached else None,
                        state=state,
                    )
                )
            else:
                cells.append(
                    LayerCell(
                        layer="attrition",
                        row=row.key,
                        stage=stage,
                        num=0.0,
                        den=0.0,
                        observations=0,
                        value=None,
                        state="blank",
                    )
                )
            # First-attempt failure; the qa cell of an all-copy row is a
            # copy whatever its runs' verdicts were (§3.3).
            if stage == "qa" and copy_rows[row_i]:
                cells.append(
                    LayerCell(
                        layer="first_attempt",
                        row=row.key,
                        stage=stage,
                        num=0.0,
                        den=0.0,
                        observations=0,
                        value=None,
                        state="copy",
                    )
                )
            else:
                num, den = first_data.get(stage, (0.0, 0.0))
                state = _cell_state(int(den), den)
                cells.append(
                    LayerCell(
                        layer="first_attempt",
                        row=row.key,
                        stage=stage,
                        num=num,
                        den=den,
                        observations=int(den),
                        value=num / den if state != "blank" else None,
                        state=state,
                    )
                )
            # Wasted tokens.
            num, den, obs, not_measured = waste_data.get(stage, (0.0, 0.0, 0, 0))
            state = _cell_state(obs, den)
            cells.append(
                LayerCell(
                    layer="wasted_tokens",
                    row=row.key,
                    stage=stage,
                    num=num,
                    den=den,
                    observations=obs,
                    value=num / den if state != "blank" else None,
                    state=state,
                    not_measured=not_measured,
                )
            )

    pre012 = sum(
        1
        for run in runs
        for r in run.records
        if r.scope is not BenchmarkScope.CELL and is_pre012(r)
    )
    return LayeredHeatmap(
        rows=tuple(rows),
        stages=stages,
        cells=tuple(cells),
        oracle_marks=tuple(marks),
        pre012_records=pre012,
    )


def render_heatmap_json(hm: LayeredHeatmap) -> str:
    """Serialise the layered model (the file name `heatmap.json` is kept;
    its schema changed in 013 — no raw records ride along)."""
    return hm.model_dump_json(indent=2)
