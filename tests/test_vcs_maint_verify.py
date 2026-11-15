"""Contract tests for the 023b verification-tree git helpers (T011).

Subjects (``sdlc.vcs.integration``):
- ``is_ancestor(repo_path, ancestor, descendant) -> bool`` (new, R8). Read-only.
- ``remove_verification_tree(repo_path, key)`` (new, R4). Idempotent.
- ``build_verification_branch`` (EXISTING, R4). Its ref-name convention is the
  one the loop relies on for ``remove_verification_tree``.

The two new names are imported inside each test, so before T012 they fail
per test with ImportError. The ``build_verification_branch`` test is a
convention PIN, not RED: it exercises existing code and is expected to pass.

Fast tier: no temporal env. The activities are plain callables and are driven
directly against a fixture git repo from ``tests/maintenance/conftest.py``.
"""

from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import pytest

from sdlc.vcs.integration import VerifyBranchInput, build_verification_branch
from tests.maintenance.conftest import git, head_sha, make_repo

CHILD_ID = "maint-demo-abcd1234-inc1-a1"
INTEGRATION_BRANCH = f"sdlc/{CHILD_ID}/integration"


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@pytest.fixture(autouse=True)
def worktrees_root(tmp_path: Path, monkeypatch) -> str:
    root = str(tmp_path / "wts")
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", root)
    return root


async def _call(fn, *args):
    """Call an activity-style helper whether it is sync or async."""
    out = fn(*args)
    if inspect.isawaitable(out):
        out = await out
    return out


def _fix_branch(repo: Path, name: str, base: str) -> None:
    """A real fix branch with one commit on top of ``base``; repo HEAD is restored."""
    git(repo, "checkout", "-b", name, base)
    (repo / "fix.txt").write_text("fixed\n", encoding="utf-8")
    git(repo, "add", "fix.txt")
    git(repo, "commit", "-m", f"fix on {name}")
    git(repo, "checkout", "main")


