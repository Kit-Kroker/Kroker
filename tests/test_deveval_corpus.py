"""Every committed DevEval case is structurally sound and reviewed (E-79)."""
from pathlib import Path

import pytest

from sdlc.benchmarks.cli import load_case_spec
from sdlc.benchmarks.tasks import ERROR_CLASSES, load_task_suite

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
DEVEVAL = sorted(CASES.glob("deveval-*"))


def test_at_least_one_case_was_imported():
    assert DEVEVAL, "no deveval-* cases committed"


@pytest.mark.parametrize("case_dir", DEVEVAL, ids=lambda p: p.name)
def test_case_is_complete_and_reviewed(case_dir):
    spec = load_case_spec(str(case_dir / "case.yaml"))
    assert spec.case_id == case_dir.name
    assert spec.language == "python"
    for rel in ("oracle", "reference", "reference_artifacts",
                "reference_env", "ATTRIBUTION.md", "tasks.yaml"):
        assert (case_dir / rel).exists(), f"{case_dir.name}: missing {rel}"

    tasks_text = (case_dir / "tasks.yaml").read_text(encoding="utf-8")
    assert "DRAFT -- REVIEW BEFORE USE" not in tasks_text, (
        f"{case_dir.name}: tasks.yaml is still an unreviewed draft")

    suite = load_task_suite(case_dir.name, cases_dir=CASES)
    assert suite is not None and suite.tasks
    for t in suite.tasks:
        assert t.error_class in ERROR_CLASSES


@pytest.mark.parametrize("case_dir", DEVEVAL, ids=lambda p: p.name)
def test_committed_cases_are_not_quarantined(case_dir):
    """A network_required case cannot run at all (expand_matrix refuses it),
    so it has no business in the committed corpus until E-21."""
    spec = load_case_spec(str(case_dir / "case.yaml"))
    assert spec.network_required is False


@pytest.mark.parametrize("case_dir", DEVEVAL, ids=lambda p: p.name)
def test_oracle_suites_do_not_leak_into_reference(case_dir):
    """reference/ is the gold implementation; a copy of the oracle inside it
    would hand E-81's Oracle Test its own answer key.

    Asserted by relative path, not by filename pattern: hone ships a genuine
    source helper at hone/utils/test_utils.py, which matches pytest's
    discovery glob but is implementation, not oracle.
    """
    oracle = case_dir / "oracle"
    ref = case_dir / "reference"
    leaked = [p.relative_to(oracle).as_posix()
              for p in oracle.rglob("*.py")
              if (ref / p.relative_to(oracle)).exists()]
    assert not leaked, f"{case_dir.name}: oracle files present in reference/: {leaked}"


@pytest.mark.parametrize("case_dir", DEVEVAL, ids=lambda p: p.name)
def test_oracle_carries_the_path_shim(case_dir):
    """grade_oracle runs bare `pytest oracle` from the repo root, which does
    not put cwd on sys.path (toolchain/adapters.py). Without the shim these
    suites error at collection regardless of the produced code."""
    shim = case_dir / "oracle" / "conftest.py"
    assert shim.is_file()
    assert "sys.path.insert" in shim.read_text(encoding="utf-8")


@pytest.mark.parametrize("case_dir", DEVEVAL, ids=lambda p: p.name)
def test_every_task_node_id_exists_in_the_oracle(case_dir):
    """A reviewed tasks.yaml that names a test the oracle does not contain
    grades as `judge="error"` forever (tasks.py grade_tasks), silently
    dropping that requirement from functional completeness."""
    suite = load_task_suite(case_dir.name, cases_dir=CASES)
    oracle = case_dir / "oracle"
    for t in suite.tasks:
        for nid in t.oracle_tests:
            rel, _, name = nid.partition("::")
            path = oracle / rel
            assert path.is_file(), f"{case_dir.name}/{t.id}: no such file {rel}"
            assert f"def {name}(" in path.read_text(encoding="utf-8"), (
                f"{case_dir.name}/{t.id}: {name} not defined in {rel}")
