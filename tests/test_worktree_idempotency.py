"""Temporal retries re-run activities; create_worktree / setup_integration_branch
must be idempotent — a repeat call with the same input must reuse the worktree
it created on the first attempt, not crash on `git worktree add -b`
("a branch named ... already exists").

Reproduces the runtime error:
  git worktree add failed (rc=255): ... a branch named 'sdlc/<run>/<task>' already exists
"""
import asyncio
import shutil

from sdlc.activities import (
    IntegrationInput, WorktreeInput,
    create_worktree, setup_integration_branch,
)
from tests.conftest import run_git

RUN = "run-idem"


def test_create_worktree_reuses_on_repeat_call(git_repo):
    """A Temporal retry calls create_worktree again with identical input;
    the branch and worktree already exist from attempt #1, so attempt #2
    must reuse them rather than raise."""
    setup = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))
    inp = WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="T01",
                        from_ref=setup.head_sha)

    first = asyncio.run(create_worktree(inp))
    second = asyncio.run(create_worktree(inp))  # raises before the fix

    assert second.path == first.path
    assert second.branch == first.branch
    assert second.branch_point == first.branch_point


def test_create_worktree_recovers_from_pruned_worktree(git_repo):
    """Worker died after creating the worktree; the dir was cleared and
    `git worktree prune` dropped the registration, but the branch lingers.
    A retry must check out the existing branch into a fresh worktree."""
    setup = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))
    inp = WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="T02",
                        from_ref=setup.head_sha)

    first = asyncio.run(create_worktree(inp))
    shutil.rmtree(first.path)                       # crash: dir gone
    run_git(["worktree", "prune"], git_repo)         # registration dropped
    assert run_git(["rev-parse", "--verify", first.branch], git_repo).strip()  # branch remains

    recovered = asyncio.run(create_worktree(inp))    # raises before the fix

    assert recovered.path == first.path
    assert recovered.branch == first.branch


def test_setup_integration_branch_reuses_on_repeat_call(git_repo):
    """Same idempotency for setup_integration_branch — identical `add -b`
    pattern, identical retry hazard."""
    inp = IntegrationInput(repo_path=git_repo, run_id="run-setup", base_branch="main")
    first = asyncio.run(setup_integration_branch(inp))
    second = asyncio.run(setup_integration_branch(inp))  # raises before the fix
    assert second.worktree_path == first.worktree_path
