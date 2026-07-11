"""Temporal activities — all the non-deterministic work.

Activities run in the worker process; workflows never touch subprocesses,
the filesystem, or the network directly.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass

from temporalio import activity

from .gate import (
    CheckResult, GateOverride, GateReport, QualityGateInput,
    evaluate_quality_gate,
)
from .harness.adapters import HARNESSES, HarnessRequest
from .models import HarnessKind, HarnessRunResult, QAReport


def _worktrees_root() -> str:
    """Read at call time so tests can point it at a temp dir."""
    default = os.path.join(tempfile.gettempdir(), "sdlc", "worktrees")
    return os.environ.get("SDLC_WORKTREES_ROOT", default)


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
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args], cwd=cwd,
        capture_output=True, encoding="utf-8", errors="replace")


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
        cwd=repo_path, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return None
    current_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = os.path.normpath(line[len("worktree "):].strip())
        elif line.startswith("branch ") and current_path is not None:
            ref = line[len("branch "):].strip()
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
    subprocess.run(["git", "worktree", "remove", "-f", path],
                   cwd=repo_path, capture_output=True)
    subprocess.run(["git", "worktree", "prune"],
                   cwd=repo_path, capture_output=True)
    if not os.path.exists(path):
        return
    _rmtree_with_retry(path)


def _ensure_worktree(repo_path: str, branch: str, path: str,
                     from_ref: str, max_alt: int = 8) -> str:
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
    process (WinError 32 — typically an orphan coding-agent subprocess
    whose CWD is the worktree, or a Defender real-time scan), no in-process
    API can move or delete it. We fall back to ``path.1``, ``path.2``, ...
    up to ``max_alt`` so the activity can still succeed; the orphaned dir
    is left behind for the OS / a later janitor to clean up once the lock
    holder releases.
    """
    subprocess.run(["git", "worktree", "prune"],
                   cwd=repo_path, capture_output=True)

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
        live = os.path.isdir(cand) and _git(
            ["rev-parse", "--is-inside-work-tree"], cand).returncode == 0
        if live:
            return cand

        if os.path.exists(cand):
            try:
                _clear_worktree_dir(repo_path, cand)
            except OSError as e:
                last_clear_err = e
                continue  # try the next candidate path

        branch_exists = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", branch],
            cwd=repo_path, capture_output=True).returncode == 0

        if branch_exists:
            wt = subprocess.run(
                ["git", "worktree", "add", cand, branch],
                cwd=repo_path, capture_output=True,
                encoding="utf-8", errors="replace")
        else:
            wt = subprocess.run(
                ["git", "worktree", "add", "-b", branch, cand, from_ref],
                cwd=repo_path, capture_output=True,
                encoding="utf-8", errors="replace")
        if wt.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed (rc={wt.returncode}): "
                f"{wt.stderr.strip() or wt.stdout.strip()}")
        return cand

    raise RuntimeError(
        f"could not clear or create worktree at {path} (tried {len(candidates)} "
        f"candidate paths). Last clear error: {last_clear_err!r}. Likely a "
        f"process is holding the dir as its CWD — kill it or reboot.")


@dataclass
class WorktreeInput:
    repo_path: str
    run_id: str
    task_id: str
    from_ref: str          # integration head SHA (ADR-14) — NOT base_branch


@dataclass
class WorktreeHandle:
    path: str
    branch: str
    branch_point: str      # SHA the task branched from (diff anchor)


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
        ["git", "rev-parse", inp.from_ref], cwd=inp.repo_path,
        capture_output=True, encoding="utf-8", errors="replace").stdout.strip()
    return WorktreeHandle(path=actual, branch=branch, branch_point=point)


@dataclass
class IntegrationInput:
    repo_path: str
    run_id: str
    base_branch: str


@dataclass
class IntegrationHandle:
    """Returned by setup_integration_branch.

    The workflow cannot compute the integration worktree path itself
    (doing so would require reading SDLC_WORKTREES_ROOT from the env — a
    determinism violation), so the activity hands back both the head SHA
    and the path. The SHA advances after each merge; the path is stable
    for the run.
    """
    head_sha: str
    worktree_path: str


