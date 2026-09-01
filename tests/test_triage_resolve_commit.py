"""E-42 D7: the commit is pinned ONCE, by an activity that also detects the
toolchain. All seven signals then read the same tree, so every evidence
citation resolves at the same path@sha."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.triage.activities import (
    TriagePin,
    TriagePinInput,
    triage_resolve_commit,
)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t.t"], d)
    _git(["config", "user.name", "t"], d)
    (d / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (d / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(["add", "."], d)
    _git(["commit", "-qm", "init"], d)
    return d


@pytest.mark.asyncio
async def test_resolves_head_to_a_concrete_sha(repo):
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(repo)))
    assert isinstance(pin, TriagePin)
    assert len(pin.commit_sha) == 40
    assert all(c in "0123456789abcdef" for c in pin.commit_sha)


@pytest.mark.asyncio
async def test_detects_the_toolchain_from_the_marker(repo):
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(repo)))
    assert pin.toolchain == "python"


@pytest.mark.asyncio
async def test_no_marker_is_a_finding_not_an_error(tmp_path):
    d = tmp_path / "bare"
    d.mkdir()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t.t"], d)
    _git(["config", "user.name", "t"], d)
    (d / "README").write_text("hi\n", encoding="utf-8")
    _git(["add", "."], d)
    _git(["commit", "-qm", "init"], d)
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(d)))
    assert pin.toolchain is None


@pytest.mark.asyncio
async def test_unresolvable_commit_raises(repo):
    """D8: there is no honest artifact describing a tree we cannot read."""
    with pytest.raises(RuntimeError, match="does not resolve"):
        await triage_resolve_commit(TriagePinInput(repo_dir=str(repo), commit="deadbeef"))
