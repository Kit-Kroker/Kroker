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
    # 025 infra stop 1, fix (a): strong arm only — the flash model's
    # backward-compat arm collides with the registry's default judge
    # roles under ADR-6 and was rejected at the workflow boundary, so the
    # smoke matrix could never fully run (see test_benchmark_corpus.py).
    assert len(cells) == 1
    assert cells[0].arm_name == "zai-coding-plan-glm-5.3"


def test_todo_api_rubric_files_exist():
    d = CASE.parent
    assert (d / "rubric-architect.md").exists()
    assert (d / "rubric-clarifier.md").exists()
