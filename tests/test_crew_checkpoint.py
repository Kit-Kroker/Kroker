# tests/test_crew_checkpoint.py
"""E-88 §2: checkpoints are per ROUND, not per task. That is what makes
`git reset --hard <round N-1>` an exact round restart, and what stops a turn
timeout from discarding work already done."""

from __future__ import annotations

import subprocess
import sys

import pytest

from sdlc.crew.activities import CheckpointInput, checkpoint_round
from sdlc.crew.worktree import prepare_orchestration

pytestmark = pytest.mark.asyncio


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    (tmp_path / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)
    return tmp_path


async def test_checkpoint_commits_the_round_and_returns_its_sha(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    sha = await checkpoint_round(CheckpointInput(worktree=str(repo), round=1, exit_code=0))
    assert sha and len(sha) == 40
    head = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "round 1" in head


async def test_checkpoint_never_commits_the_protocol_directory(tmp_path):
    repo = _repo(tmp_path)
    d = prepare_orchestration(repo, "code")
    (d / "brief.md").write_text("secret-ish", encoding="utf-8")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    await checkpoint_round(CheckpointInput(worktree=str(repo), round=1, exit_code=0))
    files = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert files == ["app.py"]
    # ... and the exclusion is local to the add, not repo state: the
    # orchestration tree stays on disk, visibly UNTRACKED (a bare
    # `git add -A` would sweep it -- that guarantee belongs to this
    # command's pathspec, nowhere else).
    assert (d / "brief.md").is_file()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    orch = [ln for ln in status.splitlines() if ".workspace" in ln]
    assert orch, "orchestration tree vanished from disk"
    assert all(ln.startswith("??") for ln in orch)


async def test_checkpoint_is_allowed_to_be_empty(tmp_path):
    """A round in which the agent changed nothing is still a round boundary,
    and the workflow decides what an empty one means."""
    repo = _repo(tmp_path)
    sha = await checkpoint_round(CheckpointInput(worktree=str(repo), round=1, exit_code=0))
    assert sha and len(sha) == 40


async def test_checkpoint_falls_back_when_orchestration_is_already_ignored(tmp_path):
    """A repo (or a stale COMMON-dir info/exclude left by an older run) can
    already ignore .workspace/orchestration on its own. Naming an
    already-ignored path in ANY pathspec -- even an :(exclude) clause --
    makes git refuse the whole `add` unless -f (confirmed empirically
    against a live git: identical repo, only difference is a pre-existing
    ignore rule for the same path). Every crew checkpoint would fail on
    such a repo without the fallback."""
    repo = _repo(tmp_path)
    (repo / ".git" / "info" / "exclude").write_text(
        "/.workspace/orchestration/\n", encoding="utf-8"
    )
    d = prepare_orchestration(repo, "code")
    (d / "brief.md").write_text("secret-ish", encoding="utf-8")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    sha = await checkpoint_round(CheckpointInput(worktree=str(repo), round=1, exit_code=0))
    assert sha and len(sha) == 40
    files = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert files == ["app.py"]


async def test_checkpoint_surfaces_gits_own_diagnostic(tmp_path):
    """A bare CalledProcessError loses stderr when Temporal serializes it."""
    with pytest.raises(RuntimeError, match="not a git repository"):
        await checkpoint_round(CheckpointInput(worktree=str(tmp_path), round=1, exit_code=0))


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="exec bits are a POSIX fact; Windows stat cannot express one",
)
async def test_checkpoint_stages_exec_bits_that_filemode_false_git_cannot_see(tmp_path):
    """A worktree of a Windows-authored template repo runs with
    core.filemode=false, and there `git add` is blind to chmod +x: the round
    commits mode 100644 and the integration merge later checks the script
    out non-executable (bench-crew-probe-1788765412 lost 4/101 entrypoint
    tests to exactly this). The checkpoint must mirror disk exec bits into
    the index itself."""
    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "config", "core.filemode", "false"], check=True)
    script = repo / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n:\n", encoding="utf-8")
    script.chmod(0o755)
    # Precondition the fix exists for: with filemode=false a plain add
    # really does stage 100644 despite the on-disk 755. (If this ever fails
    # because git staged 100755, the test environment has filemode=true and
    # no longer reproduces the bug.)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    plain = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-s", "scripts/run.sh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert plain == "100644"
    subprocess.run(["git", "-C", str(repo), "reset", "-q"], check=True)

    await checkpoint_round(CheckpointInput(worktree=str(repo), round=1, exit_code=0))

    committed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-s", "scripts/run.sh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert committed == "100755"
