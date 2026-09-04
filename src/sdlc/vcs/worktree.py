"""Worktree lifecycle activities and helpers (spec A §5)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass

from temporalio import activity

from .git import _git, _rmtree_with_retry


def _worktrees_root() -> str:
    """Read at call time so tests can point it at a temp dir."""
    default = os.path.join(tempfile.gettempdir(), "sdlc", "worktrees")
    return os.environ.get("SDLC_WORKTREES_ROOT", default)


def _find_live_worktree_for_branch(repo_path: str, branch: str) -> str | None:
    """Return the path of the worktree whose HEAD is ``branch``, or None.

    Git rejects checking the same branch out in two worktrees
    ("fatal: '...' is already checked out at '<path>'"). When a prior
    ``_ensure_worktree`` had to fall back to an alternate path (because
    the canonical one was CWD-locked), the branch is still checked out
    at that fallback path. Returning it here lets subsequent retries /
    reset runs reuse the same path instead of accumulating orphans.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    current_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = os.path.normpath(line[len("worktree ") :].strip())
        elif line.startswith("branch ") and current_path is not None:
            ref = line[len("branch ") :].strip()
            if ref == branch or ref == f"refs/heads/{branch}":
                return current_path
    return None


def _clear_worktree_dir(repo_path: str, path: str) -> None:
    """Remove every trace of a stale worktree at ``path``.

    Three mechanisms, in order: ``git worktree remove -f`` (cleans git's
    own registration + internals), ``git worktree prune`` (drops stale
    registrations), then a Windows-robust rmtree for any leftover dir.
    ``shutil.rmtree(ignore_errors=True)`` silently aborts on the first
    read-only or locked file (common with git index/pack files on
    Windows), leaving the dir in place and causing a downstream
    'already exists' failure — so we chmod read-only entries and retry.

    Raises OSError if the dir cannot be cleared (typically WinError 32:
    another process — Defender, an orphan coding-agent subprocess, etc.
    — holds an open handle on the dir or its contents). The caller is
    responsible for falling back to an alternate path; no amount of
    in-process retry can release a CWD lock.
    """
    subprocess.run(["git", "worktree", "remove", "-f", path], cwd=repo_path, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=repo_path, capture_output=True)
    if not os.path.exists(path):
        return
    _rmtree_with_retry(path)


def _ensure_worktree(
    repo_path: str, branch: str, path: str, from_ref: str, max_alt: int = 8
) -> str:
    """Idempotently create (or reuse) a worktree checked out to ``branch``.

    Returns the worktree path (which may differ from ``path`` if a
    persistent lock forced a fallback — see below).

    Temporal retries re-run the calling activity; bare ``git worktree add -b``
    fails with "a branch named ... already exists" if the branch or path
    survives from a prior partial attempt (``git worktree prune`` only drops
    registrations whose dirs are gone — it never touches a lingering branch
    ref or a live worktree). Converge all states to a live worktree:

      - branch already checked out in some worktree -> reuse that worktree
        (covers retries after a path-fallback on a prior attempt)
      - live worktree at ``path`` -> reuse as-is
      - stale dir at ``path`` (dead/broken) -> clear it, then recreate
      - branch lingers but worktree gone -> check out the existing branch
      - neither present -> fresh ``add -b`` cut from ``from_ref``

    Windows-only failure mode: if a stale ``path`` is held open by another
    process (WinError 32), no in-process API can move or delete it. We
    fall back to ``path.1``, ``path.2``, ... up to ``max_alt`` so the
    activity can still succeed; the orphaned dir is left behind for the
    OS / a later janitor to clean up once the lock holder releases.

    An orphan coding-agent subprocess holding the CWD open was the main
    cause of this — fixed at the root by ``kill_process_tree``
    (``src/sdlc/process.py``, C6), which now kills every process a timed-
    out or cancelled harness/shell run started, not just the direct
    child. This fallback stays as defense in depth for the remaining
    causes: a Defender/Search-Indexer real-time scan transiently holding a
    handle during its scan of a newly-populated worktree dir, or an
    ungraceful worker crash that bypassed cleanup.
    """
    subprocess.run(["git", "worktree", "prune"], cwd=repo_path, capture_output=True)

    # Normalize so candidate paths and git's reported paths use the same
    # separator (git emits forward slashes on Windows; os.path.join emits
    # backslashes).
    path = os.path.normpath(path)

    # If a prior fallback already checked `branch` out at an alternate path,
    # reuse it — `git worktree add` would otherwise fail with
    # "... is already checked out at '<alt_path>'".
    existing = _find_live_worktree_for_branch(repo_path, branch)
    if existing and os.path.isdir(existing):
        return existing

    candidates = [path] + [f"{path}.{i}" for i in range(1, max_alt)]
    last_clear_err: Exception | None = None
    for cand in candidates:
        live = (
            os.path.isdir(cand)
            and _git(["rev-parse", "--is-inside-work-tree"], cand).returncode == 0
        )
        if live:
            return cand

        if os.path.exists(cand):
            try:
                _clear_worktree_dir(repo_path, cand)
            except OSError as e:
                last_clear_err = e
                continue  # try the next candidate path

        branch_exists = (
            subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", branch],
                cwd=repo_path,
                capture_output=True,
            ).returncode
            == 0
        )

        if branch_exists:
            wt = subprocess.run(
                ["git", "worktree", "add", cand, branch],
                cwd=repo_path,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            wt = subprocess.run(
                ["git", "worktree", "add", "-b", branch, cand, from_ref],
                cwd=repo_path,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
        if wt.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed (rc={wt.returncode}): "
                f"{wt.stderr.strip() or wt.stdout.strip()}"
            )
        return cand

    raise RuntimeError(
        f"could not clear or create worktree at {path} (tried {len(candidates)} "
        f"candidate paths). Last clear error: {last_clear_err!r}. Likely a "
        f"process is holding the dir as its CWD — kill it or reboot."
    )


@dataclass
class WorktreeInput:
    repo_path: str
    run_id: str
    task_id: str
    from_ref: str  # integration head SHA (ADR-14) — NOT base_branch


@dataclass
class WorktreeHandle:
    path: str
    branch: str
    branch_point: str  # SHA the task branched from (diff anchor)


@activity.defn
async def create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    """Run-scoped worktree + branch, cut from the integration head.
    Idempotent across Temporal retries (see ``_ensure_worktree``).

    The returned ``path`` may differ from the canonical
    ``<root>/<run>/<task>`` if a persistent Windows lock forced a
    fallback to ``<root>/<run>/<task>.N``; the workflow treats the
    returned path as authoritative."""
    path = os.path.join(_worktrees_root(), inp.run_id, inp.task_id)
    branch = f"sdlc/{inp.run_id}/{inp.task_id}"
    actual = _ensure_worktree(inp.repo_path, branch, path, inp.from_ref)
    point = subprocess.run(
        ["git", "rev-parse", inp.from_ref],
        cwd=inp.repo_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    return WorktreeHandle(path=actual, branch=branch, branch_point=point)
