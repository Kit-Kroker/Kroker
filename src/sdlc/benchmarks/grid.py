"""013 (data-model §5, contract §2): the run-by-run grid — the main view.

One row per run inside its group (case / harness / arm / generation /
commit), a header of group figures above each table, one stage column
per recorded stage and one mark per cell (contract §2.4). `build_grid`
takes `build_runs` output — the run is the unit, never raw records.

Imports: `B/models.py`, `B/runs.py`, pydantic and the standard library
only (import discipline; no temporalio, no report/cell/recorder).

Rendering (the contract fixes the quoted strings; the layout is this
module's, pinned by `tests/test_benchmark_grid.py`): a group header
line `### <case> / <harness> / <arm> / commit <commit>` with the markers
`untrusted (pre-012)` and `arm recovered` appended in that order; a
figures line `started N, graded N, lost N, mean M, sd S, LO to HI,
all-pass K/N` where under `low_n` the four statistical figures each
carry the suffix ` (low n)` (markdown text) and the grey class — named
`low_n` after the state name in data-model §3 — in HTML. The table has
NO separator row, so the string `---` never appears (contract §2.5) and
no header cell is exactly `case` or `stage` (§11.5 depends on that).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from html import escape
from typing import Literal

from pydantic import BaseModel

from .models import (
    CELL_STAGE_ORDER,
    BenchmarkRecord,
    BenchmarkScope,
)
from .runs import (
    Group,
    Run,
    Totals,
    attempt_sort_key,
    gate_passed,
    group_runs,
    totals,
)

_EPOCH = datetime.min

# Contract §2.6: stages that never become columns however they are
# recorded — the cell summary and the oracle grade have their own places.
_NON_COLUMN_STAGES = frozenset({"cell", "oracle"})

StageMark = Literal["first", "repaired", "failed", "not_reached", "not_evaluated", "copy"]


class GridCell(BaseModel):
    """One stage column of one run row (contract §2.4)."""

    model_config = {"frozen": True}

    stage: str
    mark: StageMark
    # A task stage's cell: (tasks whose first record at the stage passed,
    # distinct tasks). None for run stages and for `copy`.
    tasks: tuple[int, int] | None = None


class GridRow(BaseModel):
    """One run: the Run's display fields plus one cell per rendered stage."""

    model_config = {"frozen": True}

    run: Run
    cells: tuple[GridCell, ...]


class _GridGroup(BaseModel):
    """The Group figures plus the group's rows (runs are the rows)."""

    model_config = {"frozen": True}

    case_id: str
    harness: str
    arm: str
    generation: str
    commit: str | None
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
    rows: tuple[GridRow, ...]


class Grid(BaseModel):
    """The whole view: groups, the rendered stage columns, the totals."""

    groups: tuple[_GridGroup, ...]
    stages: tuple[str, ...]
    totals: Totals


def _rendered_stages(runs: list[Run]) -> tuple[str, ...]:
    """Contract §2.6: the stages of `CELL_STAGE_ORDER` any run records,
    in order, then every other recorded stage except `cell`/`oracle`
    sorted by name."""
    seen: set[str] = set()
    for run in runs:
        for r in run.records:
            if r.scope in (
                BenchmarkScope.CELL,
                BenchmarkScope.ORACLE,
                BenchmarkScope.ORACLE_TASK,
            ):
                continue
            if r.stage not in _NON_COLUMN_STAGES:
                seen.add(r.stage)
    ordered = [s for s in CELL_STAGE_ORDER if s in seen]
    return tuple(ordered + sorted(seen - set(CELL_STAGE_ORDER)))


def _stage_records(run: Run, stage: str) -> list[BenchmarkRecord]:
    """The run's stage and task-attempt records at `stage` — the two
    scopes a stage verdict lives in."""
    return [
        r
        for r in run.records
        if r.stage == stage and r.scope in (BenchmarkScope.STAGE, BenchmarkScope.TASK_ATTEMPT)
    ]


