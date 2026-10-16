"""run_test_suite is the per-TASK QA gate (feature.py's _dev_task), distinct
from run_integration_checks (the merge-stage gate). Before this fix it ran
the bare test_cmd against the activity worker's ambient environment instead
of a provisioned venv, so any task needing a real third-party dependency
failed with ModuleNotFoundError on every attempt -- indistinguishable from a
real bug in the generated code (see bench-cat-cafe-monitoring-1785186777:
45/45 code-stage attempts failed this way; the same worktrees passed cleanly
once re-run against a real venv)."""

import pytest

from sdlc.stages.qa.activities import QAInput, run_test_suite

PYPROJECT_WITH_DEP = (
    "[build-system]\nrequires = ['setuptools>=68']\n"
    "build-backend = 'setuptools.build_meta'\n\n"
    "[project]\nname = 'fixture-with-dep'\nversion = '0.0.0'\n"
    "dependencies = ['sortedcontainers']\n\n"
    "[tool.setuptools]\npy-modules = ['mod']\n"
)
MODULE_WITH_DEP = (
    "from sortedcontainers import SortedList\n\n\n"
    "def covered():\n    return list(SortedList([3, 1, 2]))\n"
)
TESTFILE_WITH_DEP = (
    "from mod import covered\n\n\ndef test_covered():\n    assert covered() == [1, 2, 3]\n"
)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_test_suite_installs_the_produced_projects_own_deps(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_WITH_DEP, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")

    report = await run_test_suite(QAInput(worktree=str(tmp_path)))

    assert report.tests_passed is True, report.issues
    # The shared cache (venv_cache.py): the venv lives under the run root,
    # keyed by the manifest fingerprint, not inside the worktree.
    cache = tmp_path.parent / ".sdlc-venv-cache"
    assert cache.is_dir() and any(cache.iterdir())


REQUIREMENTS_WITH_DEP = "sortedcontainers\n"
REQUIREMENTS_DEV = "-r requirements.txt\nsortedcontainers\n"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_test_suite_installs_deps_from_requirements_txt(tmp_path):
    """`requirements.txt` is one of PythonToolchain's markers, so such a
    project IS routed through provisioning -- but the two `pip install -e`
    calls both hard-error on a project with no pyproject.toml/setup.py
    ("does not appear to be a Python project"), leaving the venv with
    pytest but none of the produced project's own dependencies. Every task
    then failed on ModuleNotFoundError regardless of code quality (see
    bench-todo-api-greenfield-1785444047: 12/12 code attempts failed this
    way; the same tree passed 41/41 once requirements.txt was installed)."""
    (tmp_path / "requirements.txt").write_text(REQUIREMENTS_WITH_DEP, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")

    report = await run_test_suite(QAInput(worktree=str(tmp_path)))

    assert report.tests_passed is True, report.issues


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_test_suite_installs_deps_from_requirements_dev_txt(tmp_path):
    """Test-only dependencies conventionally live in a dev requirements file;
    a project carrying only that one must provision just the same."""
    (tmp_path / "requirements-dev.txt").write_text(REQUIREMENTS_DEV, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")

    report = await run_test_suite(QAInput(worktree=str(tmp_path)))

    assert report.tests_passed is True, report.issues


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_test_suite_installs_a_uv_workspace_via_uv(tmp_path):
    """A project carrying uv.lock routes its install through uv, not pip:
    a uv workspace is opaque to pip (members resolve as path deps pip cannot
    install, the install dies and the failure is tolerated, leaving the
    venv without the project's deps — the merge-gate suite then fails at
    collection and reads as an introduced failure; retro phase-2 incident
    9). The shared cache keeps uv for the dependency install, reading the
    pyproject as the requirements source (`uv pip install -r
    pyproject.toml`)."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_WITH_DEP, encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")  # marker only; uv pip ignores it
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")

    report = await run_test_suite(QAInput(worktree=str(tmp_path)))

    assert report.tests_passed is True, report.issues
    cache = tmp_path.parent / ".sdlc-venv-cache"
    assert cache.is_dir() and any(cache.iterdir())


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_test_suite_keeps_a_private_venv_for_a_uv_workspace(tmp_path):
    """A true uv workspace ([tool.uv.workspace]) keeps the legacy
    per-worktree venv: uv installs workspace MEMBERS into the venv as
    editables pointing at that one task's tree, so there is no deps-only
    expression of a workspace to share (venv_cache.py module docstring)."""
    workspace_pyproject = (
        "[build-system]\nrequires = ['setuptools>=68']\n"
        "build-backend = 'setuptools.build_meta'\n\n"
        "[tool.uv.workspace]\nmembers = ['pkgs/a']\n\n"
        "[project]\nname = 'fixture-workspace'\nversion = '0.0.0'\n"
        "dependencies = ['sortedcontainers']\n\n"
        "[tool.setuptools]\npy-modules = ['mod']\n"
    )
    (tmp_path / "pyproject.toml").write_text(workspace_pyproject, encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")
    member = tmp_path / "pkgs" / "a"
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text(
        "[project]\nname = 'a'\nversion = '0.0.0'\n", encoding="utf-8"
    )

    report = await run_test_suite(QAInput(worktree=str(tmp_path)))

    assert report.tests_passed is True, report.issues
    assert (tmp_path / ".sdlc-venv").is_dir()


@pytest.mark.asyncio
async def test_run_test_suite_skips_provisioning_without_a_python_adapter(tmp_path):
    # No marker file -> detect() returns None -> falls back to the pre-fix
    # bare-PATH behaviour untouched (e.g. a non-Python contract command).
    (tmp_path / "ok.txt").write_text("nothing to detect here\n", encoding="utf-8")

    report = await run_test_suite(
        QAInput(worktree=str(tmp_path), test_cmd="python -c \"print('no tests ran')\"")
    )

    assert (tmp_path / ".sdlc-venv").is_dir() is False
    assert report.tests_passed is True


@pytest.mark.asyncio
@pytest.mark.slow
async def test_tasks_of_one_run_share_one_cached_venv(tmp_path, monkeypatch):
    """The point of the cache (venv_cache.py): two task worktrees of one
    run with the same manifests provision ONE venv — the second ensure
    creates no venv of its own (the -m venv call count stays at 1)."""
    import sdlc.stages.qa.activities as acts

    real = acts._bounded_shell
    calls: list[str] = []

    async def counting(cmd, cwd, timeout_s, env=None):
        calls.append(cmd)
        return await real(cmd, cwd, timeout_s, env)

    monkeypatch.setattr(acts, "_bounded_shell", counting)

    manifest = PYPROJECT_WITH_DEP
    venvs = []
    for name in ("T01", "T02"):
        task = tmp_path / "run-1" / name
        task.mkdir(parents=True)
        (task / "pyproject.toml").write_text(manifest, encoding="utf-8")
        (task / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
        (task / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")
        env, err = await acts._ensure_python_env(str(task), 600)
        assert err is None and env is not None
        venvs.append(env["VIRTUAL_ENV"])

    assert venvs[0] == venvs[1]
    assert sum("-m venv" in c for c in calls) == 1
    # the second task's own worktree carries no venv
    assert not (tmp_path / "run-1" / "T02" / ".sdlc-venv").exists()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_different_manifests_get_different_cached_venvs(tmp_path):
    import sdlc.stages.qa.activities as acts

    venvs = []
    for name, dep in (("T01", "sortedcontainers"), ("T02", "six")):
        task = tmp_path / "run-1" / name
        task.mkdir(parents=True)
        (task / "pyproject.toml").write_text(
            PYPROJECT_WITH_DEP.replace("sortedcontainers", dep), encoding="utf-8"
        )
        env, err = await acts._ensure_python_env(str(task), 600)
        assert err is None and env is not None
        venvs.append(env["VIRTUAL_ENV"])

    assert venvs[0] != venvs[1]
