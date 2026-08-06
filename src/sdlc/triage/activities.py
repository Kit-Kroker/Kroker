"""E-41 signal activities (FR-902). One activity per signal, deliberately:
a signal that crashes or times out yields not_collected for ITSELF while every
other signal still reports (spec D3).

Findings are read from the pinned commit through git, never from the working
checkout (spec D6): a gitignored local .env cannot produce a false positive,
untracked build output produces no noise, and every evidence citation is true
against path@sha by construction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from temporalio import activity

from ..activities import _git
from ..measurement import Measurement
from ..toolchain.adapters import detect_with_marker
from .models import SignalResult
from .signals import baseline

_log = logging.getLogger(__name__)


@dataclass
class TriageSignalInput:
    repo_dir: str
    commit_sha: str


def tracked_paths(repo_dir: str, commit_sha: str) -> list[str]:
    """Repo-relative posix paths tracked at commit_sha. Raises RuntimeError
    when the sha does not resolve -- the activity turns that into
    not_collected, which is the only honest report for a tree we cannot read."""
    proc = _git(["ls-tree", "-r", "--name-only", commit_sha], cwd=repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-tree failed for {commit_sha}: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def read_blob(repo_dir: str, commit_sha: str, path: str) -> str | None:
    """The file's bytes at the pinned commit, or None when the path does not
    resolve to a blob. Mirrors activities.read_committed_bytes -- same `git
    cat-file -t` guard, because `git show sha:dir` exits 0 with a tree
    listing, which is not the file's bytes."""
    ref = f"{commit_sha}:{path}"
    kind = _git(["cat-file", "-t", ref], cwd=repo_dir)
    if kind.returncode != 0 or kind.stdout.strip() != "blob":
        return None
    proc = _git(["show", ref], cwd=repo_dir)
    return proc.stdout if proc.returncode == 0 else None


@activity.defn
async def triage_baseline(inp: TriageSignalInput) -> SignalResult:
    """FR-902 baseline practice. Never raises: an unreadable tree is a
    not_collected report, not a failed triage."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        gitignore = ""
        if ".gitignore" in paths:
            gitignore = read_blob(inp.repo_dir, inp.commit_sha,
                                  ".gitignore") or ""
        found = detect_with_marker(inp.repo_dir)
        return baseline.evaluate(paths, gitignore,
                                 found[0] if found else None)
    except Exception as exc:                       # noqa: BLE001 -- see docstring
        _log.warning("triage baseline signal failed: %s", exc)
        return SignalResult(
            signal=baseline.SIGNAL_ID, version=baseline.VERSION,
            collected=Measurement.not_collected(
                f"baseline signal raised: {type(exc).__name__}: {exc}"))
