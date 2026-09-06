"""C2 Task 4: the deterministic backstop.

Real git fixtures throughout: drift semantics cannot be faked with dicts,
and the delete and index-bit channels only exist in a real repository.
"""

from __future__ import annotations

import subprocess

import pytest

from sdlc.vcs import DriftInput, DriftReport, check_test_drift

FENCE = ["tests/**", "**/tests/**", "conftest.py", "**/conftest.py"]
REPORT = ["pyproject.toml", "**/pyproject.toml"]


def _git(repo, *args) -> str:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=r, check=True)
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "tests" / "test_auth.py").write_text(
        "def test_a():\n    assert 1 == 2\n", encoding="utf-8"
    )
    (r / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (r / "src.py").write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _anchor(repo) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


async def _run(repo, anchor) -> DriftReport:
    return await check_test_drift(
        DriftInput(worktree=str(repo), anchor=anchor, fence_globs=FENCE, report_globs=REPORT)
    )


@pytest.mark.asyncio
async def test_clean_worktree_reports_no_drift(repo):
    r = await _run(repo, _anchor(repo))
    assert r.available is True
    assert r.found is False


@pytest.mark.asyncio
async def test_source_only_change_is_not_drift(repo):
    a = _anchor(repo)
    (repo / "src.py").write_text("x = 2\n", encoding="utf-8")
    r = await _run(repo, a)
    assert r.found is False


@pytest.mark.asyncio
async def test_bash_channel_write_to_a_test_is_fence_drift(repo):
    """The channel the hook structurally cannot see: no Write/Edit tool call
    was made at all."""
    a = _anchor(repo)
    (repo / "tests" / "test_auth.py").write_text(
        "def test_a():\n    assert True\n", encoding="utf-8"
    )
    r = await _run(repo, a)
    assert r.fence_paths == ["tests/test_auth.py"]
    assert "assert True" in r.patch


@pytest.mark.asyncio
async def test_deleted_test_is_fence_drift(repo):
    a = _anchor(repo)
    (repo / "tests" / "test_auth.py").unlink()
    r = await _run(repo, a)
    assert r.fence_paths == ["tests/test_auth.py"]


@pytest.mark.asyncio
async def test_created_test_is_fence_drift(repo):
    """Weakening-by-creation: a new conftest.py with a collection-wide skip
    never edits an existing test."""
    a = _anchor(repo)
    (repo / "conftest.py").write_text("collect_ignore_glob = ['*']\n", encoding="utf-8")
    _git(repo, "add", "-A")
    r = await _run(repo, a)
    assert "conftest.py" in r.fence_paths


@pytest.mark.asyncio
async def test_config_change_is_report_drift_not_fence_drift(repo):
    a = _anchor(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '--ignore=tests'\n", encoding="utf-8"
    )
    r = await _run(repo, a)
    assert r.report_paths == ["pyproject.toml"]
    assert r.fence_paths == []
    assert r.found is True


@pytest.mark.asyncio
async def test_skip_worktree_evasion_is_detected_cleared_and_revealed(repo):
    """THE case. Verified by hand first: with the bit set, `git add -A`
    stages nothing and `git diff` reports nothing, so the committed content
    stays the ORIGINAL failing test while pytest runs the weakened file."""
    a = _anchor(repo)
    _git(repo, "update-index", "--skip-worktree", "tests/test_auth.py")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_a():\n    assert True\n", encoding="utf-8"
    )

    # Pre-condition: prove the naive check really is blind here.
    naive = _git(repo, "diff", "--name-only", a, "--", *FENCE).split()
    assert naive == [], "fixture no longer reproduces the evasion"

    r = await _run(repo, a)
    assert r.index_bit_paths == ["tests/test_auth.py"]  # the evasion
    assert r.fence_paths == ["tests/test_auth.py"]  # the weakening
    assert "assert True" in r.patch  # adjudicable by a human
    # The bit is cleared, so a later honest check sees the truth too.
    assert "S tests/test_auth.py" not in _git(repo, "ls-files", "-v", "--", *FENCE)


@pytest.mark.asyncio
async def test_assume_unchanged_evasion_is_detected(repo):
    a = _anchor(repo)
    _git(repo, "update-index", "--assume-unchanged", "tests/test_auth.py")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_a():\n    assert True\n", encoding="utf-8"
    )
    r = await _run(repo, a)
    assert r.index_bit_paths == ["tests/test_auth.py"]
    assert r.fence_paths == ["tests/test_auth.py"]


@pytest.mark.asyncio
async def test_ordinary_tracked_files_are_never_index_bit_findings(repo):
    """`H` is the tag for every ordinary tracked file. Flagging it would
    report the entire repository as evasion."""
    r = await _run(repo, _anchor(repo))
    assert r.index_bit_paths == []


@pytest.mark.asyncio
async def test_unresolvable_anchor_is_unavailable_never_a_clean_pass(repo):
    r = await _run(repo, "0" * 40)
    assert r.available is False
    assert r.found is False
    assert r.unavailable_reason


@pytest.mark.asyncio
async def test_non_repo_is_unavailable_never_a_clean_pass(tmp_path):
    r = await check_test_drift(
        DriftInput(worktree=str(tmp_path), anchor="HEAD", fence_globs=FENCE, report_globs=REPORT)
    )
    assert r.available is False
    assert r.unavailable_reason
