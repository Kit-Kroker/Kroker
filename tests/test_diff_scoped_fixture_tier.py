"""DS12 pre-flight: the scoped gate on a throwaway repo shaped like this one.

Pre-existing at base: a "rule table" whose detail string trips the eval rule,
a secret-shaped fixture, lint debt, and 26 failing tests that sort before a
passing one. Trigger text is assembled at runtime (DS9).
"""

import pathlib
import subprocess

import pytest

from sdlc.stages.merge.activities import IntegrationChecksInput, run_integration_checks
from sdlc.stages.merge.step import lint_check, security_checks, tests_check
from sdlc.stages.qa.activities import ScopedSecurityScanInput, scoped_security_scan
from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]

EVAL = "ev" + "al("
SECRET = "AWS_SECRET_ACCESS_KEY" + ' = "' + "B" * 32 + '"'
GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8", timeout=30
    ).stdout.strip()


def commit(repo, msg) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def write(repo: pathlib.Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


async def gate(repo: pathlib.Path, base: str):
    """(verdicts by check name, test report, lint report, security report)."""
    diff = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "tier", base))
    ichecks = await run_integration_checks(
        IntegrationChecksInput(
            worktree=str(repo),
            changed_files=diff["files"],
            base_worktree=wt.path,
            base_reason=wt.reason,
            base_sha=base,
            renames=diff["renames"],
        )
    )
    sec = await scoped_security_scan(
        ScopedSecurityScanInput(
            worktree=str(repo),
            base_worktree=wt.path,
            renames=diff["renames"],
            base_reason=wt.reason,
        )
    )
    checks = [tests_check(ichecks.tests), lint_check(ichecks.lint), *security_checks(sec)]
    return {c.name: c.passed for c in checks}, ichecks.tests, ichecks.lint, sec


ALL_PASS = {
    "build_integration_green": True,
    "lint_clean": True,
    "security_scan_collected": True,
    "security_no_critical": True,
}


@pytest.fixture
def repo(tmp_path, monkeypatch) -> tuple[pathlib.Path, str]:
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, ".gitignore", ".sdlc-venv/\n.sdlc-junit*.xml\ncoverage.xml\n*.count\n")
    write(
        r,
        "pyproject.toml",
        "[project]\nname = 'tier'\nversion = '0.0.0'\n\n"
        "[tool.pytest.ini_options]\npythonpath = ['.']\n",
    )
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\n')
    write(r, "rules.py", f'DETAIL = "use of {EVAL}) on untrusted input"\n')
    write(r, "tests/test_fixture_floor.py", f"FIXTURE = {SECRET!r}\n\n\ndef test_f():\n    pass\n")
    write(r, "legacy.py", "import os\n")
    write(r, "calc.py", "def add(a, b):\n    return a + b\n")
    debt = "\n".join(f"def test_a{i:02d}():\n    assert False\n" for i in range(26))
    write(r, "tests/test_aa_debt.py", debt)
    write(
        r,
        "tests/test_zz.py",
        "from calc import add\n\n\ndef test_zz():\n    assert add(1, 1) == 2\n",
    )
    return r, commit(r, "base")


async def test_i_empty_change_passes_with_pre_existing_counts(repo):
    r, base = repo
    verdicts, t, lint, sec = await gate(r, base)
    assert verdicts == ALL_PASS
    assert len(t.preexisting) == 26 and lint.preexisting == 1 and sec.preexisting == 2


async def test_ii_second_eval_in_the_same_file_blocks(repo):
    r, base = repo
    write(r, "rules.py", f'DETAIL = "use of {EVAL}) on untrusted input"\nx = {EVAL}"1")\n')
    commit(r, "second eval")
    verdicts, *_, sec = await gate(r, base)
    assert verdicts["security_no_critical"] is False and sec.introduced_critical == 1


async def test_iii_a_break_behind_26_pre_existing_failures_blocks(repo):
    r, base = repo
    write(r, "calc.py", "def add(a, b):\n    return a - b\n")
    commit(r, "breaks add")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_zz.py::test_zz"]


async def test_iv_rename_only_introduces_nothing(repo):
    r, base = repo
    git(r, "mv", "rules.py", "rule_table.py")
    git(r, "mv", "legacy.py", "old_legacy.py")
    commit(r, "renames")
    verdicts, _, lint, sec = await gate(r, base)
    assert verdicts == ALL_PASS and lint.introduced == [] and sec.introduced == []


async def test_v_deleting_a_file_with_a_finding_resolves_it(repo):
    r, base = repo
    git(r, "rm", "-q", "legacy.py")
    commit(r, "delete legacy")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is True and lint.resolved == 1


async def test_vi_a_new_failing_test_blocks_without_tolerance(repo):
    r, base = repo
    write(r, "tests/test_new.py", "def test_new():\n    assert False\n")
    commit(r, "new failing test")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_new.py::test_new"]


async def test_vii_a_base_flaky_test_is_pre_existing_flaky(repo):
    r, _ = repo
    write(
        r,
        "tests/test_flaky.py",
        "import pathlib\nC = pathlib.Path(__file__).with_suffix('.count')\n\n\n"
        "def test_flaky():\n    n = int(C.read_text()) if C.exists() else 0\n"
        "    C.write_text(str(n + 1))\n    assert n != 1\n",
    )
    base = commit(r, "base with flaky test")
    write(r, "tests/test_flaky.py", "def test_flaky():\n    assert False\n")
    commit(r, "head breaks it")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is True
    assert t.preexisting_flaky == ["tests/test_flaky.py::test_flaky"]


async def test_viii_passing_four_of_four_at_base_then_failing_is_introduced(repo):
    r, base = repo
    write(r, "tests/test_zz.py", "def test_zz():\n    assert False\n")
    commit(r, "breaks test_zz")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_zz.py::test_zz"]


async def test_ix_policy_edit_and_noqa_pass_and_are_reported(repo):
    r, base = repo
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\nignore = []\n')
    write(r, "calc.py", "import sys  # noqa: F401\n\n\ndef add(a, b):\n    return a + b\n")
    commit(r, "relaxes nothing visible, adds a suppression")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is True
    assert lint.policy_paths_changed == ["ruff.toml"] and lint.suppressions_added == 1


async def test_x_a_finding_caused_in_an_untouched_file_blocks(repo):
    r, base = repo
    write(r, "ruff.toml", 'line-length = 5\n\n[lint]\nselect = ["F401", "E501"]\n')
    commit(r, "tightens policy")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is False
    assert {f.path for f in lint.introduced} >= {"calc.py"}
