"""run_integration_checks: the end-to-end coverage seam (E-30, FR-106/FR-108).

Proves the artifact now crosses into the worktree measure_coverage reads."""

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.activities import (
    CoverageInput,
    IntegrationChecksInput,
    measure_coverage,
    run_integration_checks,
)

PYPROJECT = "[project]\nname = 'fixture'\nversion = '0.0.0'\n"
MODULE = "def covered():\n    return 1\n\n\ndef uncovered():\n    return 2\n"
TESTFILE = "from mod import covered\n\n\ndef test_covered():\n    assert covered() == 1\n"

# sortedcontainers is deliberately NOT a dependency of this orchestrator
# (see pyproject.toml) -- proves run_integration_checks installs the
# PRODUCED project's own deps rather than relying on whatever happens to
# already be importable in the activity worker's ambient environment.
PYPROJECT_WITH_DEP = (
    "[build-system]\nrequires = ['setuptools>=68']\n"
    "build-backend = 'setuptools.build_meta'\n\n"
    "[project]\nname = 'fixture-with-dep'\nversion = '0.0.0'\n"
    "dependencies = ['sortedcontainers']\n\n"
    "[tool.setuptools]\npy-modules = ['mod']\n"
)
MODULE_WITH_DEP = (
    "from sortedcontainers import SortedList\n\n\n"
    "def covered():\n    return list(SortedList([3, 1, 2]))\n\n\n"
    "def uncovered():\n    return 2\n"
)
TESTFILE_WITH_DEP = (
    "from mod import covered\n\n\ndef test_covered():\n    assert covered() == [1, 2, 3]\n"
)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_integration_checks_produces_real_coverage(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE, encoding="utf-8")

    checks = await run_integration_checks(
        IntegrationChecksInput(worktree=str(tmp_path), changed_files=["mod.py"])
    )

    assert checks.toolchain == "python"
    assert checks.qa.tests_passed is True
    assert (tmp_path / "coverage.xml").is_file(), "coverage.xml must be emitted"

    # The gate reader now finds the artifact and measures a diff-scoped %.
    cov = await measure_coverage(CoverageInput(worktree=str(tmp_path), changed_files=["mod.py"]))
    assert cov.coverage.state is CollectionState.MEASURED
    assert 0.0 < cov.coverage.value < 100.0  # covered + uncovered => partial


@pytest.mark.asyncio
@pytest.mark.slow
async def test_integration_checks_installs_the_produced_projects_own_deps(tmp_path):
    """Before the isolated per-worktree venv, run_integration_checks ran the
    ToolchainAdapter's bare `pytest ...` string against whatever happened to
    already be on the activity worker's ambient PATH -- which has no
    relationship to the produced project's own dependencies. A project
    needing a real third-party package would fail with ModuleNotFoundError,
    indistinguishable from a genuine bug in the generated code."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_WITH_DEP, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE_WITH_DEP, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE_WITH_DEP, encoding="utf-8")

    checks = await run_integration_checks(
        IntegrationChecksInput(worktree=str(tmp_path), changed_files=["mod.py"])
    )

    assert checks.toolchain == "python"
    assert checks.qa.tests_passed is True, checks.qa.issues
    assert (tmp_path / ".sdlc-venv").is_dir()


@pytest.mark.asyncio
async def test_integration_checks_degrades_without_adapter(tmp_path):
    # No marker file -> no adapter -> caller falls back to the pre-E-30 path.
    checks = await run_integration_checks(
        IntegrationChecksInput(worktree=str(tmp_path), changed_files=[])
    )
    assert checks.toolchain is None
    assert checks.lint_clean is True  # not linted => never blocking
    assert checks.qa.tests_passed is False  # signals "no integration run here"
