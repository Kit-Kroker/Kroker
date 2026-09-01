"""The cat-cafe held-out oracle exists and discriminates (E-34, spec §6)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE = REPO_ROOT / "benchmarks" / "cases" / "cat-cafe-monitoring" / "oracle"


def test_oracle_suite_files_exist():
    for name in ("conftest.py", "test_activity.py", "test_risk.py", "test_monitoring.py"):
        assert (ORACLE / name).is_file(), f"missing oracle/{name}"


import shutil
import subprocess
import sys

import pytest

REF_APP = REPO_ROOT / "tests" / "fixtures" / "cat_cafe_ref" / "app.py"


def _run_oracle(tmp_path, break_risk=False):
    """Copy oracle + reference app into a fake produced worktree and run
    pytest there — the same shape grade_oracle uses, minus git."""
    wt = tmp_path / "wt"
    wt.mkdir()
    shutil.copytree(ORACLE, wt / "oracle")
    app_text = REF_APP.read_text(encoding="utf-8")
    if break_risk:
        # RISK_ENABLED is read at call time, so appending overrides it.
        app_text += "\nRISK_ENABLED = False\n"
    (wt / "app.py").write_text(app_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "oracle", "-q", "-p", "no:cacheprovider"],
        cwd=wt,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.slow
def test_oracle_green_against_reference(tmp_path):
    """Spec §6: the whole suite passes on a sane implementation."""
    proc = _run_oracle(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.slow
def test_oracle_red_when_risk_is_stubbed_out(tmp_path):
    """Spec §6: the oracle discriminates — a reference with risk detection
    disabled must fail, and fail in the risk tests specifically."""
    proc = _run_oracle(tmp_path, break_risk=True)
    assert proc.returncode != 0, "oracle missed the stubbed risk detection"
    assert "test_risk" in proc.stdout
