"""Git subprocess execution and git-inspection activities (spec A §5)."""

from __future__ import annotations

import os
import stat
import subprocess
import time
from dataclasses import dataclass

from temporalio import activity


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run git in ``cwd`` with the dubious-ownership check bypassed.

    Git's ``safe.directory`` ownership check (added in 2.36.3) refuses
    operations on a repo whose owner differs from the calling process —
    exit 128, "fatal: detected dubious ownership in repository at '...'".
    On Windows this fires whenever the worker's SID doesn't match the
    worktree dir's owner (service accounts, mounted volumes, containers,
    files extracted across users). Our worktrees live under
    ``SDLC_WORKTREES_ROOT`` (default ``tempfile.gettempdir()/sdlc/worktrees``)
    and are created and fully owned by this worker, so we bypass the
    check per-invocation via ``-c safe.directory=*`` rather than mutate
    global git config (which would weaken the check for the user's own
    repos too).

    Stdout/stderr are always captured so a non-zero exit surfaces git's
    actual diagnostic instead of a bare ``CalledProcessError`` that loses
    git's stderr when propagated through Temporal.
    """
    # stdin=DEVNULL (not inherited): the worker is a long-running service that
    # may be launched without a console, and inheriting an invalid STD_INPUT
    # handle makes DuplicateHandle fail (WinError 6/50). No git subcommand used
    # here reads stdin, so closing it is always safe and removes a latent
    # console-less failure mode.
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )


def _chmod_retry(func, p, _exc):
    """shutil.rmtree onerror callback: clear read-only bits and retry.

    Handles the common case of git pack/index files marked read-only on
    Windows. Does NOT clear sharing violations (WinError 32) — those are
    handled by the caller falling back to an alternate worktree path.
    """
    try:
        os.chmod(p, stat.S_IWRITE)
    except OSError:
        pass
    func(p)


def _rmtree_with_retry(path: str, attempts: int = 3, delay_s: float = 1.0) -> None:
    """rmtree with short retry for transient Windows locks.

    Windows Defender / Search Indexer briefly hold handles during their
    scans of newly-populated worktree dirs; that surfaces as WinError 32
    inside shutil.rmtree. A few short retries clears those. Persistent
    locks (orphan process holding the dir as its CWD) cannot be cleared
    in user space and will keep raising — the caller must fall back to
    a different path.
    """
    import shutil

    last_err: OSError | None = None
    for _ in range(attempts):
        try:
            shutil.rmtree(path, onerror=_chmod_retry)
            return
        except OSError as e:
            last_err = e
            time.sleep(delay_s)
    assert last_err is not None
    raise last_err


@dataclass
class DiffInput:
    worktree: str
    branch_point: str  # SHA the task branched from — NOT base_branch
    max_chars: int = 60_000


@activity.defn
async def get_task_diff(inp: DiffInput) -> dict:
    """Materialized diff for clean-context validators (FR-804), anchored to
    the task's branch point so a dependent task's diff shows only its own
    change — upstream work is invisible (Finding #1)."""
    rng = f"{inp.branch_point}...HEAD"
    stat = _git(["diff", "--stat", rng], inp.worktree).stdout
    patch = _git(["diff", rng], inp.worktree).stdout
    files = _git(["diff", "--name-only", rng], inp.worktree).stdout.splitlines()
    return {"stat": stat, "patch": patch[: inp.max_chars], "files": files}


@dataclass
class CommittedBytesInput:
    repo_dir: str
    path: str
    commit_sha: str


@activity.defn
async def read_committed_bytes(inp: CommittedBytesInput) -> str | None:
    """E-43/FR-914's third byte-source: the file's content at a pinned commit,
    for verifying a quote against `path@commit_sha`.

    Returns None -- never raises -- when the path or sha does not resolve, OR
    when the path resolves to something other than a file: `git show sha:dir`
    returns the tree listing with exit 0, which is not the file's bytes (code
    review #4). An empty file resolves to "" (its actual bytes) -- callers
    must distinguish None (unresolved) from "" (resolved empty) rather than
    use truthiness.

    The caller records a `source_unavailable` Violation; fail-closed means
    "unverified", not "crash". Pure read: no checkout, no worktree mutation,
    so it is reproducible across Temporal retries.
    """
    ref = f"{inp.commit_sha}:{inp.path}"
    try:
        kind = _git(["cat-file", "-t", ref], cwd=inp.repo_dir)
        if kind.returncode != 0 or kind.stdout.strip() != "blob":
            return None
        proc = _git(["show", ref], cwd=inp.repo_dir)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout
