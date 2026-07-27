# Task-history + error-class matrices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, cross-run task-by-task pass/fail history matrix and a fixed-taxonomy error-class×arm failure-density matrix to the benchmark reporting tooling, per `docs/superpowers/specs/2026-07-27-task-history-and-error-class-matrices-design.md`.

**Architecture:** A case optionally declares numbered tasks in `tasks.yaml`; `grade_oracle` grades each task (via mapped JUnit tests or an LLM-judge rubric) alongside its existing case-level grade; each task grade becomes a `BenchmarkRecord` with a new `ORACLE_TASK` scope. Two new pure aggregator/renderer modules scan every `bench_run_id` under `runs/benchmarks/` on demand and render the two HTML/JSON matrices. A new `sdlc benchmark history --case <id>` CLI command ties it together.

**Tech Stack:** Python, Pydantic, pytest, PyYAML, defusedxml (already a dependency via `oracle.py`), Temporal (`grade_oracle` activity only — everything else is pure/offline).

## Global Constraints

- No new `BenchmarkRecord` schema fields beyond the new `BenchmarkScope.ORACLE_TASK` value — `task_id` already exists. `error_class` is joined from `tasks.yaml` at aggregation time, never stored on the record.
- Every new/extended function that can fail on bad input (malformed `tasks.yaml`, a judge error, a missing oracle test id) must degrade to `score=None` / an empty list, never raise past `grade_oracle`'s activity boundary and never fabricate a 0 or 1.
- Pure aggregation/rendering (`tasks.py`'s combine step, `task_matrix.py`, `error_matrix.py`) must do zero I/O and zero `temporalio` imports — mirrors `heatmap.py`. All I/O lives in `grade_oracle` (activity) and the new CLI `dispatch_history` function.
- `tasks.yaml` is optional per case: a case with no file must produce zero behavior change to today's oracle grading, heatmap, or reports.
- Match existing code style exactly: pydantic `BaseModel` for typed contracts, dataclasses only where `oracle.py` already uses them (`OracleInput`/`OracleGrade`), ASCII-only in rendered output where the existing code already keeps it ASCII-only (`report.py`'s comment on Windows cp1252).

---

## Task 1: `tasks.py` — task definitions, validation, load

**Files:**
- Create: `src/sdlc/benchmarks/tasks.py`
- Test: `tests/test_tasks_suite.py`

**Interfaces:**
- Produces: `ERROR_CLASSES: list[str]`, `TaskSpec(BaseModel)` (`id: str`, `error_class: str`, `oracle_tests: list[str] = []`, `rubric: str | None = None`), `TaskSuite(BaseModel)` (`case_id: str`, `tasks: list[TaskSpec]`), `TaskGrade(BaseModel)` (`task_id: str`, `error_class: str`, `score: float | None`, `judge: Literal["oracle","llm_judge","error"]`, `detail: str`), `load_task_suite(case_id: str, cases_dir: Path | None = None) -> TaskSuite | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tasks_suite.py
import pytest
from pydantic import ValidationError

from sdlc.benchmarks.tasks import ERROR_CLASSES, TaskSpec, TaskSuite, load_task_suite


def test_error_classes_are_the_fixed_oracle_outcome_taxonomy():
    assert ERROR_CLASSES == [
        "functional", "security", "performance",
        "data_integrity", "error_handling", "api_contract",
    ]


def test_task_spec_accepts_oracle_tests_mode():
    t = TaskSpec(id="t01", error_class="functional",
                oracle_tests=["test_crud.py::test_create_todo"])
    assert t.oracle_tests == ["test_crud.py::test_create_todo"]
    assert t.rubric is None


def test_task_spec_accepts_rubric_mode():
    t = TaskSpec(id="t02", error_class="security", rubric="Rejects with 401.")
    assert t.rubric == "Rejects with 401."
    assert t.oracle_tests == []


def test_task_spec_rejects_unknown_error_class():
    with pytest.raises(ValidationError):
        TaskSpec(id="t01", error_class="not_a_class",
                oracle_tests=["x::y"])


def test_task_spec_rejects_both_modes_set():
    with pytest.raises(ValidationError):
        TaskSpec(id="t01", error_class="functional",
                oracle_tests=["x::y"], rubric="also has a rubric")


def test_task_spec_rejects_neither_mode_set():
    with pytest.raises(ValidationError):
        TaskSpec(id="t01", error_class="functional")


def test_task_suite_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        TaskSuite(case_id="c", tasks=[
            TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
            TaskSpec(id="t01", error_class="security", rubric="r"),
        ])


def test_load_task_suite_returns_none_when_file_absent(tmp_path):
    assert load_task_suite("no-such-case", cases_dir=tmp_path) is None


def test_load_task_suite_reads_valid_yaml(tmp_path):
    d = tmp_path / "c1"
    d.mkdir()
    (d / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        "    oracle_tests: [\"test_crud.py::test_create_todo\"]\n"
        "  - id: t02\n"
        "    error_class: security\n"
        "    rubric: \"Rejects with 401.\"\n",
        encoding="utf-8")
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
        "tasks:\n  - id: t01\n    error_class: bogus\n    oracle_tests: [x]\n",
        encoding="utf-8")
    with pytest.raises(ValidationError):
        load_task_suite("c1", cases_dir=tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tasks_suite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.tasks'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/benchmarks/tasks.py
"""Per-case numbered task definitions (task-history + error-class matrices).

A case optionally declares benchmarks/cases/<case_id>/tasks.yaml: a list of
numbered tasks, each graded either against specific oracle JUnit test-ids or
by the cross-family LLM judge against a rubric. Loading is pure (one YAML
read, no other I/O); a case with no file simply has no task-level records —
existing case-level oracle grading is unaffected.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ERROR_CLASSES: list[str] = [
    "functional", "security", "performance",
    "data_integrity", "error_handling", "api_contract",
]


class TaskSpec(BaseModel):
    id: str
    error_class: str
    oracle_tests: list[str] = Field(default_factory=list)
    rubric: str | None = None

    @field_validator("error_class")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in ERROR_CLASSES:
            raise ValueError(
                f"unknown error_class {v!r}; must be one of {ERROR_CLASSES}")
        return v

    @model_validator(mode="after")
    def _exactly_one_grading_mode(self) -> "TaskSpec":
        has_tests = bool(self.oracle_tests)
        has_rubric = bool(self.rubric)
        if has_tests == has_rubric:
            raise ValueError(
                f"task {self.id!r} must set exactly one of oracle_tests or "
                f"rubric (has_tests={has_tests}, has_rubric={has_rubric})")
        return self


class TaskSuite(BaseModel):
    case_id: str
    tasks: list[TaskSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> "TaskSuite":
        ids = [t.id for t in self.tasks]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate task ids: {dupes}")
        return self


class TaskGrade(BaseModel):
    task_id: str
    error_class: str
    score: float | None
    judge: Literal["oracle", "llm_judge", "error"]
    detail: str


def _cases_dir() -> Path:
    return Path(os.environ.get(
        "SDLC_CASES_ROOT",
        str(Path(__file__).resolve().parents[3] / "benchmarks" / "cases")))


def load_task_suite(case_id: str, cases_dir: Path | None = None) -> TaskSuite | None:
    """Load benchmarks/cases/<case_id>/tasks.yaml, or None if absent.

    Raises pydantic.ValidationError on a malformed file -- tasks.yaml is a
    human-authored artifact, so a load-time error is loud on purpose rather
    than silently degrading."""
    base = cases_dir if cases_dir is not None else _cases_dir()
    p = Path(base) / case_id / "tasks.yaml"
    if not p.is_file():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return TaskSuite(case_id=case_id, tasks=data.get("tasks", []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tasks_suite.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/tasks.py tests/test_tasks_suite.py
git commit -m "feat(benchmarks): TaskSpec/TaskSuite + tasks.yaml loader"
```

---

## Task 2: `grade_tasks` — pure combine step

**Files:**
- Modify: `src/sdlc/benchmarks/tasks.py`
- Test: `tests/test_tasks_suite.py` (append)

**Interfaces:**
- Consumes: `TaskSpec`, `TaskSuite`, `TaskGrade` from Task 1.
- Produces: `grade_tasks(suite: TaskSuite, testcase_results: dict[str, bool], judge_scores: dict[str, float]) -> list[TaskGrade]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tasks_suite.py
from sdlc.benchmarks.tasks import TaskGrade, grade_tasks


def _suite(*tasks: TaskSpec) -> TaskSuite:
    return TaskSuite(case_id="c1", tasks=list(tasks))


def test_grade_tasks_oracle_mapped_all_pass():
    suite = _suite(TaskSpec(id="t01", error_class="functional",
                           oracle_tests=["a.py::test_x"]))
    grades = grade_tasks(suite, {"a.py::test_x": True}, {})
    assert grades == [TaskGrade(task_id="t01", error_class="functional",
                               score=1.0, judge="oracle",
                               detail="1/1 mapped oracle tests passed")]


def test_grade_tasks_oracle_mapped_multi_test_partial():
    suite = _suite(TaskSpec(id="t01", error_class="functional",
                           oracle_tests=["a.py::x", "a.py::y"]))
    grades = grade_tasks(suite, {"a.py::x": True, "a.py::y": False}, {})
    assert grades[0].score == 0.5
    assert grades[0].judge == "oracle"


def test_grade_tasks_oracle_mapped_none_found_is_error():
    suite = _suite(TaskSpec(id="t01", error_class="functional",
                           oracle_tests=["missing::test"]))
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
        TaskSpec(id="t01", error_class="functional", oracle_tests=["a::b"]))
    grades = grade_tasks(suite, {"a::b": True}, {"t02": 1.0})
    assert [g.task_id for g in grades] == ["t02", "t01"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tasks_suite.py -v -k grade_tasks`
Expected: FAIL — `ImportError: cannot import name 'grade_tasks'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/benchmarks/tasks.py`:

```python
def grade_tasks(suite: TaskSuite, testcase_results: dict[str, bool],
                judge_scores: dict[str, float]) -> list[TaskGrade]:
    """Combine already-computed JUnit + judge results into per-task grades.

    Pure -- no I/O. testcase_results is {"file::name": passed} from
    grade_testcases_from_junit (oracle.py); judge_scores is {task_id: score}
    for whichever rubric tasks the caller already judged."""
    out: list[TaskGrade] = []
    for t in suite.tasks:
        if t.oracle_tests:
            found = [testcase_results[nid] for nid in t.oracle_tests
                    if nid in testcase_results]
            if not found:
                out.append(TaskGrade(
                    task_id=t.id, error_class=t.error_class, score=None,
                    judge="error",
                    detail=f"none of {t.oracle_tests} found in oracle report"))
                continue
            passed_n = sum(1 for ok in found if ok)
            out.append(TaskGrade(
                task_id=t.id, error_class=t.error_class,
                score=passed_n / len(found), judge="oracle",
                detail=f"{passed_n}/{len(found)} mapped oracle tests passed"))
        else:
            score = judge_scores.get(t.id)
            if score is None:
                out.append(TaskGrade(
                    task_id=t.id, error_class=t.error_class, score=None,
                    judge="error", detail="judge did not return a score"))
            else:
                out.append(TaskGrade(
                    task_id=t.id, error_class=t.error_class, score=score,
                    judge="llm_judge", detail="rubric-graded"))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tasks_suite.py -v`
Expected: PASS (18 tests total)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/tasks.py tests/test_tasks_suite.py
git commit -m "feat(benchmarks): grade_tasks pure combine step"
```

---

## Task 3: `grade_testcases_from_junit` — per-testcase JUnit parsing

**Files:**
- Modify: `src/sdlc/benchmarks/oracle.py`
- Test: `tests/test_oracle.py` (append)

**Interfaces:**
- Produces: `grade_testcases_from_junit(xml_text: str) -> dict[str, bool]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_oracle.py
from sdlc.benchmarks.oracle import grade_testcases_from_junit

JUNIT_WITH_FILE_ATTR = (
    '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="0">'
    '<testcase classname="test_crud" name="test_create_todo" '
    'file="test_crud.py"/>'
    '<testcase classname="test_crud" name="test_delete_todo" '
    'file="test_crud.py"><failure/></testcase>'
    '<testcase classname="test_crud" name="test_skipped" '
    'file="test_crud.py"><skipped/></testcase>'
    '</testsuite></testsuites>'
)

JUNIT_NO_FILE_ATTR = (
    '<testsuite tests="1" failures="0" errors="0" skipped="0">'
    '<testcase classname="test_crud" name="test_x"/></testsuite>'
)

JUNIT_NO_CLASSNAME = (
    '<testsuite tests="1" failures="0" errors="0" skipped="0">'
    '<testcase name="test_x"/></testsuite>'
)


def test_grade_testcases_keys_by_file_and_name_when_file_attr_present():
    results = grade_testcases_from_junit(JUNIT_WITH_FILE_ATTR)
    assert results == {
        "test_crud.py::test_create_todo": True,
        "test_crud.py::test_delete_todo": False,
    }
    # the skipped test is dropped entirely -- neither pass nor fail
    assert "test_crud.py::test_skipped" not in results


def test_grade_testcases_falls_back_to_classname_when_no_file_attr():
    results = grade_testcases_from_junit(JUNIT_NO_FILE_ATTR)
    assert results == {"test_crud::test_x": True}


def test_grade_testcases_falls_back_to_name_when_neither_present():
    results = grade_testcases_from_junit(JUNIT_NO_CLASSNAME)
    assert results == {"test_x": True}


def test_grade_testcases_error_child_is_failure():
    xml = ('<testsuite tests="1" failures="0" errors="1" skipped="0">'
          '<testcase name="a"><error/></testcase></testsuite>')
    assert grade_testcases_from_junit(xml) == {"a": False}


def test_grade_testcases_empty_or_malformed_returns_empty_dict():
    assert grade_testcases_from_junit("") == {}
    assert grade_testcases_from_junit("<not-xml") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_oracle.py -v -k grade_testcases`
Expected: FAIL — `ImportError: cannot import name 'grade_testcases_from_junit'`

- [ ] **Step 3: Write the implementation**

Insert into `src/sdlc/benchmarks/oracle.py` immediately after the existing `grade_from_junit` function (after line 51, before `def held_out_ok`):

```python
def grade_testcases_from_junit(xml_text: str) -> dict[str, bool]:
    """Parse individual <testcase> elements into {"node_id": passed}.

    The key prefers pytest's own file::name node-id shape (using the
    `file` attribute pytest's junit-xml already emits per testcase), so a
    case author's tasks.yaml oracle_tests entries can read exactly like a
    pytest node-id (e.g. "test_crud.py::test_create_todo"). Falls back to
    classname::name, then bare name, for hand-written JUnit fixtures that
    omit `file`. A <skipped> testcase is dropped entirely -- neither pass
    nor fail, mirroring grade_from_junit's denominator discipline.
    Malformed/empty XML yields {} rather than raising."""
    if not xml_text.strip():
        return {}
    try:
        root = DET.fromstring(xml_text)
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    except Exception:
        return {}
    out: dict[str, bool] = {}
    for s in suites:
        for tc in s.iter("testcase"):
            if tc.find("skipped") is not None:
                continue
            name = tc.get("name", "")
            file_attr = tc.get("file")
            classname = tc.get("classname", "")
            if file_attr:
                key = f"{file_attr}::{name}"
            elif classname:
                key = f"{classname}::{name}"
            else:
                key = name
            failed = tc.find("failure") is not None or tc.find("error") is not None
            out[key] = not failed
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_oracle.py -v`
Expected: PASS (all existing + 5 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/oracle.py tests/test_oracle.py
git commit -m "feat(benchmarks): per-testcase JUnit parsing (grade_testcases_from_junit)"
```

---

## Task 4: `BenchmarkScope.ORACLE_TASK`

**Files:**
- Modify: `src/sdlc/benchmarks/models.py:36-39`
- Test: `tests/test_benchmark_models.py` (append)

**Interfaces:**
- Produces: `BenchmarkScope.ORACLE_TASK` (value `"oracle_task"`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_benchmark_models.py
def test_oracle_task_scope_exists():
    assert BenchmarkScope.ORACLE_TASK.value == "oracle_task"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_models.py -v -k oracle_task_scope`
Expected: FAIL — `AttributeError: ORACLE_TASK`

- [ ] **Step 3: Write the implementation**

In `src/sdlc/benchmarks/models.py`, change:

```python
class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"
    ORACLE = "oracle"
```

to:

```python
class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"
    ORACLE = "oracle"
    ORACLE_TASK = "oracle_task"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/models.py tests/test_benchmark_models.py
git commit -m "feat(benchmarks): BenchmarkScope.ORACLE_TASK"
```

---

## Task 5: Wire task grading into `grade_oracle`

**Files:**
- Modify: `src/sdlc/benchmarks/oracle.py`
- Test: `tests/test_grade_oracle.py` (append)

**Interfaces:**
- Consumes: `TaskSuite`, `TaskGrade`, `grade_tasks`, `load_task_suite` (Tasks 1–2); `grade_testcases_from_junit` (Task 3); `JudgeInput`, `_judge_sync` (existing `judge.py`).
- Produces: `OracleInput.author_model: str = ""`, `OracleInput.judge_model: str | None = None`; `OracleGrade.task_grades: list[TaskGrade] = []`. `grade_oracle` activity now populates `task_grades` whenever the case has a `tasks.yaml`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_grade_oracle.py`. These extend the existing fixture-repo test helpers already in that file (`_git`, `FIXTURE_APP`, `ORACLE_CONFTEST`, `ORACLE_TEST` — reused as-is).

```python
from sdlc.benchmarks import judge as judge_mod


@pytest.mark.asyncio
async def test_grade_oracle_populates_oracle_mapped_task_grades(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    (cases / "case" / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        "    oracle_tests: [\"test_crud.py::test_ok\"]\n"
        "  - id: t02\n"
        "    error_class: functional\n"
        "    oracle_tests: [\"test_crud.py::test_fail\"]\n",
        encoding="utf-8")

    import os
    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id,
            language="python", base_branch="main"))
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    by_id = {g.task_id: g for g in grade.task_grades}
    assert by_id["t01"].score == 1.0 and by_id["t01"].judge == "oracle"
    assert by_id["t02"].score == 0.0 and by_id["t02"].judge == "oracle"


@pytest.mark.asyncio
async def test_grade_oracle_populates_rubric_mapped_task_grades(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    (cases / "case" / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: security\n"
        "    rubric: \"Uses a secure default.\"\n",
        encoding="utf-8")

    judge_mod._set_judge_fn(lambda inp: '{"score": 0.75, "components": {}}')

    import os
    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id,
            language="python", base_branch="main",
            author_model="anthropic:claude-sonnet-4-6",
            judge_model="openai/gpt-5.2"))
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old
        judge_mod._set_judge_fn(None)

    assert len(grade.task_grades) == 1
    assert grade.task_grades[0].score == 0.75
    assert grade.task_grades[0].judge == "llm_judge"


@pytest.mark.asyncio
async def test_grade_oracle_no_tasks_yaml_gives_empty_task_grades(tmp_path):
    # test_grade_oracle_missing_branch_returns_none's fixture has no
    # tasks.yaml at all -- task_grades must default to [], never raise.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "f").write_text("x")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text(
        "def test_x():\n    assert True\n")

    import os
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo),
            run_id="never/ran#h#m", language="python"))
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.task_grades == []


@pytest.mark.asyncio
async def test_grade_oracle_malformed_tasks_yaml_never_fails_case_grade(tmp_path):
    # A malformed tasks.yaml raises inside load_task_suite; grade_oracle's
    # try/except must swallow it and still return the case-level grade.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    # malformed: unknown error_class
    (cases / "case" / "tasks.yaml").write_text(
        "tasks:\n  - id: t01\n    error_class: bogus\n"
        "    oracle_tests: [\"x::y\"]\n", encoding="utf-8")

    import os
    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id,
            language="python", base_branch="main"))
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    # case-level grade unaffected; task grading just contributed nothing
    assert grade.total == 2
    assert grade.task_grades == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_grade_oracle.py -v -k task_grade`
Expected: FAIL — `OracleGrade` has no `task_grades` attribute / `OracleInput` has no `author_model` keyword.

- [ ] **Step 3: Write the implementation**

In `src/sdlc/benchmarks/oracle.py`:

3a. Change the dataclass import (line 14) from:

```python
from dataclasses import dataclass
```

to:

```python
from dataclasses import dataclass, field
```

3b. Add imports near the top (after the existing `from ..toolchain.adapters import ...` line):

```python
from .judge import JudgeInput, _judge_sync
from .tasks import TaskGrade, grade_tasks, load_task_suite
```

3c. Extend `OracleInput` (currently lines 70–77):

```python
@dataclass
class OracleInput:
    case_id: str
    repo_url: str
    run_id: str            # child workflow id -> sdlc/<run_id>/integration
    language: str          # manifest-declared (CaseSpec.language)
    base_branch: str = "main"
    test_timeout_s: int = 600
    author_model: str = ""          # cell's dev model; only rubric tasks need it
    judge_model: str | None = None  # spec.judge_model; only rubric tasks need it
```

3d. Extend `OracleGrade` (currently lines 80–89):

```python
@dataclass
class OracleGrade:
    score: float | None
    passed: int
    total: int
    language_manifest: str
    language_detected: str | None
    language_match: bool
    held_out_ok: bool
    detail: str
    task_grades: list[TaskGrade] = field(default_factory=list)
```

3e. Extend the `_grade` helper (currently lines 101–105) to accept and pass through `task_grades`:

```python
def _grade(score, passed, total, lang, detected, held, detail,
          task_grades: list[TaskGrade] | None = None) -> OracleGrade:
    return OracleGrade(
        score=score, passed=passed, total=total, language_manifest=lang,
        language_detected=detected, language_match=language_match(lang, detected),
        held_out_ok=held, detail=detail, task_grades=task_grades or [])
```

(Every existing early-return call site — `_grade(None, 0, 0, lang, None, True, "no oracle dir for case")` etc. — keeps working unchanged: the new parameter defaults to `None` → `[]`.)

3f. In the `grade_oracle` activity body, replace the line:

```python
        score, passed, total, detail = grade_from_junit(xml_text)
        return _grade(score, passed, total, lang, detected, held, detail)
```

with:

```python
        score, passed, total, detail = grade_from_junit(xml_text)
        task_grades: list[TaskGrade] = []
        try:
            suite = load_task_suite(inp.case_id)
            if suite is not None:
                testcase_results = grade_testcases_from_junit(xml_text)
                judge_scores: dict[str, float] = {}
                needs_diff = any(t.rubric for t in suite.tasks)
                full_diff = ""
                if needs_diff:
                    diff_res = _git(
                        ["diff", f"{inp.base_branch}...HEAD"], wt)
                    full_diff = diff_res.stdout
                for t in suite.tasks:
                    if t.rubric:
                        qs = _judge_sync(JudgeInput(
                            artifact_json=full_diff, rubric=t.rubric,
                            author_model=inp.author_model,
                            judge_model=inp.judge_model))
                        if qs.score is not None:
                            judge_scores[t.id] = qs.score
                task_grades = grade_tasks(suite, testcase_results, judge_scores)
        except Exception:
            # a broken tasks.yaml or judge call never fails the case-level
            # oracle grade -- it just contributes no task grades.
            task_grades = []
        return _grade(score, passed, total, lang, detected, held, detail,
                     task_grades=task_grades)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_grade_oracle.py tests/test_oracle.py -v`
Expected: PASS (all existing tests still pass + 4 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/oracle.py tests/test_grade_oracle.py
git commit -m "feat(benchmarks): grade_oracle grades per-task oracle_task/rubric tasks"
```

---

## Task 6: Record task grades in `BenchmarkWorkflow`

**Files:**
- Modify: `src/sdlc/benchmarks/workflow.py`
- Test: `tests/test_benchmark_workflow.py` (append)

**Interfaces:**
- Consumes: `OracleGrade.task_grades` (Task 5), `BenchmarkScope.ORACLE_TASK` (Task 4).
- Produces: `_oracle_task_records(base_cell: BenchmarkCell, grade: OracleGrade, bench_run_id: str, run_id: str, started: datetime, ended: datetime) -> list[BenchmarkRecord]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark_workflow.py`:

```python
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.tasks import TaskGrade
from sdlc.benchmarks.workflow import _oracle_task_records


def _grade_with_tasks(*task_grades):
    return OracleGrade(
        score=0.5, passed=1, total=2, language_manifest="python",
        language_detected="python", language_match=True,
        held_out_ok=True, detail="1/2", task_grades=list(task_grades))


def test_oracle_task_records_one_per_task_grade():
    t0 = datetime(2026, 7, 23, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=timezone.utc)
    grade = _grade_with_tasks(
        TaskGrade(task_id="t01", error_class="functional", score=1.0,
                  judge="oracle", detail="1/1"),
        TaskGrade(task_id="t02", error_class="security", score=0.0,
                  judge="llm_judge", detail="rubric-graded"))
    recs = _oracle_task_records(_cell(), grade, "b1",
                                "b1/todo-api#opencode#m", t0, t1)
    assert len(recs) == 2
    assert {r.task_id for r in recs} == {"t01", "t02"}
    r01 = next(r for r in recs if r.task_id == "t01")
    assert r01.scope is BenchmarkScope.ORACLE_TASK
    assert r01.stage == "oracle" and r01.role == "oracle"
    assert r01.quality.score == 1.0 and r01.quality.judge == "oracle"
    assert r01.outcome is BenchmarkOutcome.PASS
    r02 = next(r for r in recs if r.task_id == "t02")
    assert r02.outcome is BenchmarkOutcome.FAIL


def test_oracle_task_records_none_score_is_fail():
    from sdlc.benchmarks.models import BenchmarkOutcome as BO
    t0 = datetime(2026, 7, 23, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=timezone.utc)
    grade = _grade_with_tasks(
        TaskGrade(task_id="t01", error_class="functional", score=None,
                  judge="error", detail="oops"))
    recs = _oracle_task_records(_cell(), grade, "b1", "run1", t0, t1)
    assert recs[0].outcome is BO.FAIL
    assert recs[0].quality.score is None


def test_oracle_task_records_empty_when_no_task_grades():
    t0 = datetime(2026, 7, 23, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=timezone.utc)
    recs = _oracle_task_records(_cell(), _grade(), "b1", "run1", t0, t1)
    assert recs == []
```

Add `BenchmarkOutcome` to the existing import line at the top of the file
(currently `from sdlc.benchmarks.models import BenchmarkCell, BenchmarkScope, CaseSpec`):

```python
from sdlc.benchmarks.models import (
    BenchmarkCell, BenchmarkOutcome, BenchmarkScope, CaseSpec)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_workflow.py -v -k oracle_task_records`
Expected: FAIL — `ImportError: cannot import name '_oracle_task_records'`

- [ ] **Step 3: Write the implementation**

In `src/sdlc/benchmarks/workflow.py`, insert immediately after the existing `_oracle_record` function (after its closing line, currently line 122):

```python
def _oracle_task_records(base_cell: BenchmarkCell, grade: OracleGrade,
                         bench_run_id: str, run_id: str,
                         started: datetime, ended: datetime
                         ) -> list[BenchmarkRecord]:
    """One record per TaskGrade in grade.task_grades. error_class is not
    stored on the record -- task_matrix.py / error_matrix.py join it from
    tasks.yaml by (case_id, task_id) at aggregation time, so the write path
    only needs the scope + the already-existing task_id field."""
    out: list[BenchmarkRecord] = []
    for t in grade.task_grades:
        outcome = (BenchmarkOutcome.PASS if (t.score or 0.0) >= 1.0
                  else BenchmarkOutcome.FAIL)
        out.append(BenchmarkRecord(
            run_id=run_id, bench_run_id=bench_run_id, case_id=base_cell.case_id,
            scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id=t.task_id,
            role="oracle", harness=base_cell.harness, model=base_cell.arm_name,
            quality=QualityScore(score=t.score, judge=t.judge),
            speed=SpeedBag(wall_clock_s=(ended - started).total_seconds(),
                          started_at=started, ended_at=ended),
            outcome=outcome))
    return out
```

Then wire it into `BenchmarkWorkflow.run` — replace the current oracle block
(currently lines 159–172):

```python
            if spec.language:
                started = workflow.now()
                grade = await workflow.execute_activity(
                    grade_oracle,
                    OracleInput(case_id=spec.case_id,
                                repo_url=spec.repo_url or "",
                                run_id=child_id, language=spec.language,
                                base_branch=idea.base_branch),
                    **ORACLE_ACT)
                await workflow.execute_activity(
                    record_benchmark,
                    _oracle_record(cell, grade, bench_run_id, child_id,
                                   started, workflow.now()),
                    **RECORD_ACT)
```

with:

```python
            if spec.language:
                started = workflow.now()
                grade = await workflow.execute_activity(
                    grade_oracle,
                    OracleInput(case_id=spec.case_id,
                                repo_url=spec.repo_url or "",
                                run_id=child_id, language=spec.language,
                                base_branch=idea.base_branch,
                                author_model=cell.role_models.get("dev", ""),
                                judge_model=spec.judge_model),
                    **ORACLE_ACT)
                ended = workflow.now()
                await workflow.execute_activity(
                    record_benchmark,
                    _oracle_record(cell, grade, bench_run_id, child_id,
                                   started, ended),
                    **RECORD_ACT)
                for rec in _oracle_task_records(cell, grade, bench_run_id,
                                                child_id, started, ended):
                    await workflow.execute_activity(
                        record_benchmark, rec, **RECORD_ACT)
```

(This also fixes the pre-existing double `workflow.now()` call — `started`/`ended` are now each captured exactly once and shared by both the case-level and per-task records.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_workflow.py -v`
Expected: PASS (all existing tests still pass + 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/workflow.py tests/test_benchmark_workflow.py
git commit -m "feat(benchmarks): record ORACLE_TASK grades from BenchmarkWorkflow"
```

---

## Task 7: `task_matrix.py` — build + render

**Files:**
- Create: `src/sdlc/benchmarks/task_matrix.py`
- Test: `tests/test_task_matrix.py`
- Test: `tests/test_task_matrix_render.py`

**Interfaces:**
- Consumes: `BenchmarkRecord`, `BenchmarkScope` (`models.py`); `TaskSuite` (`tasks.py`).
- Produces: `TaskMatrixColumn(BaseModel)` (`bench_run_id`, `cell_id`, `harness`, `model`, `started_at`, `mean_score`), `TaskMatrix(BaseModel)` (`case_id`, `task_ids`, `columns`, `scores: dict[str, dict[str, float|None]]`), `build_task_matrix(case_id, records, suite) -> TaskMatrix`, `render_task_matrix_html(tm) -> str`, `render_task_matrix_json(tm) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_task_matrix.py
from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.task_matrix import build_task_matrix
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.models import HarnessKind


def _suite():
    return TaskSuite(case_id="c1", tasks=[
        TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
        TaskSpec(id="t02", error_class="security", rubric="r"),
    ])


def _rec(*, run="b1", cell_model="m1", task_id, score, started):
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{cell_model}", bench_run_id=run,
        case_id="c1", scope=BenchmarkScope.ORACLE_TASK, stage="oracle",
        task_id=task_id, role="oracle", harness=HarnessKind.OPENCODE,
        model=cell_model, quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=started,
                      ended_at=started + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0
        else BenchmarkOutcome.FAIL)


def test_build_task_matrix_one_column_per_run_cell():
    t0 = datetime(2026, 7, 20, 10)
    t1 = datetime(2026, 7, 21, 10)
    recs = [
        _rec(run="b1", task_id="t01", score=1.0, started=t0),
        _rec(run="b1", task_id="t02", score=0.0, started=t0),
        _rec(run="b2", task_id="t01", score=0.5, started=t1),
    ]
    tm = build_task_matrix("c1", recs, _suite())
    assert tm.task_ids == ["t01", "t02"]
    assert len(tm.columns) == 2
    assert [c.bench_run_id for c in tm.columns] == ["b1", "b2"]  # chronological


def test_build_task_matrix_missing_task_is_none_not_zero():
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec(run="b1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    key = f"{tm.columns[0].bench_run_id}#{tm.columns[0].cell_id}"
    assert tm.scores["t01"][key] == 1.0
    assert tm.scores["t02"][key] is None


def test_build_task_matrix_mean_score_excludes_none():
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec(run="b1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    # only t01 has a score in this column; t02 is missing -> mean == t01's
    assert tm.columns[0].mean_score == 1.0


def test_build_task_matrix_filters_other_case_and_scope():
    t0 = datetime(2026, 7, 20, 10)
    other_case = _rec(run="b1", task_id="t01", score=1.0, started=t0)
    other_case.case_id = "other"
    stage_rec = BenchmarkRecord(
        run_id="b1/x", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.OPENCODE, model="m1",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0,
                      ended_at=t0 + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    tm = build_task_matrix("c1", [other_case, stage_rec], _suite())
    assert tm.columns == []


def test_build_task_matrix_empty_records_gives_empty_columns():
    tm = build_task_matrix("c1", [], _suite())
    assert tm.task_ids == ["t01", "t02"]
    assert tm.columns == []
```

```python
# tests/test_task_matrix_render.py
import json

from sdlc.benchmarks.task_matrix import (
    TaskMatrix, TaskMatrixColumn, render_task_matrix_html, render_task_matrix_json)
from datetime import datetime


def _tm():
    col = TaskMatrixColumn(
        bench_run_id="b1", cell_id="c1#opencode#m1", harness="opencode",
        model="m1", started_at=datetime(2026, 7, 20, 10), mean_score=0.5)
    return TaskMatrix(
        case_id="c1", task_ids=["t01", "t02"], columns=[col],
        scores={"t01": {"b1#c1#opencode#m1": 1.0},
               "t02": {"b1#c1#opencode#m1": None}})


def test_json_round_trips():
    data = json.loads(render_task_matrix_json(_tm()))
    assert data["case_id"] == "c1"
    assert data["task_ids"] == ["t01", "t02"]


def test_html_is_wellformed_and_shows_task_rows():
    html = render_task_matrix_html(_tm())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "t01" in html and "t02" in html
    assert "m1" in html


def test_html_colors_pass_fail_and_missing_distinctly():
    html = render_task_matrix_html(_tm())
    # t01 scored 1.0 -> green; t02 is None -> grey/empty marker
    assert "#3aa757" in html
    assert "#e5e5e5" in html


def test_html_handles_no_columns():
    tm = TaskMatrix(case_id="c1", task_ids=["t01"], columns=[], scores={"t01": {}})
    html = render_task_matrix_html(tm)
    assert "No task records" in html


def test_html_escapes_case_id():
    tm = TaskMatrix(case_id="<x>", task_ids=[], columns=[], scores={})
    html = render_task_matrix_html(tm)
    assert "<x>" not in html.split("<body>")[1] or "&lt;x&gt;" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_task_matrix.py tests/test_task_matrix_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.task_matrix'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/benchmarks/task_matrix.py
"""Task-history matrix (task x run-over-time). Scans every bench_run_id's
ORACLE_TASK records for one case (report.py::scan_case_records feeds this)
and renders a persistent, cross-run pass/fail grid. Pure aggregation +
rendering -- no I/O, mirrors heatmap.py.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord, BenchmarkScope
from .tasks import TaskSuite


class TaskMatrixColumn(BaseModel):
    bench_run_id: str
    cell_id: str
    harness: str
    model: str
    started_at: datetime
    mean_score: float | None


class TaskMatrix(BaseModel):
    case_id: str
    task_ids: list[str] = Field(default_factory=list)
    columns: list[TaskMatrixColumn] = Field(default_factory=list)
    scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)


def _column_key(col: TaskMatrixColumn) -> str:
    return f"{col.bench_run_id}#{col.cell_id}"


def build_task_matrix(case_id: str, records: list[BenchmarkRecord],
                      suite: TaskSuite) -> TaskMatrix:
    task_ids = [t.id for t in suite.tasks]
    recs = [r for r in records
           if r.scope is BenchmarkScope.ORACLE_TASK and r.case_id == case_id]

    by_col: dict[tuple[str, str], list[BenchmarkRecord]] = defaultdict(list)
    for r in recs:
        cell_id = f"{case_id}#{r.harness.value if r.harness else ''}#{r.model}"
        by_col[(r.bench_run_id, cell_id)].append(r)

    columns: list[TaskMatrixColumn] = []
    scores: dict[str, dict[str, float | None]] = {tid: {} for tid in task_ids}
    for (bench_run_id, cell_id), col_recs in by_col.items():
        started = min(r.speed.started_at for r in col_recs)
        by_task = {r.task_id: r.quality.score for r in col_recs if r.task_id}
        present = [s for s in by_task.values() if s is not None]
        mean_score = sum(present) / len(present) if present else None
        harness = next((r.harness.value for r in col_recs if r.harness), "")
        model = col_recs[0].model
        col = TaskMatrixColumn(bench_run_id=bench_run_id, cell_id=cell_id,
                               harness=harness, model=model,
                               started_at=started, mean_score=mean_score)
        columns.append(col)
        key = _column_key(col)
        for tid in task_ids:
            scores[tid][key] = by_task.get(tid)

    columns.sort(key=lambda c: c.started_at)
    return TaskMatrix(case_id=case_id, task_ids=task_ids, columns=columns,
                      scores=scores)


def render_task_matrix_json(tm: TaskMatrix) -> str:
    return tm.model_dump_json(indent=2)


def _cell_style(score: float | None) -> tuple[str, str]:
    """(inline CSS, cell label) for one task-matrix cell."""
    if score is None:
        return "background:#e5e5e5", ""
    if score >= 1.0:
        return "background:#3aa757;color:#fff", "1"
    if score <= 0.0:
        return "background:#c0392b;color:#fff", "0"
    return "background:#e0a13a;color:#111", f"{score:.2f}"


def render_task_matrix_html(tm: TaskMatrix) -> str:
    if not tm.columns:
        body = "<p>No task records.</p>"
    else:
        head_cells = []
        sum_cells = []
        for col in tm.columns:
            key = _column_key(col)
            ts = col.started_at.strftime("%m-%d %H:%M")
            score_label = (f"{col.mean_score:.2f}" if col.mean_score is not None
                          else "n/a")
            head_cells.append(
                f"<th>{escape(ts)}<br>score {score_label}<br>"
                f"{escape(col.model)}</th>")
            total = sum(v for v in
                       (tm.scores[tid].get(key) for tid in tm.task_ids)
                       if v is not None)
            sum_cells.append(f"<th>{total:.2f}</th>")
        rows = []
        for tid in tm.task_ids:
            tds = [f"<th>{escape(tid)}</th>"]
            for col in tm.columns:
                key = _column_key(col)
                score = tm.scores[tid].get(key)
                style, label = _cell_style(score)
                tds.append(f'<td style="{style}">{label}</td>')
            rows.append("<tr>" + "".join(tds) + "</tr>")
        body = (
            "<table><tr><th>task</th>" + "".join(head_cells) + "</tr>"
            "<tr><th>sum</th>" + "".join(sum_cells) + "</tr>"
            + "".join(rows) + "</table>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Task history - {escape(tm.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}}
</style></head><body>
<h1>Task history - {escape(tm.case_id)}</h1>
{body}
</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_task_matrix.py tests/test_task_matrix_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/task_matrix.py tests/test_task_matrix.py tests/test_task_matrix_render.py
git commit -m "feat(benchmarks): task-history matrix builder + HTML/JSON renderer"
```

---

## Task 8: `error_matrix.py` — build + render

**Files:**
- Create: `src/sdlc/benchmarks/error_matrix.py`
- Test: `tests/test_error_matrix.py`
- Test: `tests/test_error_matrix_render.py`

**Interfaces:**
- Consumes: `BenchmarkRecord`, `BenchmarkScope` (`models.py`); `TaskSuite`, `ERROR_CLASSES` (`tasks.py`).
- Produces: `ErrorMatrixCell(BaseModel)` (`error_class`, `arm_key`, `avg_failure_mass`, `n_runs`), `ErrorMatrix(BaseModel)` (`case_id`, `error_classes`, `arms`, `cells`, `max_value`), `build_error_matrix(case_id, records, suite) -> ErrorMatrix`, `render_error_matrix_html(em) -> str`, `render_error_matrix_json(em) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_error_matrix.py
from datetime import datetime, timedelta

from sdlc.benchmarks.error_matrix import build_error_matrix
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.models import HarnessKind


def _suite():
    return TaskSuite(case_id="c1", tasks=[
        TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
        TaskSpec(id="t02", error_class="security", rubric="r"),
    ])


def _rec(*, run, model, task_id, score):
    t = datetime(2026, 7, 20, 10)
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{model}", bench_run_id=run, case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id=task_id,
        role="oracle", harness=HarnessKind.OPENCODE, model=model,
        quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                      ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0
        else BenchmarkOutcome.FAIL)


def test_build_error_matrix_averages_failure_mass_over_runs_for_same_arm():
    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),  # 1.0 failure mass
        _rec(run="b2", model="m1", task_id="t01", score=1.0),  # 0.0 failure mass
    ]
    em = build_error_matrix("c1", recs, _suite())
    cell = next(c for c in em.cells if c.arm_key == "opencode#m1"
               and c.error_class == "functional")
    assert cell.avg_failure_mass == 0.5   # (1.0 + 0.0) / 2 runs
    assert cell.n_runs == 2


def test_build_error_matrix_keeps_arms_separate():
    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),
        _rec(run="b1", model="m2", task_id="t01", score=1.0),
    ]
    em = build_error_matrix("c1", recs, _suite())
    assert set(em.arms) == {"opencode#m1", "opencode#m2"}
    m1 = next(c for c in em.cells if c.arm_key == "opencode#m1")
    m2 = next(c for c in em.cells if c.arm_key == "opencode#m2")
    assert m1.avg_failure_mass == 1.0
    assert m2.avg_failure_mass == 0.0


def test_build_error_matrix_none_score_excluded():
    recs = [_rec(run="b1", model="m1", task_id="t01", score=None)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.cells == []


def test_build_error_matrix_unknown_task_id_ignored():
    recs = [_rec(run="b1", model="m1", task_id="not-in-suite", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.cells == []


def test_build_error_matrix_error_classes_in_canonical_order():
    recs = [
        _rec(run="b1", model="m1", task_id="t02", score=0.0),
        _rec(run="b1", model="m1", task_id="t01", score=0.0),
    ]
    em = build_error_matrix("c1", recs, _suite())
    # functional precedes security in ERROR_CLASSES
    assert em.error_classes == ["functional", "security"]


def test_build_error_matrix_empty_records():
    em = build_error_matrix("c1", [], _suite())
    assert em.cells == [] and em.arms == [] and em.max_value == 0.0
```

```python
# tests/test_error_matrix_render.py
import json

from sdlc.benchmarks.error_matrix import (
    ErrorMatrix, ErrorMatrixCell, render_error_matrix_html, render_error_matrix_json)


def _em():
    return ErrorMatrix(
        case_id="c1", error_classes=["functional", "security"],
        arms=["opencode#m1"],
        cells=[ErrorMatrixCell(error_class="functional", arm_key="opencode#m1",
                              avg_failure_mass=0.5, n_runs=2)],
        max_value=0.5)


def test_json_round_trips():
    data = json.loads(render_error_matrix_json(_em()))
    assert data["case_id"] == "c1"
    assert data["cells"][0]["avg_failure_mass"] == 0.5


def test_html_is_wellformed_and_shows_classes_and_arms():
    html = render_error_matrix_html(_em())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "functional" in html and "security" in html
    assert "opencode#m1" in html
    assert "0.50" in html


def test_html_handles_empty():
    html = render_error_matrix_html(ErrorMatrix(case_id="c1"))
    assert "No task records" in html


def test_html_escapes_arm_key():
    em = ErrorMatrix(case_id="c1", error_classes=["functional"], arms=["<x>"],
                    cells=[ErrorMatrixCell(error_class="functional", arm_key="<x>",
                                          avg_failure_mass=1.0, n_runs=1)],
                    max_value=1.0)
    html = render_error_matrix_html(em)
    assert "<x>" not in html.split("<body>")[1]
    assert "&lt;x&gt;" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_error_matrix.py tests/test_error_matrix_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.error_matrix'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/benchmarks/error_matrix.py
"""Error-class x arm failure-density matrix, scoped to one case.
Scans every bench_run_id's ORACLE_TASK records for that case
(report.py::scan_case_records feeds this) and renders which fixed error
class an arm (harness#model) fails most, averaged per run. Pure
aggregation + rendering -- no I/O, mirrors heatmap.py / task_matrix.py.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord, BenchmarkScope
from .tasks import ERROR_CLASSES, TaskSuite


class ErrorMatrixCell(BaseModel):
    error_class: str
    arm_key: str
    avg_failure_mass: float
    n_runs: int


class ErrorMatrix(BaseModel):
    case_id: str
    error_classes: list[str] = Field(default_factory=list)
    arms: list[str] = Field(default_factory=list)
    cells: list[ErrorMatrixCell] = Field(default_factory=list)
    max_value: float = 0.0


def build_error_matrix(case_id: str, records: list[BenchmarkRecord],
                       suite: TaskSuite) -> ErrorMatrix:
    class_by_task = {t.id: t.error_class for t in suite.tasks}
    recs = [r for r in records
           if r.scope is BenchmarkScope.ORACLE_TASK and r.case_id == case_id
           and r.task_id in class_by_task and r.quality.score is not None]

    # failure mass per (bench_run_id, arm_key, error_class) run-instance
    mass: dict[tuple[str, str, str], float] = defaultdict(float)
    runs_by_arm: dict[str, set[str]] = defaultdict(set)
    for r in recs:
        arm_key = f"{r.harness.value if r.harness else ''}#{r.model}"
        cls = class_by_task[r.task_id]
        mass[(r.bench_run_id, arm_key, cls)] += (1.0 - r.quality.score)
        runs_by_arm[arm_key].add(r.bench_run_id)

    totals: dict[tuple[str, str], float] = defaultdict(float)
    for (bench_run_id, arm_key, cls), m in mass.items():
        totals[(arm_key, cls)] += m

    cells: list[ErrorMatrixCell] = []
    for (arm_key, cls), total in totals.items():
        n_runs = max(len(runs_by_arm[arm_key]), 1)
        cells.append(ErrorMatrixCell(
            error_class=cls, arm_key=arm_key,
            avg_failure_mass=total / n_runs, n_runs=n_runs))

    arms = sorted({c.arm_key for c in cells})
    present = {c.error_class for c in cells}
    classes = [c for c in ERROR_CLASSES if c in present]
    max_value = max((c.avg_failure_mass for c in cells), default=0.0)
    return ErrorMatrix(case_id=case_id, error_classes=classes, arms=arms,
                       cells=cells, max_value=max_value)


def render_error_matrix_json(em: ErrorMatrix) -> str:
    return em.model_dump_json(indent=2)


def _cell_color(value: float, max_value: float) -> str:
    ratio = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    g_b = round(255 - 229 * ratio)   # white (low) -> dark red (high)
    return f"rgb(255,{g_b},{g_b})"


def render_error_matrix_html(em: ErrorMatrix) -> str:
    if not em.cells:
        body = "<p>No task records.</p>"
    else:
        by = {(c.error_class, c.arm_key): c for c in em.cells}
        head = "".join(f"<th>{escape(a)}</th>" for a in em.arms)
        rows = []
        for cls in em.error_classes:
            tds = [f"<th>{escape(cls)}</th>"]
            for arm in em.arms:
                c = by.get((cls, arm))
                if c is None:
                    tds.append('<td class="empty"></td>')
                    continue
                tip = (f"{cls} / {arm}: {c.avg_failure_mass:.2f} avg failure "
                      f"mass/run over {c.n_runs} runs")
                tds.append(
                    f'<td title="{escape(tip)}" '
                    f'style="background:{_cell_color(c.avg_failure_mass, em.max_value)}">'
                    f"{c.avg_failure_mass:.2f}</td>")
            rows.append("<tr>" + "".join(tds) + "</tr>")
        body = (f"<table><tr><th>error class \\ arm</th>{head}</tr>"
               + "".join(rows) + "</table>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Error-class matrix - {escape(em.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Error-class matrix - {escape(em.case_id)}</h1>
<p>Cell = average per-task failure mass (sum of 1-score) per run, for that
error class on that harness#model arm. Whiter is cleaner; redder is more
failure-prone.</p>
{body}
</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_error_matrix.py tests/test_error_matrix_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/error_matrix.py tests/test_error_matrix.py tests/test_error_matrix_render.py
git commit -m "feat(benchmarks): error-class matrix builder + HTML/JSON renderer"
```

---

## Task 9: CLI — `sdlc benchmark history --case <id>`

**Files:**
- Modify: `src/sdlc/benchmarks/report.py`
- Modify: `src/sdlc/benchmarks/cli.py`
- Test: `tests/test_benchmark_report.py` (append)
- Test: `tests/test_benchmark_cli.py` (append)

**Interfaces:**
- Consumes: `_read_all`, `_root` (existing `report.py`/`recorder.py`); `build_task_matrix`/`render_task_matrix_html`/`render_task_matrix_json` (Task 7); `build_error_matrix`/`render_error_matrix_html`/`render_error_matrix_json` (Task 8); `load_task_suite` (Task 1).
- Produces: `report.py::scan_case_records(case_id, root=None) -> list[BenchmarkRecord]`; `cli.py::dispatch_history(case_id, root=None) -> tuple[str, str]`; CLI subcommand `benchmark history --case <id>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark_report.py` (check its existing imports first — reuse whatever fixture-building helpers it already has for `BenchmarkRecord`; if none exist, use the inline style below, matching `test_benchmark_heatmap.py`'s `_rec` pattern):

```python
def test_scan_case_records_reads_across_multiple_bench_run_ids(tmp_path):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.report import scan_case_records
    from sdlc.models import HarnessKind
    t = datetime(2026, 7, 20, 10)

    def rec(run, task_id):
        return BenchmarkRecord(
            run_id=f"{run}/c1#opencode#m1", bench_run_id=run, case_id="c1",
            scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id=task_id,
            role="oracle", harness=HarnessKind.OPENCODE, model="m1",
            quality=QualityScore(score=1.0, judge="oracle"),
            speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                          ended_at=t + timedelta(seconds=1)),
            outcome=BenchmarkOutcome.PASS)

    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec("b1", "t01"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(rec("b2", "t01"))

    records = scan_case_records("c1", root=str(tmp_path))
    assert {r.bench_run_id for r in records} == {"b1", "b2"}


def test_scan_case_records_filters_other_cases(tmp_path):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.report import scan_case_records
    from sdlc.models import HarnessKind
    t = datetime(2026, 7, 20, 10)
    rec = BenchmarkRecord(
        run_id="b1/other#opencode#m1", bench_run_id="b1", case_id="other-case",
        scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id="t01",
        role="oracle", harness=HarnessKind.OPENCODE, model="m1",
        quality=QualityScore(score=1.0, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                      ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)
    assert scan_case_records("c1", root=str(tmp_path)) == []


def test_scan_case_records_empty_root_returns_empty(tmp_path):
    from sdlc.benchmarks.report import scan_case_records
    assert scan_case_records("c1", root=str(tmp_path / "does-not-exist")) == []
```

Append to `tests/test_benchmark_cli.py`:

```python
def test_parser_accepts_history_subcommand():
    from sdlc.benchmarks.cli import build_parser
    p = build_parser()
    args = p.parse_args(["benchmark", "history", "--case", "c1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "history"
    assert args.case == "c1"


def test_dispatch_history_raises_without_tasks_yaml(tmp_path):
    from sdlc.benchmarks.cli import dispatch_history
    import pytest as _pytest
    with _pytest.raises(ValueError, match="no tasks.yaml"):
        dispatch_history("no-such-case", root=str(tmp_path))


def test_dispatch_history_writes_all_four_files(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.cli import dispatch_history
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.models import HarnessKind

    cases_dir = tmp_path / "cases"
    (cases_dir / "c1").mkdir(parents=True)
    (cases_dir / "c1" / "tasks.yaml").write_text(
        "tasks:\n  - id: t01\n    error_class: functional\n"
        "    oracle_tests: [\"x::y\"]\n", encoding="utf-8")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases_dir))

    runs_root = tmp_path / "runs"
    t = datetime(2026, 7, 20, 10)
    rec = BenchmarkRecord(
        run_id="b1/c1#opencode#m1", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id="t01",
        role="oracle", harness=HarnessKind.OPENCODE, model="m1",
        quality=QualityScore(score=1.0, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                      ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    RecordStore(root=str(runs_root), bench_run_id="b1").append(rec)

    tm_path, em_path = dispatch_history("c1", root=str(runs_root))
    out_dir = runs_root / "_history" / "c1"
    assert (out_dir / "task-matrix.html").exists()
    assert (out_dir / "task-matrix.json").exists()
    assert (out_dir / "error-matrix.html").exists()
    assert (out_dir / "error-matrix.json").exists()
    assert tm_path == str(out_dir / "task-matrix.html")
    assert em_path == str(out_dir / "error-matrix.html")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_report.py tests/test_benchmark_cli.py -v -k "scan_case_records or history"`
Expected: FAIL — `ImportError: cannot import name 'scan_case_records'` / `'dispatch_history'` / unrecognized `history` subcommand.

- [ ] **Step 3: Write the implementation**

In `src/sdlc/benchmarks/report.py`, add after the existing `_read_all` function:

```python
def scan_case_records(case_id: str, root: str | None = None) -> list[BenchmarkRecord]:
    """Read every record for case_id across EVERY bench_run_id directory
    under root (default: recorder._root()). Powers the cross-run task/error
    matrices -- scan-on-demand, no separate history store to keep in sync."""
    base = Path(root if root is not None else _root())
    if not base.is_dir():
        return []
    out: list[BenchmarkRecord] = []
    for bench_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        out.extend(r for r in _read_all(bench_dir.name, root)
                   if r.case_id == case_id)
    return out
```

In `src/sdlc/benchmarks/cli.py`:

3a. Add the `history` subparser inside `build_parser()`, right after the existing `rep` (`report`) subparser block:

```python
    hist = bsub.add_parser("history")
    hist.add_argument("--case", required=True)
```

3b. Add `dispatch_history` after `dispatch_report`:

```python
def dispatch_history(case_id: str, root: str | None = None) -> tuple[str, str]:
    from .error_matrix import (
        build_error_matrix, render_error_matrix_html, render_error_matrix_json)
    from .report import scan_case_records
    from .task_matrix import (
        build_task_matrix, render_task_matrix_html, render_task_matrix_json)
    from .tasks import load_task_suite

    suite = load_task_suite(case_id)
    if suite is None:
        raise ValueError(f"no tasks.yaml for case {case_id!r}; nothing to build")
    records = scan_case_records(case_id, root)
    tm = build_task_matrix(case_id, records, suite)
    em = build_error_matrix(case_id, records, suite)

    out_dir = Path(root if root is not None else _root()) / "_history" / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "task-matrix.html").write_text(
        render_task_matrix_html(tm), encoding="utf-8")
    (out_dir / "task-matrix.json").write_text(
        render_task_matrix_json(tm), encoding="utf-8")
    (out_dir / "error-matrix.html").write_text(
        render_error_matrix_html(em), encoding="utf-8")
    (out_dir / "error-matrix.json").write_text(
        render_error_matrix_json(em), encoding="utf-8")
    return str(out_dir / "task-matrix.html"), str(out_dir / "error-matrix.html")
```

3c. Wire the dispatch into `main_async`, adding an `elif` branch after the existing `report` branch:

```python
    elif args.bench_cmd == "history":
        tm_path, em_path = dispatch_history(args.case)
        print(tm_path)
        print(em_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_report.py tests/test_benchmark_cli.py -v`
Expected: PASS (all existing tests still pass + 6 new ones)

- [ ] **Step 5: Run the full benchmarks test suite**

Run: `pytest tests/ -k benchmark -v` and `pytest tests/test_oracle.py tests/test_grade_oracle.py tests/test_tasks_suite.py tests/test_task_matrix.py tests/test_task_matrix_render.py tests/test_error_matrix.py tests/test_error_matrix_render.py -v`
Expected: PASS — every benchmarks-related test in the repo, old and new, green.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/report.py src/sdlc/benchmarks/cli.py tests/test_benchmark_report.py tests/test_benchmark_cli.py
git commit -m "feat(benchmarks): sdlc benchmark history CLI (task + error matrices)"
```

---

## Post-implementation check

- [ ] Run the complete test suite once more: `pytest tests/ -v` — confirm no regressions anywhere else in the repo (e.g. `worker.py`'s activity registration list doesn't need a change, since `grade_oracle` is already registered and no new activity was added).
- [ ] Re-read `docs/superpowers/specs/2026-07-27-task-history-and-error-class-matrices-design.md` §7 (error handling table) and confirm each row has a corresponding test from Tasks 1–9.
