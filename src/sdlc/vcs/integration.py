"""Integration branch and verification branch activities (spec A §5)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from temporalio import activity

from .git import _git
from .worktree import _clear_worktree_dir, _ensure_worktree, _worktrees_root


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


# The provisioned per-worktree venv (stages/qa/activities.py _VENV_DIR_NAME).
# Kept across resets: re-provisioning it is the expensive part of a retry.
_KEEP_ON_CLEAN = ".sdlc-venv"


@dataclass
class BaseWorktreeInput:
    integration_wt: str  # any worktree of the repository; git worktree add runs here
    run_id: str
    base_sha: str  # FeatureWorkflow._base_sha, pinned at setup (DS2)


@dataclass
class BaseWorktree:
    path: str | None  # None = could not materialize; `reason` says why
    reason: str = ""


@activity.defn
async def prepare_base_worktree(inp: BaseWorktreeInput) -> BaseWorktree:
    """DS2/DS3: a disposable DETACHED worktree at the pinned base commit.

    Never raises on a git failure: the merge gate must fail CLOSED on an
    unmaterializable base (DS7), which it does by handing path=None to the
    scoped activities, which then report NOT_COLLECTED. Raising would instead
    fail the whole workflow. Idempotent across retries: a live worktree is
    reset to base_sha and cleaned (keeping the provisioned venv), the
    build_verification_branch pattern. Never pushed; never the operator's
    checkout.
    """
    if not inp.base_sha:
        return BaseWorktree(None, "no pinned base_sha was supplied to the merge gate")
    want = _git(
        ["rev-parse", "--verify", "--quiet", f"{inp.base_sha}^{{commit}}"], inp.integration_wt
    )
    if want.returncode != 0:
        return BaseWorktree(None, f"base_sha {inp.base_sha!r} does not resolve to a commit")
    sha = want.stdout.strip()
    root = os.path.join(_worktrees_root(), inp.run_id or "local", "base")
    for cand in [root] + [f"{root}.{i}" for i in range(1, 8)]:
        cand = os.path.normpath(cand)
        live = (
            os.path.isdir(cand)
            and _git(["rev-parse", "--is-inside-work-tree"], cand).returncode == 0
        )
        if not live:
            if os.path.exists(cand):
                try:
                    _clear_worktree_dir(inp.integration_wt, cand)
                except OSError:
                    continue  # Windows CWD lock: try the next candidate
            add = _git(["worktree", "add", "--detach", cand, sha], inp.integration_wt)
            if add.returncode != 0:
                return BaseWorktree(
                    None,
                    f"git worktree add failed: {add.stderr.strip() or add.stdout.strip()}",
                )
        for args in (
            ["checkout", "--detach", "--force", sha],
            ["reset", "--hard", sha],
            ["clean", "-fd", "-e", _KEEP_ON_CLEAN],
        ):
            r = _git(args, cand)
            if r.returncode != 0:
                err = r.stderr.strip() or r.stdout.strip()
                return BaseWorktree(None, f"git {args[0]} failed in the base worktree: {err}")
        if _git(["rev-parse", "HEAD"], cand).stdout.strip() != sha:
            return BaseWorktree(None, "base worktree HEAD does not match base_sha after reset")
        return BaseWorktree(cand)
    return BaseWorktree(None, f"could not clear or create a base worktree near {root}")
