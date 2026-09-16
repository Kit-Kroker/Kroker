from __future__ import annotations

from sdlc.stages.plan.models import DevTask
from sdlc.stages.plan.validation import validate_task_graph
from sdlc.workflows.feature import _validate_task_graph


def _task(tid: str, deps: list[str] | None = None) -> DevTask:
    return DevTask(
        id=tid, title=tid, description=tid, acceptance_criteria=["ok"], depends_on=deps or []
    )


def test_feature_alias_is_the_moved_function():
    assert _validate_task_graph is validate_task_graph


def test_cycle_and_dangling_reference_reasons_unchanged():
    assert (
        validate_task_graph([_task("A", ["B"]), _task("B", ["A"])])
        == "dependency cycle: A -> B -> A"
    )
    assert (
        validate_task_graph([_task("A", ["Z"])]) == "task 'A' depends on unknown task id(s) ['Z']"
    )
