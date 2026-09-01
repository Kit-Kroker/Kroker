import pytest
from pydantic import ValidationError

from sdlc.benchmarks.tasks import ERROR_CLASSES, TaskSpec, TaskSuite, load_task_suite


def test_error_classes_are_the_fixed_oracle_outcome_taxonomy():
    assert ERROR_CLASSES == [
        "functional",
        "security",
        "performance",
        "data_integrity",
        "error_handling",
        "api_contract",
    ]


def test_task_spec_accepts_oracle_tests_mode():
    t = TaskSpec(
        id="t01", error_class="functional", oracle_tests=["test_crud.py::test_create_todo"]
    )
    assert t.oracle_tests == ["test_crud.py::test_create_todo"]
    assert t.rubric is None


def test_task_spec_accepts_rubric_mode():
    t = TaskSpec(id="t02", error_class="security", rubric="Rejects with 401.")
    assert t.rubric == "Rejects with 401."
    assert t.oracle_tests == []


def test_task_spec_rejects_unknown_error_class():
    with pytest.raises(ValidationError):
        TaskSpec(id="t01", error_class="not_a_class", oracle_tests=["x::y"])


def test_task_spec_rejects_both_modes_set():
    with pytest.raises(ValidationError):
        TaskSpec(
            id="t01", error_class="functional", oracle_tests=["x::y"], rubric="also has a rubric"
        )


def test_task_spec_rejects_neither_mode_set():
    with pytest.raises(ValidationError):
        TaskSpec(id="t01", error_class="functional")


def test_task_suite_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        TaskSuite(
            case_id="c",
            tasks=[
                TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
                TaskSpec(id="t01", error_class="security", rubric="r"),
            ],
        )


def test_load_task_suite_returns_none_when_file_absent(tmp_path):
    assert load_task_suite("no-such-case", cases_dir=tmp_path) is None


def test_load_task_suite_reads_valid_yaml(tmp_path):
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n'
        "  - id: t02\n"
        "    error_class: security\n"
        '    rubric: "Rejects with 401."\n',
        encoding="utf-8",
    )
    suite = load_task_suite("c1", cases_dir=tmp_path)
    assert suite is not None
    assert suite.case_id == "c1"
    assert [t.id for t in suite.tasks] == ["t01", "t02"]
    assert suite.tasks[0].error_class == "functional"
    assert suite.tasks[1].rubric == "Rejects with 401."


def test_load_task_suite_raises_on_malformed_file(tmp_path):
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n  - id: t01\n    error_class: bogus\n    oracle_tests: [x]\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_task_suite("c1", cases_dir=tmp_path)


from sdlc.benchmarks.tasks import TaskGrade, grade_tasks


def _suite(*tasks: TaskSpec) -> TaskSuite:
    return TaskSuite(case_id="c1", tasks=list(tasks))


def test_grade_tasks_oracle_mapped_all_pass():
    suite = _suite(TaskSpec(id="t01", error_class="functional", oracle_tests=["a.py::test_x"]))
    grades = grade_tasks(suite, {"a.py::test_x": True}, {})
    assert grades == [
        TaskGrade(
            task_id="t01",
            error_class="functional",
            score=1.0,
            judge="oracle",
            detail="1/1 mapped oracle tests passed",
        )
    ]


def test_grade_tasks_oracle_mapped_multi_test_partial():
    suite = _suite(
        TaskSpec(id="t01", error_class="functional", oracle_tests=["a.py::x", "a.py::y"])
    )
    grades = grade_tasks(suite, {"a.py::x": True, "a.py::y": False}, {})
    assert grades[0].score == 0.5
    assert grades[0].judge == "oracle"


def test_grade_tasks_oracle_mapped_none_found_is_error():
    suite = _suite(TaskSpec(id="t01", error_class="functional", oracle_tests=["missing::test"]))
    grades = grade_tasks(suite, {"other::test": True}, {})
    assert grades[0].score is None
    assert grades[0].judge == "error"
    assert "missing::test" in grades[0].detail


def test_grade_tasks_rubric_mapped_uses_judge_score():
    suite = _suite(TaskSpec(id="t02", error_class="security", rubric="r"))
    grades = grade_tasks(suite, {}, {"t02": 0.75})
    assert grades[0].score == 0.75
    assert grades[0].judge == "llm_judge"


def test_grade_tasks_rubric_mapped_missing_score_is_error():
    suite = _suite(TaskSpec(id="t02", error_class="security", rubric="r"))
    grades = grade_tasks(suite, {}, {})
    assert grades[0].score is None
    assert grades[0].judge == "error"


def test_grade_tasks_preserves_task_order():
    suite = _suite(
        TaskSpec(id="t02", error_class="security", rubric="r"),
        TaskSpec(id="t01", error_class="functional", oracle_tests=["a::b"]),
    )
    grades = grade_tasks(suite, {"a::b": True}, {"t02": 1.0})
    assert [g.task_id for g in grades] == ["t02", "t01"]
