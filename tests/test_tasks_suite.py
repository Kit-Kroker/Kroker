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


# --- 016 T003 (RED, chaos): load_task_suite reads the private root -------------


def test_load_task_suite_default_root_finds_a_mapping_only_in_the_private_root(
    tmp_path, monkeypatch
):
    """D-3 (tasks.py:83, default branch): no cases_dir argument, the case
    exists only under the private root; the control keeps None."""
    primary = tmp_path / "primary"
    primary.mkdir()
    private = tmp_path / "store" / "cases"
    d = private / "zz-private-only"
    d.mkdir(parents=True)
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))
    suite = load_task_suite("zz-private-only")
    assert suite is not None
    assert suite.case_id == "zz-private-only"
    assert [t.id for t in suite.tasks] == ["t01"]

    monkeypatch.delenv("SDLC_PRIVATE_CASES_ROOT", raising=False)
    assert load_task_suite("zz-private-only") is None


# --- 016 T005 (RED): tier and feature on the mapping (A3) ----------------------


def test_mapping_without_tier_or_feature_loads_as_today(tmp_path):
    """PIN: a mapping whose tasks carry neither key loads exactly as
    today -- suite loads, ids and error_class as written."""
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
    assert [t.id for t in suite.tasks] == ["t01", "t02"]
    assert suite.tasks[0].error_class == "functional"
    assert suite.tasks[1].rubric == "Rejects with 401."


@pytest.mark.parametrize("tier", ["basic", "rule", "cross"])
def test_mapping_tier_accepts_each_tier_value(tmp_path, tier):
    """Names: TaskSpec.tier is Literal['basic', 'rule', 'cross'] | None;
    every task sets one and the parsed values are readable back."""
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n'
        f"    tier: {tier}\n"
        "  - id: t02\n"
        "    error_class: security\n"
        '    rubric: "Rejects with 401."\n'
        f"    tier: {tier}\n",
        encoding="utf-8",
    )
    suite = load_task_suite("c1", cases_dir=tmp_path)
    assert suite is not None
    assert [t.tier for t in suite.tasks] == [tier, tier]


def test_mapping_feature_is_a_free_string(tmp_path):
    """Names: TaskSpec.feature is a free string -- spaces and dashes both
    round-trip through the YAML."""
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n'
        "    feature: seat map\n"
        "  - id: t02\n"
        "    error_class: security\n"
        '    rubric: "Rejects with 401."\n'
        "    feature: refund-flow\n",
        encoding="utf-8",
    )
    suite = load_task_suite("c1", cases_dir=tmp_path)
    assert suite is not None
    assert [t.feature for t in suite.tasks] == ["seat map", "refund-flow"]


def test_mapping_every_task_with_tier_and_feature_loads(tmp_path):
    """A suite where every task sets both keys loads and both values are
    readable on the parsed TaskSpec objects."""
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n'
        "    tier: basic\n"
        "    feature: seat map\n"
        "  - id: t02\n"
        "    error_class: security\n"
        '    rubric: "Rejects with 401."\n'
        "    tier: cross\n"
        "    feature: refund-flow\n",
        encoding="utf-8",
    )
    suite = load_task_suite("c1", cases_dir=tmp_path)
    assert suite is not None
    assert [(t.tier, t.feature) for t in suite.tasks] == [
        ("basic", "seat map"),
        ("cross", "refund-flow"),
    ]


# --- 016 T005 (RED, chaos): the tier/feature adversarial edges -----------------


def _oracle_task(task_id: str, **extra) -> dict:
    return {
        "id": task_id,
        "error_class": "functional",
        "oracle_tests": ["test_crud.py::test_create_todo"],
        **extra,
    }


def _validator_msgs(err: ValidationError) -> str:
    """Only the validators' own messages: str(ValidationError) also echoes the
    whole input, which names every task id and would make the id assertions
    vacuous."""
    return " | ".join(e["msg"] for e in err.errors())


@pytest.mark.parametrize("bad_tier", ["advanced", "Basic", "BASIC", "", "basic ", 1])
def test_mapping_tier_rejects_a_value_outside_basic_rule_cross(bad_tier):
    """Names: tier is Literal['basic', 'rule', 'cross'] | None. Anything
    else -- an unknown word, a different case, an empty or padded string, a
    non-string -- is a loud load-time error, never a silent pass-through."""
    with pytest.raises(ValidationError):
        TaskSuite(case_id="c1", tasks=[_oracle_task("t01", tier=bad_tier)])


def test_tier_all_or_none_rejects_a_partial_suite_naming_the_tasks_without_tier():
    """Names: _tier_all_or_none -- if any task sets tier, every task must;
    the error names each task id that lacks it."""
    with pytest.raises(ValidationError) as exc:
        TaskSuite(
            case_id="c1",
            tasks=[
                _oracle_task("t01", tier="basic"),
                _oracle_task("t02"),
                _oracle_task("t03", tier="cross"),
                _oracle_task("t04"),
            ],
        )
    message = _validator_msgs(exc.value)
    assert "t02" in message
    assert "t04" in message


def test_tier_all_or_none_partial_suite_fails_through_the_loader(tmp_path):
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_create_todo"]\n'
        "    tier: rule\n"
        "  - id: t02\n"
        "    error_class: security\n"
        '    rubric: "Rejects with 401."\n',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as exc:
        load_task_suite("c1", cases_dir=tmp_path)
    assert "t02" in _validator_msgs(exc.value)


def test_tier_all_or_none_does_not_name_tasks_that_do_have_a_tier():
    with pytest.raises(ValidationError) as exc:
        TaskSuite(
            case_id="c1",
            tasks=[_oracle_task("has-tier", tier="basic"), _oracle_task("no-tier")],
        )
    message = _validator_msgs(exc.value)
    assert "no-tier" in message
    assert "has-tier" not in message


def test_mapping_feature_alone_is_not_all_or_none():
    """PIN: the all-or-none rule is tier's only. Some tasks setting
    `feature` while others do not, and no task setting `tier`, loads."""
    suite = TaskSuite(
        case_id="c1",
        tasks=[
            _oracle_task("t01", feature="seat map"),
            _oracle_task("t02"),
            _oracle_task("t03", feature="refund-flow"),
        ],
    )
    assert [t.id for t in suite.tasks] == ["t01", "t02", "t03"]
