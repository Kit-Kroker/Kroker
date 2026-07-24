"""Aggregate benchmark records into summaries and render reports."""
from __future__ import annotations

from pathlib import Path

import yaml
from temporalio import activity

from .heatmap import build_heatmap, render_heatmap_html, render_heatmap_json
from .judge import _CASES_DIR
from .models import BenchmarkRecord, BenchmarkSummary, CompositeWeights
from .recorder import RecordStore, _root
from .scoring import compute_summaries


def aggregate(bench_run_id: str, weights: CompositeWeights | None = None,
              root: str | None = None,
              _records: list[BenchmarkRecord] | None = None
              ) -> list[BenchmarkSummary]:
    records = _records if _records is not None else _read_all(bench_run_id, root)
    return sorted(
        compute_summaries(records, weights),
        key=lambda s: (s.case_id, s.stage,
                       s.harness.value if s.harness else "",
                       s.model,
                       -(s.composite or -1)),
    )


def _read_all(bench_run_id: str, root: str | None) -> list[BenchmarkRecord]:
    base = Path(root if root is not None else _root()) / bench_run_id
    if not base.exists():
        return []
    out: list[BenchmarkRecord] = []
    for p in base.rglob("*.jsonl"):
        store = RecordStore(root=root, bench_run_id=bench_run_id,
                            cell_id=p.stem if p.stem != "records" else None)
        store.path = p
        out.extend(store.read_all())
    return out


def render_markdown(summaries: list[BenchmarkSummary], calibration=None) -> str:
    from .calibration import render_calibration_markdown, trust_for_stage
    calibration = calibration or {}
    if not summaries:
        return "# Benchmark report\n\nNo records found.\n"
    lines = [
        "# Benchmark report",
        "",
        "| case | stage | harness | model | n | quality | cost ($) | "
        "wall (s) | composite | trust |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        def fmt(x):
            # ASCII only — a Windows console's default cp1252 codepage
            # mangles the em dash into "�" (Unicode replacement char)
            # when this gets printed, not just when written to the file.
            return f"{x:.3f}" if isinstance(x, float) else "n/a"
        lines.append(
            f"| {s.case_id} | {s.stage} | "
            f"{s.harness.value if s.harness else 'proposer'} | {s.model} | "
            f"{s.n} | {fmt(s.mean_quality)} | {fmt(s.mean_cost_usd)} | "
            f"{fmt(s.mean_wall_clock_s)} | {fmt(s.composite)} | "
            f"{trust_for_stage(s.stage, calibration)} |"
        )
    errored = [s for s in summaries if s.errors]
    if errored:
        lines += ["", "## Stage failures", ""]
        for s in errored:
            for err in s.errors:
                lines.append(f"- **{s.case_id} / {s.stage}** ({s.model}): {err}")
    return "\n".join(lines) + "\n" + render_calibration_markdown(calibration)


def write_report(summaries: list[BenchmarkSummary], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_markdown(summaries), encoding="utf-8")


def write_report_with_calibration(summaries: list[BenchmarkSummary],
                                  out_path: str, calibration) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_markdown(summaries, calibration),
                              encoding="utf-8")


def resolve_language_map(case_ids: list[str],
                         cases_dir: Path | None = None) -> dict[str, str]:
    """Best-effort {case_id: language} from each case's case.yaml. A missing
    manifest or language contributes ""; never raises (a broken manifest just
    means that case is language-unknown)."""
    base = cases_dir if cases_dir is not None else _CASES_DIR
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


def write_heatmap(records, out_dir: Path, language_by_case: dict[str, str],
                  calibration_html: str = "") -> tuple[Path, Path]:
    hm = build_heatmap(records, language_by_case)
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
    records = _read_all(bench_run_id, None)
    summaries = aggregate(bench_run_id, CompositeWeights(), _records=records)
    out_dir = Path(_root()) / bench_run_id
    calibration = load_calibration_reports()
    write_report_with_calibration(summaries, str(out_dir / "report.md"), calibration)
    lang = resolve_language_map(sorted({r.case_id for r in records}))
    write_heatmap(records, out_dir, lang, render_calibration_html(calibration))
    return str(out_dir / "report.md")
