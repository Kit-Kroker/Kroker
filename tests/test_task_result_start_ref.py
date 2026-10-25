"""Tests for TaskResult.start_ref and task_host stamping (017 T008, US1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.stages.plan.models import DevTask
from sdlc.vcs import WorktreeHandle
from sdlc.workflows.models import TaskResult
from sdlc.workflows.task_host import TaskHost


class _DummyHost(TaskHost):
    def __init__(self) -> None:
        super().__init__()
        self._ctx = MagicMock()


def test_pre_017_task_result_json_validates_with_start_ref_none():
    """PIN: pre-017 TaskResult JSON without start_ref field validates and defaults to None."""
    raw = (
        '{"task_id": "task-1", "status": "done", "attempts": 1, "branch": "feature/t1", '
        '"notes": "completed"}'
    )
    tr = TaskResult.model_validate_json(raw)
    assert tr.start_ref is None
    assert tr.task_id == "task-1"
    assert tr.status == "done"


@pytest.mark.asyncio
async def test_task_host_dev_task_stamps_start_ref_from_handle():
    """Unit test: _dev_task stamps start_ref using handle.branch_point."""
    host = _DummyHost()
    cfg = PipelineConfig()
    task = DevTask(
        id="t-1",
        title="Implement feature",
        description="Write code",
        acceptance_criteria=["AC1"],
    )

    handle = WorktreeHandle(
        path="/tmp/worktree",
        branch="sdlc/t-1",
        branch_point="sha-branch-point",
    )

    code_res = TaskResult(
        task_id="t-1",
        status="done",
        attempts=1,
        branch="sdlc/t-1",
    )

    with (
        patch("temporalio.workflow.info") as mock_info,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
        patch("sdlc.workflows.task_host.code_step", new_callable=AsyncMock) as mock_code_step,
    ):
        mock_info.return_value.workflow_id = "wf-123"
        mock_act.return_value = handle
        mock_code_step.return_value = code_res

        tr = await host._dev_task(
            task=task,
            repo_path="/repo",
            from_ref="from-ref-sha",
            cfg=cfg,
            prior_handoffs=[],
        )

    assert tr.start_ref == "sha-branch-point"


@pytest.mark.asyncio
async def test_task_host_dev_task_falls_back_to_from_ref_when_branch_point_empty():
    """Unit test: _dev_task falls back to from_ref if handle.branch_point is empty/None."""
    host = _DummyHost()
    cfg = PipelineConfig()
    task = DevTask(
        id="t-1",
        title="Implement feature",
        description="Write code",
        acceptance_criteria=["AC1"],
    )

    handle = WorktreeHandle(
        path="/tmp/worktree",
        branch="sdlc/t-1",
        branch_point="",  # empty
    )

    code_res = TaskResult(
        task_id="t-1",
        status="done",
        attempts=1,
        branch="sdlc/t-1",
    )

    with (
        patch("temporalio.workflow.info") as mock_info,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
        patch("sdlc.workflows.task_host.code_step", new_callable=AsyncMock) as mock_code_step,
    ):
        mock_info.return_value.workflow_id = "wf-123"
        mock_act.return_value = handle
        mock_code_step.return_value = code_res

        tr = await host._dev_task(
            task=task,
            repo_path="/repo",
            from_ref="from-ref-sha",
            cfg=cfg,
            prior_handoffs=[],
        )

    assert tr.start_ref == "from-ref-sha"
