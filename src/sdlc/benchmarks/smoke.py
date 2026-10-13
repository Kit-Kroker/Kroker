"""Smoke test conditions, stamp I/O, and repository status (US2, T007).

Spec FR-016, FR-017:
- SMOKE_CONDITIONS: ("rubric_scores", "commit_on_records", "one_file_per_cell", "oracle_all_pass")
- SmokeStamp: kroker_commit, bench_run_id, passed, failed_conditions, written
- check_smoke: verifies the 4 smoke conditions across run records and files
- write_stamp: writes <ops root>/smoke/<commit>.json
- passing_stamp: loads stamp if passed, else None
- resolve_repo_status: synchronous git/env resolution for commit and tree_dirty (T008)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .models import (
    RUBRIC_JUDGES,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

SMOKE_CONDITIONS: tuple[str, ...] = (
    "rubric_scores",
    "commit_on_records",
    "one_file_per_cell",
    "oracle_all_pass",
)

_DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[3]


class SmokeStamp(BaseModel):
    """The outcome of a smoke test run for a specific Kroker commit."""

    kroker_commit: str
    bench_run_id: str
    passed: bool
    failed_conditions: list[str] = Field(default_factory=list)
    written: str


def ops_root(root: str | Path | None = None) -> Path:
    """Returns the operations root directory."""
    if root is not None:
        return Path(root)
    env = os.environ.get("SDLC_OPS_ROOT")
    if env:
        return Path(env)
    return Path("runs/ops")


def extract_bench_run_id(output: str) -> str:
    """Extract a bench_run_id from either a direct id or a report/directory path."""
    clean = output.strip().replace("\\", "/")
    p = Path(clean)
    if p.name == "report.md" or p.suffix in (".md", ".json", ".html"):
        return p.parent.name
    return p.name


def check_smoke(
    records: Sequence[BenchmarkRecord],
    record_files: Sequence[str | Path],
    n_cells: int,
) -> list[str]:
    """Check the 4 smoke conditions and return any failed condition names."""
    failed: list[str] = []

    # 1. rubric_scores: clarify and architecture carry rubric scores
    clarify_recs = [r for r in records if r.stage == "clarify"]
    arch_recs = [r for r in records if r.stage == "architecture"]
    clarify_ok = bool(clarify_recs) and all(
        r.quality.score is not None and r.quality.judge in RUBRIC_JUDGES for r in clarify_recs
    )
    arch_ok = bool(arch_recs) and all(
        r.quality.score is not None and r.quality.judge in RUBRIC_JUDGES for r in arch_recs
    )
    if not (clarify_ok and arch_ok):
        failed.append("rubric_scores")

    # 2. commit_on_records: a commit on every record (never None, empty, or 'unknown')
    commit_ok = bool(records) and all(
        r.kroker_commit is not None and r.kroker_commit != "" and r.kroker_commit != "unknown"
        for r in records
    )
    if not commit_ok:
        failed.append("commit_on_records")

    # 3. one_file_per_cell: exactly one record file per cell
    if not (n_cells > 0 and len(record_files) == n_cells):
        failed.append("one_file_per_cell")

    # 4. oracle_all_pass: the case-level oracle record passes (D-A). Only
    # scope=ORACLE counts: oracle_task records share stage 'oracle' but carry
    # per-task writer outcomes -- sweeping by stage made six task-level error
    # grades (the D-B writer defect) fail the smoke while the case-level
    # oracle graded 6/6 (R0 runs 1791808170, 1791839267). The 012-era
    # baseline runs that define this condition carry no oracle_task records
    # at all; the case-level record is the precedent.
    oracle_recs = [r for r in records if r.scope == BenchmarkScope.ORACLE]
    oracle_ok = bool(oracle_recs) and all(
        r.outcome == BenchmarkOutcome.PASS and (r.quality.score is None or r.quality.score >= 1.0)
        for r in oracle_recs
    )
    if not oracle_ok:
        failed.append("oracle_all_pass")

    return failed


def write_stamp(stamp: SmokeStamp, root: str | Path | None = None) -> Path:
    """Write the smoke stamp to <ops root>/smoke/<commit>.json."""
    base = ops_root(root)
    smoke_dir = base / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    stamp_path = smoke_dir / f"{stamp.kroker_commit}.json"
    stamp_path.write_text(stamp.model_dump_json(indent=2), encoding="utf-8")
    return stamp_path


def passing_stamp(commit: str, root: str | Path | None = None) -> SmokeStamp | None:
    """Return the SmokeStamp if it exists, matches commit, and passed; else None."""
    base = ops_root(root)
    stamp_path = base / "smoke" / f"{commit}.json"
    if not stamp_path.is_file():
        return None
    try:
        raw = json.loads(stamp_path.read_text(encoding="utf-8"))
        stamp = SmokeStamp.model_validate(raw)
        if stamp.kroker_commit == commit and stamp.passed:
            return stamp
        return None
    except Exception:
        return None


def resolve_repo_status(
    source_root: str | Path | None = None,
) -> tuple[str, bool | None]:
    """Synchronously resolves the current commit and dirty flag (D-8).

    Makes the same two git calls as provenance.py without requiring async/Temporal.
    """
    import subprocess

    root = str(Path(source_root) if source_root is not None else _DEFAULT_SOURCE_ROOT)
    try:
        head = subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if head.returncode == 0 and head.stdout.strip():
            status = subprocess.run(
                ["git", "-c", "safe.directory=*", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            dirty = bool(status.returncode == 0 and status.stdout.strip())
            return head.stdout.strip(), dirty
    except (FileNotFoundError, OSError):
        pass

    env_commit = os.environ.get("KROKER_COMMIT")
    if env_commit:
        raw_dirty = os.environ.get("KROKER_TREE_DIRTY")
        env_dirty: bool | None = None
        if raw_dirty is not None:
            lowered = raw_dirty.strip().lower()
            if lowered in ("1", "true"):
                env_dirty = True
            elif lowered in ("0", "false"):
                env_dirty = False
        return env_commit, env_dirty

    return "unknown", None
