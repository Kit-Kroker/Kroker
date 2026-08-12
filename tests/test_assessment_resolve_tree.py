"""D10: tree_hash, not commit_sha -- two commits sharing a tree must hit the
same cache."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import (
    AssessmentTreeInput, assessment_resolve_tree,
)


def _run(args: list[str], cwd) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@t.t"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-qm", "one"], tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_resolves_the_tree_of_a_commit(repo):
    sha = _run(["git", "rev-parse", "HEAD"], repo)
    got = await assessment_resolve_tree(
        AssessmentTreeInput(repo_dir=str(repo), commit_sha=sha))
    assert len(got.tree_hash) == 40
    assert got.tree_hash == _run(["git", "rev-parse", "HEAD^{tree}"], repo)


@pytest.mark.asyncio
async def test_amending_the_message_keeps_the_tree_hash(repo):
    """The whole reason for tree_hash: an amend changes the commit sha and
    nothing about the content."""
    before = await assessment_resolve_tree(AssessmentTreeInput(
        repo_dir=str(repo),
        commit_sha=_run(["git", "rev-parse", "HEAD"], repo)))
    _run(["git", "commit", "-q", "--amend", "-m", "one, reworded"], repo)
    after = await assessment_resolve_tree(AssessmentTreeInput(
        repo_dir=str(repo),
        commit_sha=_run(["git", "rev-parse", "HEAD"], repo)))
    assert after.tree_hash == before.tree_hash


@pytest.mark.asyncio
async def test_changing_content_changes_the_tree_hash(repo):
    before = await assessment_resolve_tree(AssessmentTreeInput(
        repo_dir=str(repo),
        commit_sha=_run(["git", "rev-parse", "HEAD"], repo)))
    (repo / "a.txt").write_text("goodbye\n", encoding="utf-8")
    _run(["git", "commit", "-qam", "two"], repo)
    after = await assessment_resolve_tree(AssessmentTreeInput(
        repo_dir=str(repo),
        commit_sha=_run(["git", "rev-parse", "HEAD"], repo)))
    assert after.tree_hash != before.tree_hash


@pytest.mark.asyncio
async def test_an_unresolvable_commit_raises(repo):
    """Deliberately NOT never-raising, matching triage_resolve_commit: without
    a tree hash nothing can be memoized or reproduced, so this is the absence
    of the tree the artifact claims to describe, not a not_collected
    dimension."""
    with pytest.raises(RuntimeError, match="does not resolve"):
        await assessment_resolve_tree(
            AssessmentTreeInput(repo_dir=str(repo), commit_sha="f" * 40))
