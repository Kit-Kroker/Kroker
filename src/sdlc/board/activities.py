# src/sdlc/board/activities.py
"""Temporal activity wrappers over BoardStore (RecordStore idiom,
benchmarks/recorder.py:83). All filesystem and env reads happen here — never
in workflow code.

These are NOT best-effort. capture_session (artifacts/capture.py:29) swallows
storage failures because losing a transcript must not block delivery; the
board is different — agents read tasks from it, so a permanently failed write
must surface. Temporal's RetryPolicy absorbs transient failures; the store's
writes are idempotent so a retry is safe.
"""
from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity

from ..models import ArtifactRef, DevTask
from .models import ArtifactStatus, TaskStatus
from .store import BoardStore


class PublishArtifactInput(BaseModel):
    project: str
    key: str                       # requirements | architecture | plan
    run_id: str
    content_json: str
    actor: str
    status: ArtifactStatus = ArtifactStatus.CURRENT
    repo: str = ""


class PublishArtifactResult(BaseModel):
    ref: ArtifactRef
    version_id: int


class SyncPlanTasksInput(BaseModel):
    project: str
    plan_version: int
    run_id: str
    tasks: list[DevTask]
    actor: str


class SetTaskStatusInput(BaseModel):
    project: str
    plan_version: int
    task_id: str
    status: TaskStatus
    actor: str
    fix_attempts: int | None = None
    error: str | None = None
    branch: str | None = None


class AttachEvidenceInput(BaseModel):
    project: str
    plan_version: int
    task_id: str
    run_id: str
    kind: str                      # qa | review | deep_review
    content_json: str


@activity.defn
async def publish_artifact_version(
        inp: PublishArtifactInput) -> PublishArtifactResult:
    store = BoardStore()
    try:
        store.ensure_project(inp.project, inp.repo)
        ref, version_id = store.publish_artifact_version(
            inp.project, inp.key, inp.run_id,
            inp.content_json.encode("utf-8"),
            status=inp.status, actor=inp.actor)
        return PublishArtifactResult(ref=ref, version_id=version_id)
    finally:
        store.close()


@activity.defn
async def sync_plan_tasks(inp: SyncPlanTasksInput) -> int:
    store = BoardStore()
    try:
        return store.sync_plan_tasks(inp.project, inp.plan_version,
                                     inp.run_id, inp.tasks, actor=inp.actor)
    finally:
        store.close()


@activity.defn
async def set_task_authoritative(inp: SetTaskStatusInput) -> None:
    store = BoardStore()
    try:
        store.set_task_authoritative(
            inp.project, inp.plan_version, inp.task_id, inp.status,
            actor=inp.actor, fix_attempts=inp.fix_attempts,
            error=inp.error, branch=inp.branch)
    finally:
        store.close()


@activity.defn
async def attach_task_evidence(inp: AttachEvidenceInput) -> ArtifactRef:
    store = BoardStore()
    try:
        return store.attach_task_evidence(
            inp.project, inp.plan_version, inp.task_id, inp.run_id,
            inp.kind, inp.content_json.encode("utf-8"))
    finally:
        store.close()
