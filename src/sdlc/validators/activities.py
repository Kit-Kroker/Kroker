"""Temporal activities for the FR-205 validators library: tree reading.

pure.py holds the workflow-safe half; this module adds the one check that
must touch the filesystem, so a plan's files_hint-style paths are checked
against the actual repo right after the plan gate instead of mid-run.
"""

from __future__ import annotations

from pathlib import Path

from temporalio import activity

from .pure import _norm_path


@activity.defn
def paths_exist(repo_path: str, paths: list[str]) -> dict[str, bool]:
    """Map each requested path to whether it exists under ``repo_path``.

    Each token is normalized first (`_norm_path`, the validators-local
    normalizer, which deliberately diverges from the plan/models.py twin on
    dotfiles), so Windows separators and ``./``-prefixed hints resolve to the
    same file as the POSIX form while a dotfile keeps its leading dot.
    Missing and empty entries map to False rather
    than raising or collapsing into the repo root -- a validator that dies
    on the first absent path would hide every finding after it, and an
    empty token resolving to ``repo_path`` itself would read as a false
    pass. Pure filesystem stat, no subprocess: deterministic across
    Temporal retries.
    """
    root = Path(repo_path)
    out: dict[str, bool] = {}
    for p in paths:
        norm = _norm_path(p)
        out[p] = bool(norm) and (root / norm).exists()
    return out


ACTIVITIES = [paths_exist]
