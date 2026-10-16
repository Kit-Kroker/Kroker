"""A-terminal worktree teardown (cleanup_run_worktrees) and its janitor
backstop (vcs/janitor.py). The workflow-side call is covered by the
temporal tier indirectly (patched marker); what is proven here: the sync
cleanup converges a real worktree tree to "branches only", it is
idempotent, and the janitor sweeps exactly the dead-and-stale dirs."""

import os
import subprocess
import time

import pytest

from sdlc.vcs.janitor import sweep_once
from sdlc.vcs.worktree import (
    CleanupWorktreesInput,
    _ensure_worktree,
    _worktrees_root,
    cleanup_run_worktrees,
)


def _repo(tmp_path, name="repo"):
    repo = tmp_path / name
    repo.mkdir()
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)

    git("init", "-q")
    git("checkout", "-q", "-b", "main")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    return str(repo)


def _run_worktree(run_root, repo, run_id, task_id="T01"):
    path = os.path.join(run_root, run_id, task_id)
    return _ensure_worktree(repo, f"sdlc/{run_id}/{task_id}", path, "HEAD")


@pytest.mark.asyncio
async def test_teardown_removes_worktrees_keeps_branches(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    repo = _repo(tmp_path)
    handle = _run_worktree(_worktrees_root(), repo, "run-1")
    assert os.path.isdir(handle)

    report = await cleanup_run_worktrees(CleanupWorktreesInput(run_id="run-1"))

    assert report.errors == [] and report.missing is False
    assert report.worktrees_removed == 1
    assert os.path.isdir(repo) and not os.path.exists(handle)
    # the branch — what a forensic re-checkout needs — survives the sweep
    assert (
        subprocess.run(
            ["git", "rev-parse", "--verify", "sdlc/run-1/T01"],
            cwd=repo,
            capture_output=True,
        ).returncode
        == 0
    )
    # the registration is gone too
    out = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    assert handle not in out


@pytest.mark.asyncio
async def test_teardown_is_idempotent_on_a_missing_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    (tmp_path / "wt").mkdir()

    report = await cleanup_run_worktrees(CleanupWorktreesInput(run_id="never-was"))

    assert report.missing is True and report.errors == []


class _FakeClient:
    """The temporal client's list_workflows contract: a SYNC call returning
    an async-iterable of objects with .id."""

    def __init__(self, running):
        self._running = running

    def list_workflows(self, query):
        running = list(self._running)

        async def _it():
            for rid in running:
                yield _FakeWf(rid)

        return _it()


class _FakeWf:
    def __init__(self, id):
        self.id = id


@pytest.mark.asyncio
async def test_janitor_sweeps_only_dead_and_stale_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    wt = tmp_path / "wt"
    repo = _repo(tmp_path)
    old = time.time() - 25 * 3600

    dead = _run_worktree(str(wt), repo, "dead-run")
    alive = _run_worktree(str(wt), repo, "alive-run")
    young = _run_worktree(str(wt), repo, "young-run")
    os.utime(os.path.join(str(wt), "dead-run"), (old, old))
    os.utime(os.path.join(str(wt), "alive-run"), (old, old))
    # `young` keeps its fresh mtime

    swept = await sweep_once(
        _FakeClient({"alive-run"}), str(wt), grace_s=24 * 3600, now=time.time()
    )

    assert swept == ["dead-run"]
    assert not os.path.exists(dead)
    assert os.path.exists(alive) and os.path.exists(young)


@pytest.mark.asyncio
async def test_janitor_sweep_sweeps_everything_when_nothing_is_running(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    wt = tmp_path / "wt"
    repo = _repo(tmp_path)
    old = time.time() - 25 * 3600
    _run_worktree(str(wt), repo, "old-dead-run")
    os.utime(os.path.join(str(wt), "old-dead-run"), (old, old))

    swept = await sweep_once(_FakeClient(set()), str(wt), grace_s=24 * 3600, now=time.time())

    assert swept == ["old-dead-run"]
