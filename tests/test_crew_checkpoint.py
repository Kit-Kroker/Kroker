# tests/test_crew_checkpoint.py
"""E-88 §2: checkpoints are per ROUND, not per task. That is what makes
`git reset --hard <round N-1>` an exact round restart, and what stops a turn
timeout from discarding work already done."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.crew.activities import CheckpointInput, checkpoint_round
from sdlc.crew.worktree import prepare_orchestration

pytestmark = pytest.mark.asyncio


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v],
                       check=True)
    (tmp_path / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"],
                   check=True)
    return tmp_path


async def test_checkpoint_commits_the_round_and_returns_its_sha(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    sha = await checkpoint_round(CheckpointInput(worktree=str(repo), round=1,
                                                 exit_code=0))
    assert sha and len(sha) == 40
    head = subprocess.run(["git", "-C", str(repo), "log", "-1", "--pretty=%s"],
                          capture_output=True, text=True, check=True).stdout
    assert "round 1" in head


async def test_checkpoint_never_commits_the_protocol_directory(tmp_path):
    repo = _repo(tmp_path)
    d = prepare_orchestration(repo, "code")
    (d / "brief.md").write_text("secret-ish", encoding="utf-8")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    await checkpoint_round(CheckpointInput(worktree=str(repo), round=1,
                                           exit_code=0))
    files = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=", "HEAD"],
        capture_output=True, text=True, check=True).stdout.split()
    assert files == ["app.py"]


async def test_checkpoint_is_allowed_to_be_empty(tmp_path):
    """A round in which the agent changed nothing is still a round boundary,
    and the workflow decides what an empty one means."""
    repo = _repo(tmp_path)
    sha = await checkpoint_round(CheckpointInput(worktree=str(repo), round=1,
                                                 exit_code=0))
    assert sha and len(sha) == 40


async def test_checkpoint_surfaces_gits_own_diagnostic(tmp_path):
    """A bare CalledProcessError loses stderr when Temporal serializes it."""
    with pytest.raises(RuntimeError, match="not a git repository"):
        await checkpoint_round(CheckpointInput(worktree=str(tmp_path),
                                               round=1, exit_code=0))
