"""Git subprocess execution and git-inspection activities (spec A §5)."""

from __future__ import annotations

import fnmatch
import os
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel, Field
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
class DriftInput:
    worktree: str
    anchor: str  # commit sha A -- the last attempt in which tests were free
    fence_globs: list[str]  # G: denied at the hook AND measured here
    report_globs: list[str]  # C: measured only (config, manifests)
    max_chars: int = 60_000


class DriftReport(BaseModel):
    """C2's deterministic backstop result.

    Three independent finding channels, because they are three different
    accusations and a human adjudicates them differently:
      fence_paths     -- a protected test path changed (weakening)
      report_paths    -- test/build config changed (possibly legitimate)
      index_bit_paths -- skip-worktree/assume-unchanged was set (evasion)
    """

    available: bool = True
    unavailable_reason: str = ""
    fence_paths: list[str] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)
    index_bit_paths: list[str] = Field(default_factory=list)
    patch: str = ""

    @property
    def found(self) -> bool:
        return bool(self.fence_paths or self.report_paths or self.index_bit_paths)


def _index_bit_paths(worktree: str, globs: list[str]) -> list[str]:
    """Paths hidden from the diff by index metadata.

    `git ls-files -v` tags, MEASURED (do not "correct" this from memory):
      S            = skip-worktree
      any lowercase = assume-unchanged
      H            = an ORDINARY TRACKED FILE
    Flagging H would report every tracked file in the repo as evasion.
    """
    out = _git(["ls-files", "-v", "--", *globs], worktree)
    if out.returncode != 0:
        return []
    hidden: list[str] = []
    for line in out.stdout.splitlines():
        if len(line) < 3 or line[1] != " ":
            continue
        tag, path = line[0], line[2:].strip()
        if tag == "S" or tag.islower():
            hidden.append(path)
    return sorted(hidden)


@activity.defn
async def check_test_drift(inp: DriftInput) -> DriftReport:
    """Did this repair attempt change anything under the drift set?

    Order is detect -> record -> clear -> diff, and every step is load-bearing.
    Detection without clearing hands the human an accusation with no patch:
    while a skip-worktree bit is set, `git add -A` stages nothing and
    `git diff` reports nothing, so the checkpoint commits the ORIGINAL test
    while pytest executes the weakened file on disk. Clearing without
    recording destroys the only evidence of intent, because the bit is
    index-local state that is never committed -- once cleared, the revealed
    change is indistinguishable from ordinary drift.

    Any failure is `available=False`, NEVER an empty (clean) report. A
    backstop whose transient failure reads as "no drift" reopens the exact
    hole ADR-17 closes for the fence.

    Clearing index bits is safe under a resumable session: update-index
    touches only index metadata (no checkout, no merge, no content write),
    and this runs between attempts when no harness process is alive.
    """
    globs = [*inp.fence_globs, *inp.report_globs]
    if not globs:
        return DriftReport(available=False, unavailable_reason="empty drift set")

    probe = _git(["rev-parse", "--verify", f"{inp.anchor}^{{commit}}"], inp.worktree)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip()
        return DriftReport(
            available=False, unavailable_reason=f"anchor {inp.anchor} unresolvable: {detail}"
        )

    hidden = _index_bit_paths(inp.worktree, globs)
    # Two SEPARATE invocations. Combining the flags silently leaves
    # skip-worktree SET while exiting 0 -- the last flag wins.
    for path in hidden:
        _git(["update-index", "--no-skip-worktree", path], inp.worktree)
        _git(["update-index", "--no-assume-unchanged", path], inp.worktree)

    # Plain pathspec, never `:(glob)`: git's DEFAULT pathspec agrees with
    # Python's fnmatch on the policy's pattern forms, and `:(glob)` does not
    # (it makes `**/x` start matching root-level x). One pattern list, four
    # engines, one meaning -- see tests/test_containment_dialects.py.
    status = _git(["diff", "--name-status", inp.anchor, "--", *globs], inp.worktree)
    if status.returncode != 0:
        detail = (status.stderr or status.stdout).strip()
        return DriftReport(available=False, unavailable_reason=f"diff failed: {detail}")

    changed = [ln.split("\t", 1)[1].strip() for ln in status.stdout.splitlines() if "\t" in ln]
    fence = sorted({p for p in changed if _matches_any(p, inp.fence_globs)})
    report = sorted({p for p in changed if p not in fence})
    patch = ""
    if changed:
        pr = _git(["diff", inp.anchor, "--", *globs], inp.worktree)
        patch = pr.stdout[: inp.max_chars] if pr.returncode == 0 else ""
    return DriftReport(fence_paths=fence, report_paths=report, index_bit_paths=hidden, patch=patch)


def _matches_any(path: str, globs: list[str]) -> bool:
    """fnmatch, matching containment.PATH_MATCHES exactly -- the fence and
    the backstop must classify a path identically or a human reads two
    different accusations for one act."""
    norm = PurePosixPath(path).as_posix()
    return any(fnmatch.fnmatch(norm, g) for g in globs)


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