def _stage_mark(
    stage: str, records: list[BenchmarkRecord]
) -> tuple[StageMark, tuple[int, int] | None]:
    """The §2.4 table. Records whose verdict is `not_evaluated`
    (`gate_passed` None) are left out of first/repaired/failed — they are
    the whole mark only when they are all there is."""
    evaluated = [r for r in records if gate_passed(stage, r.outcome) is not None]
    if not evaluated:
        return "not_evaluated", None

    by_task: dict[str | None, list[BenchmarkRecord]] = defaultdict(list)
    for r in evaluated:
        by_task[r.task_id].append(r)
    for attempts in by_task.values():
        attempts.sort(key=attempt_sort_key)

    def passed(r: BenchmarkRecord) -> bool:
        return gate_passed(stage, r.outcome) is True

    first_ok = all(passed(a[0]) for a in by_task.values())
    if first_ok:
        mark: StageMark = "first"
    else:
        last_ok = all(passed(a[-1]) for a in by_task.values())
        mark = "repaired" if last_ok else "failed"

    tasks: tuple[int, int] | None = None
    if any(r.task_id is not None for r in evaluated):
        real = [a for key, a in by_task.items() if key is not None]
        tasks = (sum(1 for a in real if passed(a[0])), len(real))
    return mark, tasks


def _run_cells(run: Run, stages: tuple[str, ...]) -> tuple[GridCell, ...]:
    cells = []
    for stage in stages:
        records = _stage_records(run, stage)
        if not records:
            cells.append(GridCell(stage=stage, mark="not_reached"))
        elif stage == "qa" and run.qa_is_copy:
            cells.append(GridCell(stage=stage, mark="copy"))
        else:
            mark, tasks = _stage_mark(stage, records)
            cells.append(GridCell(stage=stage, mark=mark, tasks=tasks))
    return tuple(cells)


def _grid_group(g: Group, rows: tuple[GridRow, ...]) -> _GridGroup:
    return _GridGroup(
        case_id=g.case_id,
        harness=g.harness,
        arm=g.arm,
        generation=g.generation,
        commit=g.commit,
        started=g.started,
        graded=g.graded,
        lost=g.lost,
        grading_failed=g.grading_failed,
        no_oracle=g.no_oracle,
        mean=g.mean,
        sd=g.sd,
        lo=g.lo,
        hi=g.hi,
        all_pass=g.all_pass,
        low_n=g.low_n,
        rows=rows,
    )


def build_grid(runs: list[Run]) -> Grid:
    """Contract §2: one row per run inside its group; groups ordered by
    case, arm, generation (`012` first), then the start of the group's
    first run; rows by start."""
    groups = group_runs(runs)
    groups.sort(key=lambda g: (g.case_id, g.arm, g.generation, g.runs[0].started_at or _EPOCH))
    stages = _rendered_stages(runs)
    grid_groups = tuple(
        _grid_group(
            g,
            tuple(GridRow(run=run, cells=_run_cells(run, stages)) for run in g.runs),
        )
        for g in groups
    )
    return Grid(groups=grid_groups, stages=stages, totals=totals(runs))


# --- rendering -----------------------------------------------------------------

# The fixed header cells (contract §2.5). No separator row ever follows:
# the aggregate script finds the stage table by its `case`/`stage` header
# cells (§11.5), which these never are.
_STATIC_HEADER = (
    "run",
    "status",
    "last",
    "oracle",
    "first attempt",
    "after repair",
    "tokens",
    "wall (s)",
    "flags",
)


def _fmt3(x: float | None) -> str:
    return f"{x:.3f}" if x is not None else "n/a"


def _header_cells(stages: tuple[str, ...]) -> list[str]:
    return list(_STATIC_HEADER[:3]) + [f"s:{s}" for s in stages] + list(_STATIC_HEADER[3:])


def _header_text(g: _GridGroup) -> str:
    """The group header without the markdown `### ` prefix: arm, commit
    (`not recorded` for None, `unknown` as is), `untrusted (pre-012)`,
    `arm recovered`."""
    commit = g.commit if g.commit is not None else "not recorded"
    parts = [f"{g.case_id} / {g.harness} / {g.arm} / commit {commit}"]
    if g.generation == "pre012":
        parts.append("untrusted (pre-012)")
    if any(row.run.arm_recovered for row in g.rows):
        parts.append("arm recovered")
    return " ".join(parts)


def _figure(text: str, low: bool) -> str:
    """Markdown text: the `(low n)` suffix rides the figure itself."""
    return f"{text} (low n)" if low else text


