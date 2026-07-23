"""The cat-cafe held-out oracle exists and discriminates (E-34, spec §6)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE = (REPO_ROOT / "benchmarks" / "cases" / "cat-cafe-monitoring"
          / "oracle")


def test_oracle_suite_files_exist():
    for name in ("conftest.py", "test_activity.py", "test_risk.py",
                 "test_monitoring.py"):
        assert (ORACLE / name).is_file(), f"missing oracle/{name}"
