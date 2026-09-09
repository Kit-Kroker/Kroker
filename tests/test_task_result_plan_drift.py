"""E4: TaskResult carries the plan-drift signal through to the merge gate."""

from sdlc.stages.plan.models import PlanDrift
from sdlc.workflows.models import TaskResult


def test_task_result_defaults_plan_drift_to_none():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.plan_drift is None


def test_task_result_accepts_a_plan_drift():
    drift = PlanDrift(
        files_hinted=2,
        files_touched=2,
        hinted_untouched=["b.py"],
        touched_unhinted=["c.py"],
    )
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b", plan_drift=drift)
    assert tr.plan_drift is drift
    assert tr.plan_drift.touched_unhinted == ["c.py"]
