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


def _root() -> str:
    return os.environ.get("SDLC_BENCHMARKS_ROOT", DEFAULT_ROOT)


def records_path(bench_run_id: str, cell_id: str | None,
                 root: str | None = None) -> Path:
    base = Path(root if root is not None else _root()) / bench_run_id
    if cell_id:
        return base / f"{cell_id}.jsonl"
    return base / "records.jsonl"


class RecordStore:
    def __init__(self, root: str | None = None,
                 bench_run_id: str = "b1",
                 cell_id: str | None = None) -> None:
        self.path = records_path(bench_run_id, cell_id, root)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: BenchmarkRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def read_all(self) -> list[BenchmarkRecord]:
        if not self.path.exists():
            return []
        out: list[BenchmarkRecord] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(BenchmarkRecord.model_validate_json(line))
                except Exception:
                    continue     # skip corrupt / partial line
        return out


@activity.defn
async def record_benchmark(record: BenchmarkRecord) -> None:
    """Append one BenchmarkRecord to the cell's records.jsonl.

    Non-deterministic I/O (filesystem) — must live in an activity, never in
    workflow code. Retries on failure via Temporal RetryPolicy.
    """
    store = RecordStore(bench_run_id=record.bench_run_id,
                        cell_id=_cell_id_for(record))
    store.append(record)


def _cell_id_for(record: BenchmarkRecord) -> str | None:
    # drift records (case_id _production) go to one file per bench_run_id
    if record.case_id == "_production":
        return None
    h = record.harness.value if record.harness else "proposer"
    return f"{record.case_id}#{h}#{record.model}"
