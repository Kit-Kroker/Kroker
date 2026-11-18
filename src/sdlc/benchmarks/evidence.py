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

from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel, Field

from .. import runs_paths
from ..core.models import (
    RunSummary,
)
from .models import BenchmarkRecord

DEFAULT_EXPORT_ROOT = runs_paths.EXPORT_DEFAULT


class NoSummaryRun(BaseModel):
    """026 (FR-002, research R2): a scored run that left no summary, with
    the terminal class the cell record implies — `crashed`
    (pipeline_finished=False), `timed_out` (the same, with a
    ``(cause=TimeoutError)`` marker in the child-failure text, T004's
    BenchmarkWorkflow edit), `terminated` (no cell record at all: an
    operator stop, a parent timeout, or still running) or
    `summary_missing` (pipeline_finished=True yet no summary: fail-closed).
    """

    run_id: str
    case_id: str
    terminal_class: str  # crashed | timed_out | terminated | summary_missing


def _smoke_case_id() -> str | None:
    """The catalog's smoke case id, or None when the corpus is unreadable.

    Research R2's open item, settled here: the smoke case lives in the
    PUBLIC cases root (`benchmarks/cases/todo-api-greenfield`, `role:
    smoke`), so `smoke_case(cases_dir())` resolves it without any private
    root — but benchmark records carry no catalog role, so exclusion is by
    `case_id` equality against the resolved smoke case. An unreadable
    corpus excludes nothing (a note says so); exclusion never fails a
    score.
    """
    try:
        from .corpus import smoke_case
        from .paths import cases_dir

        return smoke_case(cases_dir()).case_id
    except Exception:  # noqa: BLE001
        return None


def _no_summary_class(run_id: str, records: list[BenchmarkRecord]) -> str:
    """The terminal class of one summary-less run (research R2: the cell
    record is the authority, keyed on `pipeline_finished`)."""
    cell_rec = next((r for r in records if r.run_id == run_id and r.cell is not None), None)
    if cell_rec is None:
        return "terminated"
    cell = cell_rec.cell
    assert cell is not None  # the filter above guarantees it
    if not cell.pipeline_finished:
        text = cell.child_result or ""
        return "timed_out" if "(cause=TimeoutError)" in text else "crashed"
    return "summary_missing"


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
    # 026 (FR-004): the selection excludes smoke-role runs, and
    # `no_summary` names every scored run that left no summary with its
    # terminal class — nothing drops out of SC-1 silently (FR-002/003).
    selection_runs: int = 0
    summary_runs: int = 0
    no_summary: list[NoSummaryRun] = Field(default_factory=list)
    excluded_smoke: list[str] = Field(default_factory=list)
    # 026 (FR-001): which roots were read and how each was chosen; None =
    # a caller-built Evidence (tests, fixtures) with no root provenance.
    roots: runs_paths.RootsReport | None = None


def export_root(root: str | None = None) -> Path:
    """Where the retro stage writes runs/<run_id>/. Mirrors
    observability/activities.py's SDLC_EXPORT_ROOT resolution."""
    if root is not None:
        return Path(root)
    return Path(runs_paths.export_root())


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
    # 026 FR-004: smoke-role runs leave the scored selection entirely —
    # SC-1, SC-2 and SC-3 never see them — and the exclusion is stated.
    # Exclusion precedes classification: a failed smoke run is excluded,
    # never reported as a crashed scored run.
    smoke_id = _smoke_case_id()
    excluded_smoke = (
        [rid for rid in run_ids if _case_of(records, rid) == smoke_id]
        if smoke_id is not None
        else []
    )
    if smoke_id is None:
        notes.append("smoke case not resolvable; nothing excluded from the selection")
    scored = [rid for rid in run_ids if rid not in set(excluded_smoke)]

    summaries, s_notes = _summaries_by_run_id(export_root(export_root_), scored)
    summarized = {s.run_id for s in summaries}
    no_summary = [
        NoSummaryRun(
            run_id=rid,
            case_id=_case_of(records, rid),
            terminal_class=_no_summary_class(rid, records),
        )
        for rid in scored
        if rid not in summarized
    ]
    roots = runs_paths.roots_report()
    if root is not None:
        roots = replace(roots, records=root)
    if export_root_ is not None:
        roots = replace(roots, export=export_root_)
    return Evidence(
        records=records,
        summaries=summaries,
        selector=selector,
        notes=notes + s_notes,
        selection_runs=len(scored),
        summary_runs=len(summaries),
        no_summary=no_summary,
        excluded_smoke=excluded_smoke,
        roots=roots,
    )


def _case_of(records: list[BenchmarkRecord], run_id: str) -> str:
    """A run's case_id (every record of one run shares it)."""
    return next((r.case_id for r in records if r.run_id == run_id), "")


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
