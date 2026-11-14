"""Pure validators of the FR-205 library (`sdlc.validators.pure`).

The plan-graph tests are ported verbatim from tests/plan/ (they pin the
migration from stages/plan/validation.py); ids_unique and the purity pin
are new. The scheduler's ready-loop (feature.py's `run_one` caller) only
discovers an unsatisfiable task graph after execution has already started,
surfacing the opaque `failed:dependency-cycle` outcome deep into a run (see
bench-todo-api-greenfield-1785868165: a plan-revision round dropped tasks
T1-T6 while the surviving T7 still depended on them). `validate_task_graph`
runs right after the plan gate so a bad graph fails fast and legibly instead.
"""

from __future__ import annotations

import json
import subprocess
import sys

from sdlc.core.models import PlanConfig
from sdlc.stages.plan.models import DevTask
from sdlc.validators import (
    covers_all,
    dag_acyclic,
    deps_resolve,
    ids_unique,
    task_size,
    validate_task_graph,
)


def _task(
    id_: str,
    depends_on: list[str] | None = None,
    *,
    covers: list[str] | None = None,
    files_hint: list[str] | None = None,
    criteria: list[str] | None = None,
) -> DevTask:
    return DevTask(
        id=id_,
        title="t",
        description="d",
        depends_on=depends_on or [],
        acceptance_criteria=criteria or [],
        files_hint=files_hint or [],
        covers=covers or [],
    )


def test_valid_dag_passes():
    assert validate_task_graph([_task("T1"), _task("T2", ["T1"])]) is None


def test_dangling_dependency_is_reported():
    err = validate_task_graph([_task("T7", ["T3", "T4", "T5", "T6"])])
    assert err is not None
    assert "T7" in err and "T3" in err


def test_true_cycle_is_reported():
    err = validate_task_graph([_task("A", ["B"]), _task("B", ["C"]), _task("C", ["A"])])
    assert err is not None
    assert "A" in err and "B" in err and "C" in err


def test_self_dependency_is_a_cycle():
    err = validate_task_graph([_task("A", ["A"])])
    assert err is not None


def test_cycle_and_dangling_reference_reasons_unchanged():
    assert (
        validate_task_graph([_task("A", ["B"]), _task("B", ["A"])])
        == "dependency cycle: A -> B -> A"
    )
    assert (
        validate_task_graph([_task("A", ["Z"])]) == "task 'A' depends on unknown task id(s) ['Z']"
    )


def test_deps_resolve_passes_when_all_deps_known():
    assert deps_resolve([_task("T1"), _task("T2", ["T1"])]) is None


def test_deps_resolve_names_unknown_ids():
    assert deps_resolve([_task("A", ["Z"])]) == "task 'A' depends on unknown task id(s) ['Z']"


def test_dag_acyclic_passes_on_a_dag():
    assert dag_acyclic([_task("T1"), _task("T2", ["T1"])]) is None


def test_dag_acyclic_names_the_cycle():
    assert dag_acyclic([_task("A", ["B"]), _task("B", ["A"])]) == "dependency cycle: A -> B -> A"


def test_ids_unique_passes():
    assert ids_unique([_task("T1"), _task("T2")]) is None


def test_ids_unique_names_duplicates_sorted():
    tasks = [_task("T2"), _task("T1"), _task("T2"), _task("T1")]
    assert ids_unique(tasks) == "duplicate task id(s): ['T1', 'T2']"


def test_covers_all_passes_when_every_fr_covered():
    frs = ["FR-1", "FR-2"]
    tasks = [_task("T1", covers=["FR-1"]), _task("T2", covers=["FR-2", "FR-3"])]
    assert covers_all(tasks, frs) == []


def test_covers_all_names_uncovered_sorted_and_ignores_unknown_covers():
    tasks = [_task("T1", covers=["FR-1", "US-9"])]
    assert covers_all(tasks, ["FR-1", "FR-2", "FR-3"]) == ["FR-2", "FR-3"]


def test_task_size_passes_at_limits():
    limits = PlanConfig()
    assert task_size([_task("T1", files_hint=["f"] * 24, criteria=["c"] * 12)], limits) is None


def test_task_size_names_first_breach():
    big = _task("T3", files_hint=["f"] * 25, criteria=["c"] * 13)
    assert task_size([big], PlanConfig()) == "task 'T3' exceeds plan limits: files_hint=25>24"


def test_devtask_covers_defaults_empty_and_old_json_deserializes():
    assert DevTask(id="T1", title="t", description="d", acceptance_criteria=["a"]).covers == []
    legacy = json.loads(
        DevTask(id="T1", title="t", description="d", acceptance_criteria=["a"]).model_dump_json()
    )
    assert "covers" in legacy and legacy["covers"] == []


def test_planconfig_defaults_pinned():
    # The false-kill guard IS the generous default — pin the wire values.
    assert PlanConfig() == PlanConfig(max_files_hint=24, max_criteria=12)


def test_pure_module_has_no_temporalio_or_io():
    """Layering: validators/pure.py must stay pure without top-level temporalio import."""
    cmd = [
        sys.executable,
        "-c",
        "import sys, sdlc.validators.pure; "
        "assert 'temporalio' not in sys.modules, 'temporalio leaked'",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"stdout: {res.stdout}, stderr: {res.stderr}"
