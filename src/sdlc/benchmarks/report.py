"""Aggregate benchmark records into summaries and render reports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from temporalio import activity

from .models import (
    BenchmarkRecord,
    BenchmarkSummary,
    CompositeWeights,
)
from .paths import cases_dir as _default_cases_dir
from .recorder import RecordStore, _root
from .scoring import compute_summaries

if TYPE_CHECKING:
    # 013 (import discipline): the new view modules are imported inside the
    # functions, never at module scope.
    from .gate_oracle import GateOracle
    from .grid import Grid
    from .runs import CompositeDecision, Totals


def aggregate(
    bench_run_id: str,
    weights: CompositeWeights | None = None,
    root: str | None = None,
    _records: list[BenchmarkRecord] | None = None,
) -> list[BenchmarkSummary]:
    records = _records if _records is not None else _read_all(bench_run_id, root)
    return sorted(
        compute_summaries(records, weights),
        # 012 (contract §7.4): 012 rows first within each (case, stage)
        # (pre012 False sorts before True), then by cell, then the base
        # ordering.
        key=lambda s: (
            s.case_id,
            s.stage,
            s.pre012,
            s.cell_id or "",
            s.harness.value if s.harness else "",
            s.lead_harness.value if s.lead_harness else "",
            s.model,
            -(s.composite or -1),
        ),
    )


def _read_all(bench_run_id: str, root: str | None) -> list[BenchmarkRecord]:
    base = Path(root if root is not None else _root()) / bench_run_id
    if not base.exists():
        return []
    out: list[BenchmarkRecord] = []
    for p in base.rglob("*.jsonl"):
        store = RecordStore(
            root=root, bench_run_id=bench_run_id, cell_id=p.stem if p.stem != "records" else None
        )
        store.path = p
        out.extend(store.read_all())
    return out


def scan_case_records(case_id: str, root: str | None = None) -> list[BenchmarkRecord]:
    """Read every record for case_id across EVERY bench_run_id directory
    under root (default: recorder._root()). Powers the cross-run task/error
    matrices -- scan-on-demand, no separate history store to keep in sync."""
    base = Path(root if root is not None else _root())
    if not base.is_dir():
        return []
    out: list[BenchmarkRecord] = []
    for bench_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        out.extend(r for r in _read_all(bench_dir.name, root) if r.case_id == case_id)
    return out


def _table_header(show_composite: bool) -> tuple[str, str]:
    """013 (contract 8 item 3): the stage table's columns in order; the
    `composite` column is emitted only when a selected case shows one."""
    cols = [
        "case",
        "stage",
        "harness",
        "arm",
        "model",
        "n",
        "quality",
        "pass rate",
        "first attempt",
        "after repair",
        "tokens",
        "cost ($)",
        "wall (s)",
    ]
    if show_composite:
        cols.append("composite")
    cols.append("trust")
    return (
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    )


def _fmt(x) -> str:
    # ASCII only — a Windows console's default cp1252 codepage mangles the
    # em dash into the replacement char when this gets printed, not just
    # when written to the file.
    return f"{x:.3f}" if isinstance(x, float) else "n/a"


def _pair(p: tuple[int, int] | None) -> str:
    return f"{p[0]}/{p[1]}" if p is not None else "n/a"


def _summary_row(s: BenchmarkSummary, calibration, show_composite: bool) -> str:
    from .calibration import trust_for_stage

    harness_col = s.harness.value if s.harness else "proposer"
    if s.lead_harness:
        harness_col = f"{harness_col}:{s.lead_harness.value}"
    # 012 rows carry the cell's arm (ruling R1); pre-012 rows have no cell.
    arm_col = s.arm if s.arm is not None else ""
    if s.qa_is_copy:
        pass_col = "copy of code"
    elif s.all_pass is not None:
        pass_col = _pair(s.all_pass)
    elif s.pass_n is not None and s.pass_d is not None:
        pass_col = f"{s.pass_n}/{s.pass_d}"
    else:
        pass_col = "n/a"
    tokens_col = str(s.tokens) if s.tokens is not None else "n/a"
    cells = [
        s.case_id,
        s.stage,
        harness_col,
        arm_col,
        s.model,
        str(s.n),
        _fmt(s.mean_quality),
        pass_col,
        _pair(s.first_attempt),
        _pair(s.after_repair),
        tokens_col,
        _fmt(s.mean_cost_usd),
        _fmt(s.mean_wall_clock_s),
    ]
    if show_composite:
        cells.append(_fmt(s.composite))
    cells.append(trust_for_stage(s.stage, calibration))
    return "| " + " | ".join(cells) + " |"


def _totals_line(t: Totals) -> str:
    """013 (contract 8 item 2): the seven figures that replace the old
    `## Cells` section. `lost` carries the count per last stage."""
    per_stage = ", ".join(f"{stage}: {n}" for stage, n in sorted(t.lost_by_stage.items()))
    lost = f"{t.lost} ({per_stage})" if per_stage else str(t.lost)
    return (
        f"- runs started: {t.started}, graded: {t.graded}, lost: {lost}, "
        f"grading failed: {t.grading_failed}, no oracle: {t.no_oracle}, "
        f"discarded oracle records: {t.discarded_oracle_records}, "
        f"statuses derived: {t.derived_statuses}"
    )


def render_markdown(
    summaries: list[BenchmarkSummary],
    calibration=None,
    records: list[BenchmarkRecord] | None = None,
    *,
    grid: Grid | None = None,
    gate_oracle: GateOracle | None = None,
    decisions: dict[str, CompositeDecision] | None = None,
    sc_rollup: str | None = None,
    notes: list[str] | None = None,
) -> str:
    """013 (contract 8): every section of report.md, in order, each heading
    exactly once. `write_score` passes the grid, the gate view, the
    composite decisions, the success-criteria markdown and the notes in and
    appends nothing after the result; callers with only records get the
    views derived here. Sections without content are omitted."""
    from .calibration import render_calibration_markdown
    from .runs import build_runs, composite_shown

    calibration = calibration or {}
    runs = build_runs(records) if records else []
    if grid is None and runs:
        from .grid import build_grid

        grid = build_grid(runs)
    if gate_oracle is None and runs:
        from .gate_oracle import build_gate_oracle

        gate_oracle = build_gate_oracle(runs)
    if decisions is None and runs:
        decisions = composite_shown(runs)

    # contract 7.2: the not-shown decision prints as a note line.
    note_lines = [
        f"composite not shown for {case}: {d.reason}"
        for case, d in sorted((decisions or {}).items())
        if not d.shown
    ]
    note_lines += list(notes or [])
    show_composite = any(d.shown for d in (decisions or {}).values())

    lines = ["# Benchmark report"]
    if not summaries and not (grid is not None and grid.groups):
        lines += ["", "No records found."]
    if grid is not None and grid.groups:
        from .grid import render_grid_markdown

        lines += ["", "## Runs", "", _totals_line(grid.totals), "", render_grid_markdown(grid)]
    # contract 7.4: the main table lists the 012 rows; pre-012 rows move to
    # their own untrusted section below (absent when there are none). A
    # summary list without any pre012 flag set (pre-012-only readers) all
    # falls into the section, exactly as at base minus the heading.
    rows_012 = [s for s in summaries if not s.pre012]
    rows_pre = [s for s in summaries if s.pre012]
    if rows_012:
        lines += ["", "## Stages", "", *_table_header(show_composite)]
        lines += [_summary_row(s, calibration, show_composite) for s in rows_012]
    if rows_pre:
        lines += [
            "",
            "## Pre-012 records (untrusted)",
            "",
            "These rows predate round 012: no kroker_commit provenance is"
            " recorded on them, so their aggregates are never averaged"
            " together with 012 rows.",
            "",
            *_table_header(show_composite),
        ]
        lines += [_summary_row(s, calibration, show_composite) for s in rows_pre]
    if gate_oracle is not None and gate_oracle.rows:
        from .gate_oracle import render_gate_oracle_markdown

        gate_md = render_gate_oracle_markdown(gate_oracle)
        if gate_md:
            lines += ["", "## Gate versus oracle", "", gate_md]
    errored = [s for s in summaries if s.errors]
    if errored:
        lines += ["", "## Stage failures", ""]
        for s in errored:
            for err in s.errors:
                lines.append(f"- **{s.case_id} / {s.stage}** ({s.model}): {err}")
    if sc_rollup:
        lines += ["", sc_rollup.strip("\n")]
    if note_lines:
        lines += ["", "## Notes", ""]
        lines += [f"- {n}" for n in note_lines]
    return "\n".join(lines) + "\n" + render_calibration_markdown(calibration)


def write_report_with_calibration(
    summaries: list[BenchmarkSummary], out_path: str, calibration, records=None
) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(
        render_markdown(summaries, calibration, records=records), encoding="utf-8"
    )


def resolve_language_map(case_ids: list[str], cases_dir: Path | None = None) -> dict[str, str]:
    """Best-effort {case_id: language} from each case's case.yaml. A missing
    manifest or language contributes ""; never raises (a broken manifest just
    means that case is language-unknown)."""
    base = cases_dir if cases_dir is not None else _default_cases_dir()
    out: dict[str, str] = {}
    for cid in case_ids:
        lang = ""
        p = Path(base) / cid / "case.yaml"
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                lang = str(data.get("language") or "")
            except Exception:
                lang = ""
        out[cid] = lang
    return out


def write_heatmap(
    runs, out_dir: Path, language_by_case: dict[str, str], calibration_html: str = ""
) -> tuple[Path, Path]:
    """013 (T008): the layered heatmap over `build_runs` output (contract
    3); the renderers live in `B/heatmap_render.py`."""
    from .heatmap import build_layers, render_heatmap_json
    from .heatmap_render import render_heatmap_html

    hm = build_layers(runs, language_by_case)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_p = out_dir / "heatmap.html"
    json_p = out_dir / "heatmap.json"
    html_p.write_text(render_heatmap_html(hm, calibration_html), encoding="utf-8")
    json_p.write_text(render_heatmap_json(hm), encoding="utf-8")
    return html_p, json_p


@activity.defn
async def finalize_benchmark_report(bench_run_id: str) -> str:
    """Activity: read all records, aggregate, write report.md AND the
    heatmap.{html,json} beside it. All file I/O lives here."""
    from .calibration import load_calibration_reports, render_calibration_html
    from .runs import build_runs

    records = _read_all(bench_run_id, None)
    summaries = aggregate(bench_run_id, CompositeWeights(), _records=records)
    out_dir = Path(_root()) / bench_run_id
    calibration = load_calibration_reports()
    write_report_with_calibration(
        summaries, str(out_dir / "report.md"), calibration, records=records
    )
    lang = resolve_language_map(sorted({r.case_id for r in records}))
    write_heatmap(build_runs(records), out_dir, lang, render_calibration_html(calibration))
    return str(out_dir / "report.md")
