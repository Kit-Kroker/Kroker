"""D6: the fixes live on unmerged branches, so the tree to re-triage has to be
constructed. Real git in a tmp repo -- the activity is git behaviour, and a
mocked subprocess would test the mock."""

import subprocess

import pytest

from sdlc.activities import (
    VerifyBranchInput,
    build_verification_branch,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-b", "main"], r)
    _git(["config", "user.email", "t@t"], r)
    _git(["config", "user.name", "t"], r)
    (r / "a.txt").write_text("base\n")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "base"], r)
    base = _git(["rev-parse", "HEAD"], r).stdout.strip()
    # Verification happens in a worktree -- keep it under tmp_path, not the
    # worker's default temp root, so each test is hermetic.
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
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
    out = await build_verification_branch(
        VerifyBranchInput(
            repo_path=str(r), base_sha=base, tidyup_id="t1", branches=["fix1", "fix2"]
        )
    )
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
    out = await build_verification_branch(
        VerifyBranchInput(
            repo_path=str(r), base_sha=base, tidyup_id="t2", branches=["fix1", "fix2", "fix3"]
        )
    )
    assert out.merged == ["fix1", "fix3"]
    assert out.conflicted == ["fix2"]


@pytest.mark.asyncio
async def test_no_branches_yields_the_base_and_merges_nothing(repo):
    r, base = repo
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t3", branches=[])
    )
    assert out.merged == [] and out.conflicted == []
    assert out.head_sha == base


@pytest.mark.asyncio
async def test_the_verification_ref_is_local_and_never_pushed(repo):
    """Operator-run; delivery is PR-only until FR-1003/E-59."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t4", branches=["fix1"])
    )
    remotes = _git(["remote"], r).stdout.strip()
    assert remotes == "", "the fixture has no remote; nothing may add one"
    assert out.ref.startswith("sdlc/tidyup-verify/")


@pytest.mark.asyncio
async def test_is_idempotent_across_a_retry(repo):
    """Temporal retries activities. A second call with the same tidyup_id must
    not fail on 'branch already exists', and must reproduce the same tree.
    The commit SHA is NOT stable across retries: a --no-ff merge carries a
    fresh committer timestamp each call. The TREE is what the after-triage
    measures, so that is the invariant pinned here."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    inp = VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t5", branches=["fix1"])
    first = await build_verification_branch(inp)
    second = await build_verification_branch(inp)
    assert first.merged == second.merged == ["fix1"]

    def tree_of(sha):
        return _git(["rev-parse", f"{sha}^{{tree}}"], r).stdout.strip()

    assert tree_of(first.head_sha) == tree_of(second.head_sha)


@pytest.mark.asyncio
async def test_the_operators_repo_is_never_touched(repo):
    """NG5: the verification tree is built in a worktree, never in the
    operator's checkout. A merge there would (a) move their main when _git's
    unchecked checkout fails on a dirty tree, and (b) leave their working tree
    checked out on the verify branch with fix-branch files in it. Both are
    fixed by operating in a worktree; this test pins that the operator's
    branch and HEAD are unchanged after the activity."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    branch_before = _git(["branch", "--show-current"], r).stdout.strip()
    head_before = _git(["rev-parse", "HEAD"], r).stdout.strip()
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t6", branches=["fix1"])
    )
    assert out.merged == ["fix1"] and out.head_sha != base
    # The operator is still on their original branch, at their original HEAD.
    assert _git(["branch", "--show-current"], r).stdout.strip() == branch_before
    assert _git(["rev-parse", "HEAD"], r).stdout.strip() == head_before
    # And their working tree has none of the fix-branch files.
    assert not (r / "b.txt").exists()


@pytest.mark.asyncio
async def test_a_dirty_working_tree_does_not_corrupt_the_operators_repo(repo):
    """The defect a worktree fixes: with the operator's tree dirty, the old
    in-repo checkout failed silently (_git has no check=True) and the merges
    landed on whatever HEAD was -- moving the operator's main. In a worktree a
    dirty operator tree is irrelevant: nothing in their repo is touched."""
    r, base = repo
    _branch_with(r, "fix1", "a.txt", "one\n", base)  # fix1 changes a.txt
    # Dirty the operator's tree on the very file fix1 touches.
    (r / "a.txt").write_text("dirty uncommitted\n")
    main_before = _git(["rev-parse", "main"], r).stdout.strip()
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t7", branches=["fix1"])
    )
    assert out.merged == ["fix1"]
    # main did not move; the dirty change is still there, uncommitted.
    assert _git(["rev-parse", "main"], r).stdout.strip() == main_before
    assert (r / "a.txt").read_text() == "dirty uncommitted\n"
