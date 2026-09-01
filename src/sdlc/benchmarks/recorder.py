"""Recorder: a Temporal activity + a tiny file-backed record store.

records.jsonl per (bench_run_id, cell_id) under SDLC_BENCHMARKS_ROOT
(default runs/benchmarks/). One JSON object per line — a partial last line
is skipped on read so a crashed writer never corrupts the readable history.
"""

from __future__ import annotations

import os
from pathlib import Path

from temporalio import activity

from .models import BenchmarkRecord

DEFAULT_ROOT = "runs/benchmarks"


_UNSAFE_CHARS = set(':<>|?*"\\/')


def _root() -> str:
    return os.environ.get("SDLC_BENCHMARKS_ROOT", DEFAULT_ROOT)


def _sanitize_segment(s: str, allow_slash: bool) -> str:
    """Replace filesystem-unsafe chars with '_' (identical behavior on all OSes).

    NTFS treats ':< > | ? * " \\ /' as illegal / ADS-separators; POSIX is lax but
    we sanitize everywhere so paths round-trip across platforms. '#' is kept —
    it's the cell-id delimiter and safe on both filesystems. When allow_slash is
    True the '/' is preserved so a bench_run_id like '_drift/2026-07-04' keeps
    functioning as a sub-path; a cell_id (a single filename) passes False.
    """
    out: list[str] = []
    for ch in s:
        if ch == "/" and allow_slash:
            out.append(ch)
        elif ch in _UNSAFE_CHARS:
            out.append("_")
        else:
            out.append(ch)
    return "".join(out)


def records_path(bench_run_id: str, cell_id: str | None, root: str | None = None) -> Path:
    base = Path(root if root is not None else _root()) / _sanitize_segment(
        bench_run_id, allow_slash=True
    )
    if cell_id:
        return base / f"{_sanitize_segment(cell_id, allow_slash=False)}.jsonl"
    return base / "records.jsonl"


class RecordStore:
    def __init__(
        self, root: str | None = None, bench_run_id: str = "b1", cell_id: str | None = None
    ) -> None:
        self.path = records_path(bench_run_id, cell_id, root)

    def append(self, record: BenchmarkRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def read_all(self) -> list[BenchmarkRecord]:
        if not self.path.exists():
            return []
        out: list[BenchmarkRecord] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(BenchmarkRecord.model_validate_json(line))
                except Exception:
                    continue  # skip corrupt / partial line
        return out


@activity.defn
async def record_benchmark(record: BenchmarkRecord) -> None:
    """Append one BenchmarkRecord to the cell's records.jsonl.

    Non-deterministic I/O (filesystem) — must live in an activity, never in
    workflow code. Retries on failure via Temporal RetryPolicy.
    """
    store = RecordStore(bench_run_id=record.bench_run_id, cell_id=_cell_id_for(record))
    store.append(record)


def _cell_id_for(record: BenchmarkRecord) -> str | None:
    # drift records (case_id _production) go to one file per bench_run_id
    if record.case_id == "_production":
        return None
    h = record.harness.value if record.harness else "proposer"
    # Mirrors BenchmarkCell.cell_id (matrix.py): a crew:<lead_harness> cell
    # must keep its own file, or the lead sweep collapses into one column.
    if record.lead_harness is not None:
        h = f"{h}:{record.lead_harness.value}"
    return f"{record.case_id}#{h}#{record.model}"