@activity.defn
async def setup_integration_branch(inp: IntegrationInput) -> IntegrationHandle:
    """Create sdlc/<run>/integration from base in its own worktree;
    return its head SHA + worktree path. Task worktrees branch from this
    head; the merge stage reuses the worktree path.
    Idempotent across Temporal retries (see ``_ensure_worktree``).

    The returned ``worktree_path`` may differ from the canonical
    ``<root>/<run>/integration`` if a persistent Windows lock forced a
    fallback to ``<root>/<run>/integration.N``; the workflow treats the
    returned path as authoritative."""
    branch = f"sdlc/{inp.run_id}/integration"
    path = os.path.join(_worktrees_root(), inp.run_id, "integration")
    actual = _ensure_worktree(inp.repo_path, branch, path, inp.base_branch)
    head = _git(["rev-parse", "HEAD"], actual).stdout.strip()
    return IntegrationHandle(head_sha=head, worktree_path=actual)


@dataclass
class MergeInput:
    repo_path: str
    run_id: str
    task_branch: str
    # Authoritative integration worktree path, as handed back by
    # setup_integration_branch (IntegrationHandle.worktree_path). Required
    # to hit the right dir when setup fell back to integration.N — see
    # merge_into_integration. Optional only for Temporal replay safety:
    # histories recorded before this field existed deserialize without it,
    # and we fall back to the canonical path (the pre-fix behavior).
    integration_path: str | None = None


@dataclass
class MergeResult:
    merged: bool
    conflict: bool
    integration_head: str


@activity.defn
async def merge_into_integration(inp: MergeInput) -> MergeResult:
    """Merge a completed task branch into the run's integration branch.
    A merge conflict = a falsified `overlaps` declaration (Finding #1):
    abort cleanly and report it so the caller serializes/escalates.

    The integration worktree path is taken from ``inp.integration_path``
    (the authoritative path returned by setup_integration_branch) — NOT
    recomputed from run_id. setup may have fallen back to
    ``<root>/<run>/integration.N`` if the canonical path was CWD-locked
    on Windows; recomputing the canonical path here would then point at
    a cleared/nonexistent dir and raise ``NotADirectoryError``
    (WinError 267) inside ``subprocess.run``. Falls back to the
    canonical path only for replay of histories recorded before this
    field existed."""
    ipath = (inp.integration_path
             or os.path.join(_worktrees_root(), inp.run_id, "integration"))
    merge = _git(
        ["merge", "--no-ff", "-m", f"merge {inp.task_branch}",
         inp.task_branch],
        ipath)
    if merge.returncode != 0:
        # Distinguish a real conflict from an infra/config failure via the
        # git index's unmerged entries (locale-independent) — must be read
        # BEFORE `merge --abort`, which clears the unmerged state.
        unmerged = _git(["ls-files", "--unmerged"], ipath).stdout
        _git(["merge", "--abort"], ipath)
        if not unmerged.strip():
            raise RuntimeError(
                f"git merge failed (not a conflict): {merge.stderr.strip()}")
        head = _git(["rev-parse", "HEAD"], ipath).stdout.strip()
        return MergeResult(merged=False, conflict=True, integration_head=head)
    head = _git(["rev-parse", "HEAD"], ipath).stdout.strip()
    return MergeResult(merged=True, conflict=False, integration_head=head)


@dataclass
class CodingTaskInput:
    harness: HarnessKind
    prompt: str
    worktree: str
    model: str | None = None
    session_id: str | None = None
    timeout_s: int = 3600


@activity.defn
async def run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    """Execute claude -p / opencode run inside the task worktree.

    Long-running: heartbeats while the harness streams output so Temporal
    can detect a hung/dead worker and retry elsewhere.
    """
    harness = HARNESSES[inp.harness]
    result = await harness.run(
        HarnessRequest(
            prompt=inp.prompt, cwd=inp.worktree, model=inp.model,
            session_id=inp.session_id, timeout_s=inp.timeout_s,
        ),
        heartbeat=activity.heartbeat,
    )
    # Checkpoint commit — the resume point if anything downstream fails.
    add = _git(["add", "-A"], inp.worktree)
    if add.returncode != 0:
        # Surface git's actual diagnostic (e.g. "dubious ownership", a
        # locked index, a corrupt repo) instead of a bare CalledProcessError
        # that loses stderr when Temporal serializes the exception.
        detail = add.stderr.strip() or add.stdout.strip()
        hint = ""
        if "not a git repository" in detail:
            # create_worktree only returns after `git worktree add` succeeds,
            # so `.git` existed when this activity started. The coding agent
            # itself must have deleted/overwritten it (e.g. ran `git init`
            # on a "greenfield" task) — this is agent misbehavior, not a
            # worktree-setup bug.
            hint = (" (the worktree's .git was intact when this task started; "
                    "the coding agent likely deleted or reinitialized it)")
        raise RuntimeError(
            f"git add failed in {inp.worktree}: {detail}{hint}")
    commit = _git(
        ["commit", "-m", f"sdlc checkpoint (exit={result.exit_code})",
         "--allow-empty"],
        inp.worktree)
    if commit.returncode == 0:
        result.commit_sha = _git(["rev-parse", "HEAD"], inp.worktree).stdout.strip()
    return result


