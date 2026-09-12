"""DS6/DS7: whole suite at head, targeted corroboration at base."""

import os
import pathlib
import subprocess
import sysconfig
import textwrap

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.scoping import scoped_tests
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]
PY = PythonToolchain()


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


async def _provision():
    return _env(), None


def _write(repo: pathlib.Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / ".gitignore").write_text(".sdlc-junit*.xml\n*.count\ncoverage.xml\n", encoding="utf-8")
    _write(r, "tests/test_ok.py", "def test_ok():\n    assert True\n")
    return r


async def _scope(repo, base, provision=_provision):
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    return await scoped_tests(PY, str(repo), wt.path, wt.reason, [], _env(), provision, 300)


@pytest.mark.asyncio
async def test_a_green_head_needs_no_base_run(repo, monkeypatch):
    base = _commit(repo, "base")
    called = []
    monkeypatch.setattr(
        PythonToolchain, "selected_tests_cmd", lambda self, ids, out: called.append(ids) or ""
    )
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.MEASURED and rep.head_failed == 0 and not called


@pytest.mark.asyncio
async def test_a_failure_that_also_fails_at_base_is_pre_existing(repo):
    _write(repo, "tests/test_old.py", "def test_old():\n    assert False\n")
    base = _commit(repo, "base")
    _write(repo, "src_new.py", "x = 1\n")
    _commit(repo, "unrelated change")
    rep = await _scope(repo, base)
    assert rep.introduced == [] and rep.preexisting == ["tests/test_old.py::test_old"]


@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_breaking_a_base_passing_test_is_introduced(repo):
    _write(repo, "tests/test_calc.py", "def test_calc():\n    assert 1 + 1 == 2\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_calc.py", "def test_calc():\n    assert 1 + 1 == 3\n")
    _commit(repo, "breaks it")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_calc.py::test_calc"]


@pytest.mark.asyncio
async def test_a_new_failing_test_is_introduced_with_zero_tolerance(repo):
    base = _commit(repo, "base")
    _write(repo, "tests/test_new.py", "def test_new():\n    assert False\n")
    _write(
        repo,
        "tests/test_ok.py",
        "def test_ok():\n    assert True\n\n\ndef test_added():\n    assert False\n",
    )
    _commit(repo, "new tests")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_new.py::test_new", "tests/test_ok.py::test_added"]


@pytest.mark.asyncio
async def test_a_base_flaky_test_is_pre_existing_flaky(repo):
    """Case (vii): passes on base attempt 1, fails on attempt 2."""
    _write(
        repo,
        "tests/test_flaky.py",
        """
        import pathlib
        C = pathlib.Path(__file__).with_suffix(".count")
        def test_flaky():
            n = int(C.read_text()) if C.exists() else 0
            C.write_text(str(n + 1))
            assert n != 1
        """,
    )
    base = _commit(repo, "base")
    _write(repo, "tests/test_flaky.py", "def test_flaky():\n    assert False\n")
    _commit(repo, "head breaks it for real")
    rep = await _scope(repo, base)
    assert rep.preexisting_flaky == ["tests/test_flaky.py::test_flaky"]
    assert rep.introduced == []


@pytest.mark.asyncio
async def test_an_introduced_failure_behind_many_pre_existing_ones_is_seen(repo):
    """Case (iii): the --maxfail leak. 30 pre-existing failures sort first."""
    body = "\n".join(f"def test_a{i:02d}():\n    assert False\n" for i in range(30))
    _write(repo, "tests/test_aa_debt.py", body)
    _write(repo, "tests/test_zz.py", "def test_zz():\n    assert True\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_zz.py", "def test_zz():\n    assert False\n")
    _commit(repo, "breaks the last test")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_zz.py::test_zz"]
    assert len(rep.preexisting) == 30


@pytest.mark.asyncio
async def test_a_pre_existing_collection_error_is_pre_existing(repo):
    _write(repo, "tests/test_broken.py", "import nonexistent_mod_xyz\n")
    base = _commit(repo, "base")
    _write(repo, "other.py", "x = 1\n")
    _commit(repo, "unrelated")
    rep = await _scope(repo, base)
    assert rep.introduced == [] and rep.preexisting == ["tests/test_broken.py"]


@pytest.mark.asyncio
async def test_an_unsafe_id_is_introduced_without_reaching_a_shell(repo):
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_odd.py",
        """
        import pytest
        @pytest.mark.parametrize("v", [1], ids=["a&b"])
        def test_odd(v):
            assert False
        """,
    )
    _commit(repo, "odd id")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_odd.py::test_odd[a&b]"]


@pytest.mark.asyncio
async def test_unmeasurable_heads_and_bases_fail_closed(repo, monkeypatch):
    base = _commit(repo, "base")
    rep = await scoped_tests(PY, str(repo), None, "locked", [], _env(), _provision, 300)
    assert rep.state is CollectionState.NOT_COLLECTED and "locked" in rep.reason

    async def broken():
        return None, "pip exploded"

    _write(repo, "tests/test_ok.py", "def test_ok():\n    assert False\n")
    _commit(repo, "fail")
    rep = await _scope(repo, base, provision=broken)
    assert rep.state is CollectionState.NOT_COLLECTED and "pip exploded" in rep.reason

    monkeypatch.setattr(
        PythonToolchain,
        "integration_test_cmd",
        lambda self, junit_out, coverage=True: 'python -c "pass"',
    )
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED  # no JUnit report was written


@pytest.mark.asyncio
async def test_a_head_that_collects_no_tests_is_not_collected(repo):
    (repo / "tests" / "test_ok.py").unlink()
    base = _commit(repo, "base")
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED
