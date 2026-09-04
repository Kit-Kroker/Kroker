"""Temporal activities — all the non-deterministic work.

Activities run in the worker process; workflows never touch subprocesses,
the filesystem, or the network directly.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from .artifacts.capture import capture_session
from .assessment.scan.sources import SOURCE_EXTENSIONS
from .context.delta import DELTA_CHECK, check_delta
from .context.models import RepoObservation
from .core.models import HarnessKind
from .gate import (
    CheckClass,
    CheckResult,
    GateReport,
    QualityGateInput,
    build_check,
    evaluate_quality_gate,
)
from .harness.adapters import HARNESSES, HarnessRequest
from .harness.containment import ContainmentError, load_policy
from .measurement import Measurement
from .models import (
    BrownfieldDelta,
    CoverageReport,
    HarnessRunResult,
    ToolGrant,
)
from .observability.logfire_setup import span
from .process import kill_process_tree
from .stages.qa.activities import (
    _diagnostic_slice,
    _ensure_python_env,
    _stopped_early,
)
from .stages.qa.models import QAReport
from .toolchain.adapters import ToolchainKind, detect

if TYPE_CHECKING:
    from .crew.activities import CrewTurnInput

_log = logging.getLogger(__name__)


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
    ipath = inp.integration_path or os.path.join(_worktrees_root(), inp.run_id, "integration")
    merge = _git(["merge", "--no-ff", "-m", f"merge {inp.task_branch}", inp.task_branch], ipath)
    if merge.returncode != 0:
        # Distinguish a real conflict from an infra/config failure via the
        # git index's unmerged entries (locale-independent) — must be read
        # BEFORE `merge --abort`, which clears the unmerged state.
        unmerged = _git(["ls-files", "--unmerged"], ipath).stdout
        _git(["merge", "--abort"], ipath)
        if not unmerged.strip():
            raise RuntimeError(f"git merge failed (not a conflict): {merge.stderr.strip()}")
        head = _git(["rev-parse", "HEAD"], ipath).stdout.strip()
        return MergeResult(merged=False, conflict=True, integration_head=head)
    head = _git(["rev-parse", "HEAD"], ipath).stdout.strip()
    return MergeResult(merged=True, conflict=False, integration_head=head)


@dataclass
class VerifyBranchInput:
    repo_path: str
    base_sha: str  # the commit the baseline triage pinned
    tidyup_id: str  # the TidyUpWorkflow's id -- makes the ref unique
    branches: list[str]  # fix-run integration branches, in accepted order


@dataclass
class VerifyResult:
    ref: str
    head_sha: str
    merged: list[str]
    conflicted: list[str]


@activity.defn
async def build_verification_branch(inp: VerifyBranchInput) -> VerifyResult:
    """E-44 D6: the tree the after-triage measures.

    open_pull_request OPENS PRs; it does not merge them, so re-triaging the
    base branch would measure a tree containing none of the fixes. This builds
    the 'if you merged all of these' tree instead: a local branch off the
    pinned commit with every successful fix branch merged into it.

    Built in a WORKTREE under SDLC_WORKTREES_ROOT, never in the operator's
    checkout. Two reasons, both load-bearing:

      - ``_git`` does not ``check=True``, so a checkout that fails on a dirty
        working tree is silent. Operating in the operator's repo would then
        merge fix branches into whatever HEAD is on -- their main -- and
        return a clean-looking success. That is NG5 violated by the one
        component whose docstring says "local only".
      - Even on the happy path, merging in the operator's repo leaves it
        checked out on the verify branch with fix-branch files in the working
        tree. Every other git activity in this file works in a worktree for
        this reason.

    Local only -- never pushed. Delivery stays PR-only until FR-1003/E-59.

    A conflict between two fix branches is a RESULT, not a failure: the merge
    is aborted, the branch is recorded in `conflicted`, and the remaining
    branches still merge. compute_delta then marks that identity UNVERIFIABLE
    rather than PERSISTED (D5 rule 3).

    Idempotent: Temporal retries activities. ``_ensure_worktree`` reuses a
    surviving worktree, so the head is reset to ``base_sha`` before the merges
    replay -- a retry never compounds onto a half-built tree.
    """
    ref = f"sdlc/tidyup-verify/{inp.tidyup_id}"
    wt_path = os.path.join(_worktrees_root(), inp.tidyup_id, "verify")
    worktree = _ensure_worktree(inp.repo_path, ref, wt_path, inp.base_sha)

    # Replay-safe: a Temporal retry reuses the worktree but must re-merge from
    # base_sha. reset --hard is safe here because this worktree is disposable
    # (no operator data lives in it). Checked explicitly: _git does not raise.
    reset = _git(["reset", "--hard", inp.base_sha], worktree)
    if reset.returncode != 0:
        raise RuntimeError(
            f"git reset to base_sha {inp.base_sha} failed: "
            f"{reset.stderr.strip() or reset.stdout.strip()}"
        )

    merged: list[str] = []
    conflicted: list[str] = []
    for branch in inp.branches:
        result = _git(["merge", "--no-ff", "-m", f"tidy-up: {branch}", branch], worktree)
        if result.returncode == 0:
            merged.append(branch)
            continue
        # Distinguish a real conflict from an infra failure via the index's
        # unmerged entries (locale-independent), and read it BEFORE
        # `merge --abort`, which clears the unmerged state. Same reasoning as
        # merge_into_integration.
        unmerged = _git(["ls-files", "--unmerged"], worktree).stdout
        _git(["merge", "--abort"], worktree)
        if not unmerged.strip():
            raise RuntimeError(
                f"git merge of {branch} failed (not a conflict): {result.stderr.strip()}"
            )
        conflicted.append(branch)

    head = _git(["rev-parse", "HEAD"], worktree).stdout.strip()
    return VerifyResult(ref=ref, head_sha=head, merged=merged, conflicted=conflicted)


@dataclass
class CodingTaskInput:
    harness: HarnessKind
    prompt: str
    worktree: str
    model: str | None = None
    session_id: str | None = None
    timeout_s: int = 3600
    task_id: str = "task"  # E-38: session artifact naming
    attempt: int = 1
    # E-15/E-16 (FR-703). Flags travel; the YAML is loaded activity-side,
    # because the workflow sandbox cannot read files — same split as the
    # agent registry.
    containment_enabled: bool = False
    containment_policy_path: str | None = None
    containment_strict: bool = False
    # E-17: human decisions about suspended tool calls. Written to a grants
    # file activity-side and read by the hook; empty on a first attempt.
    grants: list[ToolGrant] = field(default_factory=list)


def _resolve_containment(
    harness, inp: CodingTaskInput | CrewTurnInput, req: HarnessRequest | None = None
):
    """Load the policy and compile it into `req`, or fail closed.

    Returns (policy, report) — both None when containment is disabled.
    Every failure path raises: an unpoliced run that BELIEVES it is policed
    is the one outcome worse than no containment at all (ADR-17).
    """
    if not inp.containment_enabled:
        return None, None

    policy = load_policy(inp.containment_policy_path)  # raises: fail closed

    if not harness.containment:
        raise ContainmentError(
            f"containment is enabled but the {harness.kind.value} harness "
            f"cannot enforce any layer; refusing to start an unpoliced run "
            f"(ADR-17). Disable containment or choose another harness."
        )

    if req is None:  # unit-test path: compile a probe
        req = HarnessRequest(prompt=inp.prompt, cwd=inp.worktree)
    report = harness.apply_containment(policy, req, inp.grants)

    if inp.containment_strict and report.rules_unenforceable:
        raise ContainmentError(
            f"containment_strict is set and the {harness.kind.value} harness "
            f"leaves these rules unenforceable: "
            f"{', '.join(report.rules_unenforceable)}"
        )
    return policy, report


@activity.defn
async def run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    """Execute claude -p / opencode run inside the task worktree.

    Long-running: heartbeats while the harness streams output so Temporal
    can detect a hung/dead worker and retry elsewhere.
    """
    harness = HARNESSES[inp.harness]
    req = HarnessRequest(
        prompt=inp.prompt,
        cwd=inp.worktree,
        model=inp.model,
        session_id=inp.session_id,
        timeout_s=inp.timeout_s,
    )
    _, report = _resolve_containment(harness, inp, req)
    with span("harness.run", harness=inp.harness.value, task_id=inp.task_id, attempt=inp.attempt):
        result = await harness.run(req, heartbeat=activity.heartbeat)
    result.containment = report
    try:
        result.denials = harness.normalise_denials(result._raw_stdout)
        result.deferred = harness.normalise_deferral(result._raw_stdout)
    except Exception:  # noqa: BLE001
        # Best-effort, exactly like capture_session: losing the RECORD of a
        # denial must never fail a task whose denial was already enforced.
        # A lost deferral simply means no escalation is raised — the call
        # was already suspended by the hook, not allowed.
        _log.warning("denial normalisation failed", exc_info=True)
    # E-38: capture the transcript. Raw stdout rides a PrivateAttr — it
    # exists only inside this activity and is never written unscrubbed.
    # Best-effort: a failure here (incl. running outside an activity context
    # in tests) must never break the coding task itself.
    try:
        run_id = activity.info().workflow_run_id
    except RuntimeError:
        run_id = "local"
    run_id = run_id or "local"  # temporalio types the field as Optional
    with span("session.capture", task_id=inp.task_id, stdout_bytes=len(result._raw_stdout)):
        ref, digest = capture_session(
            harness, result._raw_stdout, run_id=run_id, task_id=inp.task_id, attempt=inp.attempt
        )
        result.session_ref = ref
        result.session_digest = digest
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
            hint = (
                " (the worktree's .git was intact when this task started; "
                "the coding agent likely deleted or reinitialized it)"
            )
        raise RuntimeError(f"git add failed in {inp.worktree}: {detail}{hint}")
    commit = _git(
        ["commit", "-m", f"sdlc checkpoint (exit={result.exit_code})", "--allow-empty"],
        inp.worktree,
    )
    if commit.returncode == 0:
        result.commit_sha = _git(["rev-parse", "HEAD"], inp.worktree).stdout.strip()
    return result


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
class CoverageInput:
    worktree: str
    changed_files: list[str]


@activity.defn
async def measure_coverage(inp: CoverageInput) -> CoverageReport:
    """Diff-scoped coverage from a Cobertura coverage.xml already emitted into
    the worktree by the run's test commands (FR-106). Minimal deterministic
    seam — pure filesystem read, reproducible across retries. Real per-stack
    instrumentation replaces only this body.

    The file is generated inside a harness worktree (untrusted, ARCHITECTURE.md
    §10), so it is parsed with defusedxml to block XXE / entity-expansion DoS.

    NOT_COLLECTED (check passes as a no-op) when there is no coverage.xml, it
    is unparseable/malicious, or none of the changed files appear in it; UNKNOWN
    when a changed file's line-rate is non-finite. An unbuilt measurement must
    never force a human override."""
    path = os.path.join(inp.worktree, "coverage.xml")
    if not os.path.isfile(path):
        return CoverageReport(
            coverage=Measurement.not_collected("no coverage.xml (seam not measured)")
        )
    try:
        root = DET.parse(path).getroot()
    except (DefusedXmlException, DET.ParseError, OSError):
        return CoverageReport(
            coverage=Measurement.not_collected("coverage.xml unparseable or unsafe")
        )
    rates: list[float] = []
    skipped_non_finite = 0
    for cls in root.iter("class"):
        fname = cls.get("filename") or ""
        if any(
            fname == cf or fname.endswith("/" + cf) or cf.endswith("/" + fname)
            for cf in inp.changed_files
        ):
            try:
                rate = float(cls.get("line-rate", "0"))
            except ValueError:
                continue
            if not math.isfinite(rate):
                # Hostile/corrupt input (nan, inf) -- never let it propagate
                # into a measured value, where e.g. `nan >= threshold` silently
                # evaluates False and fabricates an advisory failure. An
                # attempt DID produce output, so this is `unknown`, not
                # `not_collected` (FR-915).
                skipped_non_finite += 1
                continue
            rates.append(max(0.0, min(100.0, rate * 100.0)))
    if not rates:
        if skipped_non_finite:
            return CoverageReport(
                coverage=Measurement.unknown(
                    f"{skipped_non_finite} changed-file line-rate(s) non-finite"
                )
            )
        return CoverageReport(
            coverage=Measurement.not_collected(
                "no changed file found in coverage.xml (seam not measured)"
            )
        )
    # Unweighted mean of per-class line-rates — an approximation of true
    # diff coverage, not a line-weighted average. A 500-line file at 50%
    # and a 5-line file at 100% average to 75% here, though true line
    # coverage across both is ~50.5%. Acceptable for this seam; real
    # per-stack instrumentation should replace this with a weighted
    # (lines-covered / lines-valid) computation.
    pct = sum(rates) / len(rates)
    return CoverageReport(coverage=Measurement.measured(pct))


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


async def _bounded_shell(
    cmd: str, cwd: str, timeout_s: int, env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Run a shell command bounded by timeout_s, combining stdout+stderr.
    On timeout: kill and return (-1, message). See run_test_suite's docstring
    for why an unbounded shell command is dangerous in an activity.

    env=None inherits the activity process's own environment (the prior,
    only behaviour); passing an override (e.g. a worktree-local venv's PATH
    from _ensure_python_env) does NOT merge with it automatically — callers
    must pass a full environment dict."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return -1, f"command timed out after {timeout_s}s (cmd: {cmd!r})"
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
    return (proc.returncode or 0), out_b.decode(errors="replace")


@dataclass
class IntegrationChecksInput:
    worktree: str
    changed_files: list[str]
    test_timeout_s: int = 600
    lint_timeout_s: int = 300
    setup_timeout_s: int = 300


@dataclass
class IntegrationChecks:
    toolchain: str | None  # ToolchainKind value, or None if undetected
    qa: QAReport
    lint_clean: bool
    lint_detail: str


# pytest usage-error exit code: unrecognized args (e.g. --cov when pytest-cov is
# absent) => 4, distinct from 1 (tests failed). A MISSING coverage plugin must
# degrade coverage to measured=False, never falsely fail the ABSOLUTE
# build_integration_green check — so on a 4 we re-run WITHOUT coverage for the
# honest green signal (FR-108 green-signal invariant).
_PYTEST_USAGE_ERROR = 4


@activity.defn
async def run_integration_checks(inp: IntegrationChecksInput) -> IntegrationChecks:
    """FR-108/ADR-15: resolve the toolchain by marker file and run
    coverage-instrumented tests + lint against the merged integration head.
    Emits coverage.xml into inp.worktree, where measure_coverage reads — the
    FR-106 gap this closes.

    toolchain=None (unrecognized marker) => tests/lint NOT re-run here; the
    workflow falls back to the per-task aggregate + standalone run_lint, exactly
    as before E-30. Never blocks on a language it doesn't know."""
    adapter = detect(inp.worktree)
    if adapter is None:
        return IntegrationChecks(
            toolchain=None,
            qa=QAReport(tests_passed=False, issues=["no toolchain adapter for this worktree"]),
            lint_clean=True,
            lint_detail="no toolchain adapter (not linted)",
        )

    env = None
    if adapter.kind is ToolchainKind.PYTHON:
        env, setup_error = await _ensure_python_env(inp.worktree, inp.setup_timeout_s)
        if setup_error:
            qa = QAReport(tests_passed=False, issues=[setup_error])
            return IntegrationChecks(
                toolchain=adapter.kind.value, qa=qa, lint_clean=False, lint_detail=setup_error
            )

    code, out = await _bounded_shell(
        adapter.test_cmd(coverage=True), inp.worktree, inp.test_timeout_s, env=env
    )
    if code == _PYTEST_USAGE_ERROR:
        # Coverage tooling unavailable — get the honest green signal without it.
        prefix = (
            "coverage instrumentation unavailable (pytest usage error); coverage left unmeasured\n"
        )
        code, out = await _bounded_shell(
            adapter.test_cmd(coverage=False), inp.worktree, inp.test_timeout_s, env=env
        )
        out = prefix + out
    failing = [ln.split(" ")[0] for ln in out.splitlines() if ln.startswith("FAILED")]
    qa = QAReport(
        tests_passed=code == 0,
        failing_tests=failing[:50],
        issues=[] if code == 0 else [_diagnostic_slice(out)],
        stopped_early=_stopped_early(out),
    )

    lcode, ldetail = await _bounded_shell(
        adapter.lint_cmd(), inp.worktree, inp.lint_timeout_s, env=env
    )
    return IntegrationChecks(
        toolchain=adapter.kind.value, qa=qa, lint_clean=lcode == 0, lint_detail=ldetail[-2000:]
    )


