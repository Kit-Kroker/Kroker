"""E-43's third byte-source: quote vs. bytes at path@commit_sha.

Ships with no caller -- the assessment stage (E-41) is its consumer. Tested
against real git, because `git show` behaviour on a deleted path is exactly
the case the fail-closed rule depends on.
"""
import subprocess

import pytest

from sdlc.activities import CommittedBytesInput, read_committed_bytes
from sdlc.grounding import Profile, verify_quote


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True)


@pytest.fixture
def repo(tmp_path):
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "app.py").write_text("def f(**kwargs):\n    return kwargs\n",
                                     encoding="utf-8")
    # A sub-directory (path resolves to a tree, not a blob) and an empty file
    # (resolves to a zero-length blob) -- the two edge cases code review #4
    # pins before E-41 wires a caller.
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "one"], tmp_path)
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                           capture_output=True, encoding="utf-8",
                           check=True).stdout.strip()
    (tmp_path / "app.py").unlink()
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                            capture_output=True, encoding="utf-8",
                            check=True).stdout.strip()
    return tmp_path, first, second


@pytest.mark.asyncio
async def test_existing_path_at_a_real_sha_returns_bytes(repo):
    d, first, _ = repo
    text = await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=first))
    assert "def f(**kwargs):" in text


@pytest.mark.asyncio
async def test_the_returned_bytes_verify_under_verbatim_profile(repo):
    """The whole point of the source: a quote is checked against these bytes."""
    d, first, _ = repo
    text = await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=first))
    assert verify_quote("def f(**kwargs):", text, Profile.VERBATIM_BYTES)


@pytest.mark.asyncio
async def test_deleted_path_at_a_later_sha_returns_none(repo):
    d, _, second = repo
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=second)) is None


@pytest.mark.asyncio
async def test_nonexistent_sha_returns_none(repo):
    d, _, _ = repo
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py",
        commit_sha="0" * 40)) is None


@pytest.mark.asyncio
async def test_nonexistent_repo_returns_none_rather_than_raising(tmp_path):
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(tmp_path / "nope"), path="a.py",
        commit_sha="HEAD")) is None


@pytest.mark.asyncio
async def test_directory_path_returns_none_not_a_tree_listing(repo):
    """`git show sha:dir` returns the tree listing with exit 0, which is NOT
    the file's bytes. A directory must read as unavailable (code review #4)."""
    d, first, _ = repo
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="pkg", commit_sha=first)) is None


@pytest.mark.asyncio
async def test_empty_file_returns_empty_string_not_none(repo):
    """An empty file's bytes are "". That is a resolved read, distinct from
    None (unresolved) -- callers must check `is None`, not truthiness
    (code review #4)."""
    d, first, _ = repo
    text = await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="empty.py", commit_sha=first))
    assert text is not None
    assert text == ""
