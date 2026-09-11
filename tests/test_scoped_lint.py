"""DS5/DS7: lint measured at both points; policy relaxation reported."""

import os
import subprocess
import sysconfig

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.models import ScopedLintReport
from sdlc.stages.merge.scoping import scoped_lint
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]
PY = PythonToolchain()
RUFF_F401 = '[lint]\nselect = ["F401"]\n'


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _commit(repo, msg) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    return env


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "ruff.toml").write_text(RUFF_F401, encoding="utf-8")
    (r / "legacy.py").write_text("import os\n", encoding="utf-8")  # pre-existing F401
    return r


async def _lint(repo, base) -> ScopedLintReport:
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    renames = [
        [p[1], p[2]]
        for p in (
            ln.split("\t")
            for ln in _git(repo, "diff", "-M", "--name-status", f"{base}...HEAD").splitlines()
        )
        if len(p) == 3 and p[0].startswith("R")
    ]
    return await scoped_lint(PY, str(repo), wt.path, wt.reason, base, renames, _env(), 120)


@pytest.mark.asyncio
async def test_pre_existing_debt_is_counted_not_introduced(repo):
    base = _commit(repo, "base")
    (repo / "new.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, "clean change")
    rep = await _lint(repo, base)
    assert rep.state is CollectionState.MEASURED, rep.reason
    assert rep.introduced == [] and rep.preexisting == 1


@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_a_new_finding_is_introduced_with_its_line(repo):
    base = _commit(repo, "base")
    (repo / "new.py").write_text("import sys\n", encoding="utf-8")
    _commit(repo, "adds an unused import")
    rep = await _lint(repo, base)
    assert [(f.rule, f.path, f.line) for f in rep.introduced] == [("F401", "new.py", "import sys")]


@pytest.mark.asyncio
async def test_a_rename_keeps_debt_pre_existing(repo):
    base = _commit(repo, "base")
    _git(repo, "mv", "legacy.py", "moved.py")
    _commit(repo, "rename")
    rep = await _lint(repo, base)
    assert rep.introduced == [] and rep.preexisting == 1


@pytest.mark.asyncio
async def test_a_finding_caused_in_an_untouched_file_is_introduced(repo):
    """Case (x): the cross-file effect DS3 exists for."""
    (repo / "long.py").write_text("x = " + "1 + " * 40 + "1\n", encoding="utf-8")
    base = _commit(repo, "base")
    (repo / "ruff.toml").write_text('[lint]\nselect = ["F401", "E501"]\n', encoding="utf-8")
    _commit(repo, "enable E501")
    rep = await _lint(repo, base)
    assert [f.path for f in rep.introduced] == ["long.py"]
    assert rep.policy_paths_changed == ["ruff.toml"]


@pytest.mark.asyncio
async def test_policy_relaxation_and_suppression_are_reported_not_blocked(repo):
    """Case (ix): DS5's named residual."""
    base = _commit(repo, "base")
    (repo / "new.py").write_text("import sys  # noqa: F401\n", encoding="utf-8")
    _commit(repo, "suppressed")
    rep = await _lint(repo, base)
    assert rep.introduced == [] and rep.suppressions_added == 1


@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_not_collected(repo):
    _commit(repo, "base")
    rep = await scoped_lint(PY, str(repo), None, "locked", "abc", [], _env(), 120)
    assert rep.state is CollectionState.NOT_COLLECTED and "locked" in rep.reason


@pytest.mark.asyncio
async def test_a_lint_tool_failure_is_not_collected(repo, monkeypatch):
    base = _commit(repo, "base")
    monkeypatch.setattr(PythonToolchain, "lint_json_cmd", lambda self: "ruff --no-such-flag")
    rep = await _lint(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED and rep.introduced == []


def test_unmeasured_reports_cannot_carry_counts():
    with pytest.raises(ValueError):
        ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason="x", preexisting=1)
    with pytest.raises(ValueError):
        ScopedLintReport(state=CollectionState.NOT_COLLECTED)
