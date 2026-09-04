"""E-84 D8: resolution happens against git, activity-side."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.activities import DeltaCheckInput, check_brownfield_delta
from sdlc.stages.context.models import BrownfieldDelta


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "r"
    (d / "src").mkdir(parents=True)
    _git("init", "-b", "main", cwd=d)
    _git("config", "user.email", "t@t.t", cwd=d)
    _git("config", "user.name", "t", cwd=d)
    (d / "src" / "api.py").write_text("x = 1\n")
    _git("add", ".", cwd=d)
    _git("commit", "-m", "init", cwd=d)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True
    ).stdout.strip()
    return d, sha


@pytest.mark.asyncio
async def test_a_real_path_resolves(repo):
    d, sha = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha=sha, delta=BrownfieldDelta(modified=["src/api.py"])
        )
    )
    assert got.passed is True


@pytest.mark.asyncio
async def test_a_fabricated_path_fails(repo):
    d, sha = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha=sha, delta=BrownfieldDelta(modified=["src/ghost.py"])
        )
    )
    assert got.passed is False
    assert "src/ghost.py" in got.detail


@pytest.mark.asyncio
async def test_an_unresolvable_commit_fails_closed(repo):
    """A check that cannot read the tree must never report a pass -- that is
    the malformed-SARIF hole FR-915 exists to close."""
    d, _ = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha="0" * 40, delta=BrownfieldDelta(modified=["src/api.py"])
        )
    )
    assert got.passed is False
    assert "could not list" in got.detail.lower()
