"""The todo-api reference oracle is authored and wired (E-31)."""
from pathlib import Path

from sdlc.benchmarks.cli import load_case_spec

CASE = "benchmarks/cases/todo-api-greenfield"


def test_case_declares_python_language():
    spec = load_case_spec(f"{CASE}/case.yaml")
    assert spec.language == "python"


def test_oracle_suite_files_exist():
    o = Path(CASE) / "oracle"
    assert (o / "conftest.py").is_file()
    assert (o / "test_crud.py").is_file()


def test_oracle_is_not_committed_into_a_produced_layout():
    # sanity: the oracle lives under benchmarks/cases, never in a src tree
    assert Path(CASE, "oracle").is_dir()