def _figures_pairs(g: _GridGroup) -> list[tuple[str, bool]]:
    """The header figures as (text, low_n) pairs — started/graded/lost are
    exact counts and never grey; the statistical figures all are."""
    lo_hi = f"{_fmt3(g.lo)} to {_fmt3(g.hi)}"
    return [
        (f"started {g.started}", False),
        (f"graded {g.graded}", False),
        (f"lost {g.lost}", False),
        (f"mean {_fmt3(g.mean)}", g.low_n),
        (f"sd {_fmt3(g.sd)}", g.low_n),
        (lo_hi, g.low_n),
        (f"all-pass {g.all_pass[0]}/{g.all_pass[1]}", g.low_n),
    ]


def _figures_text(g: _GridGroup, *, html: bool) -> str:
    parts = []
    for text, low in _figures_pairs(g):
        if low and html:
            parts.append(f'<span class="low_n">{text} (low n)</span>')
        elif low:
            parts.append(f"{text} (low n)")
        else:
            parts.append(text)
    return ", ".join(parts)


def _row_texts(row: GridRow, stages: tuple[str, ...]) -> list[str]:
    """The row cells, in header order (contract §2.3)."""
    run = row.run
    by_stage = {c.stage: c for c in row.cells}
    stage_texts = []
    for stage in stages:
        cell = by_stage[stage]
        text: str = cell.mark
        if cell.tasks is not None:
            text += f" ({cell.tasks[0]}/{cell.tasks[1]})"
        stage_texts.append(text)
    status = run.status + (" derived" if run.status_derived else "")
    if run.oracle_passed is not None and run.oracle_total is not None:
        oracle = f"{run.oracle_passed}/{run.oracle_total}"
    else:
        oracle = "n/a"
    first_k, first_n = run.first_attempt
    repair_k, repair_n = run.after_repair
    tokens = str(run.tokens) if run.tokens is not None else "n/a"
    wall = f"{run.wall_clock_s:.1f}" if run.wall_clock_s is not None else "n/a"
    flags = ", ".join(
        f
        for f, on in (
            ("dirty", run.tree_dirty is True),
            (
                "unfinished",
                run.pipeline_finished is False and run.status != "lost",
            ),
        )
        if on
    )
    return [
        run.run_id,
        status,
        run.last_stage or "none",
        *stage_texts,
        oracle,
        f"{first_k}/{first_n}",
        f"{repair_k}/{repair_n}",
        tokens,
        wall,
        flags,
    ]


def render_grid_markdown(grid: Grid) -> str:
    """One pipe table per group, ASCII only, no `---` anywhere (the
    table carries no separator row)."""
    blocks = []
    for g in grid.groups:
        lines = [
            f"### {_header_text(g)}",
            "",
            _figures_text(g, html=False),
            "",
            "| " + " | ".join(_header_cells(grid.stages)) + " |",
        ]
        for row in g.rows:
            lines.append("| " + " | ".join(_row_texts(row, grid.stages)) + " |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_grid_json(grid: Grid) -> str:
    """The same figures as the markdown; `Run.records` is excluded from
    the model dump, so no raw records ride along."""
    return json.dumps(grid.model_dump(mode="json"), indent=2, sort_keys=True)


def render_grid_html(grid: Grid) -> str:
    """A standalone ASCII document carrying the same figures; under
    `low_n` the group figures take the grey class (`low_n`)."""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Run grid</title>",
        "<style>",
        "body { font-family: monospace; }",
        ".low_n { color: #666; }",
        "</style>",
        "</head>",
        "<body>",
    ]
    for g in grid.groups:
        parts.append(f"<h3>{escape(_header_text(g))}</h3>")
        parts.append(f"<p>{_figures_text(g, html=True)}</p>")
        parts.append("<table>")
        parts.append(
            "<thead><tr>"
            + "".join(f"<th>{escape(h)}</th>" for h in _header_cells(grid.stages))
            + "</tr></thead>"
        )
        parts.append("<tbody>")
        for row in g.rows:
            parts.append(
                "<tr>"
                + "".join(f"<td>{escape(t)}</td>" for t in _row_texts(row, grid.stages))
                + "</tr>"
            )
        parts.append("</tbody>")
        parts.append("</table>")
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)
