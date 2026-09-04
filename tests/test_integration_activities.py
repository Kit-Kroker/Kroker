import asyncio
from pathlib import Path

import pytest

from sdlc.vcs import (
    DiffInput,
    IntegrationInput,
    MergeInput,
    WorktreeInput,
    create_worktree,
    get_task_diff,
    merge_into_integration,
    setup_integration_branch,
)
from tests.conftest import run_git

RUN = "run1"


def _add_commit(path: str, name: str, content: str, msg: str) -> None:
    (Path(path) / name).write_text(content)
    run_git(["add", "-A"], path)
    run_git(["commit", "-m", msg], path)


def test_dependent_task_sees_prior_task_code(git_repo):
    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    head = handle.head_sha

    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(
        merge_into_integration(
            MergeInput(
                repo_path=git_repo,
                run_id=RUN,
                task_branch=a.branch,
                integration_path=handle.worktree_path,
            )
        )
    )
    assert res.merged and not res.conflict

    # B branches from the UPDATED integration head → must see A's file.
    b = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id=RUN, task_id="B", from_ref=res.integration_head
            )
        )
    )
    assert (Path(b.path) / "a.txt").read_text() == "from A\n"


def test_setup_returns_worktree_path(git_repo):
    """Resolution A: setup hands back the integration worktree path so the
    workflow doesn't read SDLC_WORKTREES_ROOT from the env."""
    import os

    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-wt", base_branch="main")
        )
    )
    assert handle.worktree_path == os.path.join(
        os.environ["SDLC_WORKTREES_ROOT"], "run-wt", "integration"
    )
    assert (Path(handle.worktree_path) / "README.md").exists()


def test_diff_anchors_to_branch_point_not_base(git_repo):
    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    head = handle.head_sha
    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(
        merge_into_integration(
            MergeInput(
                repo_path=git_repo,
                run_id=RUN,
                task_branch=a.branch,
                integration_path=handle.worktree_path,
            )
        )
    )

    b = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id=RUN, task_id="B", from_ref=res.integration_head
            )
        )
    )
    _add_commit(b.path, "b.txt", "from B\n", "B work")
    assert res.merged
    diff = asyncio.run(get_task_diff(DiffInput(worktree=b.path, branch_point=b.branch_point)))
    assert "b.txt" in diff["files"]
    assert "a.txt" not in diff["files"]  # A's change is upstream, not B's diff


def test_merge_conflict_is_detected_and_aborted(git_repo):
    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    head = handle.head_sha
    # A and B branch from the same head and edit the SAME file.
    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "shared.txt", "A version\n", "A edits shared")
    b = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="B", from_ref=head))
    )
    _add_commit(b.path, "shared.txt", "B version\n", "B edits shared")

    ra = asyncio.run(
        merge_into_integration(
            MergeInput(
                repo_path=git_repo,
                run_id=RUN,
                task_branch=a.branch,
                integration_path=handle.worktree_path,
            )
        )
    )
    assert ra.merged is True
    rb = asyncio.run(
        merge_into_integration(
            MergeInput(
                repo_path=git_repo,
                run_id=RUN,
                task_branch=b.branch,
                integration_path=handle.worktree_path,
            )
        )
    )
    assert rb.conflict is True and rb.merged is False
    # Integration head unchanged after the aborted merge → equals A's merge head.
    assert rb.integration_head == ra.integration_head


def test_merge_uses_integration_path_not_canonical(git_repo):
    """Regression: setup_integration_branch may hand back a non-canonical
    worktree path (``integration.N``) when the canonical one was CWD-locked
    on Windows. merge_into_integration must merge at the handed-back path,
    NOT recompute the canonical one — otherwise cwd points at a cleared dir
    and subprocess.run raises NotADirectoryError (WinError 267).

    Simulate the fallback by moving the worktree off the canonical path
    via `git worktree move`, then merging with integration_path=<moved>."""
    import os

    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    canonical = os.path.join(os.environ["SDLC_WORKTREES_ROOT"], RUN, "integration")
    assert handle.worktree_path == canonical  # baseline: starts canonical

    moved = canonical + ".moved"
    run_git(["worktree", "move", canonical, moved], git_repo)
    assert not os.path.exists(canonical)  # canonical is now gone

    a = asyncio.run(
        create_worktree(
            WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=handle.head_sha)
        )
    )
    _add_commit(a.path, "a.txt", "from A\n", "A work")

    res = asyncio.run(
        merge_into_integration(
            MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch, integration_path=moved)
        )
    )
    assert res.merged and not res.conflict


def test_merge_failure_that_is_not_a_conflict_raises(git_repo):
    handle = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )

    # A nonexistent branch ref makes `git merge` fail with no unmerged
    # entries in the index — this is an infra/config failure, not a real
    # task-overlap conflict, and must raise rather than report conflict=True.
    with pytest.raises(RuntimeError):
        asyncio.run(
            merge_into_integration(
                MergeInput(
                    repo_path=git_repo,
                    run_id=RUN,
                    task_branch="sdlc/nope/does-not-exist",
                    integration_path=handle.worktree_path,
                )
            )
        )
