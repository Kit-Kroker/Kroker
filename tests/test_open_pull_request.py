"""`open_pull_request` against real git — the PR path's first non-fake coverage.

Until this module the activity's only appearance under `tests/` was
`fake_open_pull_request`: every e2e reached `merged-not-deployed:`/`deployed:`
through `GIT_FAKES`, and benchmark runs short-circuit it outright
(`feature.py`, `"skipped:benchmark-run-has-no-remote"`). So `git push` and
`gh pr create` had never executed under test — which is precisely the path
P2's exit criterion ("first brownfield feature merged via PR") depends on.

`gh` is stubbed by a real program on PATH rather than a patched
`subprocess.run`, because argv construction and exit handling are the parts
that break, and a patch would assert against itself instead of against a
process that actually ran.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.activities import PROpenInput, open_pull_request
from tests.conftest import run_git

PR_URL = "https://github.com/acme/widgets/pull/7"

# Records argv and replays scripted output, so a test can assert what the
# activity asked `gh` to do and how it handled the answer.
_SHIM = """\
import json, os, sys

with open(os.environ["GH_SHIM_ARGV"], "w", encoding="utf-8") as fh:
    json.dump(sys.argv[1:], fh)
sys.stdout.write(os.environ.get("GH_SHIM_STDOUT", ""))
sys.stderr.write(os.environ.get("GH_SHIM_STDERR", ""))
sys.exit(int(os.environ.get("GH_SHIM_EXIT", "0")))
"""


@dataclass
class _GhShim:
    argv_path: Path

    @property
    def argv(self) -> list[str]:
        return json.loads(self.argv_path.read_text(encoding="utf-8"))

    @property
    def ran(self) -> bool:
        return self.argv_path.exists()


@pytest.fixture
def gh_shim(tmp_path, monkeypatch) -> _GhShim:
    """A `gh` on PATH that records its argv and returns scripted output."""
    bin_dir = tmp_path / "shim-bin"
    bin_dir.mkdir()
    script = bin_dir / "gh_shim.py"
    script.write_text(_SHIM, encoding="utf-8")
    if os.name == "nt":
        # A .cmd launcher, resolved via PATHEXT. CreateProcess appends only
        # `.exe`, so the activity must resolve `gh` through shutil.which for
        # this to be reachable at all -- which is the same lookup its
        # "is gh installed" precondition needs.
        launcher = bin_dir / "gh.cmd"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = bin_dir / "gh"
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        launcher.chmod(0o755)

    argv_path = tmp_path / "gh-argv.json"
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GH_SHIM_ARGV", str(argv_path))
    monkeypatch.setenv("GH_SHIM_STDOUT", PR_URL)
    return _GhShim(argv_path=argv_path)


@pytest.fixture
def remote_repo(git_repo, tmp_path):
    """`git_repo` with a real bare `origin` it can actually push to."""
    remote = tmp_path / "remote.git"
    run_git(["init", "--bare", "-b", "main", str(remote)], tmp_path)
    run_git(["remote", "add", "origin", str(remote)], git_repo)
    return git_repo, remote


def _open(worktree: str, base_branch: str = "main") -> str:
    return asyncio.run(
        open_pull_request(
            PROpenInput(
                worktree=worktree,
                title="Add health endpoint",
                body="Brownfield endpoint modification.",
                base_branch=base_branch,
            )
        )
    )


def test_missing_gh_is_non_retryable_and_names_gh(git_repo, tmp_path, monkeypatch):
    """A worker image without `gh` is a misconfiguration, not a blip: today
    it raises FileNotFoundError/WinError 2 and ACT retries it six times
    before killing a run in which every gate already passed."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    with pytest.raises(ApplicationError) as exc:
        _open(git_repo)

    assert exc.value.non_retryable is True
    assert "gh" in str(exc.value)


def test_missing_gh_is_detected_before_anything_is_pushed(remote_repo, tmp_path, monkeypatch):
    """Pushing first and discovering `gh` second would leave a branch on the
    remote with no PR pointing at it, so the precondition runs first."""
    repo, remote = remote_repo
    empty = tmp_path / "empty-bin"
    empty.mkdir()

    with monkeypatch.context() as m:
        m.setenv("PATH", str(empty))
        with pytest.raises(ApplicationError):
            _open(repo)

    assert run_git(["for-each-ref", "refs/heads"], remote).strip() == ""


def test_missing_origin_is_non_retryable(git_repo, gh_shim):
    """`git_repo` has no remote. Retrying cannot conjure one, and the bare
    push error ("'origin' does not appear to be a git repository") does not
    say which of the run's many git steps produced it."""
    with pytest.raises(ApplicationError) as exc:
        _open(git_repo)

    assert exc.value.non_retryable is True
    assert "origin" in str(exc.value)
    assert not gh_shim.ran


def test_push_lands_the_branch_on_the_remote(remote_repo, gh_shim):
    repo, remote = remote_repo
    local_head = run_git(["rev-parse", "HEAD"], repo).strip()

    _open(repo)

    assert run_git(["rev-parse", "main"], remote).strip() == local_head


def test_returns_the_url_gh_printed(remote_repo, gh_shim):
    repo, _ = remote_repo
    assert _open(repo) == PR_URL


def test_gh_receives_the_title_body_and_base(remote_repo, gh_shim):
    repo, _ = remote_repo

    _open(repo, base_branch="release")

    argv = gh_shim.argv
    assert argv[:3] == ["pr", "create", "--title"]
    assert argv[3] == "Add health endpoint"
    assert argv[argv.index("--body") + 1] == ("Brownfield endpoint modification.")
    assert argv[argv.index("--base") + 1] == "release"


def test_gh_failure_carries_its_stderr(remote_repo, gh_shim, monkeypatch):
    """`check=True` raises CalledProcessError, whose str() is "returned
    non-zero exit status 1" -- gh's actual diagnostic is dropped on the way
    through Temporal. The same hazard `_git`'s docstring documents."""
    monkeypatch.setenv("GH_SHIM_EXIT", "1")
    monkeypatch.setenv("GH_SHIM_STDERR", "a pull request for branch 'main' already exists")
    repo, _ = remote_repo

    with pytest.raises(ApplicationError) as exc:
        _open(repo)

    assert "already exists" in str(exc.value)


def test_gh_failure_stays_retryable(remote_repo, gh_shim, monkeypatch):
    """Deliberately split from the two preconditions above: those cannot
    succeed on a retry, whereas `gh pr create` is a network call to GitHub
    and a 5xx is worth ACT's six attempts. The diagnostic is what has to
    survive, not the attempt count."""
    monkeypatch.setenv("GH_SHIM_EXIT", "1")
    monkeypatch.setenv("GH_SHIM_STDERR", "HTTP 502")
    repo, _ = remote_repo

    with pytest.raises(ApplicationError) as exc:
        _open(repo)

    assert exc.value.non_retryable is False