def _ref_exists(repo: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _snapshot(repo: Path) -> tuple[str, str]:
    refs = git(repo, "for-each-ref")
    status = git(repo, "status", "--porcelain")
    return refs, status


# ---------------------------------------------------------------- is_ancestor (R8)


@pytest.mark.asyncio
async def test_is_ancestor_true_for_an_earlier_commit(repo_dir):
    from sdlc.vcs.integration import is_ancestor

    older = head_sha(repo_dir)
    (repo_dir / "later.txt").write_text("later\n", encoding="utf-8")
    git(repo_dir, "add", "later.txt")
    git(repo_dir, "commit", "-m", "later")
    newer = head_sha(repo_dir)

    assert await _call(is_ancestor, str(repo_dir), older, newer) is True


@pytest.mark.asyncio
async def test_is_ancestor_false_when_reversed(repo_dir):
    from sdlc.vcs.integration import is_ancestor

    older = head_sha(repo_dir)
    (repo_dir / "later.txt").write_text("later\n", encoding="utf-8")
    git(repo_dir, "add", "later.txt")
    git(repo_dir, "commit", "-m", "later")
    newer = head_sha(repo_dir)

    assert await _call(is_ancestor, str(repo_dir), newer, older) is False


@pytest.mark.asyncio
async def test_is_ancestor_never_mutates_the_repository(repo_dir):
    from sdlc.vcs.integration import is_ancestor

    base = head_sha(repo_dir)
    _fix_branch(repo_dir, INTEGRATION_BRANCH, base)
    before = _snapshot(repo_dir)

    await _call(is_ancestor, str(repo_dir), base, INTEGRATION_BRANCH)
    await _call(is_ancestor, str(repo_dir), INTEGRATION_BRANCH, base)

    assert _snapshot(repo_dir) == before


# ---------------------------------------------------------- remove_verification_tree (R4)


async def _build_verify(repo: Path, key: str) -> str:
    """The real existing activity: creates <root>/<key>/verify and ref
    sdlc/tidyup-verify/<key> off the base commit."""
    base = head_sha(repo)
    _fix_branch(repo, INTEGRATION_BRANCH, base)
    await _call(
        build_verification_branch,
        VerifyBranchInput(
            repo_path=str(repo),
            base_sha=base,
            tidyup_id=key,
            branches=[INTEGRATION_BRANCH],
        ),
    )
    return base


@pytest.mark.asyncio
async def test_remove_verification_tree_removes_the_worktree_and_the_ref(repo_dir, worktrees_root):
    from sdlc.vcs.integration import remove_verification_tree

    await _build_verify(repo_dir, CHILD_ID)
    verify_dir = os.path.join(worktrees_root, CHILD_ID, "verify")
    ref = f"refs/heads/sdlc/tidyup-verify/{CHILD_ID}"
    assert os.path.isdir(verify_dir), "precondition: verify worktree was not built"
    assert _ref_exists(repo_dir, ref), "precondition: verify ref was not built"

    await _call(remove_verification_tree, str(repo_dir), CHILD_ID)

    assert not os.path.exists(verify_dir)
    assert not _ref_exists(repo_dir, ref)


@pytest.mark.asyncio
async def test_remove_verification_tree_is_idempotent(repo_dir, worktrees_root):
    from sdlc.vcs.integration import remove_verification_tree

    await _build_verify(repo_dir, CHILD_ID)
    await _call(remove_verification_tree, str(repo_dir), CHILD_ID)

    # A second call on an already-removed tree must succeed, not raise.
    await _call(remove_verification_tree, str(repo_dir), CHILD_ID)
    assert not os.path.exists(os.path.join(worktrees_root, CHILD_ID, "verify"))


@pytest.mark.asyncio
async def test_remove_verification_tree_never_raises_when_nothing_exists(repo_dir):
    from sdlc.vcs.integration import remove_verification_tree

    # Fresh repo, no verify tree, no ref: both are absent from the start.
    await _call(remove_verification_tree, str(repo_dir), "never-built-key")


# ------------------------------------------------- build_verification_branch convention pin


@pytest.mark.asyncio
async def test_build_verification_branch_pins_the_ref_convention(repo_dir):
    """CONVENTION PIN (not RED). Exercises the existing activity and pins the
    ref name ``sdlc/tidyup-verify/<tidyup_id>`` that remove_verification_tree
    relies on. Expected to PASS at HEAD."""
    base = head_sha(repo_dir)
    _fix_branch(repo_dir, INTEGRATION_BRANCH, base)

    result = await _call(
        build_verification_branch,
        VerifyBranchInput(
            repo_path=str(repo_dir),
            base_sha=base,
            tidyup_id=CHILD_ID,
            branches=[INTEGRATION_BRANCH],
        ),
    )

    assert result.ref == f"sdlc/tidyup-verify/{CHILD_ID}"
    assert _ref_exists(repo_dir, f"refs/heads/{result.ref}")
    assert result.head_sha != base


# ---------------------------------------------------------------- EDGE (023b T011, RED) -- qa-chaos
#
# Edge cases the contract half above does not reach. New names are imported
# inside each test, so each missing name fails on its own test.


@pytest.mark.asyncio
async def test_is_ancestor_treats_the_same_sha_as_its_own_ancestor(repo_dir):
    """R8 edge: git merge-base --is-ancestor counts an equal commit as an
    ancestor of itself. Pinned so T012 maps it the same way."""
    from sdlc.vcs.integration import is_ancestor

    sha = head_sha(repo_dir)
    assert await _call(is_ancestor, str(repo_dir), sha, sha) is True


@pytest.mark.asyncio
async def test_remove_verification_tree_cleans_the_dir_when_the_ref_is_already_gone(
    repo_dir, worktrees_root
):
    """R4 edge: the worktree dir exists but the ref was deleted first. The call
    must still remove the dir and must not raise."""
    from sdlc.vcs.integration import remove_verification_tree

    await _build_verify(repo_dir, CHILD_ID)
    verify_dir = os.path.join(worktrees_root, CHILD_ID, "verify")
    ref = f"refs/heads/sdlc/tidyup-verify/{CHILD_ID}"
    git(repo_dir, "update-ref", "-d", ref)
    assert os.path.isdir(verify_dir), "precondition: verify dir should still exist"

    await _call(remove_verification_tree, str(repo_dir), CHILD_ID)

    assert not os.path.exists(verify_dir)


@pytest.mark.asyncio
async def test_remove_verification_tree_deletes_the_ref_when_the_dir_is_already_gone(
    repo_dir, worktrees_root
):
    """R4 edge, the reverse: the ref exists but the worktree dir was removed by
    hand. The call must still delete the ref and must not raise."""
    import shutil

    from sdlc.vcs.integration import remove_verification_tree

    await _build_verify(repo_dir, CHILD_ID)
    verify_dir = os.path.join(worktrees_root, CHILD_ID, "verify")
    ref = f"refs/heads/sdlc/tidyup-verify/{CHILD_ID}"
    shutil.rmtree(verify_dir)
    assert _ref_exists(repo_dir, ref), "precondition: verify ref should still exist"

    await _call(remove_verification_tree, str(repo_dir), CHILD_ID)

    assert not _ref_exists(repo_dir, ref)


@pytest.mark.asyncio
async def test_is_ancestor_creates_no_refs_and_leaves_head_for_unrelated_shas(repo_dir):
    """Read-only edge, one more shape: two unrelated, unreferenced commits. Refs,
    HEAD and the worktree status must be unchanged afterwards."""
    from sdlc.vcs.integration import is_ancestor

    base = head_sha(repo_dir)
    unrelated = git(repo_dir, "commit-tree", "HEAD^{tree}", "-m", "unrelated root").strip()
    assert unrelated != base
    before = (*_snapshot(repo_dir), git(repo_dir, "rev-parse", "HEAD"))

    await _call(is_ancestor, str(repo_dir), unrelated, base)
    await _call(is_ancestor, str(repo_dir), base, unrelated)

    after = (*_snapshot(repo_dir), git(repo_dir, "rev-parse", "HEAD"))
    assert after == before
