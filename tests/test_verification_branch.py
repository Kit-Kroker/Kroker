"""D6: the fixes live on unmerged branches, so the tree to re-triage has to be
constructed. Real git in a tmp repo -- the activity is git behaviour, and a
mocked subprocess would test the mock."""
import subprocess

import pytest

from sdlc.activities import (
    VerifyBranchInput, build_verification_branch,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-b", "main"], r)
    _git(["config", "user.email", "t@t"], r)
    _git(["config", "user.name", "t"], r)
    (r / "a.txt").write_text("base\n")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "base"], r)
    base = _git(["rev-parse", "HEAD"], r).stdout.strip()
    return r, base


def _branch_with(repo_dir, name, filename, content, base):
    _git(["checkout", "-q", "-b", name, base], repo_dir)
    (repo_dir / filename).write_text(content)
    _git(["add", "-A"], repo_dir)
    _git(["commit", "-q", "-m", name], repo_dir)
    _git(["checkout", "-q", "main"], repo_dir)


@pytest.mark.asyncio
async def test_merges_every_branch_and_reports_the_head(repo):
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    _branch_with(r, "fix2", "c.txt", "two\n", base)
    out = await build_verification_branch(VerifyBranchInput(
        repo_path=str(r), base_sha=base, tidyup_id="t1",
        branches=["fix1", "fix2"]))
    assert out.merged == ["fix1", "fix2"]
    assert out.conflicted == []
    assert out.head_sha != base
    assert "t1" in out.ref


@pytest.mark.asyncio
async def test_a_conflicting_branch_is_recorded_and_the_rest_still_merge(repo):
    r, base = repo
    _branch_with(r, "fix1", "shared.txt", "one\n", base)
    _branch_with(r, "fix2", "shared.txt", "two\n", base)
    _branch_with(r, "fix3", "d.txt", "three\n", base)
    out = await build_verification_branch(VerifyBranchInput(
        repo_path=str(r), base_sha=base, tidyup_id="t2",
        branches=["fix1", "fix2", "fix3"]))
    assert out.merged == ["fix1", "fix3"]
    assert out.conflicted == ["fix2"]


@pytest.mark.asyncio
async def test_no_branches_yields_the_base_and_merges_nothing(repo):
    r, base = repo
    out = await build_verification_branch(VerifyBranchInput(
        repo_path=str(r), base_sha=base, tidyup_id="t3", branches=[]))
    assert out.merged == [] and out.conflicted == []
    assert out.head_sha == base


@pytest.mark.asyncio
async def test_the_verification_ref_is_local_and_never_pushed(repo):
    """Operator-run; delivery is PR-only until FR-1003/E-59."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    out = await build_verification_branch(VerifyBranchInput(
        repo_path=str(r), base_sha=base, tidyup_id="t4", branches=["fix1"]))
    remotes = _git(["remote"], r).stdout.strip()
    assert remotes == "", "the fixture has no remote; nothing may add one"
    assert out.ref.startswith("sdlc/tidyup-verify/")


@pytest.mark.asyncio
async def test_is_idempotent_across_a_retry(repo):
    """Temporal retries activities. A second call with the same tidyup_id must
    not fail on 'branch already exists'."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    inp = VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t5",
                            branches=["fix1"])
    first = await build_verification_branch(inp)
    second = await build_verification_branch(inp)
    assert first.head_sha == second.head_sha
