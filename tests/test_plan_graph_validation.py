"""The scheduler's ready-loop (feature.py's `run_one` caller) only discovers
an unsatisfiable task graph after execution has already started, surfacing
the opaque `failed:dependency-cycle` outcome deep into a run (see
bench-todo-api-greenfield-1785868165: a plan-revision round dropped tasks
T1-T6 while the surviving T7 still depended on them). `_validate_task_graph`
runs right after the plan gate so a bad graph fails fast and legibly instead."""
from sdlc.models import DevTask
from sdlc.workflows.feature import _validate_task_graph


def _task(id_: str, depends_on: list[str] | None = None) -> DevTask:
    return DevTask(id=id_, title="t", description="d",
                   depends_on=depends_on or [], acceptance_criteria=[])


def test_valid_dag_passes():
    assert _validate_task_graph([_task("T1"), _task("T2", ["T1"])]) is None


def test_dangling_dependency_is_reported():
    err = _validate_task_graph([_task("T7", ["T3", "T4", "T5", "T6"])])
    assert err is not None
    assert "T7" in err and "T3" in err


def test_true_cycle_is_reported():
    err = _validate_task_graph(
        [_task("A", ["B"]), _task("B", ["C"]), _task("C", ["A"])])
    assert err is not None
    assert "A" in err and "B" in err and "C" in err


def test_self_dependency_is_a_cycle():
    err = _validate_task_graph([_task("A", ["A"])])
    assert err is not None