@dataclass
class PROpenInput:
    worktree: str
    title: str
    body: str
    base_branch: str


@activity.defn
async def open_pull_request(inp: PROpenInput) -> str:
    """Push the integration branch and open a PR for it.

    Preconditions first, and both non-retryable: a worker image without `gh`
    and a worktree without an `origin` are misconfigurations, not blips, so
    ACT's six attempts with backoff only delay a failure that is already
    decided. Checking `gh` *before* the push also keeps a missing binary from
    leaving a pushed branch on the remote with no PR pointing at it.

    `gh` is resolved through shutil.which rather than invoked by name: it is
    the same lookup the precondition needs, and on Windows CreateProcess
    appends only `.exe`, so a bare `["gh", ...]` misses a `gh.cmd` that is
    plainly on PATH.

    `gh pr create` is deliberately left retryable — unlike the preconditions
    it is a network call to GitHub, where a 5xx is worth another attempt. What
    must survive either way is the diagnostic: `check=True` raised a
    CalledProcessError whose str() is "returned non-zero exit status 1", so
    gh's own message was dropped on the way through Temporal (the hazard
    `_git`'s docstring documents, one seam over).
    """
    gh = shutil.which("gh")
    if gh is None:
        raise ApplicationError(
            "gh CLI not found on PATH: the worker cannot open a pull request "
            "without it (it is installed in the worker image; a source "
            "checkout needs it installed separately)",
            non_retryable=True,
        )

    remote = _git(["remote", "get-url", "origin"], inp.worktree)
    if remote.returncode != 0:
        raise ApplicationError(
            f"no 'origin' remote in {inp.worktree!r}: "
            f"{remote.stderr.strip() or remote.stdout.strip()}",
            non_retryable=True,
        )

    push = _git(["push", "-u", "origin", "HEAD"], inp.worktree)
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr.strip() or push.stdout.strip()}")

    # stdin=DEVNULL for the console-less-worker reason _git documents.
    pr = subprocess.run(
        [gh, "pr", "create", "--title", inp.title, "--body", inp.body, "--base", inp.base_branch],
        cwd=inp.worktree,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    if pr.returncode != 0:
        raise ApplicationError(f"gh pr create failed: {pr.stderr.strip() or pr.stdout.strip()}")
    return pr.stdout.strip()  # PR url


@activity.defn
async def evaluate_gate(inp: QualityGateInput) -> GateReport:
    """Activity wrapper over the pure DeterministicQualityGate."""
    return evaluate_quality_gate(inp.checks, inp.overrides)


class RepoProbeInput(BaseModel):
    repo_dir: str
    base_branch: str = "main"


@activity.defn
async def classify_repo(inp: RepoProbeInput) -> RepoObservation:
    """E-84 D3: probe the repository for intake classification.

    Never raises: missing repo / branch / unreadable tree / subprocess error
    are all observations intake turns into a verdict with a reason -- raising
    here would make "the path is wrong" indistinguishable from "the worker
    died", which is the retry policy's business, not intake's.
    """
    try:
        probe = _git(["rev-parse", "--is-inside-work-tree"], cwd=inp.repo_dir)
        if probe.returncode != 0:
            return RepoObservation(
                is_git_repo=False,
                base_branch_resolves=False,
                reason=(probe.stderr.strip() or f"{inp.repo_dir!r} is not reachable")[:300],
            )

        rev = _git(["rev-parse", "--verify", f"{inp.base_branch}^{{commit}}"], cwd=inp.repo_dir)
        if rev.returncode != 0:
            return RepoObservation(
                is_git_repo=True,
                base_branch_resolves=False,
                reason=(rev.stderr.strip() or f"branch {inp.base_branch!r} does not resolve")[:300],
            )
        commit_sha = rev.stdout.strip()

        listing = _git(
            ["-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", commit_sha],
            cwd=inp.repo_dir,
        )
        if listing.returncode != 0:
            return RepoObservation(
                is_git_repo=True,
                base_branch_resolves=True,
                commit_sha=commit_sha,
                reason=(listing.stderr.strip() or "could not list the tree")[:300],
            )

        count = sum(1 for p in listing.stdout.splitlines() if p.strip().endswith(SOURCE_EXTENSIONS))
        return RepoObservation(
            is_git_repo=True,
            base_branch_resolves=True,
            commit_sha=commit_sha,
            source_file_count=count,
        )
    except Exception as exc:
        return RepoObservation(
            is_git_repo=False,
            base_branch_resolves=False,
            reason=f"{inp.repo_dir!r} probe failed: {exc}"[:300],
        )


class DeltaCheckInput(BaseModel):
    repo_dir: str
    commit_sha: str
    delta: BrownfieldDelta | None = None


@activity.defn
async def check_brownfield_delta(inp: DeltaCheckInput) -> CheckResult:
    """E-84 D8: supply the tree's path list, then run the pure check.

    The listing stays here rather than travelling to the workflow: a large
    repository's full path set inline would bloat every brownfield run's
    history against ADR-10, and would push CodebaseMap past the Architect's
    context_budget_tokens (FR-801).
    """
    try:
        listing = _git(
            ["-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", inp.commit_sha],
            cwd=inp.repo_dir,
        )
    except Exception as exc:
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            f"could not list the tree at {inp.commit_sha[:12]}: {exc}",
        )
    if listing.returncode != 0:
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            f"could not list the tree at {inp.commit_sha[:12]}: {listing.stderr.strip()[:200]}",
        )
    paths = frozenset(p for p in listing.stdout.splitlines() if p.strip())
    return check_delta(inp.delta, paths)
