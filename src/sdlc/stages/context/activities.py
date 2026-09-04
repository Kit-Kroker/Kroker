"""Context stage activities (spec A §5)."""

from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity

from ...assessment.scan.sources import SOURCE_EXTENSIONS
from ...context.delta import DELTA_CHECK, check_delta
from ...context.models import RepoObservation
from ...gate import CheckClass, CheckResult, build_check
from ...vcs.git import _git
from .models import BrownfieldDelta


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


ACTIVITIES = [classify_repo, check_brownfield_delta]

__all__ = [
    "ACTIVITIES",
    "DeltaCheckInput",
    "RepoProbeInput",
    "check_brownfield_delta",
    "classify_repo",
]
