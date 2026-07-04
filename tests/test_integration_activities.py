import asyncio
from pathlib import Path

import pytest

from sdlc.activities import (
    DiffInput, IntegrationInput, MergeInput, WorktreeInput,
    create_worktree, get_task_diff, merge_into_integration,
    setup_integration_branch,
)
from tests.conftest import run_git

RUN = "run1"


def _add_commit(path: str, name: str, content: str, msg: str) -> None:
    (Path(path) / name).write_text(content)
    run_git(["add", "-A"], path)
    run_git(["commit", "-m", msg], path)


def test_dependent_task_sees_prior_task_code(git_repo):
    head = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))

    a = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head)))
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(merge_into_integration(
        MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch)))
    assert res.merged and not res.conflict

    # B branches from the UPDATED integration head → must see A's file.
    b = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="B",
                      from_ref=res.integration_head)))
    assert (Path(b.path) / "a.txt").read_text() == "from A\n"


def test_diff_anchors_to_branch_point_not_base(git_repo):
    head = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))
    a = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head)))
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(merge_into_integration(
        MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch)))

    b = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="B",
                      from_ref=res.integration_head)))
    _add_commit(b.path, "b.txt", "from B\n", "B work")
    assert res.merged
    diff = asyncio.run(get_task_diff(
        DiffInput(worktree=b.path, branch_point=b.branch_point)))
    assert "b.txt" in diff["files"]
    assert "a.txt" not in diff["files"]  # A's change is upstream, not B's diff


def test_merge_conflict_is_detected_and_aborted(git_repo):
    head = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))
    # A and B branch from the same head and edit the SAME file.
    a = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head)))
    _add_commit(a.path, "shared.txt", "A version\n", "A edits shared")
    b = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="B", from_ref=head)))
    _add_commit(b.path, "shared.txt", "B version\n", "B edits shared")

    ra = asyncio.run(merge_into_integration(
        MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch)))
    assert ra.merged is True
    rb = asyncio.run(merge_into_integration(
        MergeInput(repo_path=git_repo, run_id=RUN, task_branch=b.branch)))
    assert rb.conflict is True and rb.merged is False
    # Integration head unchanged after the aborted merge → equals A's merge head.
    assert rb.integration_head == ra.integration_head


def test_merge_failure_that_is_not_a_conflict_raises(git_repo):
    asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")))

    # A nonexistent branch ref makes `git merge` fail with no unmerged
    # entries in the index — this is an infra/config failure, not a real
    # task-overlap conflict, and must raise rather than report conflict=True.
    with pytest.raises(RuntimeError):
        asyncio.run(merge_into_integration(
            MergeInput(repo_path=git_repo, run_id=RUN,
                      task_branch="sdlc/nope/does-not-exist")))
