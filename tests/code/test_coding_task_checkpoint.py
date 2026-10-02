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

A third leg (006-B1): the ``git commit`` half must not fail silently
either. A non-zero commit is logged — exactly one WARNING naming the
worktree and git's stderr-or-stdout — while the activity still returns
with ``commit_sha`` unset instead of raising. (``git add`` failures
still raise: that path loses the worktree, not just the anchor.)
"""

import asyncio
import logging
import subprocess

import sdlc.stages.code.activities
from sdlc.core.models import (
    HarnessKind,
)
from sdlc.harness.base import CodingHarness
from sdlc.harness.models import HarnessRunResult
from sdlc.stages.code.activities import (
    CodingTaskInput,
    run_coding_task,
)
from sdlc.vcs import (
    IntegrationInput,
    WorktreeInput,
    create_worktree,
    setup_integration_branch,
)
from sdlc.vcs.git import _git

_ACTIVITIES_LOGGER = "sdlc.stages.code.activities"


class _StubHarness(CodingHarness):
    """Harness that does no real work — lets us test run_coding_task's
    checkpoint-commit logic without spawning claude/opencode."""

    kind = HarnessKind.CLAUDE_CODE

    def build_cmd(self, req):  # never called — run() is overridden
        return []

    def parse(self, stdout, exit_code):
        raise NotImplementedError

    async def run(self, req, heartbeat=None):
        return HarnessRunResult(harness=self.kind, exit_code=0, summary="stub")


def _git_with_failing_commit(failing):
    """A passthrough ``_git`` whose ``git commit`` returns `failing` as-is;
    every other command (``add``) still reaches the real git. A real broken
    identity is machine-dependent, so the failure is injected instead."""

    def _fake(args, cwd):
        if args[0] == "commit":
            return failing
        return _git(args, cwd)

    return _fake


def _activity_warnings(caplog):
    """WARNING records emitted by the activities logger itself — other
    loggers' noise (logfire, capture) never counts toward the contract."""
    return [
        r for r in caplog.records if r.name == _ACTIVITIES_LOGGER and r.levelno == logging.WARNING
    ]


def test_checkpoint_survives_dubious_ownership(git_repo, monkeypatch):
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-cp", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(repo_path=git_repo, run_id="run-cp", task_id="T", from_ref=setup.head_sha)
        )
    )

    # Flip on git's dubious-ownership check — the production trigger is a
    # different SID; this flag forces the same code path deterministically.
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )

    result = asyncio.run(
        run_coding_task(  # raises before the fix
            CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
        )
    )

    assert result.commit_sha  # checkpoint commit landed despite dubious ownership


def test_checkpoint_surfaces_git_stderr_on_failure(git_repo, monkeypatch):
    """When the checkpoint commit fails for a reason OTHER than dubious
    ownership, the real git error must reach Temporal — not a bare
    CalledProcessError that loses git's stderr. We force a failure by
    deleting the worktree's .git pointer so ``git add`` cannot find a
    repository, then assert git's diagnostic text is in the raised error.
    """
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-stderr", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-stderr", task_id="T", from_ref=setup.head_sha
            )
        )
    )

    import os

    git_link = os.path.join(wt.path, ".git")
    if os.path.exists(git_link):
        os.remove(git_link)

    import pytest

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            run_coding_task(
                CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
            )
        )
    # git's own diagnostic — not just "non-zero exit status 128".
    assert (
        "not a git repository" in str(exc_info.value).lower()
        or "fatal" in str(exc_info.value).lower()
    )


def test_failed_checkpoint_commit_logs_one_warning_naming_worktree_and_stderr(
    git_repo, monkeypatch, caplog
):
    """A non-zero checkpoint commit must not vanish (006-B1): run_coding_task
    logs exactly one WARNING naming the worktree and git's stderr, leaves
    ``commit_sha`` unset, and does not raise. The failure rides a passthrough
    ``_git`` because a real broken committer identity is machine-dependent."""
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-warn-stderr", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-warn-stderr", task_id="T", from_ref=setup.head_sha
            )
        )
    )
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )
    failing = subprocess.CompletedProcess(
        args=["git", "commit"],
        returncode=1,
        stdout="",
        stderr="fatal: qa-006 injected commit failure: no committer identity",
    )
    monkeypatch.setattr(sdlc.stages.code.activities, "_git", _git_with_failing_commit(failing))

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = asyncio.run(
            run_coding_task(
                CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
            )
        )

    warnings = _activity_warnings(caplog)
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert wt.path in message
    assert "qa-006 injected commit failure: no committer identity" in message
    assert not result.commit_sha  # the anchor cannot advance past a failed commit


def test_failed_checkpoint_commit_warning_carries_stdout_when_stderr_is_empty(
    git_repo, monkeypatch, caplog
):
    """git sometimes fails a commit with empty stderr and its diagnostic on
    stdout (hooks do this). The WARNING must carry whichever stream git spoke
    through — here, stdout (006-B1)."""
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-warn-stdout", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-warn-stdout", task_id="T", from_ref=setup.head_sha
            )
        )
    )
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )
    failing = subprocess.CompletedProcess(
        args=["git", "commit"],
        returncode=1,
        stdout="qa-006 injected failure on stdout: pre-commit hook declined",
        stderr="",
    )
    monkeypatch.setattr(sdlc.stages.code.activities, "_git", _git_with_failing_commit(failing))

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = asyncio.run(
            run_coding_task(
                CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
            )
        )

    warnings = _activity_warnings(caplog)
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert wt.path in message
    assert "qa-006 injected failure on stdout: pre-commit hook declined" in message
    assert not result.commit_sha


def test_failed_checkpoint_commit_still_logs_one_warning_when_git_output_is_empty(
    git_repo, monkeypatch, caplog
):
    """A commit can fail with BOTH streams empty. The contract is still
    exactly one WARNING — naming the worktree is the only content guaranteed
    to exist (006-B1)."""
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-warn-silent", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-warn-silent", task_id="T", from_ref=setup.head_sha
            )
        )
    )
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )
    failing = subprocess.CompletedProcess(
        args=["git", "commit"], returncode=1, stdout="", stderr=""
    )
    monkeypatch.setattr(sdlc.stages.code.activities, "_git", _git_with_failing_commit(failing))

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = asyncio.run(
            run_coding_task(
                CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
            )
        )

    warnings = _activity_warnings(caplog)
    assert len(warnings) == 1
    assert wt.path in warnings[0].getMessage()
    assert not result.commit_sha


def test_successful_checkpoint_commit_is_silent_and_lands_head(git_repo, monkeypatch, caplog):
    """CONTROL — passes before the fix, and guards the new warning against
    crying wolf: a healthy checkpoint commit produces NO WARNING on the
    activities logger, and ``commit_sha`` is the worktree's real HEAD."""
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-warn-control", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-warn-control", task_id="T", from_ref=setup.head_sha
            )
        )
    )
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _StubHarness()
    )

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = asyncio.run(
            run_coding_task(
                CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="noop", worktree=wt.path)
            )
        )

    assert _activity_warnings(caplog) == []
    head = _git(["rev-parse", "HEAD"], wt.path).stdout.strip()
    assert result.commit_sha == head
