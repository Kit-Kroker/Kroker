"""DS2/DS3: the disposable detached base worktree, and rename pairs."""

import os
import pathlib
import subprocess

import pytest

from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "head")
    return repo, base


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


@pytest.mark.asyncio
async def test_materializes_the_base_commit_detached(tmp_path):
    repo, base = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert wt.path is not None, wt.reason
    assert (pathlib.Path(wt.path) / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert _git(wt.path, "rev-parse", "HEAD") == base


@pytest.mark.asyncio
async def test_a_retry_reuses_and_resets_but_keeps_the_provisioned_venv(tmp_path):
    repo, base = _repo(tmp_path)
    first = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    p = pathlib.Path(first.path)
    (p / "a.py").write_text("dirty\n", encoding="utf-8")
    (p / "stray.py").write_text("x\n", encoding="utf-8")
    (p / ".sdlc-venv").mkdir()
    again = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert os.path.normpath(again.path) == os.path.normpath(first.path)
    assert (p / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert not (p / "stray.py").exists()
    assert (p / ".sdlc-venv").is_dir()


@pytest.mark.asyncio
async def test_no_base_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", ""))
    assert wt.path is None and "base_sha" in wt.reason


@pytest.mark.asyncio
async def test_an_unknown_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", "0" * 40))
    assert wt.path is None and wt.reason


@pytest.mark.asyncio
async def test_get_task_diff_reports_rename_pairs(tmp_path):
    repo, _ = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "rename")
    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    assert d["renames"] == [["a.py", "b.py"]]
    assert "b.py" in d["files"]
