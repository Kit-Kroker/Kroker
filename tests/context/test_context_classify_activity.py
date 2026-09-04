"""E-84 D3: the observation half of intake, against real git repositories."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.stages.context.activities import RepoProbeInput, classify_repo


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def empty_repo(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    _git("init", "-b", "main", cwd=d)
    _git("config", "user.email", "t@t.t", cwd=d)
    _git("config", "user.name", "t", cwd=d)
    (d / "README.md").write_text("# hi\n")
    _git("add", ".", cwd=d)
    _git("commit", "-m", "init", cwd=d)
    return d


@pytest.fixture
def source_repo(empty_repo):
    (empty_repo / "app.py").write_text("x = 1\n")
    (empty_repo / "util.ts").write_text("export const y = 2;\n")
    _git("add", ".", cwd=empty_repo)
    _git("commit", "-m", "code", cwd=empty_repo)
    return empty_repo


@pytest.mark.asyncio
async def test_a_repo_with_source_is_observed_as_such(source_repo):
    got = await classify_repo(RepoProbeInput(repo_dir=str(source_repo), base_branch="main"))
    assert got.is_git_repo is True
    assert got.base_branch_resolves is True
    assert got.source_file_count == 2
    assert len(got.commit_sha) == 40


@pytest.mark.asyncio
async def test_readme_only_is_not_source(empty_repo):
    """SOURCE_EXTENSIONS, not "any file" -- a docs-only repo has nothing to
    map, and intake must agree with the scan about that."""
    got = await classify_repo(RepoProbeInput(repo_dir=str(empty_repo), base_branch="main"))
    assert got.is_git_repo is True
    assert got.source_file_count == 0


@pytest.mark.asyncio
async def test_a_missing_path_is_not_a_repo_and_never_raises(tmp_path):
    got = await classify_repo(RepoProbeInput(repo_dir=str(tmp_path / "nope"), base_branch="main"))
    assert got.is_git_repo is False
    assert got.reason != ""


@pytest.mark.asyncio
async def test_a_missing_base_branch_is_reported_not_raised(source_repo):
    got = await classify_repo(RepoProbeInput(repo_dir=str(source_repo), base_branch="nonexistent"))
    assert got.is_git_repo is True
    assert got.base_branch_resolves is False
    assert got.reason != ""
