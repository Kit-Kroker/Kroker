from pathlib import Path

from sdlc.benchmarks.cli import load_case_spec
from sdlc.benchmarks.matrix import expand_matrix

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE = REPO_ROOT / "benchmarks" / "cases" / "todo-api-greenfield" / "case.yaml"


def test_todo_api_case_file_exists_and_loads():
    assert CASE.exists(), f"missing {CASE}"
    spec = load_case_spec(str(CASE))
    assert spec.case_id == "todo-api-greenfield"
    cells = expand_matrix(spec)
    assert len(cells) == 1  # opencode × 1 model


def test_todo_api_rubric_files_exist():
    d = CASE.parent
    assert (d / "rubric-architect.md").exists()
    assert (d / "rubric-clarifier.md").exists()
