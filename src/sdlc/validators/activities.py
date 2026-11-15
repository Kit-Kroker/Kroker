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
    dotfiles and leading slashes), so Windows separators, ``./``-prefixed
    hints and absolute-form tokens (``/src/app.py``) resolve to the same
    repo-relative file while a dotfile keeps its leading dot -- without the
    slash strip, pathlib's ``/`` operator would replace the repo root and
    settle an absolute-form probe against the worker HOST filesystem.
    A token whose normalized form still carries a ``..`` path segment is
    UNSETTLED BY CONSTRUCTION: it is not checked and not mapped -- absent
    from the result, so the consumer's missing set (built from falsy
    entries) can never include it and it can never ground a question
    discard. Traversal-shaped probes are noise, never repo findings.
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
        if ".." in norm.split("/"):
            continue  # unsettled by construction: never checked, never reported missing
        out[p] = bool(norm) and (root / norm).exists()
    return out


ACTIVITIES = [paths_exist]
