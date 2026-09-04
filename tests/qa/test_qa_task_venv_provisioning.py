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
    assert (tmp_path / ".sdlc-venv").is_dir()


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
async def test_run_test_suite_skips_provisioning_without_a_python_adapter(tmp_path):
    # No marker file -> detect() returns None -> falls back to the pre-fix
    # bare-PATH behaviour untouched (e.g. a non-Python contract command).
    (tmp_path / "ok.txt").write_text("nothing to detect here\n", encoding="utf-8")

    report = await run_test_suite(
        QAInput(worktree=str(tmp_path), test_cmd="python -c \"print('no tests ran')\"")
    )

    assert (tmp_path / ".sdlc-venv").is_dir() is False
    assert report.tests_passed is True
