# tests/test_board_activities.py
"""Board activities: Temporal markers, worker registration, behaviour."""

import inspect

import pytest

from sdlc.board.activities import (
    AttachEvidenceInput,
    PublishArtifactInput,
    SetTaskStatusInput,
    SyncPlanTasksInput,
    attach_task_evidence,
    publish_artifact_version,
    set_task_authoritative,
    sync_plan_tasks,
)
from sdlc.board.models import TaskStatus
from sdlc.stages.plan.models import DevTask

ACTIVITIES = [
    publish_artifact_version,
    sync_plan_tasks,
    set_task_authoritative,
    attach_task_evidence,
]


@pytest.mark.parametrize("fn", ACTIVITIES, ids=lambda f: f.__name__)
def test_is_a_temporal_activity(fn):
    assert getattr(fn, "__temporal_activity_definition", None) is not None


@pytest.mark.parametrize("name", [f.__name__ for f in ACTIVITIES])
def test_registered_on_the_worker(name):
    from sdlc import worker

    assert name in inspect.getsource(worker), f"{name} missing from worker registration"


@pytest.fixture
def board_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "b.sqlite3"))
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "runs"))


@pytest.mark.asyncio
async def test_publish_then_sync_then_transition(board_env):
    pub = await publish_artifact_version(
        PublishArtifactInput(
            project="proj",
            key="plan",
            run_id="run-1",
            content_json='{"tasks":[]}',
            actor="workflow:run-1",
        )
    )
    assert pub.version_id > 0
    assert pub.ref.sha256

    n = await sync_plan_tasks(
        SyncPlanTasksInput(
            project="proj",
            plan_version=pub.version_id,
            run_id="run-1",
            tasks=[DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"])],
            actor="workflow:run-1",
        )
    )
    assert n == 1

    await set_task_authoritative(
        SetTaskStatusInput(
            project="proj",
            plan_version=pub.version_id,
            task_id="T01",
            status=TaskStatus.IN_PROGRESS,
            actor="workflow:run-1",
        )
    )

    ref = await attach_task_evidence(
        AttachEvidenceInput(
            project="proj",
            plan_version=pub.version_id,
            task_id="T01",
            run_id="run-1",
            kind="qa",
            content_json='{"passed":true}',
        )
    )
    assert ref.kind == "board_evidence"


@pytest.mark.asyncio
async def test_activities_are_idempotent_under_retry(board_env):
    """Temporal retries activities; a second execution must not duplicate."""
    pub = await publish_artifact_version(
        PublishArtifactInput(
            project="proj", key="plan", run_id="run-1", content_json="{}", actor="workflow:run-1"
        )
    )
    inp = SyncPlanTasksInput(
        project="proj",
        plan_version=pub.version_id,
        run_id="run-1",
        tasks=[DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"])],
        actor="workflow:run-1",
    )
    assert await sync_plan_tasks(inp) == 1
    assert await sync_plan_tasks(inp) == 0
