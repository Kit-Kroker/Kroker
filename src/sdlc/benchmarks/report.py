"""Aggregate benchmark records into summaries and render reports."""
from __future__ import annotations

from pathlib import Path

from temporalio import activity

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


def render_markdown(summaries: list[BenchmarkSummary]) -> str:
    if not summaries:
        return "# Benchmark report\n\nNo records found.\n"
    lines = [
        "# Benchmark report",
        "",
        "| case | stage | harness | model | n | quality | cost ($) | "
        "wall (s) | composite |",
        "|---|---|---|---|---|---|---|---|---|",
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
            f"{fmt(s.mean_wall_clock_s)} | {fmt(s.composite)} |"
        )
    errored = [s for s in summaries if s.errors]
    if errored:
        lines += ["", "## Stage failures", ""]
        for s in errored:
            for err in s.errors:
                lines.append(f"- **{s.case_id} / {s.stage}** ({s.model}): {err}")
    return "\n".join(lines) + "\n"


def write_report(summaries: list[BenchmarkSummary], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_markdown(summaries), encoding="utf-8")


@activity.defn
async def finalize_benchmark_report(bench_run_id: str) -> str:
    """Activity: read all records for the bench run, aggregate, write the
    Markdown report, return the report path. All file I/O lives here —
    never in workflow code."""
    summaries = aggregate(bench_run_id, CompositeWeights())
    out_path = f"runs/benchmarks/{bench_run_id}/report.md"
    write_report(summaries, out_path)
    return out_path
