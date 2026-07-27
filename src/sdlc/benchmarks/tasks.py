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
