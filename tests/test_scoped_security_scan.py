"""DS4/DS7: per-match scan over tracked content, two points, fail closed."""

import pathlib
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.qa.activities import (
    ScopedSecurityScanInput,
    scan_paths,
    scoped_security_scan,
)
from sdlc.stages.qa.models import ScopedSecurityReport
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

EVAL = "ev" + "al("  # DS9: never literal in test source
SECRET = "AWS_SECRET_ACCESS_KEY" + ' = "' + "A" * 32 + '"'
GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _commit_all(repo: pathlib.Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    return r


async def _scoped(repo: pathlib.Path, base: str) -> ScopedSecurityReport:
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    assert wt.path, wt.reason
    return await scoped_security_scan(
        ScopedSecurityScanInput(worktree=str(repo), base_worktree=wt.path)
    )


def test_scan_emits_one_finding_per_match_with_its_line(tmp_path):
    (tmp_path / "a.py").write_text(f"x = {EVAL}s)\ny = {EVAL}t)\n", encoding="utf-8")
    rep = scan_paths(str(tmp_path), ["a.py"])
    assert rep.state is CollectionState.MEASURED
    assert [f.line for f in rep.findings] == [f"x = {EVAL}s)", f"y = {EVAL}t)"]
    assert rep.critical == 2


def test_scan_skips_listed_paths_under_skip_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text(f"{EVAL}1)\n", encoding="utf-8")
    assert scan_paths(str(tmp_path), ["node_modules/x.js"]).findings == []


def test_an_unreadable_tracked_file_is_not_collected(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    def boom(self, *a, **k):
        raise OSError("locked")

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rep = scan_paths(str(tmp_path), ["a.py"])
    assert rep.state is CollectionState.NOT_COLLECTED
    assert "a.py" in rep.reason


@pytest.mark.clause("QA-1.6")
@pytest.mark.asyncio
async def test_a_second_identical_finding_in_one_file_is_introduced(repo):
    (repo / "a.py").write_text(f"return {EVAL}s)\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "a.py").write_text(f"return {EVAL}s)\nreturn {EVAL}s)\n", encoding="utf-8")
    _commit_all(repo, "head")
    rep = await _scoped(repo, base)
    assert rep.state is CollectionState.MEASURED
    assert rep.introduced_critical == 1 and rep.preexisting == 1


@pytest.mark.asyncio
async def test_untracked_files_and_venvs_are_never_scanned(repo):
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "loose.py").write_text(f"{EVAL}1)\n", encoding="utf-8")
    (repo / ".sdlc-venv").mkdir()
    (repo / ".sdlc-venv" / "v.py").write_text(f"{EVAL}1)\n", encoding="utf-8")
    rep = await _scoped(repo, base)
    assert rep.state is CollectionState.MEASURED and rep.introduced == []


@pytest.mark.asyncio
async def test_a_planted_fixture_in_a_new_file_still_trips_the_floor(repo):
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "planted.py").write_text(f"{SECRET}\nrun = {EVAL}s)\n", encoding="utf-8")
    _commit_all(repo, "head")
    rep = await _scoped(repo, base)
    assert {f.rule for f in rep.introduced} == {"hardcoded-secret", "dangerous-eval"}
    assert rep.introduced_critical == 2


@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_not_collected(repo):
    rep = await scoped_security_scan(
        ScopedSecurityScanInput(worktree=str(repo), base_worktree=None, base_reason="lock")
    )
    assert rep.state is CollectionState.NOT_COLLECTED and "lock" in rep.reason
    assert rep.introduced == []


def test_a_not_collected_report_cannot_carry_findings():
    with pytest.raises(ValueError):
        ScopedSecurityReport(state=CollectionState.NOT_COLLECTED, reason="x", preexisting=3)
    with pytest.raises(ValueError):
        ScopedSecurityReport(state=CollectionState.NOT_COLLECTED)
