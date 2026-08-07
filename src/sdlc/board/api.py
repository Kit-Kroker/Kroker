# src/sdlc/board/api.py
"""HTTP surface over BoardStore.

Lives under src/ (not interfaces/) because pyproject's packages.find is
rooted at src — anything outside it is not importable by tests.
interfaces/dashboard/api/main.py is the uvicorn entrypoint.

Reads are unrestricted; writes are the two narrow agent routes in Task 8.
Content reads are byte-capped the way load_session is (artifacts/read.py:18)
so one large artifact cannot blow a consumer's context.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from ..artifacts.store import ref_to_path
from .models import (ArtifactVersion, BoardArtifact, BoardEvent, BoardStats,
                     BoardTask, TaskEvidence, TaskStatus)
from .store import BoardStore, NotFoundError

MAX_CONTENT_BYTES = 512 * 1024


class ProjectDetail(BaseModel):
    key: str
    repo: str
    artifacts: list[BoardArtifact]
    stats: BoardStats


class ProjectSummary(BaseModel):
    key: str
    repo: str


class VersionContent(BaseModel):
    id: int
    n: int
    run_id: str
    sha256: str
    uri: str
    content: str
    truncated: bool


class TaskDetail(BaseModel):
    task: BoardTask
    evidence: list[TaskEvidence]


def create_app(store_factory: Callable[[], BoardStore] | None = None
               ) -> FastAPI:
    factory = store_factory or BoardStore
    app = FastAPI(title="SDLC Agent Board", version="1.0")

    def get_store() -> BoardStore:
        store = factory()
        try:
            yield store
        finally:
            store.close()

    def _current_plan_version(store: BoardStore, project: str) -> int:
        try:
            art = store.get_artifact(project, "plan")
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        if art.current_version is None:
            raise HTTPException(404, f"project {project!r} has no current plan")
        return art.current_version

    def _require_project(store: BoardStore, project: str) -> dict:
        row = store._conn.execute(
            "SELECT key, repo FROM project WHERE key=?",
            (project,)).fetchone()
        if row is None:
            raise HTTPException(404, f"no project {project!r}")
        return {"key": row["key"], "repo": row["repo"]}

    app.state.require_project = _require_project
    app.state.current_plan_version = _current_plan_version
    app.state.get_store = get_store

    @app.get("/projects", response_model=list[ProjectSummary])
    def list_projects(store: BoardStore = Depends(get_store)):
        rows = store._conn.execute(
            "SELECT key, repo FROM project ORDER BY key").fetchall()
        return [ProjectSummary(key=r["key"], repo=r["repo"]) for r in rows]

    @app.get("/projects/{project}", response_model=ProjectDetail)
    def get_project(project: str, store: BoardStore = Depends(get_store)):
        meta = _require_project(store, project)
        rows = store._conn.execute(
            "SELECT project,key,current_version,status FROM artifact "
            "WHERE project=? ORDER BY key", (project,)).fetchall()
        return ProjectDetail(
            key=meta["key"], repo=meta["repo"],
            artifacts=[BoardArtifact(**dict(r)) for r in rows],
            stats=store.stats(project))

    @app.get("/projects/{project}/artifacts/{key}",
             response_model=list[ArtifactVersion])
    def list_versions(project: str, key: str,
                      store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        try:
            store.get_artifact(project, key)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return store.list_versions(project, key)

    @app.get("/projects/{project}/artifacts/{key}/versions/{version_id}",
             response_model=VersionContent)
    def get_version(project: str, key: str, version_id: int,
                    store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        try:
            v = store.get_version(project, version_id)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        if v.key != key:
            raise HTTPException(
                404, f"version {version_id} belongs to {v.key!r}, not {key!r}")
        path = ref_to_path(v)
        if not path.exists():
            # Metadata outlives the blob: the version row and its sha256 are
            # still authoritative history even when runs/ has been pruned.
            raise HTTPException(
                410, {"message": "blob pruned from the claim-check store",
                      "sha256": v.sha256, "uri": v.uri})
        data = path.read_bytes()
        truncated = len(data) > MAX_CONTENT_BYTES
        return VersionContent(
            id=v.id, n=v.n, run_id=v.run_id, sha256=v.sha256, uri=v.uri,
            content=data[:MAX_CONTENT_BYTES].decode("utf-8",
                                                    errors="replace"),
            truncated=truncated)

    @app.get("/projects/{project}/tasks", response_model=list[BoardTask])
    def list_tasks(project: str, status: TaskStatus | None = None,
                   run_id: str | None = None, plan: int | None = None,
                   store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        pv = plan if plan is not None else _current_plan_version(store,
                                                                 project)
        return store.list_tasks(project, pv, status=status, run_id=run_id)

    @app.get("/projects/{project}/tasks/{task_id}",
             response_model=TaskDetail)
    def get_task(project: str, task_id: str, plan: int | None = None,
                 store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        pv = plan if plan is not None else _current_plan_version(store,
                                                                 project)
        try:
            task = store.get_task(project, pv, task_id)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return TaskDetail(task=task,
                          evidence=store.list_evidence(project, pv, task_id))

    @app.get("/projects/{project}/events", response_model=list[BoardEvent])
    def list_events(project: str, since: int = 0, subject: str | None = None,
                    store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        return store.list_events(project, since=since, subject=subject)

    @app.get("/projects/{project}/stats", response_model=BoardStats)
    def get_stats(project: str, store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        return store.stats(project)

    return app


app = create_app()