@dataclass
class DiffInput:
    worktree: str
    branch_point: str      # SHA the task branched from — NOT base_branch
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
    return {"stat": stat, "patch": patch[:inp.max_chars], "files": files}


@dataclass
class QAInput:
    worktree: str
    test_cmd: str = "pytest -q --maxfail=25"
    timeout_s: int = 600


@activity.defn
async def run_test_suite(inp: QAInput) -> QAReport:
    """Bounded by timeout_s (default 10 min): a contract-specified command
    can accidentally chain in a long-running process (e.g. `npm run dev`,
    which never exits) instead of a one-shot test run. Without a bound
    here, that hang is only caught by the activity's heartbeat_timeout
    (60 min by default) — and since run_test_suite never heartbeats, a
    genuine hang burns the full hour AND, once retries are exhausted,
    fails as an uncaught activity error that crashes the whole workflow
    rather than being handled as a normal (fixable) task failure."""
    proc = await asyncio.create_subprocess_shell(
        inp.test_cmd, cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(
            proc.communicate(), timeout=inp.timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return QAReport(
            tests_passed=False, failing_tests=[],
            issues=[f"test command timed out after {inp.timeout_s}s "
                    f"(cmd: {inp.test_cmd!r}) — likely hung on a "
                    "long-running process (e.g. a dev server) rather "
                    "than exiting after a one-shot test run"])
    out = out_b.decode(errors="replace")
    failing = [ln.split(" ")[0] for ln in out.splitlines()
               if ln.startswith("FAILED")]
    return QAReport(tests_passed=proc.returncode == 0,
                    failing_tests=failing[:50],
                    issues=[] if proc.returncode == 0
                    else [out[-2000:]])


@dataclass
class LintInput:
    worktree: str
    lint_cmd: str = "ruff check ."
    timeout_s: int = 600


@activity.defn
async def run_lint(inp: LintInput) -> tuple[bool, str]:
    """Run a linter; return (clean, detail). P1 runs the repo's configured
    linter; non-zero exit = not clean. `detail` is the tail of stdout for
    the gate's CheckResult.detail. Bounded by timeout_s — see
    run_test_suite's docstring for why an unbounded shell command is
    dangerous here."""
    proc = await asyncio.create_subprocess_shell(
        inp.lint_cmd, cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(
            proc.communicate(), timeout=inp.timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, (f"lint command timed out after {inp.timeout_s}s "
                       f"(cmd: {inp.lint_cmd!r})")
    out = out_b.decode(errors="replace")
    return proc.returncode == 0, out[-2000:]


@dataclass
class PROpenInput:
    worktree: str
    title: str
    body: str
    base_branch: str


@activity.defn
async def open_pull_request(inp: PROpenInput) -> str:
    push = _git(["push", "-u", "origin", "HEAD"], inp.worktree)
    if push.returncode != 0:
        raise RuntimeError(
            f"git push failed: {push.stderr.strip() or push.stdout.strip()}")
    pr = subprocess.run(
        ["gh", "pr", "create", "--title", inp.title, "--body", inp.body,
         "--base", inp.base_branch],
        cwd=inp.worktree, check=True, capture_output=True, encoding="utf-8", errors="replace",
    )
    return pr.stdout.strip()  # PR url


@dataclass
class DeployInput:
    environment: str
    version: str
    command: str  # e.g. "make deploy ENV=staging"
    cwd: str


@activity.defn
async def deploy(inp: DeployInput) -> str:
    proc = await asyncio.create_subprocess_shell(
        inp.command, cwd=inp.cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"deploy failed: {out_b.decode()[-2000:]}")
    return out_b.decode(errors="replace")[-2000:]


@activity.defn
async def evaluate_gate(inp: QualityGateInput) -> GateReport:
    """Activity wrapper over the pure DeterministicQualityGate."""
    return evaluate_quality_gate(inp.checks, inp.overrides)

