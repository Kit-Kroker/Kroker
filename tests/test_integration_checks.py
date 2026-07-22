"""run_integration_checks: the end-to-end coverage seam (E-30, FR-106/FR-108).

Proves the artifact now crosses into the worktree measure_coverage reads."""
import pytest

from sdlc.activities import (
    CoverageInput, IntegrationChecksInput, measure_coverage,
    run_integration_checks,
)

PYPROJECT = "[project]\nname = 'fixture'\nversion = '0.0.0'\n"
MODULE = "def covered():\n    return 1\n\n\ndef uncovered():\n    return 2\n"
TESTFILE = "from mod import covered\n\n\ndef test_covered():\n    assert covered() == 1\n"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_integration_checks_produces_real_coverage(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE, encoding="utf-8")

    checks = await run_integration_checks(IntegrationChecksInput(
        worktree=str(tmp_path), changed_files=["mod.py"]))

    assert checks.toolchain == "python"
    assert checks.qa.tests_passed is True
    assert (tmp_path / "coverage.xml").is_file(), "coverage.xml must be emitted"

    # The gate reader now finds the artifact and measures a diff-scoped %.
    cov = await measure_coverage(CoverageInput(
        worktree=str(tmp_path), changed_files=["mod.py"]))
    assert cov.measured is True
    assert 0.0 < (cov.diff_pct or 0.0) < 100.0  # covered + uncovered => partial


@pytest.mark.asyncio
async def test_integration_checks_degrades_without_adapter(tmp_path):
    # No marker file -> no adapter -> caller falls back to the pre-E-30 path.
    checks = await run_integration_checks(IntegrationChecksInput(
        worktree=str(tmp_path), changed_files=[]))
    assert checks.toolchain is None
    assert checks.lint_clean is True          # not linted => never blocking
    assert checks.qa.tests_passed is False    # signals "no integration run here"
