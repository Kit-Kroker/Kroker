"""run_coding_task's checkpoint commit (``git add -A`` + ``git commit``)
must succeed when git considers the worktree's ownership "dubious", and
must surface git's actual stderr if it fails for any other reason.

Reproduces the runtime error:
  Command '['git', 'add', '-A']' returned non-zero exit status 128.

On Windows, git's ``safe.directory`` ownership check (added in 2.36.3)
refuses operations on a repo whose owner differs from the calling
process — exit 128, "fatal: detected dubious ownership in repository
at '...'". It fires whenever the worker's SID doesn't match the
worktree dir's owner: service accounts, mounted volumes, containers,
files extracted across users. Our worktrees live under
``SDLC_WORKTREES_ROOT`` (default ``tempfile.gettempdir()/sdlc/worktrees``)
and are created and fully owned by this worker, so the checkpoint
commit must bypass the check rather than crash the activity.

``GIT_TEST_ASSUME_DIFFERENT_OWNER=1`` is git's own test-assist flag that
forces the dubious-ownership code path regardless of actual SIDs — the
same trigger as production, deterministic across platforms. It is set
*after* worktree creation so only the checkpoint-commit git calls run
under the dubious condition.
"""
import asyncio

import sdlc.activities
from sdlc.activities import (
    CodingTaskInput, IntegrationInput, WorktreeInput,
    create_worktree, run_coding_task, setup_integration_branch,
)
from sdlc.harness.adapters import CodingHarness
from sdlc.models import HarnessKind, HarnessRunResult


class _StubHarness(CodingHarness):
    """Harness that does no real work — lets us test run_coding_task's
    checkpoint-commit logic without spawning claude/opencode."""
    kind = HarnessKind.CLAUDE_CODE

    def build_cmd(self, req):  # never called — run() is overridden
        return []

    def parse(self, stdout, exit_code):
        raise NotImplementedError

    async def run(self, req, heartbeat=None):
        return HarnessRunResult(
            harness=self.kind, exit_code=0, summary="stub")


def test_checkpoint_survives_dubious_ownership(git_repo, monkeypatch):
    setup = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id="run-cp",
                         base_branch="main")))
    wt = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id="run-cp", task_id="T",
                      from_ref=setup.head_sha)))

    # Flip on git's dubious-ownership check — the production trigger is a
    # different SID; this flag forces the same code path deterministically.
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    monkeypatch.setitem(sdlc.activities.HARNESSES,
                        HarnessKind.CLAUDE_CODE, _StubHarness())

    result = asyncio.run(run_coding_task(  # raises before the fix
        CodingTaskInput(harness=HarnessKind.CLAUDE_CODE,
                        prompt="noop", worktree=wt.path)))

    assert result.commit_sha  # checkpoint commit landed despite dubious ownership


def test_checkpoint_surfaces_git_stderr_on_failure(git_repo, monkeypatch):
    """When the checkpoint commit fails for a reason OTHER than dubious
    ownership, the real git error must reach Temporal — not a bare
    CalledProcessError that loses git's stderr. We force a failure by
    deleting the worktree's .git pointer so ``git add`` cannot find a
    repository, then assert git's diagnostic text is in the raised error.
    """
    monkeypatch.setitem(sdlc.activities.HARNESSES,
                        HarnessKind.CLAUDE_CODE, _StubHarness())
    setup = asyncio.run(setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id="run-stderr",
                         base_branch="main")))
    wt = asyncio.run(create_worktree(
        WorktreeInput(repo_path=git_repo, run_id="run-stderr", task_id="T",
                      from_ref=setup.head_sha)))

    import os
    git_link = os.path.join(wt.path, ".git")
    if os.path.exists(git_link):
        os.remove(git_link)

    import pytest
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(run_coding_task(
            CodingTaskInput(harness=HarnessKind.CLAUDE_CODE,
                            prompt="noop", worktree=wt.path)))
    # git's own diagnostic — not just "non-zero exit status 128".
    assert "not a git repository" in str(exc_info.value).lower() \
        or "fatal" in str(exc_info.value).lower()
