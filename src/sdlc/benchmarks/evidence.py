"""One reader for every evidence store the scorer needs.

Two stores, joined here and nowhere else:
  - runs/benchmarks/<bench_run_id>/*.jsonl   BenchmarkRecords
  - runs/pipeline/<run_id>/summary.json      RunSummary (E-32 retro export)

The artifact store (harness transcripts) is deliberately NOT read: OQ-B7
leaves the transcript TTL open, so any aggregation joining against it goes
blind once retention prunes. The bounded WasteBag rides on the record
instead.

`sdlc benchmark score` must run with no worker, no server and no client
connection. `report.py` imports `from temporalio import activity` for
finalize_benchmark_report, so it is imported LAZILY below rather than at
module scope.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from ..core.models import (
    RunSummary,
)
from .models import BenchmarkRecord

DEFAULT_EXPORT_ROOT = "./runs/pipeline"


class Evidence(BaseModel):
    """Everything a score run reads, plus the notes explaining what was
    missing. `notes` is rendered into report.md so a degraded score is
    visibly degraded rather than quietly partial."""

    records: list[BenchmarkRecord] = Field(default_factory=list)
    summaries: list[RunSummary] = Field(default_factory=list)
    selector: str = "_all"
    notes: list[str] = Field(default_factory=list)
    # 013 contract §9: how many runs the selection covers and how many of
    # them left a run summary (rendered as the SC section's opening line).
    selection_runs: int = 0
    summary_runs: int = 0


def export_root(root: str | None = None) -> Path:
    """Where the retro stage writes runs/<run_id>/. Mirrors
    observability/activities.py's SDLC_EXPORT_ROOT resolution."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get("SDLC_EXPORT_ROOT", DEFAULT_EXPORT_ROOT))


def load_run_summaries(root: str | None = None) -> tuple[list[RunSummary], list[str]]:
    """Every runs/*/summary.json under the export root, plus notes for the
    ones that could not be read. A malformed export degrades that one run,
    never the rollup."""
    base = export_root(root)
    notes: list[str] = []
    if not base.is_dir():
        return [], [f"export root {base} does not exist; no SC rates computed"]
    out: list[RunSummary] = []
    for p in sorted(base.glob("*/summary.json")):
        try:
            out.append(RunSummary.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            notes.append(f"unreadable summary {p.parent.name}: {e}")
    if not out and not notes:
        notes.append(f"no summary.json under {base}; no SC rates computed")
    return out, notes


def _summaries_by_run_id(base: Path, run_ids: list[str]) -> tuple[list[RunSummary], list[str]]:
    """Contract §9.1/§9.2: the summary at `base / run_id / 'summary.json'`
    for each run of the selection and nowhere else (research R-12: exact
    membership cannot admit a `bf-e2e-*` summary sitting beside them). A
    missing, unreadable or self-inconsistent summary degrades that one
    run, never the score."""
    if not run_ids:
        return [], []
    if not base.is_dir():
        return [], [f"export root {base} does not exist; no run summaries read"]
    notes: list[str] = []
    out: list[RunSummary] = []
    for run_id in run_ids:
        p = base / run_id / "summary.json"
        if not p.is_file():
            notes.append(f"no summary for run {run_id}")
            continue
        try:
            summary = RunSummary.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            notes.append(f"unreadable summary for run {run_id}: {e}")
            continue
        if summary.run_id != run_id:
            notes.append(f"summary for run {run_id} reports run_id {summary.run_id}; ignored")
            continue
        out.append(summary)
    return out, notes


def load_evidence(
    *,
    bench: str | None = None,
    case: str | None = None,
    all_: bool = False,
    root: str | None = None,
    export_root_: str | None = None,
) -> Evidence:
    """Load records for exactly one selector, plus the run summary of
    every run in that selection (contract §9; research R-12).

    Selectors are mutually exclusive so a score directory always has one
    unambiguous provenance.
    """

    from .report import _read_all, scan_case_records

    chosen = [x for x in (bench, case, True if all_ else None) if x is not None]
    if len(chosen) != 1:
        raise ValueError("exactly one of bench=, case=, all_= must be given")

    notes: list[str] = []
    if bench is not None:
        records = _read_all(bench, root)
        selector = bench
    elif case is not None:
        records = scan_case_records(case, root)
        selector = f"_case/{case}"
    else:
        records = _read_all_benches(root)
        selector = "_all"

    if not records:
        notes.append(f"no benchmark records for selector {selector}")

    run_ids = sorted({r.run_id for r in records})
    summaries, s_notes = _summaries_by_run_id(export_root(export_root_), run_ids)
    return Evidence(
        records=records,
        summaries=summaries,
        selector=selector,
        notes=notes + s_notes,
        selection_runs=len(run_ids),
        summary_runs=len(summaries),
    )


def _read_all_benches(root: str | None) -> list[BenchmarkRecord]:
    """Every record under every bench_run_id directory."""
    from .recorder import _root
    from .report import _read_all

    base = Path(root if root is not None else _root())
    if not base.is_dir():
        return []
    out: list[BenchmarkRecord] = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        out.extend(_read_all(d.name, root))
    return out
