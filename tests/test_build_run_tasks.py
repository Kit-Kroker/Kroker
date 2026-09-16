"""E-74 §4.3: the task scheduler moved verbatim into build.run_tasks."""

from __future__ import annotations

import asyncio

from sdlc.core.models import ExecutionMode, PipelineConfig
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.workflows.build import run_tasks
from sdlc.workflows.models import TaskResult


def _task(tid: str, deps: list[str] | None = None, overlaps: list[str] | None = None) -> DevTask:
    return DevTask(
        id=tid,
        title=tid,
        description=tid,
        acceptance_criteria=["ok"],
        depends_on=deps or [],
        overlaps=overlaps or [],
    )


class FakeHost:
    def __init__(self, statuses: dict[str, str] | None = None, conflict_on: str | None = None):
        self._integration_head = "h0"
        self.statuses = statuses or {}
        self.conflict_on = conflict_on
        self.calls: list[tuple[str, ...]] = []

    async def _board_task_status(self, cfg, tid, status, **kw):
        self.calls.append(("status", tid, status.value))

    async def _dev_task(self, task, repo_path, from_ref, cfg, handoffs):
        self.calls.append(("dev", task.id, from_ref))
        return TaskResult(
            task_id=task.id,
            status=self.statuses.get(task.id, "done"),
            attempts=1,
            branch=f"b/{task.id}",
        )

    async def _board_evidence(self, cfg, tid, kind, report_json):
        self.calls.append(("evidence", tid, kind))

    async def _merge_task(self, tr, repo_path):
        self.calls.append(("merge", tr.task_id))
        if tr.task_id == self.conflict_on:
            return f"failed:integration-conflict:{tr.task_id}"
        self._integration_head = f"h-{tr.task_id}"
        return None

    async def _check_budget(self, cfg):
        self.calls.append(("budget",))


def _run(host: FakeHost, tasks: list[DevTask], mode: ExecutionMode = ExecutionMode.SERIAL):
    cfg = PipelineConfig(execution_mode=mode)
    return asyncio.run(
        run_tasks(host, cfg=cfg, plan=ImplementationPlan(tasks=tasks), repo_path="/r")
    )


def test_serial_success_branches_each_task_from_the_advanced_head():
    host = FakeHost()
    done, failure = _run(host, [_task("t1"), _task("t2", ["t1"])])
    assert failure is None
    assert list(done) == ["t1", "t2"]
    assert ("dev", "t2", "h-t1") in host.calls
    assert host.calls.count(("budget",)) == 2


def test_dependency_cycle_is_returned_not_raised():
    done, failure = _run(FakeHost(), [_task("a", ["b"]), _task("b", ["a"])])
    assert (done, failure) == ({}, "failed:dependency-cycle")


def test_integration_conflict_stops_the_loop():
    done, failure = _run(FakeHost(conflict_on="t1"), [_task("t1"), _task("t2")])
    assert failure == "failed:integration-conflict:t1"
    assert list(done) == ["t1"]


def test_quarantined_task_fails_the_run_after_its_wave():
    done, failure = _run(FakeHost(statuses={"t1": "quarantined"}), [_task("t1"), _task("t2")])
    assert failure == "failed:quarantined-tasks"
    assert list(done) == ["t1"]


def test_waves_serialize_tasks_that_share_an_overlap():
    host = FakeHost()
    done, failure = _run(
        host,
        [_task("t1", overlaps=["m"]), _task("t2", overlaps=["m"]), _task("t3")],
        ExecutionMode.WAVES,
    )
    assert failure is None
    devs = [c[1] for c in host.calls if c[0] == "dev"]
    assert devs == ["t1", "t3", "t2"]
